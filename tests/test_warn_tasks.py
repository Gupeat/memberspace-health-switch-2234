from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_missing_warn_task_fails(cli, pre_out, tmp_path):
    document = json.loads((ROOT / "fixtures" / "warn_tasks.json").read_text(encoding="utf-8"))
    tasks = document["tasks"]
    removed = tasks[0]["company_pid"]
    document["tasks"] = tasks[1:]
    warn_path = tmp_path / "warn_tasks_missing.json"
    warn_path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    out = tmp_path / "post"
    result = cli(
        "verify-health-switch", "--from", "v3", "--to", "v4", "--mode", "post",
        "--actual", str(ROOT / "fixtures" / "actual.csv"),
        "--estimate", str(pre_out / "estimate.csv"),
        "--warn-tasks", str(warn_path), "--out", str(out),
    )
    assert result.returncode == 2, result.stderr
    payload = json.loads((out / "compare.json").read_text(encoding="utf-8"))
    assert payload["warn_task_errors"] == [{"company_pid": removed, "problem": "missing_warn_task"}]
    assert payload["passed"] is False
