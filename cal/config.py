"""Configuration, weight files, and CRM fixture loading."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from cal.models import Company, WEIGHT_KEYS

DEFAULT_BANDS = {"active_min": 75.0, "silent_min": 60.0}


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _as_float(raw: object, field: str) -> float:
    if isinstance(raw, bool):
        raise ValueError(f"{field} must be numeric, got {raw!r}")
    try:
        return float(raw)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field} must be numeric, got {raw!r}") from exc


def parse_bool(value: object, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("true", "1", "yes", "y", "是"):
            return True
        if text in ("false", "0", "no", "n", "否", ""):
            return False
    raise ValueError(f"{field} must be a boolean, got {value!r}")


def load_weights(path: str | Path) -> tuple[str, dict[str, float]]:
    document = load_json(path)
    if not isinstance(document, dict):
        raise ValueError(f"weight file must be an object: {path}")
    version = str(document.get("version") or "")
    weights = document.get("weights") or document
    if not isinstance(weights, dict):
        raise ValueError(f"weight file has no weights object: {path}")
    if not version:
        raise ValueError(f"weight file has no version: {path}")
    missing = [key for key in WEIGHT_KEYS if key not in weights]
    if missing:
        raise ValueError(f"weight file {path} missing keys: {missing}")
    cleaned = {key: _as_float(weights[key], f"weight {key} in {path}") for key in WEIGHT_KEYS}
    for key, value in cleaned.items():
        if not math.isfinite(value):
            raise ValueError(f"weight {key} in {path} is not finite: {value}")
    total = sum(cleaned.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"weights in {path} sum to {total}, expected 1.0")
    return version, cleaned


def load_config(path: str | Path) -> dict[str, Any]:
    document = load_json(path)
    if not isinstance(document, dict):
        raise ValueError(f"config must be an object: {path}")
    bands = dict(DEFAULT_BANDS)
    bands.update(document.get("bands") or {})
    active_min = _as_float(bands["active_min"], "bands.active_min")
    silent_min = _as_float(bands["silent_min"], "bands.silent_min")
    if not (math.isfinite(active_min) and math.isfinite(silent_min)):
        raise ValueError("active_min and silent_min must be finite")
    if active_min <= silent_min:
        raise ValueError("active_min must be greater than silent_min")
    return {
        "active_version": str(document.get("active_version") or ""),
        "bands": {"active_min": active_min, "silent_min": silent_min},
        "asof": str(document.get("asof") or ""),
        "raw": document,
    }


def companies_from_rows(rows: list[dict], source: str | Path = "<memory>") -> list[Company]:
    """Validate already-normalized company rows (internal snapshot shape)."""
    companies: list[Company] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"company row {index} must be an object")
        raw_pid = row.get("company_pid")
        if isinstance(raw_pid, bool) or not isinstance(raw_pid, (str, int)):
            raise ValueError(f"company row {index} has invalid company_pid: {raw_pid!r}")
        pid = str(raw_pid).strip()
        if not pid:
            raise ValueError(f"company row {index} has no company_pid")
        if pid in seen:
            raise ValueError(f"duplicate company_pid: {pid}")
        seen.add(pid)
        signals = row.get("signals") or {}
        missing = [key for key in WEIGHT_KEYS if key not in signals]
        if missing:
            raise ValueError(f"{pid} missing signals: {missing}")
        state = str(row.get("state") or "").strip()
        if state not in ("active", "silent", "churn_warning", "renewed", "churned"):
            raise ValueError(f"{pid} has unsupported state: {state!r}")
        clean_signals: dict[str, float] = {}
        for key in WEIGHT_KEYS:
            value = _as_float(signals[key], f"{pid} signal {key}")
            if not math.isfinite(value):
                raise ValueError(f"{pid} signal {key} is not finite: {value}")
            clean_signals[key] = value
        companies.append(
            Company(
                company_pid=pid,
                company_name=str(row.get("company_name") or pid),
                state=state,
                club_id=str(row.get("club_id") or ""),
                manager_id=str(row.get("manager_id") or ""),
                key_member=parse_bool(row.get("key_member", False), "key_member"),
                signals=clean_signals,
            )
        )
    return companies


def load_companies(path: str | Path) -> list[Company]:
    document = load_json(path)
    rows = document.get("companies") if isinstance(document, dict) else document
    if not isinstance(rows, list):
        raise ValueError(f"company file must be a list or contain 'companies': {path}")
    return companies_from_rows(rows, source=path)