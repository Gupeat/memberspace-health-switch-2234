#!/usr/bin/env python3
"""Reproduce the acceptance chain in a clean copy and capture the evidence."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IGNORE = shutil.ignore_patterns(
    ".git",
    "__pycache__",
    "*.pyc",
    ".pytest_cache",
    ".venv",
    "venv",
    "out",
    "clean-room",
)
EVIDENCE_FILES = ("ACCEPTANCE.md", "FINAL-SCAN.md", "final-scan.log", "acceptance.json")


def publish_evidence(room: Path, evidence: Path, failed: bool) -> None:
    """Copy this run's evidence, never leaving an older PASS generation behind."""
    evidence.mkdir(parents=True, exist_ok=True)
    marker = evidence / "FAILED"
    if failed:
        for name in EVIDENCE_FILES:
            (evidence / name).unlink(missing_ok=True)
        marker.write_text("clean-room run failed; previous PASS evidence was removed\n", encoding="utf-8", newline="\n")
        return
    marker.unlink(missing_ok=True)
    for name in EVIDENCE_FILES:
        source = room / "artifacts" / name
        if source.is_file():
            shutil.copyfile(source, evidence / name)
        else:
            (evidence / name).unlink(missing_ok=True)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="2234-clean-") as tmp:
        room = Path(tmp) / "repo"
        shutil.copytree(ROOT, room, ignore=IGNORE)

        steps = [
            ([sys.executable, "--version"], "python --version"),
            ([sys.executable, "-m", "pytest", "-q"], "python -m pytest -q"),
            ([sys.executable, "scripts/run_acceptance.py"], "python scripts/run_acceptance.py"),
        ]
        lines = ["# clean-room reproduction", "", f"source: {ROOT.name} (copy without caches/out)", ""]
        failed = False
        for command, label in steps:
            result = subprocess.run(
                command,
                cwd=room,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
            )
            lines.append(f"$ {label}")
            lines.append(f"[exit {result.returncode}]")
            lines.extend((result.stdout + result.stderr).strip().splitlines())
            lines.append("")
            if result.returncode != 0:
                failed = True
                break

        evidence = ROOT / "artifacts" / "clean-room"
        publish_evidence(room, evidence, failed)
        text = "\n".join(lines).replace(str(room), "<repo>")
        (evidence / "clean-room.log").write_text(text, encoding="utf-8", newline="\n")

    print("clean room PASS" if not failed else "clean room FAIL")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
