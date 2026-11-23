"""Post-switch comparison against the pre-switch estimate."""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

from cal.config import load_json, parse_bool
from cal.models import (
    ChangeRow,
    Company,
    FROZEN_STATUSES,
    REASON,
    STATUSES,
    direction_for,
    validate_status,
)
from cal.scoring import score_company


def _csv_rows(reader: csv.DictReader, label: str):
    try:
        yield from reader
    except csv.Error as exc:
        raise ValueError(f"{label} is not valid CSV: {exc}") from exc


def load_actual_snapshot(path: str | Path) -> dict[str, dict[str, Any]]:
    """Load a full-state snapshot plus each changed row's change record.

    Required columns: company_pid,state,score,reason,weight_from,weight_to.
    reason/weight_from/weight_to must be populated on rows whose state changed;
    check_reasons() validates the values read from the input instead of
    synthesizing them from CLI arguments.
    """
    snapshot: dict[str, dict[str, Any]] = {}
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"company_pid", "state", "score", "reason", "weight_from", "weight_to"}
        missing_columns = required - set(reader.fieldnames or [])
        if missing_columns:
            raise ValueError(f"actual snapshot missing columns: {sorted(missing_columns)}")
        for line_number, row in enumerate(_csv_rows(reader, f"actual snapshot {path}"), start=2):
            pid = (row.get("company_pid") or "").strip()
            if not pid:
                raise ValueError(f"actual snapshot line {line_number}: empty company_pid")
            if pid in snapshot:
                raise ValueError(f"actual snapshot duplicate company_pid: {pid}")
            state = (row.get("state") or "").strip()
            if state not in STATUSES:
                raise ValueError(f"actual snapshot {pid}: unsupported state {state!r}")
            try:
                score = float(row.get("score") or "")
            except ValueError as exc:
                raise ValueError(f"actual snapshot {pid}: score is not numeric") from exc
            if not math.isfinite(score):
                raise ValueError(f"actual snapshot {pid}: score is not finite")
            snapshot[pid] = {
                "state": state,
                "score": round(score, 2),
                "reason": (row.get("reason") or "").strip(),
                "weight_from": (row.get("weight_from") or "").strip(),
                "weight_to": (row.get("weight_to") or "").strip(),
            }
    return snapshot


def derive_actual_changes(
    companies: list[Company],
    snapshot: dict[str, dict[str, Any]],
    weights_from: dict[str, float],
) -> tuple[list[ChangeRow], list[dict[str, Any]], list[str], list[str]]:
    """Derive actual changes from a full post-switch state snapshot.

    Returns (changes, entity_errors, frozen_state_errors, missing_actual).
    """
    changes: list[ChangeRow] = []
    entity_errors: list[dict[str, Any]] = []
    frozen_errors: list[str] = []
    missing: list[str] = []
    for company in sorted(companies, key=lambda item: item.company_pid):
        actual = snapshot.get(company.company_pid)
        if actual is None:
            missing.append(company.company_pid)
            if company.state in FROZEN_STATUSES:
                frozen_errors.append(f"{company.company_pid}: frozen company missing from actual snapshot")
            continue
        if company.state in FROZEN_STATUSES:
            if actual["state"] != company.state:
                frozen_errors.append(
                    f"{company.company_pid}: frozen status changed {company.state}->{actual['state']}"
                )
            continue
        if actual["state"] in FROZEN_STATUSES:
            entity_errors.append(
                {
                    "company_pid": company.company_pid,
                    "problem": "frozen_status_appeared",
                    "old_status": company.state,
                    "new_status": actual["state"],
                }
            )
            continue
        validate_status(actual["state"])
        if company.state == actual["state"]:
            continue
        direction = direction_for(company.state, actual["state"])
        if direction is None:
            entity_errors.append(
                {
                    "company_pid": company.company_pid,
                    "problem": "unsupported_transition",
                    "old_status": company.state,
                    "new_status": actual["state"],
                }
            )
            continue
        changes.append(
            ChangeRow(
                company_pid=company.company_pid,
                old_status=company.state,
                new_status=actual["state"],
                old_score=score_company(company, weights_from),
                new_score=actual["score"],
                manager_id=company.manager_id,
                key_member=company.key_member,
                direction=direction,
                reason=actual["reason"],
                weight_from=actual["weight_from"],
                weight_to=actual["weight_to"],
            )
        )
    return changes, entity_errors, frozen_errors, missing


def load_estimate_rows(path: str | Path) -> list[ChangeRow]:
    rows: list[ChangeRow] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"company_pid", "old_status", "new_status", "direction", "old_score", "new_score"}
        missing_columns = required - set(reader.fieldnames or [])
        if missing_columns:
            raise ValueError(f"estimate file missing columns: {sorted(missing_columns)}")
        for row in _csv_rows(reader, f"estimate file {path}"):
            pid = (row.get("company_pid") or "").strip()
            if not pid:
                raise ValueError("estimate file contains empty company_pid")
            old_score_text = (row.get("old_score") or "").strip()
            new_score_text = (row.get("new_score") or "").strip()
            if not old_score_text or not new_score_text:
                raise ValueError(f"estimate file {pid}: score is empty")
            try:
                old_score = float(old_score_text)
                new_score = float(new_score_text)
            except ValueError as exc:
                raise ValueError(f"estimate file {pid}: score is not numeric") from exc
            if not math.isfinite(old_score) or not math.isfinite(new_score):
                raise ValueError(f"estimate file {pid}: score is not finite")
            rows.append(
                ChangeRow(
                    company_pid=pid,
                    old_status=(row.get("old_status") or "").strip(),
                    new_status=(row.get("new_status") or "").strip(),
                    old_score=round(old_score, 2),
                    new_score=round(new_score, 2),
                    manager_id=(row.get("manager_id") or "").strip(),
                    key_member=parse_bool((row.get("key_member") or "").strip(), f"estimate file {pid} key_member"),
                    direction=(row.get("direction") or "").strip(),
                    reason=(row.get("reason") or "").strip(),
                    weight_from=(row.get("weight_from") or "").strip(),
                    weight_to=(row.get("weight_to") or "").strip(),
                )
            )
    return rows


