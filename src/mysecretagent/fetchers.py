from __future__ import annotations

from dataclasses import dataclass

import requests


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36 mysecretagent/0.1"
    )
}


@dataclass(slots=True)
class FetchedPage:
    url: str
    html: str


class StaticFetcher:
    def __init__(self, *, timeout: float = 15.0) -> None:
        self.timeout = timeout

    def fetch(self, url: str) -> FetchedPage:
        response = requests.get(url, headers=DEFAULT_HEADERS, timeout=self.timeout)
        response.raise_for_status()
        return FetchedPage(url=response.url, html=response.text)


class DynamicFetcher:
    def __init__(self, *, timeout: float = 15.0) -> None:
        self.timeout = timeout

    def fetch(self, url: str) -> FetchedPage:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Dynamic fallback requires Playwright. Install with "
                "`pip install 'mysecretagent[dynamic]'` and run `playwright install`."
            ) from exc

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page(user_agent=DEFAULT_HEADERS["User-Agent"])
                page.goto(url, wait_until="networkidle", timeout=self.timeout * 1000)
                return FetchedPage(url=page.url, html=page.content())
            finally:
                browser.close()
