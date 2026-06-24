import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import psycopg2

from config_loader import load_companies, load_yaml
from logger_setup import setup_logger


DISPLAY_NAMES = {
    "total_revenue": "Total Revenue",
    "cost_of_revenue": "Cost of Revenue",
    "gross_profit": "Gross Profit",
    "operating_income": "Operating Income",
    "net_income": "Net Income",
    "research_and_development_expense": "Research & Development Expense",
    "sga_expense": "Selling, General & Administrative Expense",
    "diluted_eps": "Diluted Earnings Per Share",
    "total_assets": "Total Assets",
    "total_liabilities": "Total Liabilities",
    "total_equity": "Total Equity",
    "cash_and_equivalents": "Cash & Cash Equivalents",
    "current_assets": "Current Assets",
    "current_liabilities": "Current Liabilities",
    "total_debt_long_term": "Long-Term Debt",
    "operating_cash_flow": "Operating Cash Flow",
    "investing_cash_flow": "Investing Cash Flow",
    "financing_cash_flow": "Financing Cash Flow",
    "capital_expenditures": "Capital Expenditures",
    "depreciation_and_amortization": "Depreciation & Amortization",
}


def get_connection(dbname="sector_financial_intelligence", user="postgres"):
    import os
    password = os.environ.get("PGPASSWORD")
    return psycopg2.connect(dbname=dbname, user=user, password=password)


def load_dim_company(conn, companies, logger):
    with conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE fact_financials, dim_company, dim_line_item CASCADE;")
        for company in companies:
            cur.execute(
                "INSERT INTO dim_company (ticker, company_name, subsector) VALUES (%s, %s, %s)",
                (company["ticker"], company["name"], company["subsector"]),
            )
    conn.commit()
    logger.info(f"Loaded {len(companies)} rows into dim_company.")


def load_dim_line_item(conn, tag_map, logger):
    rows_inserted = 0
    with conn.cursor() as cur:
        for statement_type in ["income_statement", "balance_sheet", "cash_flow_statement"]:
            line_items = tag_map.get(statement_type, {})
            for line_item in line_items.keys():
                display_name = DISPLAY_NAMES.get(line_item, line_item)
                cur.execute(
                    "INSERT INTO dim_line_item (line_item, statement_type, display_name) VALUES (%s, %s, %s)",
                    (line_item, statement_type, display_name),
                )
                rows_inserted += 1
    conn.commit()
    logger.info(f"Loaded {rows_inserted} rows into dim_line_item.")


def load_fact_financials(conn, processed_dir, logger):
    total_rows = 0
    for statement_name in ["income_statement", "balance_sheet", "cash_flow_statement"]:
        csv_path = processed_dir / f"{statement_name}.csv"
        if not csv_path.exists():
            logger.error(f"Expected CSV not found: {csv_path} - skipping this statement.")
            continue

        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        with conn.cursor() as cur:
            for row in rows:
                value = row["value"] if row["value"] not in ("", None) else None
                cur.execute(
                    "INSERT INTO fact_financials (ticker, fiscal_year, line_item, value, source_tag) VALUES (%s, %s, %s, %s, %s)",
                    (row["ticker"], int(row["fiscal_year"]), row["line_item"], value, row["source_tag"]),
                )

        conn.commit()
        total_rows += len(rows)
        logger.info(f"Loaded {len(rows)} rows from {csv_path.name} into fact_financials.")

    logger.info(f"Total fact_financials rows loaded: {total_rows}")
    return total_rows


def run_load(settings_path="config/settings.yaml",
             companies_path="config/companies.yaml",
             tag_map_path="config/xbrl_tag_map.yaml"):
    logger = setup_logger(name="load_to_postgres", log_file="logs/load_to_postgres.log", level="INFO")

    logger.info("=" * 70)
    logger.info("Starting PostgreSQL load.")
    logger.info("=" * 70)

    companies = load_companies(companies_path)
    tag_map = load_yaml(tag_map_path)
    processed_dir = Path("data/processed")

    conn = get_connection()
    try:
        load_dim_company(conn, companies, logger)
        load_dim_line_item(conn, tag_map, logger)
        total_rows = load_fact_financials(conn, processed_dir, logger)

        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM fact_financials;")
            db_count = cur.fetchone()[0]

        logger.info("=" * 70)
        logger.info(f"Load complete. CSV rows loaded: {total_rows}, rows now in database: {db_count}.")
        if db_count != total_rows:
            logger.warning(f"MISMATCH: expected {total_rows} rows but database has {db_count}.")
        logger.info("=" * 70)
    finally:
        conn.close()


if __name__ == "__main__":
    run_load()
