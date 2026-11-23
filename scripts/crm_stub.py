#!/usr/bin/env python3
"""Generate the deterministic 500-company CRM stub and expected snapshots."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cal.config import DEFAULT_BANDS  # noqa: E402
from cal.models import REASON, WEIGHT_KEYS  # noqa: E402
from cal.scoring import band_for, score_company  # noqa: E402

NAMES = [
    "星澜科技",
    "远山制造",
    "青禾咨询",
    "澄川设计",
    "云帆物流",
    "木棉教育",
    "恒益法务",
    "启明人力",
    "苍梧资本",
    "远山传媒",
    "辰光医疗",
    "拾光文旅",
    "简一软件",
    "海桐能源",
    "知微研究",
    "白鹭会展",
    "零度实验室",
    "经纬咨询",
    "南山培训",
    "瀚海贸易",
]

WEIGHTS_V3 = {
    "version": "v3",
    "weights": {"activity": 0.40, "transaction": 0.30, "engagement": 0.20, "tenure": 0.10},
}
WEIGHTS_V4 = {
    "version": "v4",
    "weights": {"activity": 0.20, "transaction": 0.25, "engagement": 0.35, "tenure": 0.20},
}
TARGETS = {
    "active_to_silent": (78.0, 72.0),
    "silent_to_active": (72.0, 78.0),
    "enter_churn_warning": (64.0, 58.0),
    "exit_churn_warning": (58.0, 64.0),
}


def solve_pair(old_target: float, new_target: float) -> dict[str, float]:
    w3 = WEIGHTS_V3["weights"]
    w4 = WEIGHTS_V4["weights"]
    for transaction in range(5, 96, 5):
        for tenure in range(5, 96, 5):
            r1 = old_target - w3["transaction"] * transaction - w3["tenure"] * tenure
            r2 = new_target - w4["transaction"] * transaction - w4["tenure"] * tenure
            determinant = w3["activity"] * w4["engagement"] - w3["engagement"] * w4["activity"]
            if abs(determinant) < 1e-12:
                continue
            activity = (r1 * w4["engagement"] - w3["engagement"] * r2) / determinant
            engagement = (w3["activity"] * r2 - r1 * w4["activity"]) / determinant
            if not (0 <= activity <= 100 and 0 <= engagement <= 100):
                continue
            signals = {
                "activity": round(activity, 2),
                "transaction": float(transaction),
                "engagement": round(engagement, 2),
                "tenure": float(tenure),
            }
            old = round(sum(w3[key] * signals[key] for key in WEIGHT_KEYS) + 1e-9, 2)
            new = round(sum(w4[key] * signals[key] for key in WEIGHT_KEYS) + 1e-9, 2)
            if abs(old - old_target) < 0.005 and abs(new - new_target) < 0.005:
                return signals
    raise SystemExit(f"no signal vector found for {old_target}->{new_target}")


def company(index: int, state: str, signals: dict[str, float]) -> dict:
    return {
        "company_pid": f"c-{index:04d}",
        "company_name": f"{NAMES[(index - 1) % len(NAMES)]}{index:03d}",
        "state": state,
        "club_id": f"club-{(index - 1) % 5 + 1:02d}",
        "manager_id": f"mgr-{(index - 1) % 20 + 1:03d}",
        "key_member": index % 7 == 0,
        "signals": signals,
    }


def stable_signals(value: float) -> dict[str, float]:
    return {key: value for key in WEIGHT_KEYS}


def build_companies() -> list[dict]:
    rows: list[dict] = []
    index = 1
    for direction in ("active_to_silent", "silent_to_active", "enter_churn_warning", "exit_churn_warning"):
        signals = solve_pair(*TARGETS[direction])
        old_state = {
            "active_to_silent": "active",
            "silent_to_active": "silent",
            "enter_churn_warning": "silent",
            "exit_churn_warning": "churn_warning",
        }[direction]
        for _ in range(30):
            rows.append(company(index, old_state, dict(signals)))
            index += 1
    for value, state, count in ((88.0, "active", 120), (66.0, "silent", 120), (50.0, "churn_warning", 80)):
        for _ in range(count):
            rows.append(company(index, state, stable_signals(value)))
            index += 1
    # Frozen statuses: keep the counts fixed. A few have a v3/v4 band drift so
    # frozen_would_change.csv is exercised without changing lifecycle status.
    frozen_renewed = solve_pair(78.0, 72.0)
    for i in range(30):
        signals = dict(frozen_renewed) if i < 3 else stable_signals(80.0)
        rows.append(company(index, "renewed", signals))
        index += 1
    frozen_churned = solve_pair(58.0, 64.0)
    for i in range(30):
        signals = dict(frozen_churned) if i < 3 else stable_signals(40.0)
        rows.append(company(index, "churned", signals))
        index += 1
    assert len(rows) == 500, len(rows)
    assert index == 501
    return rows


def build_actual(
    companies: list[dict],
    weights: dict[str, float],
    bands: dict[str, float],
    version_from: str,
    version_to: str,
) -> list[dict]:
    rows: list[dict] = []
    for raw in companies:
        parsed = load_companies_from_records([raw])[0]
        score = score_company(parsed, weights)
        state = parsed.state if parsed.state in ("renewed", "churned") else band_for(score, bands)
        changed = state != parsed.state
        rows.append(
            {
                "company_pid": parsed.company_pid,
                "state": state,
                "score": score,
                # A real CRM change record carries its own reason/version fields;
                # unchanged rows leave them empty. The verifier reads these
                # values instead of filling them from --from/--to.
                "reason": REASON if changed else "",
                "weight_from": version_from if changed else "",
                "weight_to": version_to if changed else "",
            }
        )
    return rows


def load_companies_from_records(records: list[dict]):
    # Reuse the production loader by writing through its public shape without
    # touching disk on every row.
    from cal.models import Company

    result = []
    for row in records:
        result.append(
            Company(
                company_pid=row["company_pid"],
                company_name=row["company_name"],
                state=row["state"],
                club_id=row["club_id"],
                manager_id=row["manager_id"],
                key_member=bool(row["key_member"]),
                signals={key: float(row["signals"][key]) for key in WEIGHT_KEYS},
            )
        )
    return result


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["company_pid", "state", "score", "reason", "weight_from", "weight_to"],
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> int:
    fixtures = ROOT / "fixtures"
    companies = build_companies()
    parsed = load_companies_from_records(companies)
    actual = build_actual(
        companies,
        WEIGHTS_V4["weights"],
        DEFAULT_BANDS,
        WEIGHTS_V3["version"],
        WEIGHTS_V4["version"],
    )
    negative = [dict(row) for row in actual]
    changes = [
        row for row in parsed
        if row.state not in ("renewed", "churned")
        and band_for(score_company(row, WEIGHTS_V4["weights"]), DEFAULT_BANDS) != row.state
    ]
    assert len(changes) == 120, len(changes)
    for row in changes[:2]:
        target = next(item for item in negative if item["company_pid"] == row.company_pid)
        target["state"] = row.state
        target["score"] = score_company(row, WEIGHTS_V3["weights"])
        target["reason"] = ""
        target["weight_from"] = ""
        target["weight_to"] = ""

    warn_tasks = [
        {
            "task_id": f"warn-{row.company_pid}",
            "company_pid": row.company_pid,
            "batch_id": "2026-11-22-post-switch",
            "status": "open",
        }
        for row in changes
        if band_for(score_company(row, WEIGHTS_V4["weights"]), DEFAULT_BANDS) == "churn_warning"
    ]

    write_json(fixtures / "weights-v3.json", WEIGHTS_V3)
    write_json(fixtures / "weights-v4.json", WEIGHTS_V4)
    write_json(
        fixtures / "config-pre.json",
        {"active_version": "v3", "bands": DEFAULT_BANDS, "asof": "2026-11-22"},
    )
    write_json(
        fixtures / "config-post.json",
        {"active_version": "v4", "bands": DEFAULT_BANDS, "asof": "2026-11-22"},
    )
    write_json(fixtures / "companies.json", companies)
    write_json(fixtures / "warn_tasks.json", {"tasks": warn_tasks})
    (fixtures / "company_names.txt").write_text("\n".join(NAMES) + "\n", encoding="utf-8")
    write_csv(fixtures / "actual.csv", actual)
    write_csv(fixtures / "negative_actual.csv", negative)
    write_json(
        fixtures / "manifest.json",
        {
            "companies": len(companies),
            "actual_rows": len(actual),
            "warn_tasks": len(warn_tasks),
            "names": len(NAMES),
            "bands": DEFAULT_BANDS,
            "weights_from": WEIGHTS_V3["weights"],
            "weights_to": WEIGHTS_V4["weights"],
        },
    )
    print(
        f"stub written: companies={len(companies)} actual={len(actual)} "
        f"changes={len(changes)} warn_tasks={len(warn_tasks)} names={len(NAMES)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