def compare_changes(
    estimate_rows: list[ChangeRow],
    actual_rows: list[ChangeRow],
    threshold: float,
) -> dict[str, Any]:
    estimate_by_pid = {row.company_pid: row for row in estimate_rows}
    actual_by_pid = {row.company_pid: row for row in actual_rows}
    if len(estimate_by_pid) != len(estimate_rows):
        raise ValueError("estimate file contains duplicate company_pid")
    if len(actual_by_pid) != len(actual_rows):
        raise ValueError("actual changes contain duplicate company_pid")
    all_pids = sorted(set(estimate_by_pid) | set(actual_by_pid))
    matched = 0
    missing_in_actual: list[str] = []
    missing_in_estimate: list[str] = []
    set_drift: list[dict[str, str]] = []
    mismatch: list[dict[str, Any]] = []
    score_drift: list[dict[str, Any]] = []
    for pid in all_pids:
        expected = estimate_by_pid.get(pid)
        got = actual_by_pid.get(pid)
        if expected is None:
            missing_in_estimate.append(pid)
            set_drift.append({"company_pid": pid, "side": "actual_only"})
            continue
        if got is None:
            missing_in_actual.append(pid)
            set_drift.append({"company_pid": pid, "side": "estimate_only"})
            continue
        expected_key = (expected.old_status, expected.new_status, expected.direction)
        actual_key = (got.old_status, got.new_status, got.direction)
        score_matches = (
            abs(expected.old_score - got.old_score) <= 0.01
            and abs(expected.new_score - got.new_score) <= 0.01
        )
        if expected_key == actual_key and score_matches:
            matched += 1
        elif expected_key == actual_key:
            score_drift.append(
                {
                    "company_pid": pid,
                    "estimate_old_score": expected.old_score,
                    "actual_old_score": got.old_score,
                    "estimate_new_score": expected.new_score,
                    "actual_new_score": got.new_score,
                }
            )
            mismatch.append(
                {
                    "company_pid": pid,
                    "kind": "score_drift",
                    "estimate": {
                        "old_status": expected.old_status,
                        "new_status": expected.new_status,
                        "old_score": expected.old_score,
                        "new_score": expected.new_score,
                    },
                    "actual": {
                        "old_status": got.old_status,
                        "new_status": got.new_status,
                        "old_score": got.old_score,
                        "new_score": got.new_score,
                    },
                }
            )
        else:
            mismatch.append(
                {
                    "company_pid": pid,
                    "estimate": {
                        "old_status": expected.old_status,
                        "new_status": expected.new_status,
                        "direction": expected.direction,
                    },
                    "actual": {
                        "old_status": got.old_status,
                        "new_status": got.new_status,
                        "direction": got.direction,
                    },
                }
            )
    total = len(all_pids)
    ratio = round(matched / total, 6) if total else 1.0
    return {
        "ratio": ratio,
        "matched_rows": matched,
        "total_rows": total,
        "threshold": threshold,
        "estimate_rows": len(estimate_rows),
        "actual_rows": len(actual_rows),
        "missing_in_actual": missing_in_actual,
        "missing_in_estimate": missing_in_estimate,
        "set_drift": set_drift,
        "mismatch": mismatch,
        "score_drift": score_drift,
    }


def check_reasons(rows: list[ChangeRow], version_from: str, version_to: str) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if version_from == version_to:
        errors.append({"company_pid": "*", "problem": "from_version_equals_to_version"})
        return errors
    for row in rows:
        if row.reason != REASON:
            errors.append({"company_pid": row.company_pid, "problem": "missing_or_wrong_reason"})
        if row.weight_from != version_from or row.weight_to != version_to:
            errors.append({"company_pid": row.company_pid, "problem": "wrong_weight_version"})
    return errors


def load_warn_task_pids(path: str | Path) -> set[str]:
    document = load_json(path)
    rows = document.get("tasks") if isinstance(document, dict) else document
    if not isinstance(rows, list):
        raise ValueError("warn task file must be a list or contain 'tasks'")
    pids: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"warn task row {index} must be an object")
        raw_pid = row.get("company_pid")
        if isinstance(raw_pid, bool) or not isinstance(raw_pid, (str, int)):
            raise ValueError(f"warn task row {index} has invalid company_pid: {raw_pid!r}")
        pid = str(raw_pid).strip()
        if not pid:
            raise ValueError(f"warn task row {index} has empty company_pid")
        pids.add(pid)
    return pids


def check_warn_tasks(actual_rows: list[ChangeRow], warn_pids: set[str]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for row in actual_rows:
        if row.new_status == "churn_warning" and row.old_status != "churn_warning":
            if row.company_pid not in warn_pids:
                errors.append({"company_pid": row.company_pid, "problem": "missing_warn_task"})
    return errors


def frozen_counts(companies: list[Company], snapshot: dict[str, dict[str, Any]]) -> dict[str, Any]:
    baseline = {"renewed": 0, "churned": 0}
    actual = {"renewed": 0, "churned": 0}
    for company in companies:
        if company.state in FROZEN_STATUSES:
            baseline[company.state] += 1
            got = snapshot.get(company.company_pid)
            if got and got["state"] in FROZEN_STATUSES:
                actual[got["state"]] += 1
    return {"baseline": baseline, "actual": actual}