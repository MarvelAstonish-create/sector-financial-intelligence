-- ============================================================
-- SEMANTIC LAYER
-- Canonical metric definitions, computed once and reused by
-- every downstream consumer (SQL exports, Tableau, future BI).
-- ============================================================

CREATE SCHEMA IF NOT EXISTS semantic;

-- ------------------------------------------------------------
-- 1. Wide pivot of the EAV fact table -> one row per company/year.
--    Replaces the MAX(CASE WHEN...) pivot that was previously
--    duplicated across the 01/03/04 Phase 4 queries.
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW semantic.company_year_financials AS
SELECT
    f.ticker,
    f.fiscal_year,
    MAX(CASE WHEN f.line_item = 'total_revenue' THEN f.value END) AS total_revenue,
    MAX(CASE WHEN f.line_item = 'net_income' THEN f.value END) AS net_income,
    MAX(CASE WHEN f.line_item = 'gross_profit' THEN f.value END) AS gross_profit,
    MAX(CASE WHEN f.line_item = 'cost_of_revenue' THEN f.value END) AS cost_of_revenue,
    MAX(CASE WHEN f.line_item = 'operating_income' THEN f.value END) AS operating_income,
    MAX(CASE WHEN f.line_item = 'research_and_development_expense' THEN f.value END) AS research_and_development_expense,
    MAX(CASE WHEN f.line_item = 'sga_expense' THEN f.value END) AS sga_expense,
    MAX(CASE WHEN f.line_item = 'operating_cash_flow' THEN f.value END) AS operating_cash_flow,
    MAX(CASE WHEN f.line_item = 'capital_expenditures' THEN f.value END) AS capital_expenditures
FROM fact_financials f
GROUP BY f.ticker, f.fiscal_year;

-- ------------------------------------------------------------
-- 2. Canonical derived metrics - one formula per metric.
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW semantic.company_year_metrics AS
WITH base AS (
    SELECT cyf.*, c.company_name, c.subsector
    FROM semantic.company_year_financials cyf
    JOIN dim_company c ON c.ticker = cyf.ticker
)
SELECT
    *,
    gross_profit / NULLIF(total_revenue, 0) AS gross_margin,
    net_income   / NULLIF(total_revenue, 0) AS net_margin,
    (operating_cash_flow - capital_expenditures) AS free_cash_flow,
    (operating_cash_flow - capital_expenditures) / NULLIF(total_revenue, 0) AS fcf_margin,
    operating_cash_flow / NULLIF(net_income, 0) AS cash_flow_quality_ratio,
    (total_revenue - LAG(total_revenue) OVER (PARTITION BY ticker ORDER BY fiscal_year))
        / NULLIF(LAG(total_revenue) OVER (PARTITION BY ticker ORDER BY fiscal_year), 0) AS revenue_yoy_growth,
    (net_income - LAG(net_income) OVER (PARTITION BY ticker ORDER BY fiscal_year))
        / NULLIF(LAG(net_income) OVER (PARTITION BY ticker ORDER BY fiscal_year), 0) AS net_income_yoy_growth,
    (
        POWER(
            NULLIF(LAST_VALUE(total_revenue) OVER (PARTITION BY ticker ORDER BY fiscal_year
                RANGE BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING), 0)
            / NULLIF(FIRST_VALUE(total_revenue) OVER (PARTITION BY ticker ORDER BY fiscal_year
                RANGE BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING), 0),
            1.0 / NULLIF(
                (MAX(fiscal_year) OVER (PARTITION BY ticker)) - (MIN(fiscal_year) OVER (PARTITION BY ticker)),
                0)
        ) - 1
    ) AS revenue_cagr_5yr
FROM base;

-- ------------------------------------------------------------
-- 3. Subsector medians. PERCENTILE_CONT already correctly
--    excludes NULL inputs in Postgres (confirmed against the
--    Oracle case earlier), so no fix needed here - just
--    consolidation into one place.
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW semantic.subsector_medians AS
SELECT
    subsector,
    fiscal_year,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY gross_margin) AS median_gross_margin,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY net_margin) AS median_net_margin,
    COUNT(DISTINCT ticker) AS subsector_company_count
FROM semantic.company_year_metrics
GROUP BY subsector, fiscal_year;

-- ------------------------------------------------------------
-- 4. Peer comparison - both business rules we discovered the
--    hard way now live in exactly one place:
--      a) NULL gross_margin never ranks as top percentile
--         (the NULLS LAST bug fixed in 04_peer_ranking.sql)
--      b) Singleton subsectors get an explicit availability flag
--         (the Option C decision for Tableau)
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW semantic.peer_comparison AS
SELECT
    m.ticker,
    m.company_name,
    m.subsector,
    m.fiscal_year,
    ROUND(m.gross_margin::numeric, 4) AS gross_margin,
    ROUND(sm.median_gross_margin::numeric, 4) AS subsector_median_gross_margin,
    ROUND((m.gross_margin - sm.median_gross_margin)::numeric, 4) AS gross_margin_variance_vs_subsector,
    CASE WHEN m.gross_margin IS NOT NULL THEN
        ROUND((PERCENT_RANK() OVER (PARTITION BY m.subsector, m.fiscal_year ORDER BY m.gross_margin))::numeric, 4)
    ELSE NULL END AS gross_margin_percentile_in_subsector,
    ROUND(m.net_margin::numeric, 4) AS net_margin,
    ROUND(sm.median_net_margin::numeric, 4) AS subsector_median_net_margin,
    sm.subsector_company_count,
    (sm.subsector_company_count > 1) AS peer_comparison_available
FROM semantic.company_year_metrics m
JOIN semantic.subsector_medians sm
    ON sm.subsector = m.subsector AND sm.fiscal_year = m.fiscal_year;
