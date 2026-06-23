import time
from typing import Any

import requests

from logger_setup import setup_logger


class EdgarAPIError(Exception):
    pass


class EdgarClient:
    def __init__(self, user_agent: str, base_url: str,
                 requests_per_second: float = 4,
                 max_retries: int = 4,
                 backoff_base_seconds: float = 2,
                 request_timeout_seconds: float = 15,
                 logger=None):
        self.user_agent = user_agent
        self.base_url = base_url.rstrip("/")
        self.min_interval = 1.0 / requests_per_second
        self.max_retries = max_retries
        self.backoff_base_seconds = backoff_base_seconds
        self.request_timeout_seconds = request_timeout_seconds
        self.logger = logger or setup_logger(__name__, "logs/extraction.log")

        self._last_request_time = 0.0

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip, deflate",
        })

    def _throttle(self):
        elapsed = time.monotonic() - self._last_request_time
        wait = self.min_interval - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_request_time = time.monotonic()

    def get_company_facts(self, cik, ticker):
        padded_cik = str(cik).zfill(10)
        url = f"{self.base_url}/CIK{padded_cik}.json"

        last_exception = None

        for attempt in range(1, self.max_retries + 1):
            self._throttle()
            try:
                self.logger.info(
                    f"[{ticker}] Requesting company facts (attempt {attempt}/{self.max_retries}) - {url}"
                )
                response = self.session.get(url, timeout=self.request_timeout_seconds)

                if response.status_code == 404:
                    raise EdgarAPIError(
                        f"[{ticker}] CIK {padded_cik} not found on EDGAR (404). "
                        f"Check companies.yaml for a typo'd CIK."
                    )
                if response.status_code == 403:
                    raise EdgarAPIError(
                        f"[{ticker}] Request forbidden (403) - almost always means "
                        f"the User-Agent header is missing, malformed, or has been "
                        f"blocked by SEC. Check config/settings.yaml."
                    )

                if response.status_code == 429:
                    self.logger.warning(f"[{ticker}] Rate limited (429) on attempt {attempt}.")
                    self._sleep_backoff(attempt)
                    continue

                if 500 <= response.status_code < 600:
                    self.logger.warning(
                        f"[{ticker}] Server error ({response.status_code}) on attempt {attempt}."
                    )
                    self._sleep_backoff(attempt)
                    continue

                response.raise_for_status()

                self.logger.info(f"[{ticker}] Successfully retrieved company facts.")
                return response.json()

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                self.logger.warning(f"[{ticker}] Network error on attempt {attempt}: {e}")
                last_exception = e
                self._sleep_backoff(attempt)
                continue

            except EdgarAPIError:
                raise

        raise EdgarAPIError(
            f"[{ticker}] Failed to retrieve company facts after {self.max_retries} attempts. "
            f"Last error: {last_exception}"
        )

    def _sleep_backoff(self, attempt):
        delay = self.backoff_base_seconds ** attempt
        self.logger.info(f"Backing off for {delay:.0f}s before retrying.")
        time.sleep(delay)
