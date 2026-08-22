"""Milestone 32.1, Part 6 -- shared, responsible HTTP fetch helper for
every live network call this package makes (MLB Stats API, Baseball
Savant, Open-Meteo). Bounded retries with exponential backoff, explicit
Retry-After handling, and a module-level pacing delay between calls so
a full 18-month build never hammers a public, unauthenticated source.

Deliberately NOT applied to research/collector.py's existing
fetch_schedule/fetch_person functions (those are shared LIVE-pipeline
code -- see this milestone's Part 38 "do not modify shared production
code without justification"). Those functions already fail soft
(return None) by their own design; this module is used for every NEW
call this package makes on top of them (game logs, Statcast, weather).
"""

import time
import urllib.error
import urllib.request
from typing import Optional

DEFAULT_TIMEOUT = 30
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE = 1.0  # seconds; doubles each retry (1, 2, 4)
DEFAULT_PACING_DELAY = 0.25  # seconds between successive calls -- conservative, not maximized for speed

_last_request_time = 0.0


class FetchError(Exception):
    """Raised only after every retry is exhausted -- carries the last
    underlying error for the caller to log/report."""


def _pace() -> None:
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < DEFAULT_PACING_DELAY:
        time.sleep(DEFAULT_PACING_DELAY - elapsed)
    _last_request_time = time.time()


def fetch_url(
    url: str, timeout: int = DEFAULT_TIMEOUT, max_retries: int = DEFAULT_MAX_RETRIES,
    backoff_base: float = DEFAULT_BACKOFF_BASE, user_agent: str = "BigMoneyDFS-HistoricalWarehouse/1.0",
) -> bytes:
    """One responsibly-paced, retried GET. Returns raw response bytes.
    Raises FetchError only after max_retries+1 total attempts fail."""
    last_error: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        _pace()
        req = urllib.request.Request(url, headers={"User-Agent": user_agent})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code == 429:
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                delay = float(retry_after) if retry_after and retry_after.isdigit() else backoff_base * (2 ** attempt)
            elif 500 <= exc.code < 600:
                delay = backoff_base * (2 ** attempt)
            else:
                raise FetchError(f"Non-retryable HTTP {exc.code} for {url}: {exc}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            delay = backoff_base * (2 ** attempt)

        if attempt < max_retries:
            time.sleep(delay)

    raise FetchError(f"Exhausted {max_retries + 1} attempts for {url}: {last_error}") from last_error
