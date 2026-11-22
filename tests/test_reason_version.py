from __future__ import annotations

import csv
import json
from pathlib import Path

from cal.compare import check_reasons
from cal.models import ChangeRow, REASON

ROOT = Path(__file__).resolve().parents[1]


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
