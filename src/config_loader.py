from pathlib import Path
from typing import Any
import yaml


class ConfigError(Exception):
    pass


def load_yaml(path: str) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        raise ConfigError(f"Config file not found: {path}")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"Failed to parse YAML in {path}: {e}")

    if data is None:
        raise ConfigError(f"Config file is empty: {path}")

    return data


def load_settings(path: str = "config/settings.yaml") -> dict[str, Any]:
    settings = load_yaml(path)

    user_agent = settings.get("edgar_api", {}).get("user_agent", "")
    if not user_agent or user_agent.startswith("REPLACE_ME"):
        raise ConfigError(
            "edgar_api.user_agent in settings.yaml is still a placeholder. "
            "SEC EDGAR requires a real identifying User-Agent "
            "(format: 'YourApp/1.0 your-email@example.com'). "
            "Update config/settings.yaml before running extraction."
        )

    fy = settings.get("fiscal_years", {})
    start, end = fy.get("start"), fy.get("end")
    if not start or not end or start > end:
        raise ConfigError(
            f"Invalid fiscal_years range in settings.yaml: start={start}, end={end}"
        )

    return settings


def load_companies(path: str = "config/companies.yaml") -> list[dict[str, Any]]:
    data = load_yaml(path)
    companies = data.get("companies", [])

    if not companies:
        raise ConfigError(f"No companies found in {path}")

    required_fields = {"ticker", "name", "cik", "subsector"}
    for i, company in enumerate(companies):
        missing = required_fields - set(company.keys())
        if missing:
            raise ConfigError(
                f"Company entry #{i} in {path} is missing fields: {missing} "
                f"(entry: {company})"
            )

    return companies
