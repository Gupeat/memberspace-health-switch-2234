from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_report_scan_passes(cli, pre_out, tmp_path):
    out = tmp_path / "post"
    result = cli(
        "verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "post",
        "--actual", str(ROOT / "fixtures" / "actual.csv"),
        "--estimate", str(pre_out / "estimate.csv"), "--out", str(out),
    )
    assert result.returncode == 0, result.stderr
    scan = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "scan_report.py"), "--dir", str(out)],
        cwd=ROOT, text=True, capture_output=True,
    )
    assert scan.returncode == 0, scan.stdout + scan.stderr
    assert "hits=0" in (out / "scan.log").read_text(encoding="utf-8")
    payload = json.loads((out / "compare.json").read_text(encoding="utf-8"))
    assert payload["passed"] is True


def test_report_scan_detects_name(cli, pre_out, tmp_path):
    out = tmp_path / "post"
    result = cli(
        "verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "post",
        "--actual", str(ROOT / "fixtures" / "actual.csv"),
        "--estimate", str(pre_out / "estimate.csv"), "--out", str(out),
    )
    assert result.returncode == 0, result.stderr
    names = (ROOT / "fixtures" / "company_names.txt").read_text(encoding="utf-8").splitlines()
    with (out / "report.md").open("a", encoding="utf-8") as handle:
        handle.write(f"\n{names[0]}有限公司\n")
    scan = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "scan_report.py"), "--dir", str(out)],
        cwd=ROOT, text=True, capture_output=True,
    )
    assert scan.returncode == 1
    log = (out / "scan.log").read_text(encoding="utf-8")
    assert "hits=0" not in log
    assert "blacklist" in log
