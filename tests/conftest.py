from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "cal.cli", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


@pytest.fixture
def cli():
    return run_cli


@pytest.fixture
def pre_out(tmp_path: Path) -> Path:
    out = tmp_path / "pre"
    result = run_cli("verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "pre", "--out", str(out))
    assert result.returncode == 0, result.stderr
    assert (out / "estimate.csv").is_file()
    return out
