WITH company_year_pivot AS (
    SELECT
        ticker,
        fiscal_year,
        MAX(CASE WHEN line_item = 'operating_cash_flow' THEN value END)      AS operating_cash_flow,
        MAX(CASE WHEN line_item = 'capital_expenditures' THEN value END)    AS capital_expenditures,
        MAX(CASE WHEN line_item = 'net_income' THEN value END)              AS net_income,
        MAX(CASE WHEN line_item = 'total_revenue' THEN value END)           AS total_revenue
    FROM fact_financials
    WHERE line_item IN ('operating_cash_flow', 'capital_expenditures', 'net_income', 'total_revenue')
    GROUP BY ticker, fiscal_year
)

SELECT
    p.ticker,
    c.company_name,
    c.subsector,
    p.fiscal_year,
    p.operating_cash_flow,
    p.capital_expenditures,
    p.net_income,
    (p.operating_cash_flow - p.capital_expenditures) AS free_cash_flow,
    ROUND(
        (p.operating_cash_flow - p.capital_expenditures) / NULLIF(p.total_revenue, 0),
        4
    ) AS fcf_margin,
    ROUND(
        p.operating_cash_flow / NULLIF(p.net_income, 0),
        4
    ) AS cash_flow_quality_ratio
FROM company_year_pivot p
JOIN dim_company c ON c.ticker = p.ticker
ORDER BY p.ticker, p.fiscal_year;
