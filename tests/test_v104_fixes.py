from __future__ import annotations

import json
from pathlib import Path

import pytest

from cal.adapters.crm_source import map_crm_record
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
