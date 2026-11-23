#!/usr/bin/env python3
"""Run the full acceptance chain and write a four-group evidence report."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cal.report import check_log_consistency, write_json, write_run_log  # noqa: E402

EXPECTED_TESTS = 64
MIN_SCANNED_FILES = 12
ASOF = "2026-11-22"
EVIDENCE_FILES = ("acceptance.json", "ACCEPTANCE.md", "FINAL-SCAN.md", "final-scan.log")


def invalidate_evidence(artifacts: Path) -> None:
    """Remove an older PASS generation before this run can fail."""
    for name in EVIDENCE_FILES:
        (artifacts / name).unlink(missing_ok=True)
    (artifacts / "FAILED").unlink(missing_ok=True)


def write_failure(artifacts: Path, message: str) -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_json(
        artifacts / "acceptance.json",
        {"generated_at": stamp, "all_passed": False, "error": message, "final_scan": None, "final_scan_skipped": True},
    )
    (artifacts / "ACCEPTANCE.md").write_text(
        "# 验收记录（AC1–AC4）\n\n"
        f"- 生成时间：{stamp}\n"
        "- 总体：FAIL\n"
        f"- 错误：{message}\n",
        encoding="utf-8",
        newline="\n",
    )
    (artifacts / "FAILED").write_text(
        "acceptance run failed; previous PASS evidence was removed\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"acceptance FAIL: {message}", file=sys.stderr)
    return 1


def run(args: list[str]) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    return {
        "command": "python " + " ".join(args),
        "exit": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def write_log(path: Path, result: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = f"$ {result['command']}\n[exit {result['exit']}]\n{result['stdout']}{result['stderr']}"
    path.write_text(text.replace(str(ROOT), "<repo>"), encoding="utf-8", newline="\n")


def parse_passed(text: str) -> int:
    match = re.search(r"(\d+) passed", text)
    return int(match.group(1)) if match else 0


def parse_skipped(text: str) -> int:
    match = re.search(r"(\d+) skipped", text)
    return int(match.group(1)) if match else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="out/report")
    parser.add_argument("--negative-out", default="out/negative")
    parser.add_argument("--artifacts", default="artifacts")
    args = parser.parse_args()

    out = ROOT / args.out
    negative = ROOT / args.negative_out
    artifacts = ROOT / args.artifacts
    for target in (out, negative):
        if target.exists():
            shutil.rmtree(target)
    artifacts.mkdir(parents=True, exist_ok=True)
    invalidate_evidence(artifacts)
    logs = artifacts / "logs"
    if logs.exists():
        shutil.rmtree(logs)

    steps = {}
    steps["pre"] = run(["-m", "cal.cli", "verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "pre", "--asof", ASOF, "--out", args.out])
    steps["post"] = run(["-m", "cal.cli", "verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "post", "--asof", ASOF, "--actual", "fixtures/actual.csv", "--estimate", f"{args.out}/estimate.csv", "--out", args.out])
    steps["negative"] = run(["-m", "cal.cli", "verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "post", "--asof", ASOF, "--actual", "fixtures/negative_actual.csv", "--estimate", f"{args.out}/estimate.csv", "--out", args.negative_out])
    steps["pytest"] = run(["-m", "pytest", "-q"])

    # Scan artifacts only after the step logs exist; otherwise a truly clean
    # checkout (no stale artifacts/) makes the scan directory empty.
    for name in ("pre", "post", "negative", "pytest"):
        write_log(logs / f"{name}.log", steps[name])
    steps["scan"] = run([
        "scripts/scan_report.py",
        "--dir", args.out,
        "--dir", args.negative_out,
        "--dir", args.artifacts,
        "--blacklist", "fixtures/company_names.txt",
        "--log", f"{args.out}/scan.log",
        "--exclude", "artifacts/clean-room",
        "--min-files", str(MIN_SCANNED_FILES),
    ])
    write_log(logs / "scan.log", steps["scan"])

    required_paths = [
        out / "compare.json",
        negative / "compare.json",
        out / "scan.log",
        out / "pre-report.md",
        out / "report.md",
    ]
    missing_paths = [str(path.relative_to(ROOT)) for path in required_paths if not path.is_file()]
    if missing_paths:
        return write_failure(artifacts, f"missing outputs: {', '.join(missing_paths)}")

    try:
        compare = json.loads((out / "compare.json").read_text(encoding="utf-8"))
        negative_payload = json.loads((negative / "compare.json").read_text(encoding="utf-8"))
        scan_text = (out / "scan.log").read_text(encoding="utf-8")
        scanned = int(re.search(r"scanned_files=(\d+)", scan_text).group(1))
        hits = int(re.search(r"hits=(\d+)", scan_text).group(1))
    except (OSError, ValueError, KeyError, AttributeError) as exc:
        return write_failure(artifacts, f"cannot parse acceptance outputs: {exc}")
    test_output = str(steps["pytest"]["stdout"]) + str(steps["pytest"]["stderr"])
    tests_passed = parse_passed(test_output)
    tests_skipped = parse_skipped(test_output)

    checks = {
        "ratio": compare["ratio"],
        "matched_rows": compare["matched_rows"],
        "total_rows": compare["total_rows"],
        "threshold": compare["threshold"],
        "frozen_counts": compare["frozen_counts"],
        "frozen_counts_ok": compare["frozen_counts_ok"],
        "reason_errors": len(compare["reason_errors"]),
        "set_drift": len(compare["set_drift"]),
        "scan_scanned_files": scanned,
        "scan_hits": hits,
        "negative_ratio": negative_payload["ratio"],
        "negative_exit": steps["negative"]["exit"],
        "post_exit": steps["post"]["exit"],
        "scan_min_files": MIN_SCANNED_FILES,
        "tests_passed": tests_passed,
        "tests_skipped": tests_skipped,
        "tests_expected": EXPECTED_TESTS,
        "tests_exit": steps["pytest"]["exit"],
    }
    write_run_log(
        out / "run.log",
        mode="acceptance",
        version_from="v3",
        version_to="v4",
        out=args.out,
        asof=ASOF,
        checks=checks,
    )
    log_errors = check_log_consistency(out / "run.log", checks)
    all_passed = (
        steps["pre"]["exit"] == 0
        and steps["post"]["exit"] == 0
        and compare["passed"] is True
        and steps["negative"]["exit"] == 2
        and negative_payload["ratio"] < compare["threshold"]
        and steps["scan"]["exit"] == 0
        and scanned >= MIN_SCANNED_FILES
        and hits == 0
        and steps["pytest"]["exit"] == 0
        and tests_passed == EXPECTED_TESTS
        and tests_skipped == 0
        and not log_errors
    )

    # Provisional record: all_passed stays False until the final scan below
    # succeeds, so a crash cannot leave a PASS acceptance.json without
    # final_scan evidence.
    acceptance = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "all_passed": False,
        "checks": checks,
        "log_errors": log_errors,
        "steps": {name: {"command": result["command"], "exit": result["exit"]} for name, result in steps.items()},
        "final_scan": None,
    }
    write_json(artifacts / "acceptance.json", acceptance)

    rows = [
        ("pre", steps["pre"]["exit"], 0),
        ("post", steps["post"]["exit"], 0),
        ("negative（预期 2）", steps["negative"]["exit"], 2),
        ("scan", steps["scan"]["exit"], 0),
        ("pytest", steps["pytest"]["exit"], 0),
    ]
    lines = [
        "# 验收记录（AC1–AC4）",
        "",
        f"- 生成时间：{acceptance['generated_at']}",
        f"- 总体：{'PASS（待最终复扫确认）' if all_passed else 'FAIL'}",
        f"- 预估值：{compare['estimate_rows']} 家；实际变化：{compare['actual_rows']} 家；并集：{compare['total_rows']} 家",
        f"- 一致率：{compare['ratio'] * 100:.2f}%（{compare['matched_rows']}/{compare['total_rows']}），阈值 {compare['threshold'] * 100:.2f}%",
        f"- 冻结：{json.dumps(compare['frozen_counts'], ensure_ascii=False, sort_keys=True)}；reason 错误 {len(compare['reason_errors'])}；set_drift {len(compare['set_drift'])}",
        f"- 扫描（验收前）：{scanned} 个文件（要求 ≥{MIN_SCANNED_FILES}），命中 {hits}；最终复扫见 artifacts/FINAL-SCAN.md；negative：{negative_payload['ratio']:.6f}（exit {steps['negative']['exit']}）",
        f"- 测试：{tests_passed}/{EXPECTED_TESTS} passed，skipped {tests_skipped}（exit {steps['pytest']['exit']}）；run.log 回读错误 {len(log_errors)}",
        "",
        "## 命令与退出码",
        "",
        "| 步骤 | 命令 | 退出码 | 期望 |",
        "|---|---|---:|---:|",
    ]
    for name, code, expected in rows:
        command = steps[name.replace("（预期 2）", "")]["command"]
        lines.append(f"| {name} | {command} | {code} | {expected} |")
    lines += [
        "",
        "## 四组证据",
        "",
        f"1. 一致率（状态+分数）：{compare['matched_rows']}/{compare['total_rows']} = {compare['ratio']:.6f}，阈值 {compare['threshold']:.2f}；分数漂移 {len(compare['score_drift'])} 个（计为不匹配）。",
        f"2. 冻结集合：{json.dumps(compare['frozen_counts'], ensure_ascii=False, sort_keys=True)}，逐家错误 {len(compare['frozen_state_errors'])}。",
        f"3. 原因/版本：changed.csv 每条 reason=权重版本切换、weight_from=v3、weight_to=v4；错误 {len(compare['reason_errors'])}。",
        f"4. 企业名扫描（验收前）：out/report、out/negative、artifacts 共 {scanned} 个文本文件，命中 {hits}；ACCEPTANCE.md/acceptance.json 写出后的最终复扫见 FINAL-SCAN.md。",
        "",
        "## 日志",
        "",
        "- artifacts/logs/pre.log / post.log / negative.log / scan.log / pytest.log",
        "- out/report/pre-report.md 为 pre 预估样例；out/report/report.md 为 post 核对样例。",
        "- out/report/run.log 末行 mode=acceptance，checks 同时包含上述四组证据、post 退出码与测试数。",
        "- out/report/compare.json 与 out/report/report.md 由同一 checks 生成；run.log 末行可回读对账。",
        "",
    ]
    (artifacts / "ACCEPTANCE.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")

    # The wrapper scan above runs before this run's acceptance metadata exists.
    # Rescan after writing it so the delivered ACCEPTANCE.md/acceptance.json
    # are themselves covered; FINAL-SCAN.md and final-scan.log are written only
    # after that rescan, so they are not claimed as scanned.
    final_log = artifacts / "final-scan.log"
    final_md = artifacts / "FINAL-SCAN.md"
    for stale in (final_log, final_md):
        if stale.exists():
            stale.unlink()
    final_scan = run([
        "scripts/scan_report.py",
        "--dir", args.out,
        "--dir", args.negative_out,
        "--dir", args.artifacts,
        "--blacklist", "fixtures/company_names.txt",
        "--log", str(final_log),
        "--exclude", "artifacts/clean-room",
        "--min-files", str(MIN_SCANNED_FILES),
    ])
    final_text = final_log.read_text(encoding="utf-8") if final_log.is_file() else ""
    final_scanned = int(re.search(r"scanned_files=(\d+)", final_text).group(1)) if "scanned_files=" in final_text else 0
    final_hits = int(re.search(r"hits=(\d+)", final_text).group(1)) if "hits=" in final_text else -1
    final_ok = final_scan["exit"] == 0 and final_scanned >= MIN_SCANNED_FILES and final_hits == 0
    acceptance["final_scan"] = {"scanned_files": final_scanned, "hits": final_hits, "exit": final_scan["exit"]}
    acceptance["all_passed"] = bool(all_passed and final_ok)
    write_json(artifacts / "acceptance.json", acceptance)
    md = artifacts / "ACCEPTANCE.md"
    md.write_text(
        md.read_text(encoding="utf-8").replace(
            "PASS（待最终复扫确认）", "PASS" if acceptance["all_passed"] else "FAIL"
        ),
        encoding="utf-8",
        newline="\n",
    )
    coverage = "本轮 ACCEPTANCE.md、acceptance.json、artifacts/logs、out/report、out/negative"
    coverage += "；上一代 artifacts/clean-room 是嵌套的历史证据，扫描时排除，避免计数随历史目录变化。"
    final_lines = [
        "# 最终复扫",
        "",
        f"- 时间：{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        f"- 命令：{str(final_scan['command']).replace(str(ROOT), '<repo>').replace(chr(92), '/')}",
        f"- 结果：{'PASS' if final_ok else 'FAIL'}；scanned_files={final_scanned}；hits={final_hits}；exit={final_scan['exit']}",
        f"- 覆盖：{coverage}",
        "- 边界：FINAL-SCAN.md 与 final-scan.log 在本次复扫之后写入，不声称被本次扫描覆盖。",
        "",
    ]
    final_md.write_text("\n".join(final_lines), encoding="utf-8", newline="\n")
    if not final_ok:
        acceptance["all_passed"] = False
        acceptance["final_scan"] = {"scanned_files": final_scanned, "hits": final_hits, "exit": final_scan["exit"]}
        write_json(artifacts / "acceptance.json", acceptance)
        text = (artifacts / "ACCEPTANCE.md").read_text(encoding="utf-8")
        text += f"\n- 最终复扫：FAIL（scanned_files={final_scanned}，hits={final_hits}，exit={final_scan['exit']}）；见 artifacts/FINAL-SCAN.md\n"
        (artifacts / "ACCEPTANCE.md").write_text(text, encoding="utf-8", newline="\n")
        (artifacts / "FAILED").write_text(
            "acceptance run failed at final scan; previous PASS evidence was removed\n",
            encoding="utf-8",
            newline="\n",
        )
        print(f"acceptance FAIL: final scan scanned={final_scanned} hits={final_hits} exit={final_scan['exit']}")
        return 1
    print(f"acceptance {'PASS' if all_passed else 'FAIL'}: ratio={compare['ratio']:.6f} scan_hits={hits} final_scan={final_scanned} tests_passed={tests_passed} log_errors={len(log_errors)}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())