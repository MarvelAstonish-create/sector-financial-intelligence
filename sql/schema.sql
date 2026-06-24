DROP TABLE IF EXISTS fact_financials CASCADE;
DROP TABLE IF EXISTS dim_company CASCADE;
DROP TABLE IF EXISTS dim_line_item CASCADE;

CREATE TABLE dim_company (
    ticker        VARCHAR(10)   PRIMARY KEY,
    company_name  VARCHAR(100)  NOT NULL,
    subsector     VARCHAR(50)   NOT NULL
);

CREATE TABLE dim_line_item (
    line_item       VARCHAR(50)  PRIMARY KEY,
    statement_type  VARCHAR(30)  NOT NULL
        CHECK (statement_type IN ('income_statement', 'balance_sheet', 'cash_flow_statement')),
    display_name    VARCHAR(100) NOT NULL
);

CREATE TABLE fact_financials (
    ticker        VARCHAR(10)   NOT NULL REFERENCES dim_company(ticker),
    fiscal_year   INTEGER       NOT NULL CHECK (fiscal_year BETWEEN 2000 AND 2100),
    line_item     VARCHAR(50)   NOT NULL REFERENCES dim_line_item(line_item),
    value         NUMERIC,
    source_tag    VARCHAR(150)  NOT NULL,
    PRIMARY KEY (ticker, fiscal_year, line_item)
);

CREATE INDEX idx_fact_financials_ticker ON fact_financials(ticker);
CREATE INDEX idx_fact_financials_fiscal_year ON fact_financials(fiscal_year);
CREATE INDEX idx_fact_financials_line_item ON fact_financials(line_item);
