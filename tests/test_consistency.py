from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read_actual() -> list[dict[str, str]]:
    with (ROOT / "fixtures" / "actual.csv").open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_actual(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["company_pid", "state", "score"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _switching_pid(rows: list[dict[str, str]]) -> str:
    # First fixture block is active -> silent; its pre-switch state is active.
    return rows[0]["company_pid"]


def test_positive_120_of_120(cli, pre_out, tmp_path):
    out = tmp_path / "post"
    result = cli(
        "verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "post",
        "--actual", str(ROOT / "fixtures" / "actual.csv"),
        "--estimate", str(pre_out / "estimate.csv"), "--out", str(out),
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads((out / "compare.json").read_text(encoding="utf-8"))
    assert payload["ratio"] == 1.0
    assert payload["matched_rows"] == 120
    assert payload["total_rows"] == 120
    assert payload["passed"] is True


def test_one_wrong_still_passes(cli, pre_out, tmp_path):
    rows = _read_actual()
    pid = _switching_pid(rows)
    for row in rows:
        if row["company_pid"] == pid:
            row["state"] = "active"  # old state: no actual change
            row["score"] = "78.0"
            break
    actual = tmp_path / "actual_one_wrong.csv"
    _write_actual(actual, rows)
    out = tmp_path / "post"
    result = cli(
        "verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "post",
        "--actual", str(actual), "--estimate", str(pre_out / "estimate.csv"), "--out", str(out),
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads((out / "compare.json").read_text(encoding="utf-8"))
    assert payload["matched_rows"] == 119
    assert payload["total_rows"] == 120
    assert payload["ratio"] == 0.991667
    assert payload["passed"] is True
    report = (out / "report.md").read_text(encoding="utf-8")
    assert "结论：PASS" in report
    assert "| 集合漂移（set_drift） | WARN |" in report


def test_two_wrong_fails(cli, pre_out, tmp_path):
    out = tmp_path / "post"
    result = cli(
        "verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "post",
        "--actual", str(ROOT / "fixtures" / "negative_actual.csv"),
        "--estimate", str(pre_out / "estimate.csv"), "--out", str(out),
    )
    assert result.returncode == 2, result.stderr
    payload = json.loads((out / "compare.json").read_text(encoding="utf-8"))
    assert payload["matched_rows"] == 118
    assert payload["total_rows"] == 120
    assert payload["ratio"] == 0.983333
    assert payload["passed"] is False
    assert len(payload["missing_in_actual"]) == 2
