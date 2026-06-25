-- PURPOSE: For each company-year, compare its gross margin and net margin
--          to the MEDIAN of its own subsector peers in that same year, and
--          rank where it sits (percentile) within that peer group.
-- INPUTS:  total_revenue, gross_profit, net_income (from fact_financials),
--          subsector (from dim_company)
-- NOTES:   Comparisons are WITHIN subsector only - comparing AAPL's margin
--          structure to NVDA's would conflate a hardware/device business
--          model with a fabless chip designer's.
--
-- IMPORTANT POSTGRES QUIRK: PERCENTILE_CONT is an ORDERED-SET AGGREGATE,
-- not a window function. It works with GROUP BY, but cannot be combined
-- with OVER (...) at all. Fix: compute subsector medians as a SEPARATE
-- grouped aggregate, then JOIN back to per-company rows. PERCENT_RANK()
-- IS a real window function and works fine with OVER (PARTITION BY ...).

WITH company_year_margins AS (
    SELECT
        f.ticker,
        f.fiscal_year,
        MAX(CASE WHEN f.line_item = 'gross_profit' THEN f.value END)
            / NULLIF(MAX(CASE WHEN f.line_item = 'total_revenue' THEN f.value END), 0) AS gross_margin,
        MAX(CASE WHEN f.line_item = 'net_income' THEN f.value END)
            / NULLIF(MAX(CASE WHEN f.line_item = 'total_revenue' THEN f.value END), 0) AS net_margin
    FROM fact_financials f
    WHERE f.line_item IN ('gross_profit', 'net_income', 'total_revenue')
    GROUP BY f.ticker, f.fiscal_year
),

with_subsector AS (
    SELECT m.*, c.subsector
    FROM company_year_margins m
    JOIN dim_company c ON c.ticker = m.ticker
),

subsector_medians AS (
    SELECT
        subsector,
        fiscal_year,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY gross_margin) AS median_gross_margin,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY net_margin)   AS median_net_margin
    FROM with_subsector
    GROUP BY subsector, fiscal_year
)

SELECT
    w.ticker,
    c.company_name,
    w.subsector,
    w.fiscal_year,
    ROUND(w.gross_margin, 4) AS gross_margin,
    ROUND(sm.median_gross_margin::numeric, 4) AS subsector_median_gross_margin,
    ROUND(w.gross_margin - sm.median_gross_margin::numeric, 4) AS gross_margin_variance_vs_subsector,
    ROUND(
        (PERCENT_RANK() OVER (PARTITION BY w.subsector, w.fiscal_year ORDER BY w.gross_margin))::numeric,
        4
    ) AS gross_margin_percentile_in_subsector,
    ROUND(w.net_margin, 4) AS net_margin,
    ROUND(sm.median_net_margin::numeric, 4) AS subsector_median_net_margin
FROM with_subsector w
JOIN dim_company c ON c.ticker = w.ticker
JOIN subsector_medians sm ON sm.subsector = w.subsector AND sm.fiscal_year = w.fiscal_year
ORDER BY w.subsector, w.fiscal_year, w.ticker;
