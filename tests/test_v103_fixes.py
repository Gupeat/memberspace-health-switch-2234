from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_crm_shaped_snapshot_works_via_adapter(cli, tmp_path):
    crm = tmp_path / "crm-shape.json"
    crm.write_text(json.dumps([
        {
            "pid": "c-9001",
            "name": "适配器样例企业",
            "lifecycle_status": "active",
            "club_id": "club-1",
            "owner_manager_id": "mgr-9",
            "key_member": 1,
            "activity_score": 95,
            "transaction_score": 90,
            "engagement_score": 85,
            "tenure_score": 80,
        }
    ], ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "pre"
    result = cli(
        "verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "pre",
        "--crm", str(crm), "--out", str(out),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["company_count"] == 1
    assert summary["asof"] == "2026-11-22"


def test_post_rejects_estimate_version_mismatch(cli, pre_out, tmp_path):
    relabeled = tmp_path / "estimate-v2-v3.csv"
    with (pre_out / "estimate.csv").open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = reader.fieldnames
    for row in rows:
        row["weight_from"] = "v2"
        row["weight_to"] = "v3"
    with relabeled.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    result = cli(
        "verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "post",
        "--actual", str(ROOT / "fixtures" / "actual.csv"),
        "--estimate", str(relabeled), "--out", str(tmp_path / "post"),
    )
    assert result.returncode == 1
    assert "estimate file version mismatch" in result.stderr


def test_pre_defaults_asof_from_config_and_rejects_invalid(cli, tmp_path):
    out = tmp_path / "pre"
    result = cli("verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "pre", "--out", str(out))
    assert result.returncode == 0, result.stderr
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["asof"] == "2026-11-22"
    bad = cli(
        "verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "pre",
        "--asof", "2026-02-31", "--out", str(tmp_path / "bad"),
    )
    assert bad.returncode == 1
    assert "--asof is not a valid" in bad.stderr


def test_post_rejects_empty_estimate_and_non_finite_score(cli, pre_out, tmp_path):
    empty = tmp_path / "empty.csv"
    header = (pre_out / "estimate.csv").read_text(encoding="utf-8").splitlines()[0]
    empty.write_text(header + "\n", encoding="utf-8")
    result = cli(
        "verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "post",
        "--actual", str(ROOT / "fixtures" / "actual.csv"),
        "--estimate", str(empty), "--out", str(tmp_path / "empty-post"),
    )
    assert result.returncode == 1
    assert "estimate file has no rows" in result.stderr

    bad_actual = tmp_path / "actual-nan.csv"
    with (ROOT / "fixtures" / "actual.csv").open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = reader.fieldnames
    rows[0]["score"] = "nan"
    with bad_actual.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    result = cli(
        "verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "post",
        "--actual", str(bad_actual), "--estimate", str(pre_out / "estimate.csv"),
        "--out", str(tmp_path / "nan-post"),
    )
    assert result.returncode == 1
    assert "score is not finite" in result.stderr

def test_successful_pre_rerun_clears_stale_post_evidence(cli, pre_out):
    for name in ("actual.csv", "changed.csv", "compare.json", "report.md"):
        (pre_out / name).write_text("stale post evidence\n", encoding="utf-8")
    result = cli(
        "verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "pre", "--out", str(pre_out),
    )
    assert result.returncode == 0, result.stderr
    for name in ("actual.csv", "changed.csv", "compare.json", "report.md"):
        assert not (pre_out / name).exists(), name
    lines = [line for line in (pre_out / "run.log").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["mode"] == "pre"
