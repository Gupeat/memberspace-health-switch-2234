from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_post_changed_csv_is_byte_stable(cli, pre_out, tmp_path):
    hashes = []
    for name in ("post-a", "post-b"):
        out = tmp_path / name
        result = cli(
            "verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "post",
            "--actual", str(ROOT / "fixtures" / "actual.csv"),
            "--estimate", str(pre_out / "estimate.csv"), "--out", str(out),
        )
        assert result.returncode == 0, result.stderr
        hashes.append(_sha(out / "changed.csv"))
    assert hashes[0] == hashes[1]


def test_pre_estimate_csv_is_byte_stable(cli, tmp_path):
    hashes = []
    for name in ("pre-a", "pre-b"):
        out = tmp_path / name
        result = cli(
            "verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "pre", "--out", str(out),
        )
        assert result.returncode == 0, result.stderr
        hashes.append(_sha(out / "estimate.csv"))
    assert hashes[0] == hashes[1]
