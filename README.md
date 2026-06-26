# Sector Financial Intelligence Platform

A multi-company financial analytics platform built on real SEC EDGAR filing data — covering 15 technology companies across FY2019–2023. Built end-to-end: Python ETL → PostgreSQL data warehouse → semantic layer → SQL analytics layer, with Tableau dashboards and AI-assisted insights in progress.

**Status: Work in progress.** Phases 0–4 are complete; a June 2026 audit fixed a real defect in the peer-ranking SQL and added a semantic layer for canonical metric definitions — see `CLEANING_NOTES.md` for details. See the Roadmap below for what's done and what's next.

---

## Why this project exists

Most portfolio analytics projects start from a pre-cleaned CSV. This one doesn't. It pulls financial statement data directly from the SEC's public EDGAR API — the same regulatory source professional analysts use — and works through the real mess that comes with it: inconsistent XBRL tagging across companies, quarterly figures mixed in with annual totals, and genuine gaps where companies simply don't report a line item the way others do.

The goal: build something closer to what a financial analyst actually does — make defensible judgment calls about messy data, document every one of them, and only then start answering business questions.

## What's in scope

- **15 technology companies**: AAPL, MSFT, GOOGL, AMZN, META, NVDA, ORCL, CRM, ADBE, INTC, CSCO, IBM, AVGO, TXN, QCOM
- **5 fiscal years**: 2019–2023
- **3 financial statements**: Income Statement, Balance Sheet, Cash Flow Statement
- **Source**: SEC EDGAR `companyfacts` API (real regulatory filings, not a third-party dataset)

## Architecture

```
SEC EDGAR API
      │
      ▼
Python ETL (src/)
  ├─ extract_filings.py      → pulls raw XBRL facts per company
  ├─ xbrl_resolver.py        → resolves the TRUE annual value from
  │                            messy duration/instant XBRL facts
  ├─ derived_metrics.py      → documented fallback formulas for
  │                            line items some companies don't report
  ├─ normalize_financials.py → batch-runs resolution across all
  │                            companies/years, writes clean CSVs
  └─ load_to_postgres.py     → loads cleaned data into the warehouse
      │
      ▼
PostgreSQL (sql/schema.sql)
  Star schema: dim_company, dim_line_item, fact_financials
      │
      ▼
Semantic Layer (sql/semantic/semantic_layer.sql)
  Canonical metric definitions: margins, peer comparisons, growth rates
     |
     v

SQL Analysis Layer (sql/queries/)
  ├─ 01_cash_flow_analysis.sql   → FCF, FCF margin, cash flow quality
  ├─ 02_core_ratios.sql          → profitability, returns, liquidity, leverage
  ├─ 03_trend_analysis.sql       → YoY growth, 5-year CAGR
  └─ 04_peer_ranking.sql         → subsector median, percentile rank
      │
      ▼
Tableau dashboards (in progress)
```

## What makes the data trustworthy

Every line item resolved from EDGAR's raw data carries a `source_tag` audit trail showing exactly where it came from:
- A real XBRL tag name (e.g. `RevenueFromContractWithCustomerExcludingAssessedTax`) — directly reported by the company
- `COMPUTED: ...` — a documented fallback formula, used only when no direct tag exists
- `MISSING` — a genuine, honestly-flagged data gap, never silently guessed or defaulted to zero

Every judgment call behind these decisions — including real bugs found and fixed along the way — is written up in [`CLEANING_NOTES.md`](./CLEANING_NOTES.md). A few highlights from that log:
- A bug that caused every balance sheet value to silently fail for every company, traced to the difference between "point in time" and "over a period" financial facts
- Discovering that Amazon stopped using a specific reporting tag back in 2011 — a genuine data limitation, not a code defect
- Two real PostgreSQL quirks hit (and documented) while building peer-ranking SQL, plus a third found in a later audit: `PERCENT_RANK()` was ranking `NULL` gross-margin values as the *top* percentile instead of excluding them - fixed in `04_peer_ranking.sql` (June 2026)
- Metric logic (margins, peer comparisons, growth rates) consolidated into a single semantic layer (`sql/semantic/semantic_layer.sql`), so each calculation is defined once instead of being reimplemented per query

## Roadmap

| Phase | Focus | Status |
|---|---|---|
| 0 | Scoping & architecture | Done |
| 1 | EDGAR data ingestion | Done |
| 2 | Data cleaning & normalization | Done |
| 3 | PostgreSQL star schema & loader | Done |
| 4 | SQL analysis layer | Done* |
| 5 | Python statistical analysis & forecasting | Planned |
| 6 | AI-assisted insight generation, NL querying | Planned |
| 7 | Tableau dashboards | In progress |
| 8 | Business communication (exec summary) | Planned |
| 9 | Portfolio packaging & polish | Planned |

*Extended June 2026 with a semantic layer (`sql/semantic/`) defining canonical metrics once. The Phase 4 queries above still contain their own duplicate logic, pending a refactor to consume it directly.

## Tech stack

Python · PostgreSQL · SQL (window functions, CTEs, ordered-set aggregates) · Tableau Public

## Running this yourself

1. Set up `config/settings.yaml` with your own SEC EDGAR User-Agent (required by SEC, format: `YourApp/1.0 your-email@example.com`)
2. `pip install -r requirements.txt`
3. `python3 src/extract_filings.py` — pulls raw data from EDGAR
4. `python3 src/normalize_financials.py` — cleans and resolves into CSVs
5. Create a PostgreSQL database, run `sql/schema.sql`
6. `python3 src/load_to_postgres.py` — loads cleaned data into PostgreSQL
7. Run any query in `sql/queries/` against the database

---

*Built by Marvel Astonish — Chartered Accountant transitioning into data analytics, applying financial-statement judgment to real-world data engineering.*
