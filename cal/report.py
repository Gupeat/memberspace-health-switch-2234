"""Deterministic CSV/JSON/Markdown writers for the switch verifier."""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from cal.models import DIRECTION_LABELS, ChangeRow, Company

CHANGE_FIELDS = [
    "company_pid",
    "old_status",
    "new_status",
    "old_score",
    "new_score",
    "manager_id",
    "key_member",
    "direction",
    "reason",
    "weight_from",
    "weight_to",
]


def _write_csv(path: str | Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_change_csv(path: str | Path, rows: list[ChangeRow]) -> None:
    _write_csv(path, CHANGE_FIELDS, [row.as_dict() for row in rows])


def write_frozen_csv(path: str | Path, rows: list[dict[str, Any]]) -> None:
    fields = ["company_pid", "locked_status", "band_from", "band_to", "old_score", "new_score"]
    _write_csv(path, fields, rows)


def write_actual_csv(path: str | Path, snapshot: dict[str, dict[str, Any]]) -> None:
    fields = ["company_pid", "state", "score", "reason", "weight_from", "weight_to"]
    rows = [
        {
            "company_pid": pid,
            "state": row["state"],
            "score": row["score"],
            "reason": row["reason"],
            "weight_from": row["weight_from"],
            "weight_to": row["weight_to"],
        }
        for pid, row in sorted(snapshot.items())
    ]
    _write_csv(path, fields, rows)


def write_pivot_csv(path: str | Path, rows: list[ChangeRow], companies: list[Company]) -> None:
    by_pid = {company.company_pid: company for company in companies}
    counts: Counter[tuple[str, str, str]] = Counter()
    for row in rows:
        company = by_pid.get(row.company_pid)
        counts[(company.club_id if company else "", row.manager_id, row.direction)] += 1
    fields = ["club_id", "manager_id", "direction", "count"]
    out = [
        {"club_id": key[0], "manager_id": key[1], "direction": key[2], "count": count}
        for key, count in sorted(counts.items())
    ]
    _write_csv(path, fields, out)


def direction_counts(rows: list[ChangeRow]) -> dict[str, int]:
    counts = {key: 0 for key in DIRECTION_LABELS}
    for row in rows:
        counts[row.direction] = counts.get(row.direction, 0) + 1
    return counts


def club_counts(rows: list[ChangeRow], companies: list[Company]) -> dict[str, int]:
    by_pid = {company.company_pid: company for company in companies}
    counts: Counter[str] = Counter()
    for row in rows:
        company = by_pid.get(row.company_pid)
        counts[company.club_id if company else ""] += 1
    return dict(sorted(counts.items()))


def manager_counts(rows: list[ChangeRow]) -> dict[str, int]:
    counts: Counter[str] = Counter(row.manager_id for row in rows)
    return dict(sorted(counts.items()))


def write_json(path: str | Path, payload: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def write_pre_report(
    path: str | Path,
    *,
    version_from: str,
    version_to: str,
    companies: list[Company],
    changes: list[ChangeRow],
    frozen_rows: list[dict[str, Any]],
    asof: str,
    generated_at: str,
) -> None:
    frozen_total = sum(1 for company in companies if company.state in ("renewed", "churned"))
    lines = [
        "# 健康分权重切换影响预估",
        "",
        f"- 模式：pre（切换前）",
        f"- 权重版本：{version_from} → {version_to}",
        f"- 数据日期：{asof}",
        f"- 生成时间：{generated_at}",
        f"- 企业总数：{len(companies)}",
        f"- 预计状态变化：{len(changes)}",
        f"- 冻结状态企业：{frozen_total}（续约/已流失，不进入变化清单）",
        f"- 冻结但分数档位会变：{len(frozen_rows)}",
        "",
        "## 四方向分布",
        "",
        "| 方向 | 含义 | 数量 |",
        "|---|---|---:|",
    ]
    for direction, label in DIRECTION_LABELS.items():
        lines.append(f"| {direction} | {label} | {direction_counts(changes).get(direction, 0)} |")
    lines += ["", "## 按会所", "", "| club_id | 数量 |", "|---|---:|"]
    for club_id, count in club_counts(changes, companies).items():
        lines.append(f"| {club_id or '(空)'} | {count} |")
    lines += ["", "## 按会员经理", "", "| manager_id | 数量 |", "|---|---:|"]
    for manager_id, count in manager_counts(changes).items():
        lines.append(f"| {manager_id or '(空)'} | {count} |")
    lines += [
        "",
        "## 明细与口径",
        "",
        "- 明细：estimate.csv；分方向/会所/经理交叉计数：pivot.csv。",
        "- 匹配键：company_pid + old_status + new_status + direction；一致率分母为两侧变化行并集。",
        "- 续约（renewed）与已流失（churned）为冻结状态，不进入变化清单；其数量单独保留。",
        "- 报告只含 company_pid、manager_id、club_id 等假名标识。",
        "",
    ]
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def write_post_report(
    path: str | Path,
    *,
    version_from: str,
    version_to: str,
    comparison: dict[str, Any],
    estimate_path: str,
    estimate_sha256: str,
    frozen_errors: list[str],
    frozen_counts_payload: dict[str, Any] | None,
    frozen_counts_ok: bool,
    warn_errors: list[dict[str, str]],
    reason_errors: list[dict[str, str]],
    entity_errors: list[dict[str, Any]],
    snapshot_errors: list[dict[str, Any]],
    set_drift: list[dict[str, str]],
    log_errors: list[str],
    asof: str,
    generated_at: str,
) -> None:
    passed = (
        comparison["total_rows"] > 0
        and comparison["ratio"] >= comparison["threshold"]
        and frozen_counts_ok
        and not frozen_errors
        and not warn_errors
        and not reason_errors
        and not entity_errors
        and not snapshot_errors
        and not log_errors
    )
    lines = [
        "# 健康分权重切换验证报告",
        "",
        f"- 模式：post（切换后验证）",
        f"- 权重版本：{version_from} → {version_to}",
        f"- 数据日期：{asof}",
        f"- 生成时间：{generated_at}",
        f"- 预估输入：{estimate_path}，SHA-256 {estimate_sha256}",
        f"- 一致率（状态+分数，分数容差 0.01）：{comparison['ratio'] * 100:.2f}%（{comparison['matched_rows']}/{comparison['total_rows']}）",
        f"- 阈值：{comparison['threshold'] * 100:.2f}%",
        f"- 结论：{'PASS' if passed else 'FAIL'}",
        "",
        "## 校验项",
        "",
        "| 检查 | 结果 | 说明 |",
        "|---|---|---|",
        f"| 一致率（状态+分数） | {'PASS' if comparison['total_rows'] > 0 and comparison['ratio'] >= comparison['threshold'] else 'FAIL'} | {comparison['matched_rows']}/{comparison['total_rows']} = {comparison['ratio']:.6f}；分数差 >0.01 计不匹配 |",
        f"| 续约/已流失冻结 | {'PASS' if not frozen_errors else 'FAIL'} | {len(frozen_errors)} 个错误 |",
        f"| 续约/已流失计数 | {'PASS' if frozen_counts_ok else 'FAIL'} | 切换前 renewed={((frozen_counts_payload or {}).get('baseline') or {}).get('renewed', 'n/a')}, churned={((frozen_counts_payload or {}).get('baseline') or {}).get('churned', 'n/a')}；切换后 renewed={((frozen_counts_payload or {}).get('actual') or {}).get('renewed', 'n/a')}, churned={((frozen_counts_payload or {}).get('actual') or {}).get('churned', 'n/a')} |",
        f"| 流失预警任务 | {'PASS' if not warn_errors else 'FAIL'} | {len(warn_errors)} 个缺失 |",
        f"| 原因与版本号 | {'PASS' if not reason_errors else 'FAIL'} | {len(reason_errors)} 个错误 |",
        f"| 状态流转合法性 | {'PASS' if not entity_errors else 'FAIL'} | {len(entity_errors)} 个错误 |",
        f"| 快照完整性 | {'PASS' if not snapshot_errors else 'FAIL'} | 缺失或多余 PID {len(snapshot_errors)} 个 |",
        f"| 集合漂移（set_drift） | {'WARN' if set_drift else 'PASS'} | {len(set_drift)} 行；actual_only={sum(1 for row in set_drift if row['side'] == 'actual_only')}，estimate_only={sum(1 for row in set_drift if row['side'] == 'estimate_only')}；诊断项，已计入一致率并集分母 |",
        f"| run.log checks 自校验 | {'PASS' if not log_errors else 'FAIL'} | {len(log_errors)} 个字段不一致；以 run.log 末行为准 |",
        "",
        "## 差集摘要",
        "",
        f"- 预估行：{comparison['estimate_rows']}；实际变化行：{comparison['actual_rows']}；并集：{comparison['total_rows']}",
        f"- 实际缺失：{len(comparison['missing_in_actual'])} 个；预估缺失：{len(comparison['missing_in_estimate'])} 个",
        f"- 集合漂移 set_drift：{len(set_drift)} 行（只在一侧出现的变化行，计入一致率并集分母）",
        f"- 分数漂移（状态匹配但 old/new 分数差 >0.01）：{len(comparison['score_drift'])} 个（计为不匹配）",
        f"- 不匹配行：{len(comparison['mismatch'])} 个",
        "",
        "## 不匹配明细（最多 10 条）",
        "",
        "| company_pid | 类型 | 预估 | 实际 |",
        "|---|---|---|---|",
        *[
            f"| {item.get('company_pid', '')} | {item.get('kind', 'status_or_direction')} | "
            f"{item.get('estimate', {}).get('old_status', '')}→{item.get('estimate', {}).get('new_status', '')} "
            f"({item.get('estimate', {}).get('old_score', '')}/{item.get('estimate', {}).get('new_score', '')}) | "
            f"{item.get('actual', {}).get('old_status', '')}→{item.get('actual', {}).get('new_status', '')} "
            f"({item.get('actual', {}).get('old_score', '')}/{item.get('actual', {}).get('new_score', '')}) |"
            for item in comparison['mismatch'][:10]
        ],
        "",
        "## 明细",
        "",
        "- actual.csv：切换后 CRM 快照的规范化输出（company_pid/state/score/reason/weight_from/weight_to），不含企业名称；变化行的原因与版本号来自输入，不是工具自填。",
        "- changed.csv：实际变化清单，每条带 reason=权重版本切换 与 weight_from/weight_to。",
        "- compare.json：一致率、差集、set_drift、分数漂移、冻结/预警/原因校验的机器可读结果。",
        "- pivot.csv：按会所、会员经理、四方向分组的计数。",
        "- run.log：末行 checks 与本次运行使用同一组 checks；check_log_consistency 只回读 run.log 末行做自校验（不解析 compare.json/report.md）。",
        "- 一致率口径：匹配键为 company_pid + old_status + new_status + direction，且 old_score/new_score 与预估差都不超过 0.01；分数差超过 0.01 的行计为不匹配。",
        "- 报告与日志只含假名 id，不含企业名称。",
        "",
    ]
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def write_run_log(
    path: str | Path,
    *,
    mode: str,
    version_from: str,
    version_to: str,
    out: str,
    asof: str,
    checks: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = json.dumps(
        {
            "generated_at": stamp,
            "mode": mode,
            "from": version_from,
            "to": version_to,
            "out": Path(out).as_posix(),
            "asof": asof,
            "checks": checks or {},
            **(extra or {}),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    with target.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line + "\n")


def read_last_run_log(path: str | Path) -> dict[str, Any] | None:
    target = Path(path)
    if not target.is_file():
        return None
    last = None
    for raw in target.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if raw:
            last = json.loads(raw)
    return last


def check_log_consistency(path: str | Path, expected_checks: dict[str, Any]) -> list[str]:
    """Compare expected checks with the last run.log line."""
    try:
        last = read_last_run_log(path)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"run.log unreadable: {exc}"]
    if last is None:
        return ["run.log missing or empty"]
    actual = last.get("checks")
    if not isinstance(actual, dict):
        return ["run.log has no checks object"]
    errors = []
    for key, expected in expected_checks.items():
        got = actual.get(key)
        if got != expected:
            errors.append(f"{key}: run.log={got!r} expected={expected!r}")
    return errors
