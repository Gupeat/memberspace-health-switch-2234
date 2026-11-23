from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from cal.adapters.crm_source import map_crm_record
from cal.compare import load_warn_task_pids
from cal.config import companies_from_rows
from scripts import run_acceptance
from scripts.run_clean_room import publish_evidence

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"


def _write_config(tmp_path: Path, **changes) -> Path:
    config = json.loads((FIXTURES / "config-pre.json").read_text(encoding="utf-8"))
    config.update(changes)
    path = tmp_path / "config-pre.json"
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _stale(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text("old PASS\n", encoding="utf-8")
    (out / "scan.log").write_text("old scan\n", encoding="utf-8")


def test_config_asof_invalid_fails_and_clears_old_outputs(tmp_path, cli):
    config = _write_config(tmp_path, asof="2026-02-31")
    out = tmp_path / "out"
    _stale(out)
    result = cli("verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "pre",
                 "--config", str(config), "--out", str(out))
    assert result.returncode == 1
    assert "not a valid YYYY-MM-DD" in result.stderr
    assert not (out / "report.md").exists()
    assert not (out / "scan.log").exists()
    assert '"mode": "pre-failed"' in (out / "run.log").read_text(encoding="utf-8")


def test_weight_version_mismatch_clears_old_outputs(tmp_path, cli):
    weights = json.loads((FIXTURES / "weights-v3.json").read_text(encoding="utf-8"))
    weights["version"] = "v9"
    bad_weights = tmp_path / "weights-v9.json"
    bad_weights.write_text(json.dumps(weights), encoding="utf-8")
    out = tmp_path / "out"
    _stale(out)
    result = cli("verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "pre",
                 "--weights-from", str(bad_weights), "--out", str(out))
    assert result.returncode == 1
    assert "does not match" in result.stderr
    assert not (out / "report.md").exists()
    assert '"mode": "pre-failed"' in (out / "run.log").read_text(encoding="utf-8")


def test_nan_weight_is_rejected(tmp_path, cli):
    weights = json.loads((FIXTURES / "weights-v3.json").read_text(encoding="utf-8"))
    weights["weights"]["activity"] = float("nan")
    bad_weights = tmp_path / "weights-nan.json"
    bad_weights.write_text(json.dumps(weights), encoding="utf-8")
    out = tmp_path / "out"
    result = cli("verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "pre",
                 "--weights-from", str(bad_weights), "--out", str(out))
    assert result.returncode == 1
    assert "not finite" in result.stderr
    assert '"mode": "pre-failed"' in (out / "run.log").read_text(encoding="utf-8")


def test_empty_company_snapshot_is_rejected(tmp_path, cli):
    empty = tmp_path / "companies.json"
    empty.write_text('{"companies": []}', encoding="utf-8")
    out = tmp_path / "out"
    _stale(out)
    result = cli("verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "pre",
                 "--crm", str(empty), "--out", str(out))
    assert result.returncode == 1
    assert "company snapshot is empty" in result.stderr
    assert not (out / "report.md").exists()
    assert '"mode": "pre-failed"' in (out / "run.log").read_text(encoding="utf-8")


def test_crm_mapping_rejects_missing_or_null_scores():
    with pytest.raises(ValueError, match="missing activity_score"):
        map_crm_record({"pid": "c-1", "lifecycle_status": "active"})
    with pytest.raises(ValueError, match="must be numeric"):
        map_crm_record({
            "pid": "c-1", "lifecycle_status": "active",
            "activity_score": None, "transaction_score": 1,
            "engagement_score": 1, "tenure_score": 1,
        })


def test_crm_mapping_parses_key_member_strictly():
    base = {
        "pid": "c-1", "lifecycle_status": "active",
        "activity_score": 1, "transaction_score": 1,
        "engagement_score": 1, "tenure_score": 1,
    }
    assert map_crm_record({**base, "key_member": "false"})["key_member"] is False
    assert map_crm_record({**base, "key_member": "yes"})["key_member"] is True
    with pytest.raises(ValueError, match="key_member"):
        map_crm_record({**base, "key_member": "maybe"})


def test_clean_room_failure_never_keeps_old_pass_evidence(tmp_path):
    room = tmp_path / "room"
    evidence = tmp_path / "evidence"
    (room / "artifacts").mkdir(parents=True)
    (room / "artifacts" / "ACCEPTANCE.md").write_text("new PASS\n", encoding="utf-8")
    evidence.mkdir()
    for name in ("ACCEPTANCE.md", "FINAL-SCAN.md", "final-scan.log", "acceptance.json"):
        (evidence / name).write_text("old PASS\n", encoding="utf-8")
    publish_evidence(room, evidence, failed=True)
    for name in ("ACCEPTANCE.md", "FINAL-SCAN.md", "final-scan.log", "acceptance.json"):
        assert not (evidence / name).exists()
    assert (evidence / "FAILED").is_file()

    publish_evidence(room, evidence, failed=False)
    assert (evidence / "ACCEPTANCE.md").read_text(encoding="utf-8") == "new PASS\n"
    assert not (evidence / "FINAL-SCAN.md").exists()
    assert not (evidence / "FAILED").exists()

def test_cli_invalid_asof_clears_old_outputs(tmp_path, cli):
    out = tmp_path / "out"
    _stale(out)
    result = cli("verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "pre",
                 "--asof", "20261123", "--out", str(out))
    assert result.returncode == 1
    assert "--asof must be YYYY-MM-DD" in result.stderr
    assert not (out / "report.md").exists()
    assert '"mode": "pre-failed"' in (out / "run.log").read_text(encoding="utf-8")


def test_null_weight_clears_old_outputs(tmp_path, cli):
    weights = json.loads((FIXTURES / "weights-v3.json").read_text(encoding="utf-8"))
    weights["weights"] = {key: None for key in weights["weights"]}
    bad_weights = tmp_path / "weights-null.json"
    bad_weights.write_text(json.dumps(weights), encoding="utf-8")
    out = tmp_path / "out"
    _stale(out)
    result = cli("verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "pre",
                 "--weights-from", str(bad_weights), "--out", str(out))
    assert result.returncode == 1
    assert "must be numeric" in result.stderr
    assert not (out / "report.md").exists()
    assert '"mode": "pre-failed"' in (out / "run.log").read_text(encoding="utf-8")


def test_post_failure_clears_stale_pass_but_keeps_estimate(cli, pre_out, tmp_path):
    for name in ("actual.csv", "changed.csv", "compare.json", "report.md", "run.log", "scan.log"):
        (pre_out / name).write_text("old PASS\n", encoding="utf-8")
    result = cli(
        "verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "post",
        "--actual", str(tmp_path / "missing-actual.csv"),
        "--estimate", str(pre_out / "estimate.csv"), "--out", str(pre_out),
    )
    assert result.returncode == 1
    assert "missing" in result.stderr.lower() or "not found" in result.stderr.lower()
    for name in ("actual.csv", "changed.csv", "compare.json", "report.md", "scan.log"):
        assert not (pre_out / name).exists(), name
    assert (pre_out / "estimate.csv").is_file()
    assert '"mode": "post-failed"' in (pre_out / "run.log").read_text(encoding="utf-8")


def test_internal_key_member_string_false_stays_false():
    row = {
        "company_pid": "c-0001", "state": "active",
        "signals": {"activity": 1, "transaction": 1, "engagement": 1, "tenure": 1},
        "key_member": "false",
    }
    assert companies_from_rows([row])[0].key_member is False
    assert companies_from_rows([{**row, "key_member": "否"}])[0].key_member is False


def test_acceptance_early_failure_invalidates_old_pass(tmp_path, monkeypatch):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(parents=True)
    for name in run_acceptance.EVIDENCE_FILES:
        (artifacts / name).write_text("old PASS\n", encoding="utf-8")

    def fake_run(args):
        return {"command": "python " + " ".join(args), "exit": 1, "stdout": "", "stderr": "boom"}

    monkeypatch.setattr(run_acceptance, "ROOT", tmp_path)
    monkeypatch.setattr(run_acceptance, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["run_acceptance.py", "--artifacts", "artifacts"])

    assert run_acceptance.main() == 1
    payload = json.loads((artifacts / "acceptance.json").read_text(encoding="utf-8"))
    assert payload["all_passed"] is False
    assert "总体：FAIL" in (artifacts / "ACCEPTANCE.md").read_text(encoding="utf-8")
    assert (artifacts / "FAILED").is_file()
    assert not (artifacts / "FINAL-SCAN.md").exists()

def test_null_warn_task_row_is_rejected(tmp_path):
    path = tmp_path / "warn_tasks.json"
    path.write_text('{"tasks": [null]}', encoding="utf-8")
    with pytest.raises(ValueError, match="row 0 must be an object"):
        load_warn_task_pids(path)
