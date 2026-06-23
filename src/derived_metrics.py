"""
derived_metrics.py
-------------------
Applies DOCUMENTED fallback calculations for line items that a company
doesn't report directly via any XBRL tag we tried.

WHY THIS IS ITS OWN MODULE (separate from xbrl_resolver.py):
xbrl_resolver.py's job is narrow and honest: "find the value a company
actually reported, or tell me it's not there." It should never silently
invent numbers. Computing a derived value (e.g. gross profit from revenue
minus cost of revenue) is a DIFFERENT kind of operation — it's us making a
judgment call, not reading a disclosed fact. Keeping that logic in a
separate module makes the distinction obvious in the codebase itself, not
just in a comment.

EVERY FALLBACK RULE HERE MUST HAVE A MATCHING ENTRY IN CLEANING_NOTES.md.
If you add a fallback rule to this file without documenting it there, the
project's documentation has silently gone stale — treat that as a bug.

HOW source_tag WORKS FOR COMPUTED VALUES:
A directly-resolved value's source_tag is a real XBRL tag name (e.g.
"GrossProfit"). A computed fallback's source_tag instead starts with the
literal prefix "COMPUTED: " followed by the formula used, e.g.
"COMPUTED: total_revenue - cost_of_revenue". Any downstream consumer of
this data (a SQL query, a Power BI report, a person reading the CSV) can
check for that prefix to distinguish reported-vs-computed values without
needing to consult this code.
"""

from dataclasses import dataclass
from typing import Optional

from xbrl_resolver import ResolvedFact


COMPUTED_TAG_PREFIX = "COMPUTED: "


@dataclass
class ResolvedLineItems:
    """
    A bundle of already-resolved line items for one company-year, used as
    input to fallback calculations. Each field is an Optional[ResolvedFact]
    because not every line item will necessarily be present.
    """
    total_revenue: Optional[ResolvedFact] = None
    cost_of_revenue: Optional[ResolvedFact] = None
    gross_profit: Optional[ResolvedFact] = None
    research_and_development_expense: Optional[ResolvedFact] = None
    sga_expense: Optional[ResolvedFact] = None
    operating_income: Optional[ResolvedFact] = None
    # Additional fields will be added here as more fallback rules are
    # introduced (see CLEANING_NOTES.md section 3 for the full policy).


def apply_gross_profit_fallback(items: ResolvedLineItems) -> Optional[ResolvedFact]:
    """
    Fallback rule for gross_profit, per CLEANING_NOTES.md section 3:

        gross_profit = total_revenue - cost_of_revenue

    Only used when items.gross_profit is None (i.e. the GrossProfit XBRL
    tag itself had no valid annual datapoint). If the direct tag WAS
    resolved, this function should not be called at all — the caller is
    responsible for trying the direct tag first and only falling back here
    on a genuine miss.

    Returns None (a real, logged data gap) if total_revenue or
    cost_of_revenue are themselves unavailable — we do not chain fallbacks
    or guess further.
    """
    if items.gross_profit is not None:
        # Defensive check: this function should never be called when a
        # direct value already exists, but if it is, we refuse to override
        # a real reported figure with a computed one. See CLEANING_NOTES.md:
        # "never to override a real reported figure."
        return items.gross_profit

    if items.total_revenue is None or items.cost_of_revenue is None:
        return None  # genuine data gap — required inputs are missing too

    if items.total_revenue.fiscal_year != items.cost_of_revenue.fiscal_year:
        # Sanity guard: never combine values from two different fiscal years
        # even if both happen to be non-None. This should not occur in
        # correct usage (both should be resolved for the same fy), but a
        # silent year-mismatch would be a far worse bug than a logged gap.
        return None

    computed_value = items.total_revenue.value - items.cost_of_revenue.value

    return ResolvedFact(
        fiscal_year=items.total_revenue.fiscal_year,
        value=computed_value,
        source_tag=f"{COMPUTED_TAG_PREFIX}total_revenue - cost_of_revenue",
        period_start=items.total_revenue.period_start,
        period_end=items.total_revenue.period_end,
        filed_date=items.total_revenue.filed_date,
        accession_number=items.total_revenue.accession_number,
    )


def apply_operating_income_fallback(items: ResolvedLineItems) -> Optional[ResolvedFact]:
    """
    Fallback rule for operating_income, per CLEANING_NOTES.md section 3:

        operating_income = gross_profit - research_and_development_expense - sga_expense

    Only used when items.operating_income is None (i.e. the
    OperatingIncomeLoss XBRL tag had no valid annual datapoint). As with
    the gross profit fallback, this function refuses to override a real
    reported value and returns None (a genuine, logged gap) if any
    required input is missing — it does not chain fallbacks or guess.

    KNOWN LIMITATION (documented in CLEANING_NOTES.md): this formula only
    subtracts R&D and SG&A. A company with material OTHER operating
    expenses we don't separately track (restructuring, impairments, etc.)
    will have its computed operating_income OVERSTATED relative to what
    the company itself would report. This is an accepted, documented
    tradeoff — the COMPUTED source_tag flag lets us audit affected rows
    later rather than hiding the limitation.
    """
    if items.operating_income is not None:
        # Never override a real reported figure with a computed one.
        return items.operating_income

    required = [items.gross_profit, items.research_and_development_expense, items.sga_expense]
    if any(field is None for field in required):
        return None  # genuine data gap — at least one required input is missing

    fiscal_years = {f.fiscal_year for f in required}
    if len(fiscal_years) != 1:
        # Sanity guard: never combine values from mismatched fiscal years.
        return None

    computed_value = (
        items.gross_profit.value
        - items.research_and_development_expense.value
        - items.sga_expense.value
    )

    return ResolvedFact(
        fiscal_year=items.gross_profit.fiscal_year,
        value=computed_value,
        source_tag=(
            f"{COMPUTED_TAG_PREFIX}gross_profit - "
            f"research_and_development_expense - sga_expense"
        ),
        period_start=items.gross_profit.period_start,
        period_end=items.gross_profit.period_end,
        filed_date=items.gross_profit.filed_date,
        accession_number=items.gross_profit.accession_number,
    )


def is_computed_value(resolved_fact: ResolvedFact) -> bool:
    """
    Convenience check: does this ResolvedFact represent a value WE
    calculated, rather than one the company directly reported?
    Used by downstream code (e.g. the cleaning summary report) to count
    and flag computed values separately from directly-reported ones.
    """
    return resolved_fact.source_tag.startswith(COMPUTED_TAG_PREFIX)
