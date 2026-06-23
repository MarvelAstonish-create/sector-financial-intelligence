import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config_loader import ConfigError, load_companies, load_settings
from edgar_client import EdgarAPIError, EdgarClient
from logger_setup import setup_logger


def run_extraction(settings_path="config/settings.yaml",
                    companies_path="config/companies.yaml"):
    settings = load_settings(settings_path)
    companies = load_companies(companies_path)

    logger = setup_logger(
        name="extract_filings",
        log_file=settings["logging"]["log_file"],
        level=settings["logging"]["level"],
        max_bytes=settings["logging"]["max_bytes"],
        backup_count=settings["logging"]["backup_count"],
    )

    logger.info("=" * 70)
    logger.info(f"Starting extraction run for {len(companies)} companies.")
    logger.info(f"Fiscal year scope: {settings['fiscal_years']['start']}-{settings['fiscal_years']['end']}")
    logger.info("=" * 70)

    raw_dir = Path(settings["paths"]["raw_data_dir"])
    raw_dir.mkdir(parents=True, exist_ok=True)

    client = EdgarClient(
        user_agent=settings["edgar_api"]["user_agent"],
        base_url=settings["edgar_api"]["base_url"],
        requests_per_second=settings["edgar_api"]["requests_per_second"],
        max_retries=settings["edgar_api"]["max_retries"],
        backoff_base_seconds=settings["edgar_api"]["backoff_base_seconds"],
        request_timeout_seconds=settings["edgar_api"]["request_timeout_seconds"],
        logger=logger,
    )

    run_started_at = datetime.now(timezone.utc).isoformat()
    succeeded = []
    failed = []
    start_time = time.monotonic()

    for company in companies:
        ticker = company["ticker"]
        cik = company["cik"]

        try:
            facts = client.get_company_facts(cik=cik, ticker=ticker)

            output_path = raw_dir / f"{ticker}_companyfacts.json"
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(facts, f)

            succeeded.append(ticker)
            logger.info(f"[{ticker}] Saved raw facts -> {output_path}")

        except EdgarAPIError as e:
            logger.error(f"[{ticker}] Extraction failed: {e}")
            failed.append({"ticker": ticker, "cik": cik, "error": str(e)})

    elapsed = time.monotonic() - start_time

    summary = {
        "run_started_at": run_started_at,
        "fiscal_years": settings["fiscal_years"],
        "total_companies": len(companies),
        "succeeded": succeeded,
        "failed": failed,
        "elapsed_seconds": round(elapsed, 1),
    }

    summary_path = raw_dir / "extraction_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    logger.info("=" * 70)
    logger.info(
        f"Extraction complete in {elapsed:.1f}s - "
        f"{len(succeeded)} succeeded, {len(failed)} failed."
    )
    if failed:
        logger.warning(f"Failed companies: {[f['ticker'] for f in failed]}")
    logger.info(f"Summary written to {summary_path}")
    logger.info("=" * 70)

    return summary


if __name__ == "__main__":
    try:
        run_extraction()
    except ConfigError as e:
        print(f"\nConfiguration error: {e}\n")
        sys.exit(1)
