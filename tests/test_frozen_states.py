from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _counts(rows: list[dict[str, str]]) -> dict[str, int]:
    result = {"renewed": 0, "churned": 0}
    for row in rows:
        if row["state"] in result:
            result[row["state"]] += 1
    return result


def test_frozen_counts_and_states_survive_switch(cli, pre_out, tmp_path):
    companies = json.loads((ROOT / "fixtures" / "companies.json").read_text(encoding="utf-8"))
    baseline = _counts(companies)
    with (ROOT / "fixtures" / "actual.csv").open(encoding="utf-8", newline="") as handle:
        actual = list(csv.DictReader(handle))
    assert _counts(actual) == baseline
    baseline_states = {row["company_pid"]: row["state"] for row in companies if row["state"] in ("renewed", "churned")}
    actual_states = {row["company_pid"]: row["state"] for row in actual if row["company_pid"] in baseline_states}
    assert actual_states == baseline_states

    out = tmp_path / "post"
    result = cli(
        "verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "post",
        "--actual", str(ROOT / "fixtures" / "actual.csv"),
        "--estimate", str(pre_out / "estimate.csv"), "--out", str(out),
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads((out / "compare.json").read_text(encoding="utf-8"))
    assert payload["frozen_counts"] == {"baseline": baseline, "actual": baseline}
    assert payload["frozen_counts_ok"] is True
    assert payload["frozen_state_errors"] == []


def test_tampered_frozen_status_fails(cli, pre_out, tmp_path):
    with (ROOT / "fixtures" / "actual.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        if row["state"] == "renewed":
            row["state"] = "active"
            row["reason"] = ""
            row["weight_from"] = ""
            row["weight_to"] = ""
            break
    actual = tmp_path / "actual_bad_frozen.csv"
    with actual.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["company_pid", "state", "score", "reason", "weight_from", "weight_to"],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    out = tmp_path / "post"
    result = cli(
        "verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "post",
        "--actual", str(actual), "--estimate", str(pre_out / "estimate.csv"), "--out", str(out),
    )
    assert result.returncode == 2, result.stderr
    payload = json.loads((out / "compare.json").read_text(encoding="utf-8"))
    assert payload["frozen_state_errors"]
    assert payload["frozen_counts_ok"] is False
