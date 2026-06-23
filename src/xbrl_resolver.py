"""
xbrl_resolver.py
----------------
Resolves a single, authoritative annual value for a given XBRL concept tag,
company, and fiscal year — from EDGAR's companyfacts payload, which contains
MANY overlapping datapoints per fiscal year (quarterly chunks, prior-year
comparatives, and the true annual figure all stamped with the same `fy`).

THE PROBLEM THIS SOLVES (verified against real AAPL data):
For AAPL's tag 'RevenueFromContractWithCustomerExcludingAssessedTax', the
single 10-K filing for FY2019 (accn 0000320193-19-000119) contains NINE
separate start/end date ranges all labeled fy=2019 — eight of them are
quarterly figures or prior-year comparatives, and only ONE is the true
~365-day annual total ($260,174,000,000). Naively taking "any row where
fy == 2019" risks silently grabbing a single quarter instead of the full
year, which would corrupt every downstream ratio without raising an error.

THE RULE WE APPLY (in order):
  1. Only consider datapoints from form == '10-K' (annual filings, not 10-Q).
  2. Only consider datapoints whose date span (end - start) falls within
     330-380 days — this is what actually distinguishes "the full fiscal
     year" from a quarter or a half-year chunk, since `fp == 'FY'` alone is
     NOT reliable (we observed quarter-length spans mislabeled fp='FY' in
     real data).
  3. Among the candidates that pass #1 and #2 for a given fiscal year, take
     the one with the EARLIEST `filed` date. This means we prefer the value
     AS ORIGINALLY REPORTED in that year's own 10-K, not a later restated
     comparative figure appearing in a subsequent year's filing. This is a
     deliberate, documented judgment call — restated figures are a valid
     alternative choice, but mixing originally-reported and restated values
     inconsistently across companies would make peer comparison unreliable.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Optional


MIN_ANNUAL_SPAN_DAYS = 330
MAX_ANNUAL_SPAN_DAYS = 380


@dataclass
class ResolvedFact:
    """A single resolved annual value, with full audit trail."""
    fiscal_year: int
    value: float
    source_tag: str
    period_start: str
    period_end: str
    filed_date: str
    accession_number: str


def _parse_date(date_str: str) -> Optional[date]:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _is_full_year_span(start_str: str, end_str: str) -> bool:
    """Check whether a start/end date pair spans roughly one fiscal year."""
    start = _parse_date(start_str)
    end = _parse_date(end_str)
    if start is None or end is None:
        return False
    span_days = (end - start).days
    return MIN_ANNUAL_SPAN_DAYS <= span_days <= MAX_ANNUAL_SPAN_DAYS


def resolve_annual_fact(
    company_facts: dict[str, Any],
    tag_candidates: list[str],
    fiscal_year: int,
) -> Optional[ResolvedFact]:
    """
    Find the single authoritative annual value for one line item, for one
    company, for one fiscal year — trying each candidate tag in priority
    order until one succeeds.

    Parameters
    ----------
    company_facts : dict
        The full parsed JSON payload for one company (as saved by
        extract_filings.py), i.e. the dict with top-level keys like
        'cik', 'entityName', 'facts'.
    tag_candidates : list[str]
        XBRL tags to try, in priority order (from xbrl_tag_map.yaml).
    fiscal_year : int
        The fiscal year we want a value for (e.g. 2021).

    Returns
    -------
    ResolvedFact or None
        None means NO candidate tag had a valid full-year datapoint for
        this fiscal year — a genuine data gap that the caller should log,
        not silently skip.
    """
    gaap_facts = company_facts.get("facts", {}).get("us-gaap", {})

    for tag in tag_candidates:
        tag_data = gaap_facts.get(tag)
        if not tag_data:
            continue  # this company doesn't use this tag at all — try the next

        usd_units = tag_data.get("units", {}).get("USD", [])

        # Filter to: annual filings only, for our target fiscal year, with a
        # date span that actually looks like a full year (not a quarter).
        candidates = [
            u for u in usd_units
            if u.get("form") == "10-K"
            and u.get("fy") == fiscal_year
            and _is_full_year_span(u.get("start", ""), u.get("end", ""))
        ]

        if not candidates:
            continue  # this tag exists but has no valid annual datapoint for this year — try next tag

        # IMPORTANT: a single 10-K can legitimately disclose MULTIPLE
        # full-year-shaped spans under the same fy label — e.g. the current
        # fiscal year (2018-09-30 to 2019-09-28) AND the prior comparative
        # year (2016-09-25 to 2017-09-30), since prior-year comparatives are
        # routinely included in a 10-K. Both pass the span-length check.
        # The genuine fiscal year for THIS filing is the one whose period
        # ends MOST RECENTLY — a company's fiscal year is always the latest
        # 12-month period it's reporting on, never an older comparative.
        best = max(
            candidates,
            key=lambda u: (_parse_date(u.get("end", "")) or date.min, u.get("filed", "")),
        )
        # Among candidates sharing that same (latest) end date — e.g. the
        # value as originally reported vs. a later restated repeat of the
        # exact same period — prefer the EARLIEST filed date, i.e. the
        # value as originally reported, not a later restatement.
        latest_end = best.get("end", "")
        same_period = [u for u in candidates if u.get("end", "") == latest_end]
        best = min(same_period, key=lambda u: u.get("filed", "9999-99-99"))

        return ResolvedFact(
            fiscal_year=fiscal_year,
            value=float(best["val"]),
            source_tag=tag,
            period_start=best.get("start", ""),
            period_end=best.get("end", ""),
            filed_date=best.get("filed", ""),
            accession_number=best.get("accn", ""),
        )

    return None  # exhausted every candidate tag with no valid result
