-- PURPOSE: For each company, track revenue and net income growth year-over-
--          year, and compute the smoothed 5-year CAGR (Compound Annual
--          Growth Rate) - the standard way analysts express "average annual
--          growth" without being thrown off by one noisy year.
-- INPUTS:  total_revenue, net_income (from fact_financials)
-- NOTES:   YoY growth for FY2019 is always NULL for every company - there is
--          no FY2018 in our dataset to compare against, so this is an
--          expected, structural NULL (a real data boundary), not a bug.
--          CAGR is calculated once per company, anchored to FY2019 (first
--          year in scope) and FY2023 (last year in scope).

WITH yearly_values AS (
    SELECT
        ticker,
        fiscal_year,
        MAX(CASE WHEN line_item = 'total_revenue' THEN value END) AS total_revenue,
        MAX(CASE WHEN line_item = 'net_income' THEN value END)    AS net_income
    FROM fact_financials
    WHERE line_item IN ('total_revenue', 'net_income')
    GROUP BY ticker, fiscal_year
),

yoy_growth AS (
    SELECT
        ticker,
        fiscal_year,
        total_revenue,
        net_income,
        LAG(total_revenue, 1) OVER (PARTITION BY ticker ORDER BY fiscal_year) AS prior_year_revenue,
        LAG(net_income, 1) OVER (PARTITION BY ticker ORDER BY fiscal_year)   AS prior_year_net_income
    FROM yearly_values
),

cagr_inputs AS (
    SELECT
        ticker,
        MAX(CASE WHEN fiscal_year = 2019 THEN total_revenue END) AS revenue_start,
        MAX(CASE WHEN fiscal_year = 2023 THEN total_revenue END) AS revenue_end
    FROM yearly_values
    GROUP BY ticker
)

SELECT
    g.ticker,
    c.company_name,
    c.subsector,
    g.fiscal_year,
    g.total_revenue,
    g.net_income,
    ROUND((g.total_revenue - g.prior_year_revenue) / NULLIF(g.prior_year_revenue, 0), 4) AS revenue_yoy_growth,
    ROUND((g.net_income - g.prior_year_net_income) / NULLIF(g.prior_year_net_income, 0), 4) AS net_income_yoy_growth,
    ROUND((POWER(ci.revenue_end / NULLIF(ci.revenue_start, 0), 1.0 / 4) - 1), 4) AS revenue_cagr_5yr
FROM yoy_growth g
JOIN dim_company c ON c.ticker = g.ticker
JOIN cagr_inputs ci ON ci.ticker = g.ticker
ORDER BY g.ticker, g.fiscal_year;
