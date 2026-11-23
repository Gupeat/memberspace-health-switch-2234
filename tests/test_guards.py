from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

from cal.adapters.crm_source import map_crm_record

ROOT = Path(__file__).resolve().parents[1]


def test_pre_report_is_written_separately(cli, pre_out):
    report = pre_out / "pre-report.md"
    assert report.is_file()
    text = report.read_text(encoding="utf-8")
    assert "模式：pre" in text
    assert "预计状态变化：120" in text
    assert not (pre_out / "report.md").exists()


def test_threshold_below_099_is_rejected(cli, pre_out, tmp_path):
    out = tmp_path / "post"
    result = cli(
        "verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "post",
        "--actual", str(ROOT / "fixtures" / "actual.csv"),
        "--estimate", str(pre_out / "estimate.csv"), "--out", str(out),
        "--threshold", "0.5",
    )
    assert result.returncode == 1
    assert "threshold" in result.stderr
    assert not (out / "compare.json").exists()


def test_same_from_and_to_is_rejected(cli, tmp_path):
    out = tmp_path / "pre"
    result = cli("verify-health-switch", "--from", "v3", "--to", "v3", "--mode", "pre", "--out", str(out))
    assert result.returncode == 1
    assert "--from and --to must differ" in result.stderr
    assert not (out / "estimate.csv").exists()


def test_unexpected_pid_fails(cli, pre_out, tmp_path):
    actual = tmp_path / "actual_extra.csv"
    shutil.copyfile(ROOT / "fixtures" / "actual.csv", actual)
    with actual.open("a", encoding="utf-8", newline="") as handle:
        handle.write("c-0999,active,70.00,,,\n")
    out = tmp_path / "post"
    result = cli(
        "verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "post",
        "--actual", str(actual), "--estimate", str(pre_out / "estimate.csv"), "--out", str(out),
    )
    assert result.returncode == 2
    payload = json.loads((out / "compare.json").read_text(encoding="utf-8"))
    assert payload["passed"] is False
    assert any(item.get("problem") == "unexpected_pid" and item.get("company_pid") == "c-0999" for item in payload["snapshot_errors"])
    assert payload["entity_errors"] == []


def test_missing_pid_is_snapshot_error(cli, pre_out, tmp_path):
    with (ROOT / "fixtures" / "actual.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))[1:]
    actual = tmp_path / "actual_missing.csv"
    with actual.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["company_pid", "state", "score", "reason", "weight_from", "weight_to"],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    out = tmp_path / "post"
    result = cli(
        "verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "post",
        "--actual", str(actual), "--estimate", str(pre_out / "estimate.csv"), "--out", str(out),
    )
    assert result.returncode == 2
    payload = json.loads((out / "compare.json").read_text(encoding="utf-8"))
    assert payload["passed"] is False
    assert any(item.get("problem") == "missing_from_actual" and item.get("company_pid") == "c-0001" for item in payload["snapshot_errors"])
    assert payload["entity_errors"] == []
    report = (out / "report.md").read_text(encoding="utf-8")
    assert "| 快照完整性 | FAIL |" in report


def test_pivot_counts_sum_to_changes(pre_out):
    with (pre_out / "pivot.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert list(rows[0]) == ["club_id", "manager_id", "direction", "count"]
    assert sum(int(row["count"]) for row in rows) == 120


def test_crm_adapter_maps_signals():
    mapped = map_crm_record(
        {
            "company_pid": "c-0001",
            "company_name": "示例企业",
            "state": "active",
            "club_id": "club-1",
            "manager_id": "m-1",
            "key_member": 1,
            "activity_score": 80,
            "transaction_score": 70,
            "engagement_score": 60,
            "tenure_score": 50,
        }
    )
    assert mapped["company_pid"] == "c-0001"
    assert mapped["key_member"] is True
    assert mapped["signals"] == {"activity": 80.0, "transaction": 70.0, "engagement": 60.0, "tenure": 50.0}
