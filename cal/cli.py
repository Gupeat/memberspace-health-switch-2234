"""Command-line entry point for the health-score switch verifier."""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from cal.compare import (
    check_reasons,
    check_warn_tasks,
    compare_changes,
    derive_actual_changes,
    frozen_counts,
    load_actual_snapshot,
    load_estimate_rows,
    load_warn_task_pids,
)
from cal.adapters.crm_source import load_companies_from_snapshot
from cal.config import load_config, load_weights
from cal.report import (
    check_log_consistency,
    club_counts,
    direction_counts,
    manager_counts,
    write_actual_csv,
    write_change_csv,
    write_frozen_csv,
    write_json,
    write_pivot_csv,
    write_post_report,
    write_pre_report,
    write_run_log,
)
from cal.scoring import estimate_changes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cal", description="健康分权重切换影响验证")
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("verify-health-switch", help="预估（pre）或验证（post）一次权重切换")
    cmd.add_argument("--from", dest="from_version", required=True, help="切换前权重版本，如 v3")
    cmd.add_argument("--to", dest="to_version", required=True, help="切换后权重版本，如 v4")
    cmd.add_argument("--mode", choices=("pre", "post"), required=True)
    cmd.add_argument("--config", default=None, help="pre 配置 JSON；默认 fixtures/config-pre.json；post 不接受该参数")
    cmd.add_argument("--crm", default="fixtures/companies.json", help="企业快照 JSON")
    cmd.add_argument("--weights-from", default="fixtures/weights-v3.json")
    cmd.add_argument("--weights-to", default="fixtures/weights-v4.json")
    cmd.add_argument("--actual", default=None, help="post 必填：切换后全量状态快照 CSV")
    cmd.add_argument("--warn-tasks", default="fixtures/warn_tasks.json", help="切换后预警任务 JSON")
    cmd.add_argument("--estimate", default=None, help="post 读取的预估 CSV；默认 <out>/estimate.csv")
    cmd.add_argument("--out", default="out/report", help="输出目录")
    cmd.add_argument("--threshold", type=float, default=0.99, help="一致率阈值，默认 0.99")
    cmd.add_argument("--asof", default=None, help="数据日期 YYYY-MM-DD；pre 默认读配置 asof，post 默认今天")
    return parser


def _config_path(args: argparse.Namespace) -> Path:
    if args.config:
        return Path(args.config)
    return Path("fixtures/config-pre.json")


def _clear_outputs(out: Path) -> None:
    for name in (
        "estimate.csv", "frozen_would_change.csv", "pivot.csv", "summary.json", "pre-report.md", "run.log",
        "actual.csv", "changed.csv", "compare.json", "report.md",
    ):
        (out / name).unlink(missing_ok=True)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_pre(args: argparse.Namespace) -> int:
    out = Path(args.out)
    config = load_config(_config_path(args))
    asof = args.asof or config.get("asof") or date.today().isoformat()
    if config["active_version"] != args.from_version:
        _clear_outputs(out)
        write_run_log(
            out / "run.log",
            mode="pre-guard-failed",
            version_from=args.from_version,
            version_to=args.to_version,
            out=str(out),
            asof=asof,
            extra={"error": f"active_version={config['active_version']!r}, expected {args.from_version!r}"},
        )
        print(
            f"pre guard failed: active_version={config['active_version']!r}, expected {args.from_version!r}",
            file=sys.stderr,
        )
        return 3
    version_from, weights_from = load_weights(args.weights_from)
    version_to, weights_to = load_weights(args.weights_to)
    if version_from != args.from_version or version_to != args.to_version:
        print("weight file version does not match --from/--to", file=sys.stderr)
        return 1
    companies = load_companies_from_snapshot(args.crm)
    changes, frozen_rows = estimate_changes(
        companies,
        weights_from,
        weights_to,
        config["bands"],
        version_from,
        version_to,
    )
    out.mkdir(parents=True, exist_ok=True)
    _clear_outputs(out)
    estimate_path = Path(args.estimate) if args.estimate else out / "estimate.csv"
    write_change_csv(estimate_path, changes)
    write_frozen_csv(out / "frozen_would_change.csv", frozen_rows)
    write_pivot_csv(out / "pivot.csv", changes, companies)
    summary = {
        "mode": "pre",
        "from": version_from,
        "to": version_to,
        "asof": asof,
        "company_count": len(companies),
        "changed_count": len(changes),
        "by_direction": direction_counts(changes),
        "by_club": club_counts(changes, companies),
        "by_manager": manager_counts(changes),
        "frozen_total": sum(1 for company in companies if company.state in ("renewed", "churned")),
        "frozen_would_change": len(frozen_rows),
    }
    write_json(out / "summary.json", summary)
    write_pre_report(
        out / "pre-report.md",
        version_from=version_from,
        version_to=version_to,
        companies=companies,
        changes=changes,
        frozen_rows=frozen_rows,
        asof=asof,
        generated_at=_utc_now(),
    )
    write_run_log(
        out / "run.log",
        mode="pre",
        version_from=version_from,
        version_to=version_to,
        out=str(out),
        asof=asof,
        extra={"companies": len(companies), "estimated_changes": len(changes)},
    )
    print(
        f"pre ok: from={version_from} to={version_to} companies={len(companies)} "
        f"changes={len(changes)} frozen_would_change={len(frozen_rows)} out={out}"
    )
    return 0


