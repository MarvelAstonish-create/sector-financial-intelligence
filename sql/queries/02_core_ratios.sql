-- PURPOSE: For each company-year, compute the fundamental financial health
--          ratios a CFO, lender, or investor checks first.
-- INPUTS:  total_revenue, gross_profit, operating_income, net_income,
--          total_equity, total_assets, current_assets, current_liabilities,
--          total_debt_long_term (all from fact_financials)
-- NOTES:   NULLIF guards every denominator against division-by-zero. A
--          missing input (see CLEANING_NOTES.md for known gaps) correctly
--          produces a NULL ratio rather than a fabricated number.
--
-- COVERS FOUR CATEGORIES:
--   Profitability - how much of revenue becomes profit
--   Returns       - how efficiently the company uses its capital/assets
--   Liquidity     - can the company cover short-term obligations
--   Leverage      - how much debt-financed risk the company carries

WITH company_year_pivot AS (
    SELECT
        ticker,
        fiscal_year,
        MAX(CASE WHEN line_item = 'total_revenue' THEN value END)          AS total_revenue,
        MAX(CASE WHEN line_item = 'gross_profit' THEN value END)           AS gross_profit,
        MAX(CASE WHEN line_item = 'operating_income' THEN value END)       AS operating_income,
        MAX(CASE WHEN line_item = 'net_income' THEN value END)             AS net_income,
        MAX(CASE WHEN line_item = 'total_equity' THEN value END)           AS total_equity,
        MAX(CASE WHEN line_item = 'total_assets' THEN value END)           AS total_assets,
        MAX(CASE WHEN line_item = 'current_assets' THEN value END)         AS current_assets,
        MAX(CASE WHEN line_item = 'current_liabilities' THEN value END)    AS current_liabilities,
        MAX(CASE WHEN line_item = 'total_debt_long_term' THEN value END)   AS total_debt_long_term
    FROM fact_financials
    WHERE line_item IN (
        'total_revenue', 'gross_profit', 'operating_income', 'net_income',
        'total_equity', 'total_assets', 'current_assets', 'current_liabilities',
        'total_debt_long_term'
    )
    GROUP BY ticker, fiscal_year
)
SELECT
    p.ticker,
    c.company_name,
    c.subsector,
    p.fiscal_year,
    ROUND(p.gross_profit / NULLIF(p.total_revenue, 0), 4)      AS gross_margin,
    ROUND(p.operating_income / NULLIF(p.total_revenue, 0), 4)  AS operating_margin,
    ROUND(p.net_income / NULLIF(p.total_revenue, 0), 4)        AS net_margin,
    ROUND(p.net_income / NULLIF(p.total_equity, 0), 4)         AS return_on_equity,
    ROUND(p.net_income / NULLIF(p.total_assets, 0), 4)         AS return_on_assets,
    ROUND(p.current_assets / NULLIF(p.current_liabilities, 0), 4) AS current_ratio,
    (p.current_assets - p.current_liabilities)                     AS working_capital,
    ROUND(p.total_debt_long_term / NULLIF(p.total_equity, 0), 4)  AS debt_to_equity,
    ROUND(p.total_debt_long_term / NULLIF(p.total_assets, 0), 4)  AS debt_to_assets
FROM company_year_pivot p
JOIN dim_company c ON c.ticker = p.ticker
ORDER BY p.ticker, p.fiscal_year;
