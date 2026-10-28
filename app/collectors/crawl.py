"""Shared polite-fetch policy for the long catalog runs.

- A redirect to the canonical spelling of the same page (case or trailing slash) is followed once.
- Any other redirect, or an HTTP 404/410, means the page is gone: the caller records it and moves on (`Gone`).
  Any other HTTP error (403, 429, 5xx...) is not a stale page and stops the run.
- Five gone pages in a row trigger a canary: the last page that worked is requested again. If it still loads, the
  run was crossing a retired family of products; if it does not, the site stopped answering and the run stops.
- A redirect to an address that mentions captcha/block/denied/challenge stops the run at once.
"""
import re
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit

from app.collectors import sitemaps
from app.collectors.discovery import Redirected

MAX_CONSECUTIVE_REDIRECTS = 5
SUSPICIOUS = re.compile(r"captcha|block|denied|challenge", re.I)


class Gone(ValueError):
    """The page no longer exists at this address (redirected elsewhere)."""


def same_page(url: str, target: str) -> bool:
    a, b = urlsplit(url), urlsplit(target)
    return a.netloc == b.netloc and a.path.lower().rstrip("/") == b.path.lower().rstrip("/") and target != url


class Guard:
    def __init__(self, now: datetime, state: dict, expected: str = "text/html"):
        self.now, self.state, self.expected = now, state, expected
        self.redirects = 0
        self.last_ok: tuple[str, Path] | None = None

    def fetch(self, url: str, cache_file: Path) -> tuple[bytes, bool]:
        try:
            result = sitemaps.fetch_cached(url, cache_file, self.now, self.state, expected=self.expected)
        except HTTPError as err:
            if err.code not in (404, 410):
                raise
            return self._gone(err.code, "", f"HTTP {err.code} (page no longer available)")
        except Redirected as moved:
            target = urljoin(url, moved.location)
            if same_page(url, target):  # canonical spelling of the same page: follow once
                try:
                    result = sitemaps.fetch_cached(target, cache_file, self.now, self.state, expected=self.expected)
                except Redirected as again:
                    return self._gone(again.code, again.location)
            else:
                return self._gone(moved.code, moved.location)
        self.redirects = 0
        self.last_ok = (url, cache_file)
        return result

    def _gone(self, code: int, location: str, message: str | None = None):
        self.redirects += 1
        suspicious = SUSPICIOUS.search(location)
        if self.redirects >= MAX_CONSECUTIVE_REDIRECTS or suspicious:
            stop = f"{self.redirects} consecutive gone pages (last {code} {location}); stop for manual review"
            if suspicious or self.last_ok is None:
                raise ValueError(stop)
            try:
                sitemaps.fetch_cached(self.last_ok[0], self.last_ok[1], self.now, self.state, max_age_days=0, expected=self.expected)
            except (ValueError, HTTPError) as exc:  # includes Redirected
                raise ValueError(f"{stop}; canary page {self.last_ok[0]} also fails: {exc}") from exc
            self.redirects = 0  # the canary still loads: these were retired products
        raise Gone(message or f"redirected {code} to {location} (page no longer available)")