def _run_post(args: argparse.Namespace) -> int:
    if args.config:
        print("--config is only supported in pre mode; post reads --weights-from/--weights-to and --actual", file=sys.stderr)
        return 1
    if not args.actual:
        print("post requires --actual", file=sys.stderr)
        return 1
    asof = args.asof or date.today().isoformat()
    version_from, weights_from = load_weights(args.weights_from)
    version_to, weights_to = load_weights(args.weights_to)
    if version_from != args.from_version or version_to != args.to_version:
        print("weight file version does not match --from/--to", file=sys.stderr)
        return 1
    companies = load_companies_from_snapshot(args.crm)
    estimate_path = Path(args.estimate) if args.estimate else Path(args.out) / "estimate.csv"
    if not estimate_path.is_file():
        print(f"estimate file not found: {estimate_path}", file=sys.stderr)
        return 1
    estimate_rows = load_estimate_rows(estimate_path)
    if not estimate_rows:
        print(f"estimate file has no rows: {estimate_path}", file=sys.stderr)
        return 1
    bad_versions = sorted(
        {
            f"{row.weight_from}->{row.weight_to}"
            for row in estimate_rows
            if row.weight_from != version_from or row.weight_to != version_to
        }
    )
    if bad_versions:
        print(
            f"estimate file version mismatch: expected {version_from}->{version_to}, "
            f"found {', '.join(bad_versions)}",
            file=sys.stderr,
        )
        return 1
    estimate_sha256 = hashlib.sha256(estimate_path.read_bytes()).hexdigest()
    snapshot = load_actual_snapshot(args.actual)
    actual_rows, entity_errors, frozen_errors, missing_actual = derive_actual_changes(
        companies, snapshot, weights_from, version_from, version_to
    )
    baseline_pids = {company.company_pid for company in companies}
    snapshot_errors: list[dict[str, Any]] = []
    for pid in sorted(set(snapshot) - baseline_pids):
        snapshot_errors.append({"company_pid": pid, "problem": "unexpected_pid"})
    for pid in missing_actual:
        snapshot_errors.append({"company_pid": pid, "problem": "missing_from_actual"})
    comparison = compare_changes(estimate_rows, actual_rows, args.threshold)
    warn_pids = load_warn_task_pids(args.warn_tasks)
    warn_errors = check_warn_tasks(actual_rows, warn_pids)
    reason_errors = check_reasons(actual_rows, version_from, version_to)
    counts = frozen_counts(companies, snapshot)
    frozen_counts_ok = counts["baseline"] == counts["actual"]
    base_passed = (
        comparison["total_rows"] > 0
        and comparison["ratio"] >= comparison["threshold"]
        and not frozen_errors
        and frozen_counts_ok
        and not warn_errors
        and not reason_errors
        and not entity_errors
        and not snapshot_errors
    )
    out = Path(args.out)
    write_actual_csv(out / "actual.csv", snapshot)
    write_change_csv(out / "changed.csv", actual_rows)
    write_pivot_csv(out / "pivot.csv", actual_rows, companies)
    checks = {
        "ratio": comparison["ratio"],
        "matched_rows": comparison["matched_rows"],
        "total_rows": comparison["total_rows"],
        "threshold": comparison["threshold"],
        "estimate_rows": comparison["estimate_rows"],
        "actual_rows": comparison["actual_rows"],
        "frozen_state_errors": len(frozen_errors),
        "frozen_counts": counts,
        "frozen_counts_ok": frozen_counts_ok,
        "warn_task_errors": len(warn_errors),
        "reason_errors": len(reason_errors),
        "entity_errors": len(entity_errors),
        "snapshot_errors": len(snapshot_errors),
        "set_drift": len(comparison["set_drift"]),
    }
    write_run_log(
        out / "run.log",
        mode="post",
        version_from=version_from,
        version_to=version_to,
        out=str(out),
        asof=asof,
        checks=checks,
    )
    log_errors = check_log_consistency(out / "run.log", checks)
    passed = base_passed and not log_errors
    payload: dict[str, Any] = {
        "mode": "post",
        "from": version_from,
        "to": version_to,
        "asof": asof,
        "generated_at": _utc_now(),
        "estimate_path": estimate_path.as_posix(),
        "estimate_sha256": estimate_sha256,
        **comparison,
        "frozen_state_errors": frozen_errors,
        "frozen_counts": counts,
        "frozen_counts_ok": frozen_counts_ok,
        "warn_task_errors": warn_errors,
        "reason_errors": reason_errors,
        "entity_errors": entity_errors,
        "snapshot_errors": snapshot_errors,
        "log_errors": log_errors,
        "passed": passed,
    }
    write_json(out / "compare.json", payload)
    write_post_report(
        out / "report.md",
        version_from=version_from,
        version_to=version_to,
        comparison=comparison,
        estimate_path=estimate_path.as_posix(),
        estimate_sha256=estimate_sha256,
        frozen_errors=frozen_errors,
        frozen_counts_payload=counts,
        frozen_counts_ok=frozen_counts_ok,
        warn_errors=warn_errors,
        reason_errors=reason_errors,
        entity_errors=entity_errors,
        snapshot_errors=snapshot_errors,
        set_drift=comparison["set_drift"],
        log_errors=log_errors,
        asof=asof,
        generated_at=_utc_now(),
    )
    print(
        f"post {'PASS' if passed else 'FAIL'}: ratio={comparison['ratio']:.6f} "
        f"matched={comparison['matched_rows']} total={comparison['total_rows']} "
        f"threshold={comparison['threshold']:.2f} out={out}"
    )
    if not passed:
        print(
            f"checks: ratio={comparison['ratio']:.6f} matched={comparison['matched_rows']} "
            f"total={comparison['total_rows']} score_drift={len(comparison['score_drift'])} "
            f"frozen_errors={len(frozen_errors)} frozen_counts_ok={frozen_counts_ok} "
            f"warn_errors={len(warn_errors)} reason_errors={len(reason_errors)} "
            f"entity_errors={len(entity_errors)} snapshot_errors={len(snapshot_errors)}",
            file=sys.stderr,
        )
        for item in (entity_errors + snapshot_errors)[:5]:
            print(f"  {item.get('problem')}: {item.get('company_pid')}", file=sys.stderr)
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "verify-health-switch":
            if args.from_version == args.to_version:
                print("--from and --to must differ", file=sys.stderr)
                return 1
            if args.asof:
                try:
                    date.fromisoformat(args.asof)
                except ValueError:
                    print(f"--asof is not a valid YYYY-MM-DD date: {args.asof}", file=sys.stderr)
                    return 1
            if not 0.99 <= args.threshold <= 1.0:
                print("--threshold must be between 0.99 and 1.0", file=sys.stderr)
                return 1
            return _run_pre(args) if args.mode == "pre" else _run_post(args)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
