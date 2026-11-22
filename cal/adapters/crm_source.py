"""CRM adapter boundary.

The sample CRM source is a JSON snapshot with fields documented in
fixtures/companies.json. A production adapter should call the S2-CRM read API
and map each company to the same shape; the verifier never needs to know the
upstream transport.
"""

from __future__ import annotations

from pathlib import Path

from cal.config import load_companies
from cal.models import Company

SIGNAL_MAP = {
    "activity_score": "activity",
    "transaction_score": "transaction",
    "engagement_score": "engagement",
    "tenure_score": "tenure",
}


def load_companies_from_snapshot(path: str | Path) -> list[Company]:
    return load_companies(path)


def map_crm_record(record: dict) -> dict:
    signals = record.get("signals") or {}
    mapped = {
        "company_pid": record.get("company_pid") or record.get("pid"),
        "company_name": record.get("company_name") or record.get("name"),
        "state": record.get("state") or record.get("lifecycle_status"),
        "club_id": record.get("club_id"),
        "manager_id": record.get("manager_id") or record.get("owner_manager_id"),
        "key_member": bool(record.get("key_member", False)),
        "signals": {
            target: float(signals.get(source, record.get(source, 0)))
            for source, target in SIGNAL_MAP.items()
        },
    }
    return mapped
