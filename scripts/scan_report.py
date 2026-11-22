#!/usr/bin/env python3
"""Scan report artifacts for enterprise names and report hit counts."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SUFFIX = re.compile(r"(有限公司|集团|工作室|中心)")
TEXT_SUFFIXES = {".md", ".csv", ".json", ".txt", ".log", ".html", ".xml", ".yaml", ".yml"}


def load_blacklist(path: str | Path) -> list[str]:
    names = []
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        name = line.strip()
        if name:
            names.append(name)
    if not names:
        raise ValueError(f"blacklist is empty: {path}")
    return names


def scan(directories: list[str | Path], names: list[str], log_path: str | Path) -> tuple[int, int, list[str]]:
    # Every requested directory must exist and contain at least one text file;
    # an empty directory is a coverage failure, not a silent no-op.
    log_target = Path(log_path)
    hits: list[str] = []
    scanned = 0
    roots = [Path(directory) for directory in directories]
    empty_roots: list[str] = []
    for root in roots:
        if not root.is_dir():
            raise ValueError(f"scan directory not found: {root}")
        root_scanned = 0
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if path.resolve() == log_target.resolve():
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            scanned += 1
            root_scanned += 1
            label = f"{root.name}/{path.relative_to(root).as_posix()}"
            try:
                text = path.read_text(encoding="utf-8-sig", errors="replace")
            except OSError as exc:
                hits.append(f"{label}:0 rule=read_error:{exc.__class__.__name__}")
                continue
            for line_number, line in enumerate(text.splitlines(), start=1):
                for name in names:
                    if name in line:
                        hits.append(f"{label}:{line_number} rule=blacklist")
                        break
                if SUFFIX.search(line):
                    hits.append(f"{label}:{line_number} rule=suffix")
        if root_scanned == 0:
            empty_roots.append(str(root))
    log_target.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"scanned_files={scanned}", f"hits={len(hits)}"]
    lines.extend(f"- {hit}" for hit in hits)
    log_target.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return scanned, len(hits), empty_roots


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", action="append", required=True, help="要扫描的报告目录，可重复")
    parser.add_argument("--blacklist", default="fixtures/company_names.txt")
    parser.add_argument("--log", default=None)
    parser.add_argument("--min-files", type=int, default=0, help="扫描文件数下限；低于该值判失败")
    args = parser.parse_args()
    log_path = Path(args.log) if args.log else Path(args.dir[0]) / "scan.log"
    try:
        names = load_blacklist(args.blacklist)
        scanned, hits, empty_roots = scan(args.dir, names, log_path)
    except (OSError, ValueError) as exc:
        print(f"scan error: {exc}", file=sys.stderr)
        return 1
    if empty_roots:
        print(f"scan FAIL: scanned_files={scanned} empty_dirs={len(empty_roots)} log={log_path}")
        return 1
    if args.min_files and scanned < args.min_files:
        print(f"scan FAIL: scanned_files={scanned} < min_files={args.min_files} log={log_path}")
        return 1
    if scanned == 0:
        print(f"scan FAIL: scanned_files=0 (no report files found) log={log_path}")
        return 1
    if hits:
        print(f"scan FAIL: scanned_files={scanned} hits={hits} log={log_path}")
        return 1
    print(f"scan PASS: scanned_files={scanned} hits=0 log={log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())