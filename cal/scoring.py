"""Health-score computation, banding, and pre-switch estimation."""

from __future__ import annotations

from cal.models import (
    Company,
    ChangeRow,
    FROZEN_STATUSES,
    direction_for,
    validate_status,
)


def score_company(company: Company, weights: dict[str, float]) -> float:
    total = sum(weights[key] * company.signals[key] for key in weights)
    return round(total + 1e-9, 2)


def band_for(score: float, bands: dict[str, float]) -> str:
    if score >= bands["active_min"]:
        return "active"
    if score >= bands["silent_min"]:
        return "silent"
    return "churn_warning"


def estimate_changes(
    companies: list[Company],
    weights_from: dict[str, float],
    weights_to: dict[str, float],
    bands: dict[str, float],
    version_from: str,
    version_to: str,
) -> tuple[list[ChangeRow], list[dict[str, object]]]:
    """Return (non-frozen changes, frozen companies whose band would move)."""
    changes: list[ChangeRow] = []
    frozen_would_change: list[dict[str, object]] = []
    for company in sorted(companies, key=lambda item: item.company_pid):
        old_score = score_company(company, weights_from)
        new_score = score_company(company, weights_to)
        if company.state in FROZEN_STATUSES:
            old_band = band_for(old_score, bands)
            new_band = band_for(new_score, bands)
            if old_band != new_band:
                frozen_would_change.append(
                    {
                        "company_pid": company.company_pid,
                        "locked_status": company.state,
                        "band_from": old_band,
                        "band_to": new_band,
                        "old_score": old_score,
                        "new_score": new_score,
                    }
                )
            continue
        validate_status(company.state)
        new_status = band_for(new_score, bands)
        if company.state == new_status:
            continue
        direction = direction_for(company.state, new_status)
        if direction is None:
            raise ValueError(
                f"unsupported transition {company.state}->{new_status} for {company.company_pid}"
            )
        changes.append(
            ChangeRow(
                company_pid=company.company_pid,
                old_status=company.state,
                new_status=new_status,
                old_score=old_score,
                new_score=new_score,
                manager_id=company.manager_id,
                key_member=company.key_member,
                direction=direction,
                weight_from=version_from,
                weight_to=version_to,
            )
        )
    return changes, frozen_would_change
