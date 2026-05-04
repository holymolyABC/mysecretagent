from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from .fetchers import DynamicFetcher, StaticFetcher
from .strategies import CrawlPayload, SiteStrategy, default_strategies


@dataclass(slots=True)
class CrawlResult:
    url: str
    final_url: str
    title: str | None
    text: str
    links: list[str]
    source: str
    strategy: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class SecretAgentCrawler:
    def __init__(
        self,
        *,
        strategies: Iterable[SiteStrategy] | None = None,
        allow_dynamic: bool = True,
        timeout: float = 15.0,
    ) -> None:
        self.strategies = list(strategies or default_strategies())
        self.allow_dynamic = allow_dynamic
        self.static_fetcher = StaticFetcher(timeout=timeout)
        self.dynamic_fetcher = DynamicFetcher(timeout=timeout)

    def crawl(self, url: str) -> CrawlResult:
        strategy = self._strategy_for(url)
        static_page = self.static_fetcher.fetch(url)
        payload = strategy.extract(static_page.html, static_page.url)

        if self._needs_dynamic(strategy, payload):
            dynamic_page = self.dynamic_fetcher.fetch(static_page.url)
            payload = strategy.extract(dynamic_page.html, dynamic_page.url)
            return self._result(dynamic_page.url, payload, "dynamic", strategy)

        return self._result(static_page.url, payload, "static", strategy)

    def _strategy_for(self, url: str) -> SiteStrategy:
        for strategy in self.strategies:
            if strategy.matches(url):
                return strategy
        return self.strategies[-1]

    def _needs_dynamic(self, strategy: SiteStrategy, payload: CrawlPayload) -> bool:
        if not self.allow_dynamic:
            return False
        return strategy.prefers_dynamic or len(payload.text.strip()) < strategy.min_text_length

    @staticmethod
    def _result(
        final_url: str,
        payload: CrawlPayload,
        source: str,
        strategy: SiteStrategy,
    ) -> CrawlResult:
        return CrawlResult(
            url=payload.url,
            final_url=final_url,
            title=payload.title,
            text=payload.text,
            links=payload.links,
            source=source,
            strategy=type(strategy).__name__,
        )
