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
    logs = artifacts / "logs"
    if logs.exists():
        shutil.rmtree(logs)

    steps = {}
    steps["pre"] = run(["-m", "cal.cli", "verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "pre", "--out", args.out])
    steps["post"] = run(["-m", "cal.cli", "verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "post", "--actual", "fixtures/actual.csv", "--estimate", f"{args.out}/estimate.csv", "--out", args.out])
    steps["negative"] = run(["-m", "cal.cli", "verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "post", "--actual", "fixtures/negative_actual.csv", "--estimate", f"{args.out}/estimate.csv", "--out", args.negative_out])
    steps["scan"] = run(["scripts/scan_report.py", "--dir", args.out, "--blacklist", "fixtures/company_names.txt"])
    steps["pytest"] = run(["-m", "pytest", "-q"])

    for name, result in steps.items():
        write_log(logs / f"{name}.log", result)

    compare = json.loads((out / "compare.json").read_text(encoding="utf-8"))
    negative_payload = json.loads((negative / "compare.json").read_text(encoding="utf-8"))
    scan_text = (out / "scan.log").read_text(encoding="utf-8")
    scanned = int(re.search(r"scanned_files=(\d+)", scan_text).group(1))
    hits = int(re.search(r"hits=(\d+)", scan_text).group(1))
    tests_passed = parse_passed(str(steps["pytest"]["stdout"]) + str(steps["pytest"]["stderr"]))

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
        "tests_passed": tests_passed,
        "tests_exit": steps["pytest"]["exit"],
    }
    write_run_log(
        out / "run.log",
        mode="acceptance",
        version_from="v3",
        version_to="v4",
        out=args.out,
        asof=datetime.now(timezone.utc).date().isoformat(),
        checks=checks,
    )
    log_errors = check_log_consistency(out / "run.log", checks)
    all_passed = (
        steps["pre"]["exit"] == 0
        and compare["passed"] is True
        and steps["negative"]["exit"] == 2
        and negative_payload["ratio"] < compare["threshold"]
        and hits == 0
        and steps["pytest"]["exit"] == 0
        and not log_errors
    )

    acceptance = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "all_passed": all_passed,
        "checks": checks,
        "log_errors": log_errors,
        "steps": {name: {"command": result["command"], "exit": result["exit"]} for name, result in steps.items()},
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
        f"- 总体：{'PASS' if all_passed else 'FAIL'}",
        f"- 预估值：120 家；实际变化：{compare['actual_rows']} 家；并集：{compare['total_rows']} 家",
        f"- 一致率：{compare['ratio'] * 100:.2f}%（{compare['matched_rows']}/{compare['total_rows']}），阈值 {compare['threshold'] * 100:.2f}%",
        f"- 冻结：{json.dumps(compare['frozen_counts'], ensure_ascii=False, sort_keys=True)}；reason 错误 {len(compare['reason_errors'])}；set_drift {len(compare['set_drift'])}",
        f"- 扫描：{scanned} 个文件，命中 {hits}；negative：{negative_payload['ratio']:.6f}（exit {steps['negative']['exit']}）",
        f"- 测试：{tests_passed} passed（exit {steps['pytest']['exit']}）；run.log 同源错误 {len(log_errors)}",
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
        f"1. 一致率：{compare['matched_rows']}/{compare['total_rows']} = {compare['ratio']:.6f}，阈值 {compare['threshold']:.2f}。",
        f"2. 冻结集合：{json.dumps(compare['frozen_counts'], ensure_ascii=False, sort_keys=True)}，逐家错误 {len(compare['frozen_state_errors'])}。",
        f"3. 原因/版本：changed.csv 每条 reason=权重版本切换、weight_from=v3、weight_to=v4；错误 {len(compare['reason_errors'])}。",
        f"4. 企业名扫描：扫描 {scanned} 个文本文件，命中 {hits}；报告与日志只含假名 id。",
        "",
        "## 日志",
        "",
        "- artifacts/logs/pre.log / post.log / negative.log / scan.log / pytest.log",
        "- out/report/run.log 末行 mode=acceptance，checks 同时包含上述四组证据。",
        "- out/report/compare.json 与 out/report/report.md 为 post 的同源结果。",
        "",
    ]
    (artifacts / "ACCEPTANCE.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"acceptance {'PASS' if all_passed else 'FAIL'}: ratio={compare['ratio']:.6f} scan_hits={hits} tests_passed={tests_passed} log_errors={len(log_errors)}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
