"""Configuration, weight files, and CRM fixture loading."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cal.models import Company, WEIGHT_KEYS

DEFAULT_BANDS = {"active_min": 75.0, "silent_min": 60.0}


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_weights(path: str | Path) -> tuple[str, dict[str, float]]:
    document = load_json(path)
    version = str(document.get("version") or "")
    weights = document.get("weights") or document
    if not version:
        raise ValueError(f"weight file has no version: {path}")
    missing = [key for key in WEIGHT_KEYS if key not in weights]
    if missing:
        raise ValueError(f"weight file {path} missing keys: {missing}")
    cleaned = {key: float(weights[key]) for key in WEIGHT_KEYS}
    total = sum(cleaned.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"weights in {path} sum to {total}, expected 1.0")
    return version, cleaned


def load_config(path: str | Path) -> dict[str, Any]:
    document = load_json(path)
    bands = dict(DEFAULT_BANDS)
    bands.update(document.get("bands") or {})
    active_min = float(bands["active_min"])
    silent_min = float(bands["silent_min"])
    if active_min <= silent_min:
        raise ValueError("active_min must be greater than silent_min")
    return {
        "active_version": str(document.get("active_version") or ""),
        "bands": {"active_min": active_min, "silent_min": silent_min},
        "asof": str(document.get("asof") or ""),
        "raw": document,
    }


def companies_from_rows(rows: list[dict], source: str | Path = "<memory>") -> list[Company]:
    """Validate already-normalized company rows (internal snapshot shape)."""
    companies: list[Company] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        pid = str(row.get("company_pid") or "").strip()
        if not pid:
            raise ValueError(f"company row {index} has no company_pid")
        if pid in seen:
            raise ValueError(f"duplicate company_pid: {pid}")
        seen.add(pid)
        signals = row.get("signals") or {}
        missing = [key for key in WEIGHT_KEYS if key not in signals]
        if missing:
            raise ValueError(f"{pid} missing signals: {missing}")
        state = str(row.get("state") or "").strip()
        if state not in ("active", "silent", "churn_warning", "renewed", "churned"):
            raise ValueError(f"{pid} has unsupported state: {state!r}")
        companies.append(
            Company(
                company_pid=pid,
                company_name=str(row.get("company_name") or pid),
                state=state,
                club_id=str(row.get("club_id") or ""),
                manager_id=str(row.get("manager_id") or ""),
                key_member=bool(row.get("key_member", False)),
                signals={key: float(signals[key]) for key in WEIGHT_KEYS},
            )
        )
    return companies


def load_companies(path: str | Path) -> list[Company]:
    document = load_json(path)
    rows = document.get("companies") if isinstance(document, dict) else document
    if not isinstance(rows, list):
        raise ValueError(f"company file must be a list or contain 'companies': {path}")
    return companies_from_rows(rows, source=path)
