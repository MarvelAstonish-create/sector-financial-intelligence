from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Optional


MIN_ANNUAL_SPAN_DAYS = 330
MAX_ANNUAL_SPAN_DAYS = 380


@dataclass
class ResolvedFact:
    fiscal_year: int
    value: float
    source_tag: str
    period_start: str
    period_end: str
    filed_date: str
    accession_number: str


def _parse_date(date_str):
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _is_full_year_span(start_str, end_str):
    start = _parse_date(start_str)
    end = _parse_date(end_str)
    if start is None or end is None:
        return False
    span_days = (end - start).days
    return MIN_ANNUAL_SPAN_DAYS <= span_days <= MAX_ANNUAL_SPAN_DAYS


def _resolve_duration_fact(usd_units, fiscal_year):
    candidates = [
        u for u in usd_units
        if u.get("form") == "10-K"
        and u.get("fy") == fiscal_year
        and _is_full_year_span(u.get("start", ""), u.get("end", ""))
    ]

    if not candidates:
        return None

    best = max(
        candidates,
        key=lambda u: (_parse_date(u.get("end", "")) or date.min, u.get("filed", "")),
    )
    latest_end = best.get("end", "")
    same_period = [u for u in candidates if u.get("end", "") == latest_end]
    return min(same_period, key=lambda u: u.get("filed", "9999-99-99"))


def _resolve_instant_fact(usd_units, fiscal_year):
    candidates = [
        u for u in usd_units
        if u.get("form") == "10-K"
        and u.get("fy") == fiscal_year
    ]

    if not candidates:
        return None

    best = max(
        candidates,
        key=lambda u: (_parse_date(u.get("end", "")) or date.min, u.get("filed", "")),
    )
    latest_end = best.get("end", "")
    same_period = [u for u in candidates if u.get("end", "") == latest_end]
    return min(same_period, key=lambda u: u.get("filed", "9999-99-99"))


def resolve_annual_fact(company_facts, tag_candidates, fiscal_year, fact_type="duration"):
    gaap_facts = company_facts.get("facts", {}).get("us-gaap", {})

    for tag in tag_candidates:
        tag_data = gaap_facts.get(tag)
        if not tag_data:
            continue

        usd_units = tag_data.get("units", {}).get("USD", [])

        if fact_type == "instant":
            best = _resolve_instant_fact(usd_units, fiscal_year)
        else:
            best = _resolve_duration_fact(usd_units, fiscal_year)

        if best is None:
            continue

        return ResolvedFact(
            fiscal_year=fiscal_year,
            value=float(best["val"]),
            source_tag=tag,
            period_start=best.get("start", ""),
            period_end=best.get("end", ""),
            filed_date=best.get("filed", ""),
            accession_number=best.get("accn", ""),
        )

    return None
