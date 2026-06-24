import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config_loader import load_companies, load_settings, load_yaml
from xbrl_resolver import resolve_annual_fact, ResolvedFact
from derived_metrics import (
    ResolvedLineItems,
    apply_gross_profit_fallback,
    apply_operating_income_fallback,
    apply_total_liabilities_fallback,
    is_computed_value,
)
from logger_setup import setup_logger


MISSING_TAG = "MISSING"

FALLBACK_DEPENDENCIES = {
    "gross_profit": ["total_revenue", "cost_of_revenue"],
    "operating_income": ["gross_profit", "research_and_development_expense", "sga_expense"],
}


def resolve_statement(statement_name, line_item_tags, company_facts, ticker, fiscal_year, logger):
    fact_type = "instant" if statement_name == "balance_sheet" else "duration"
    resolved = {}

    for line_item, tag_candidates in line_item_tags.items():
        resolved[line_item] = resolve_annual_fact(company_facts, tag_candidates, fiscal_year, fact_type=fact_type)

    if "gross_profit" in resolved and resolved.get("gross_profit") is None:
        items = ResolvedLineItems(
            gross_profit=None,
            total_revenue=resolved.get("total_revenue"),
            cost_of_revenue=resolved.get("cost_of_revenue"),
        )
        resolved["gross_profit"] = apply_gross_profit_fallback(items)

    if "operating_income" in resolved and resolved.get("operating_income") is None:
        items = ResolvedLineItems(
            operating_income=None,
            gross_profit=resolved.get("gross_profit"),
            research_and_development_expense=resolved.get("research_and_development_expense"),
            sga_expense=resolved.get("sga_expense"),
        )
        resolved["operating_income"] = apply_operating_income_fallback(items)

    if "total_liabilities" in resolved and resolved.get("total_liabilities") is None:
        items = ResolvedLineItems(
            total_liabilities=None,
            current_liabilities=resolved.get("current_liabilities"),
        )
        resolved["total_liabilities"] = apply_total_liabilities_fallback(
            items, company_facts, fiscal_year
        )

    rows = []
    for line_item, fact in resolved.items():
        if fact is None:
            logger.warning(
                f"[{ticker}] FY{fiscal_year} {statement_name}.{line_item}: "
                f"no direct tag or fallback resolved a value (MISSING)."
            )
            rows.append({
                "ticker": ticker, "fiscal_year": fiscal_year, "line_item": line_item,
                "value": None, "source_tag": MISSING_TAG,
            })
        else:
            rows.append({
                "ticker": ticker, "fiscal_year": fiscal_year, "line_item": line_item,
                "value": fact.value, "source_tag": fact.source_tag,
            })

    return rows


def write_csv(rows, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["ticker", "fiscal_year", "line_item", "value", "source_tag"]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run_normalization(settings_path="config/settings.yaml",
                       companies_path="config/companies.yaml",
                       tag_map_path="config/xbrl_tag_map.yaml"):
    settings = load_settings(settings_path)
    companies = load_companies(companies_path)
    tag_map = load_yaml(tag_map_path)

    logger = setup_logger(
        name="normalize_financials",
        log_file="logs/normalization.log",
        level=settings["logging"]["level"],
        max_bytes=settings["logging"]["max_bytes"],
        backup_count=settings["logging"]["backup_count"],
    )

    fy_start = settings["fiscal_years"]["start"]
    fy_end = settings["fiscal_years"]["end"]
    fiscal_years = list(range(fy_start, fy_end + 1))

    raw_dir = Path(settings["paths"]["raw_data_dir"])
    processed_dir = Path(settings["paths"]["processed_data_dir"])

    logger.info("=" * 70)
    logger.info(f"Starting normalization for {len(companies)} companies, FY{fy_start}-{fy_end}.")
    logger.info("=" * 70)

    statement_rows = {"income_statement": [], "balance_sheet": [], "cash_flow_statement": []}

    total_attempted = 0
    total_direct = 0
    total_computed = 0
    total_missing = 0
    companies_skipped = []

    for company in companies:
        ticker = company["ticker"]
        raw_file = raw_dir / f"{ticker}_companyfacts.json"

        if not raw_file.exists():
            logger.error(f"[{ticker}] Raw data file not found: {raw_file} - skipping company entirely.")
            companies_skipped.append(ticker)
            continue

        with open(raw_file, "r", encoding="utf-8") as f:
            company_facts = json.load(f)

        for fiscal_year in fiscal_years:
            for statement_name in ["income_statement", "balance_sheet", "cash_flow_statement"]:
                line_item_tags = tag_map.get(statement_name, {})
                rows = resolve_statement(statement_name, line_item_tags, company_facts, ticker, fiscal_year, logger)
                statement_rows[statement_name].extend(rows)

                for row in rows:
                    total_attempted += 1
                    if row["source_tag"] == MISSING_TAG:
                        total_missing += 1
                    elif row["source_tag"].startswith("COMPUTED:"):
                        total_computed += 1
                    else:
                        total_direct += 1

    output_paths = {}
    for statement_name, rows in statement_rows.items():
        output_path = processed_dir / f"{statement_name}.csv"
        write_csv(rows, output_path)
        output_paths[statement_name] = str(output_path)
        logger.info(f"Wrote {len(rows)} rows -> {output_path}")

    summary = {
        "fiscal_years": {"start": fy_start, "end": fy_end},
        "total_companies": len(companies),
        "companies_skipped": companies_skipped,
        "total_values_attempted": total_attempted,
        "resolved_directly": total_direct,
        "resolved_via_fallback": total_computed,
        "missing": total_missing,
        "missing_rate_pct": round(100 * total_missing / total_attempted, 1) if total_attempted else 0,
        "output_files": output_paths,
    }

    summary_path = processed_dir / "normalization_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    logger.info("=" * 70)
    logger.info(
        f"Normalization complete: {total_attempted} values attempted, "
        f"{total_direct} direct, {total_computed} computed via fallback, "
        f"{total_missing} missing ({summary['missing_rate_pct']}%)."
    )
    logger.info(f"Summary written to {summary_path}")
    logger.info("=" * 70)

    return summary


if __name__ == "__main__":
    run_normalization()
