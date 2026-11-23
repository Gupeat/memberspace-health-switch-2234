"""CRM adapter boundary.

The sample CRM source is a JSON snapshot with fields documented in
fixtures/companies.json. A production adapter should call the S2-CRM read API
and map each company to the same shape; the verifier never needs to know the
upstream transport.
"""

from __future__ import annotations

from pathlib import Path

from cal.config import companies_from_rows, load_json, parse_bool
from cal.models import Company

SIGNAL_MAP = {
    "activity_score": "activity",
    "transaction_score": "transaction",
    "engagement_score": "engagement",
    "tenure_score": "tenure",
}
SIGNAL_TARGETS = tuple(SIGNAL_MAP.values())


def _is_internal_snapshot(record: dict) -> bool:
    signals = record.get("signals")
    return (
        "company_pid" in record
        and isinstance(signals, dict)
        and all(key in signals for key in SIGNAL_TARGETS)
        and not any(key in record for key in SIGNAL_MAP)
    )


def _normalize_record(record: dict) -> dict:
    # Internal snapshot rows already carry company_pid + the four target
    # signals; CRM-shaped rows carry pid/lifecycle_status/*_score and must go
    # through the explicit mapping boundary. Anything else is rejected by it.
    if not isinstance(record, dict):
        raise ValueError(f"company record must be an object, got {type(record).__name__}")
    if _is_internal_snapshot(record):
        return record
    return map_crm_record(record)


def load_companies_from_snapshot(path: str | Path) -> list[Company]:
    document = load_json(path)
    rows = document.get("companies") if isinstance(document, dict) else document
    if not isinstance(rows, list):
        raise ValueError(f"company file must be a list or contain 'companies': {path}")
    normalized = [_normalize_record(row) for row in rows]
    return companies_from_rows(normalized, source=path)


def map_crm_record(record: dict) -> dict:
    if not isinstance(record, dict):
        raise ValueError(f"CRM record must be an object, got {type(record).__name__}")
    signals = record.get("signals")
    if signals is None:
        signals = {}
    if not isinstance(signals, dict):
        raise ValueError("signals must be an object")
    mapped_signals: dict[str, float] = {}
    for source, target in SIGNAL_MAP.items():
        if source in signals:
            raw = signals[source]
        elif target in signals:
            raw = signals[target]
        elif source in record:
            raw = record[source]
        else:
            raise ValueError(f"CRM record is missing {source}")
        try:
            value = float(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"CRM {source} must be numeric, got {raw!r}") from exc
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError(f"CRM {source} must be finite, got {raw!r}")
        mapped_signals[target] = value
    return {
        "company_pid": record.get("company_pid") or record.get("pid"),
        "company_name": record.get("company_name") or record.get("name"),
        "state": record.get("state") or record.get("lifecycle_status"),
        "club_id": record.get("club_id"),
        "manager_id": record.get("manager_id") or record.get("owner_manager_id"),
        "key_member": parse_bool(record.get("key_member"), "key_member"),
        "signals": mapped_signals,
    }