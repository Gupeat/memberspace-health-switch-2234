from __future__ import annotations

import csv
import json
from pathlib import Path

from cal.report import check_log_consistency, read_last_run_log, write_run_log

ROOT = Path(__file__).resolve().parents[1]


def test_post_outputs_actual_csv_and_same_source_run_log(cli, pre_out, tmp_path):
    out = tmp_path / "post"
    result = cli(
        "verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "post",
        "--actual", str(ROOT / "fixtures" / "actual.csv"),
        "--estimate", str(pre_out / "estimate.csv"), "--out", str(out),
    )
    assert result.returncode == 0, result.stderr
    with (out / "actual.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 500
    assert list(rows[0]) == ["company_pid", "state", "score", "reason", "weight_from", "weight_to"]
    assert rows[0]["reason"] == "权重版本切换"
    assert (rows[0]["weight_from"], rows[0]["weight_to"]) == ("v3", "v4")
    payload = json.loads((out / "compare.json").read_text(encoding="utf-8"))
    assert payload["set_drift"] == []
    assert payload["log_errors"] == []
    last = read_last_run_log(out / "run.log")
    assert last is not None
    checks = last["checks"]
    assert checks["ratio"] == payload["ratio"]
    assert checks["matched_rows"] == payload["matched_rows"]
    assert checks["frozen_counts"] == payload["frozen_counts"]
    assert checks["reason_errors"] == len(payload["reason_errors"])
    assert check_log_consistency(out / "run.log", checks) == []


def test_negative_snapshot_lists_set_drift(cli, pre_out, tmp_path):
    out = tmp_path / "post"
    result = cli(
        "verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "post",
        "--actual", str(ROOT / "fixtures" / "negative_actual.csv"),
        "--estimate", str(pre_out / "estimate.csv"), "--out", str(out),
    )
    assert result.returncode == 2, result.stderr
    payload = json.loads((out / "compare.json").read_text(encoding="utf-8"))
    assert len(payload["set_drift"]) == 2
    assert {row["side"] for row in payload["set_drift"]} == {"estimate_only"}
    assert len(payload["missing_in_actual"]) == 2


def test_log_consistency_detects_tampering(tmp_path):
    log = tmp_path / "run.log"
    checks = {"ratio": 1.0, "matched_rows": 120}
    write_run_log(
        log,
        mode="post",
        version_from="v3",
        version_to="v4",
        out=str(tmp_path),
        asof="2026-11-22",
        checks=checks,
    )
    assert check_log_consistency(log, checks) == []
    errors = check_log_consistency(log, {"ratio": 0.98, "matched_rows": 120})
    assert any("ratio" in error for error in errors)
