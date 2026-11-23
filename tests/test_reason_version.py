from __future__ import annotations

import csv
import json
from pathlib import Path

from cal.compare import check_reasons
from cal.models import ChangeRow, REASON

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_FIELDS = ["company_pid", "state", "score", "reason", "weight_from", "weight_to"]


def _post_with_mutation(cli, pre_out, tmp_path, column: str, value: str):
    with (ROOT / "fixtures" / "actual.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["company_pid"] == "c-0001"
    rows[0][column] = value
    actual = tmp_path / "actual_tampered.csv"
    with actual.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SNAPSHOT_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    out = tmp_path / "post"
    result = cli(
        "verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "post",
        "--actual", str(actual), "--estimate", str(pre_out / "estimate.csv"), "--out", str(out),
    )
    return result, json.loads((out / "compare.json").read_text(encoding="utf-8"))


def test_post_rejects_changed_row_with_missing_reason(cli, pre_out, tmp_path):
    result, payload = _post_with_mutation(cli, pre_out, tmp_path, "reason", "")
    assert result.returncode == 2, result.stderr
    assert payload["reason_errors"] == [{"company_pid": "c-0001", "problem": "missing_or_wrong_reason"}]


def test_post_rejects_changed_row_with_wrong_version(cli, pre_out, tmp_path):
    result, payload = _post_with_mutation(cli, pre_out, tmp_path, "weight_from", "v2")
    assert result.returncode == 2, result.stderr
    assert payload["reason_errors"] == [{"company_pid": "c-0001", "problem": "wrong_weight_version"}]


def test_every_changed_row_has_reason_and_version(cli, pre_out, tmp_path):
    out = tmp_path / "post"
    result = cli(
        "verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "post",
        "--actual", str(ROOT / "fixtures" / "actual.csv"),
        "--estimate", str(pre_out / "estimate.csv"), "--out", str(out),
    )
    assert result.returncode == 0, result.stderr
    with (out / "changed.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 120
    assert {row["reason"] for row in rows} == {REASON}
    assert {row["weight_from"] for row in rows} == {"v3"}
    assert {row["weight_to"] for row in rows} == {"v4"}
    payload = json.loads((out / "compare.json").read_text(encoding="utf-8"))
    assert payload["reason_errors"] == []


def test_check_reasons_rejects_bad_and_same_version():
    good = ChangeRow(
        "c-0001", "active", "silent", 78.0, 72.0, "mgr-001", False,
        "active_to_silent", REASON, "v3", "v4",
    )
    assert check_reasons([good], "v3", "v4") == []
    bad = ChangeRow(
        "c-0002", "active", "silent", 78.0, 72.0, "mgr-001", False,
        "active_to_silent", "", "v3", "v4",
    )
    assert check_reasons([bad], "v3", "v4")
    assert check_reasons([good], "v4", "v4")
