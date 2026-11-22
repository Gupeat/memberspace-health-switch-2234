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

def test_scan_multiple_directories_and_detects_negative(tmp_path):
    first = tmp_path / "report"
    second = tmp_path / "negative"
    first.mkdir()
    second.mkdir()
    (first / "report.md").write_text("post 报告\n", encoding="utf-8")
    (second / "report.md").write_text("negative 报告\n", encoding="utf-8")
    log = tmp_path / "scan.log"
    command = [
        sys.executable, str(ROOT / "scripts" / "scan_report.py"),
        "--dir", str(first), "--dir", str(second),
        "--blacklist", str(ROOT / "fixtures" / "company_names.txt"),
        "--log", str(log),
    ]
    scan = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    assert scan.returncode == 0, scan.stdout + scan.stderr
    assert "scanned_files=2" in log.read_text(encoding="utf-8")

    names = (ROOT / "fixtures" / "company_names.txt").read_text(encoding="utf-8").splitlines()
    with (second / "report.md").open("a", encoding="utf-8") as handle:
        handle.write(f"{names[0]}有限公司\n")
    scan = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    assert scan.returncode == 1
    text = log.read_text(encoding="utf-8")
    assert "negative/report.md" in text
    assert "blacklist" in text


def test_scan_empty_directory_fails(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    log = tmp_path / "scan.log"
    scan = subprocess.run(
        [
            sys.executable, str(ROOT / "scripts" / "scan_report.py"),
            "--dir", str(empty),
            "--blacklist", str(ROOT / "fixtures" / "company_names.txt"),
            "--log", str(log),
        ],
        cwd=ROOT, text=True, capture_output=True,
    )
    assert scan.returncode == 1
    assert "scanned_files=0" in scan.stdout

def test_scan_requires_each_directory_to_have_text(tmp_path):
    first = tmp_path / "report"
    second = tmp_path / "binary-only"
    first.mkdir()
    second.mkdir()
    (first / "report.md").write_text("post 报告\n", encoding="utf-8")
    (second / "image.bin").write_bytes(b"\x00\x01")
    log = tmp_path / "scan.log"
    scan = subprocess.run(
        [
            sys.executable, str(ROOT / "scripts" / "scan_report.py"),
            "--dir", str(first), "--dir", str(second),
            "--blacklist", str(ROOT / "fixtures" / "company_names.txt"),
            "--log", str(log),
        ],
        cwd=ROOT, text=True, capture_output=True,
    )
    assert scan.returncode == 1
    assert "empty_dirs=1" in scan.stdout
    assert "scanned_files=1" in log.read_text(encoding="utf-8")


def test_scan_min_files_rejects_thin_coverage(tmp_path):
    out = tmp_path / "report"
    out.mkdir()
    (out / "report.md").write_text("post 报告\n", encoding="utf-8")
    log = tmp_path / "scan.log"
    scan = subprocess.run(
        [
            sys.executable, str(ROOT / "scripts" / "scan_report.py"),
            "--dir", str(out), "--min-files", "2",
            "--blacklist", str(ROOT / "fixtures" / "company_names.txt"),
            "--log", str(log),
        ],
        cwd=ROOT, text=True, capture_output=True,
    )
    assert scan.returncode == 1
    assert "min_files=2" in scan.stdout
    assert "scanned_files=1" in log.read_text(encoding="utf-8")
