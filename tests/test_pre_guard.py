from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_pre_guard_rejects_wrong_active_version(cli, tmp_path):
    out = tmp_path / "pre"
    result = cli(
        "verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "pre",
        "--config", str(ROOT / "fixtures" / "config-post.json"), "--out", str(out),
    )
    assert result.returncode == 3
    assert not (out / "estimate.csv").exists()


def test_pre_writes_120_changes_and_6_frozen_drifts(cli, pre_out):
    with (pre_out / "estimate.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 120
    assert {row["direction"] for row in rows} == {
        "active_to_silent", "silent_to_active", "enter_churn_warning", "exit_churn_warning"
    }
    assert (pre_out / "frozen_would_change.csv").read_text(encoding="utf-8").count("\n") == 7
