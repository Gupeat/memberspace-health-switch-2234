from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _changed_pids(pre_out: Path) -> list[str]:
    with (pre_out / "estimate.csv").open(encoding="utf-8", newline="") as handle:
        return [row["company_pid"] for row in csv.DictReader(handle)]


def _snapshot_with_changed_scores(tmp_path: Path, pids: set[str]) -> Path:
    source = ROOT / "fixtures" / "actual.csv"
    target = tmp_path / "actual-with-score-drift.csv"
    with source.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = reader.fieldnames
    for row in rows:
        if row["company_pid"] in pids:
            row["score"] = "999.0"
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return target


def test_score_drift_counts_as_mismatch_and_can_fail(cli, pre_out, tmp_path):
    pids = set(_changed_pids(pre_out)[:3])
    actual = _snapshot_with_changed_scores(tmp_path, pids)
    out = tmp_path / "post"
    result = cli(
        "verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "post",
        "--actual", str(actual), "--estimate", str(pre_out / "estimate.csv"), "--out", str(out),
    )
    assert result.returncode == 2, result.stdout + result.stderr
    payload = json.loads((out / "compare.json").read_text(encoding="utf-8"))
    assert payload["score_drift"]
    assert all(item["kind"] == "score_drift" for item in payload["mismatch"])
    assert payload["matched_rows"] == 117
    assert payload["ratio"] == 117 / 120
    assert payload["passed"] is False


def test_single_score_drift_still_passes_above_threshold(cli, pre_out, tmp_path):
    pids = set(_changed_pids(pre_out)[:1])
    actual = _snapshot_with_changed_scores(tmp_path, pids)
    out = tmp_path / "post"
    result = cli(
        "verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "post",
        "--actual", str(actual), "--estimate", str(pre_out / "estimate.csv"), "--out", str(out),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads((out / "compare.json").read_text(encoding="utf-8"))
    assert payload["matched_rows"] == 119
    assert payload["ratio"] < 1.0
    assert len(payload["score_drift"]) == 1
    assert payload["passed"] is True


def test_post_rejects_config(cli, pre_out, tmp_path):
    out = tmp_path / "post"
    result = cli(
        "verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "post",
        "--actual", str(ROOT / "fixtures" / "actual.csv"),
        "--estimate", str(pre_out / "estimate.csv"),
        "--config", str(ROOT / "fixtures" / "config-post.json"), "--out", str(out),
    )
    assert result.returncode == 1
    assert "--config is only supported in pre mode" in result.stderr
    assert not out.exists()


def test_pre_guard_clears_stale_outputs(cli, pre_out):
    assert (pre_out / "estimate.csv").is_file()
    for name in ("actual.csv", "changed.csv", "compare.json", "report.md"):
        (pre_out / name).write_text("stale\n", encoding="utf-8")
    result = cli(
        "verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "pre",
        "--config", str(ROOT / "fixtures" / "config-post.json"), "--out", str(pre_out),
    )
    assert result.returncode == 3
    for name in (
        "estimate.csv", "frozen_would_change.csv", "pivot.csv", "summary.json", "pre-report.md",
        "actual.csv", "changed.csv", "compare.json", "report.md",
    ):
        assert not (pre_out / name).exists(), name
    lines = [line for line in (pre_out / "run.log").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["mode"] == "pre-guard-failed"
    assert "expected 'v3'" in json.loads(lines[0])["error"]
