"""Domain models and shared constants for health-score switch verification."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

STATUSES = ("active", "silent", "churn_warning", "renewed", "churned")
FROZEN_STATUSES = frozenset({"renewed", "churned"})
DIRECTION_LABELS = {
    "active_to_silent": "活跃→沉默",
    "silent_to_active": "沉默→活跃",
    "enter_churn_warning": "进入流失预警",
    "exit_churn_warning": "退出流失预警",
}
REASON = "权重版本切换"
WEIGHT_KEYS = ("activity", "transaction", "engagement", "tenure")


@dataclass(frozen=True)
class Company:
    company_pid: str
    company_name: str
    state: str
    club_id: str
    manager_id: str
    key_member: bool
    signals: dict[str, float]


@dataclass
class ChangeRow:
    company_pid: str
    old_status: str
    new_status: str
    old_score: float
    new_score: float
    manager_id: str
    key_member: bool
    direction: str
    reason: str = REASON
    weight_from: str = ""
    weight_to: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "company_pid": self.company_pid,
            "old_status": self.old_status,
            "new_status": self.new_status,
            "old_score": self.old_score,
            "new_score": self.new_score,
            "manager_id": self.manager_id,
            "key_member": self.key_member,
            "direction": self.direction,
            "reason": self.reason,
            "weight_from": self.weight_from,
            "weight_to": self.weight_to,
        }


def direction_for(old_status: str, new_status: str) -> str | None:
    if old_status == new_status:
        return None
    if old_status == "active" and new_status == "silent":
        return "active_to_silent"
    if old_status == "silent" and new_status == "active":
        return "silent_to_active"
    if new_status == "churn_warning":
        return "enter_churn_warning"
    if old_status == "churn_warning":
        return "exit_churn_warning"
    return None


def validate_status(status: str) -> None:
    if status not in STATUSES:
        raise ValueError(f"unsupported lifecycle status: {status!r}")
