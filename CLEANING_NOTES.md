# Phase 2 Cleaning Notes — Sector Financial Intelligence Platform

This file documents every judgment call made while turning raw SEC EDGAR
XBRL data into clean, analysis-ready financial statement tables. The goal
is that anyone reviewing this project — a hiring manager, an interviewer,
or future-me — can see exactly *why* a number is what it is, without
re-deriving the logic from source code.

---

## 1. Annual Value Resolution (the core problem)

EDGAR's `companyfacts` API returns every datapoint a company has ever
reported under a given XBRL tag — including quarterly figures and
prior-year comparatives, all sometimes labeled with the same fiscal year.
A single 10-K filing can contain 5-9 different datapoints stamped
`fy=2019`, only one of which is the true annual total.

**Rule applied** (implemented in `src/xbrl_resolver.py`):
1. Only consider `form == "10-K"` datapoints (annual filings, not 10-Q).
2. Only consider datapoints whose period spans roughly 330-380 days
   (filters out quarterly and half-year chunks).
3. Among the candidates that pass #1 and #2, take the one whose period
   **ends most recently** — a company's real fiscal year is always the
   most recent 12-month period being reported, never an older comparative
   that happens to also span ~365 days.
4. If multiple datapoints share that same period-end (e.g. a value as
   originally reported, vs. the same period repeated as a comparative in
   a later year's 10-K), prefer the **earliest filed date** — i.e. the
   value as originally reported, not a later restatement.

**Verified against:** Apple Inc. (AAPL), FY2019–FY2023 revenue, cross-checked
against publicly known annual figures. All five years resolved correctly
after an initial bug (span-length alone was not a sufficient filter — see
git history / conversation log for the specific failure case caught during
testing).

---

## 2. XBRL Tag Inconsistency Across Companies

Companies don't all use the same XBRL concept tag for the same line item.
For example, AAPL and GOOGL both use
`RevenueFromContractWithCustomerExcludingAssessedTax` for revenue, but some
companies use the legacy `Revenues` or `SalesRevenueNet` tags instead
(more common in pre-2018 filings, before ASC 606 took effect — though some
companies still populate these alongside the newer tag).

**Rule applied:** `config/xbrl_tag_map.yaml` defines a *priority-ordered
list* of acceptable tags per line item. The resolver tries each tag in
order and uses the first one with a valid annual datapoint for the target
fiscal year. The tag actually used is recorded in the `source_tag` field
of every resolved value — this is our audit trail.

---

## 3. Fallback Policy for Missing Line Items (Derived Metrics)

Some companies don't directly report every line item we want, even though
the underlying information is reconstructable from other reported figures.

**Current fallback rules:**

| Line Item | Direct Tag Tried First | Fallback Formula (if direct tag missing) |
|---|---|---|
| `gross_profit` | `GrossProfit` | `total_revenue - cost_of_revenue` |
| `operating_income` | `OperatingIncomeLoss` | `gross_profit - research_and_development_expense - sga_expense` |

**Policy:**
- A fallback only fires when the **direct tag is completely unavailable**
  for that company-year — never to override a real reported figure, even
  if the computed version would differ slightly (e.g. due to non-GAAP
  adjustments a company makes when presenting `GrossProfit` directly).
- A computed fallback value is recorded with `source_tag` set to a
  descriptive string starting with `"COMPUTED:"` (e.g.
  `"COMPUTED: total_revenue - cost_of_revenue"`), never disguised as a
  directly-reported tag name. Anyone reading the output data can instantly
  tell the difference between a number the company reported and a number
  we calculated.
- If a fallback's own required inputs are ALSO missing, we do not chain
  further fallbacks or guess. The value is left as `None` and logged as a
  genuine data gap in the cleaning run's summary output — a missing value
  that's visibly missing is far safer than a silently wrong one.
- For `operating_income` specifically: this formula only captures R&D and
  SG&A as operating expenses. If a company reports OTHER material
  operating expense line items we are not separately tracking (e.g.
  restructuring charges, impairments classified as operating), the
  computed fallback will OVERSTATE operating income relative to what the
  company would have reported directly. This is a known, accepted
  limitation of the fallback — it only fires when the direct tag is
  missing, and a logged `COMPUTED` flag lets us audit affected rows later.

**Line items we deliberately did NOT add a fallback for, and why:**

| Line Item | Why no fallback |
|---|---|
| `total_debt_long_term` | No clean derivation exists from other tracked line items. `total_liabilities - current_liabilities` would include deferred tax liabilities, pension obligations, and lease liabilities — not just debt. A formula here would produce a plausible-looking but materially wrong number, which is worse than a logged gap. |
| `capital_expenditures` | Not derivable from any other line item we track. Flagged as a known risk to Free Cash Flow calculations (`operating_cash_flow - capex`) in later phases — if a company is missing this tag, FCF will be unavailable for them, and that should be visible, not silently estimated. |

*(This table will grow as more fallback rules are added in later steps of
Phase 2 — e.g. potential fallbacks for `free_cash_flow` itself, which may
warrant its own dedicated treatment once we reach KPI design in Phase 4.)*

---

## 4. Open Items / Not Yet Addressed

- Fiscal year-end differences across companies (not all 15 companies have
  a December fiscal year-end) — to be documented here once addressed.
- Stock-based compensation treatment consistency across companies — flagged
  for later review, not yet resolved.
- Lease accounting (ASC 842) comparability — flagged for later review.

**Residual gap, investigated and confirmed genuine (not a bug):** after
adding this fallback, AMZN and INTC STILL show total_liabilities as
MISSING for several years. Traced directly: AMZN's LiabilitiesNoncurrent
tag has exactly ONE datapoint in its entire reporting history - fiscal
year 2011, fourteen years before our FY2019-2023 window. Amazon evidently
stopped using this specific XBRL tag after 2011, likely restructuring how
they present balance sheet liabilities in later filings. The fallback
correctly attempted resolution, correctly found no applicable data, and
correctly returned a logged MISSING rather than fabricating a number
(e.g. assuming zero noncurrent liabilities, which would have understated
Amazon's true total liabilities). This is the documented fallback policy
working exactly as intended on a genuine data gap, not a defect to fix.
