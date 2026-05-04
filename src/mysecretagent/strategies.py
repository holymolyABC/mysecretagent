from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup


@dataclass(slots=True)
class CrawlPayload:
    url: str
    title: str | None
    text: str
    links: list[str]


class SiteStrategy:
    domains: tuple[str, ...] = ()
    prefers_dynamic = False
    min_text_length = 120

    def matches(self, url: str) -> bool:
        hostname = urlparse(url).hostname or ""
        return any(hostname == domain or hostname.endswith(f".{domain}") for domain in self.domains)

    def extract(self, html: str, url: str) -> CrawlPayload:
        soup = BeautifulSoup(html, "html.parser")
        self._remove_noise(soup)
        title = self._title(soup)
        text = self._main_text(soup)
        links = self._links(soup, url)
        return CrawlPayload(url=url, title=title, text=text, links=links)

    def _main_text(self, soup: BeautifulSoup) -> str:
        candidates = [
            soup.find("article"),
            soup.find("main"),
            soup.find(attrs={"role": "main"}),
            soup.body,
            soup,
        ]
        for node in candidates:
            if node is None:
                continue
            text = node.get_text(" ", strip=True)
            if len(text) >= self.min_text_length:
                return text
        return soup.get_text(" ", strip=True)

    @staticmethod
    def _remove_noise(soup: BeautifulSoup) -> None:
        for tag in soup(["script", "style", "noscript", "svg", "iframe", "nav", "footer"]):
            tag.decompose()

    @staticmethod
    def _title(soup: BeautifulSoup) -> str | None:
        if soup.title and soup.title.string:
            return soup.title.string.strip()
        heading = soup.find(["h1", "h2"])
        return heading.get_text(" ", strip=True) if heading else None

    @staticmethod
    def _links(soup: BeautifulSoup, base_url: str) -> list[str]:
        links: list[str] = []
        seen: set[str] = set()
        for anchor in soup.find_all("a", href=True):
            href = urljoin(base_url, anchor["href"])
            if href not in seen:
                seen.add(href)
                links.append(href)
        return links


class GenericArticleStrategy(SiteStrategy):
    pass


class NaverNewsStrategy(SiteStrategy):
    domains = ("news.naver.com", "n.news.naver.com")
    min_text_length = 80

    def _main_text(self, soup: BeautifulSoup) -> str:
        article = soup.select_one("#dic_area, #newsct_article, article")
        if article:
            return article.get_text(" ", strip=True)
        return super()._main_text(soup)


class DaumNewsStrategy(SiteStrategy):
    domains = ("v.daum.net", "news.daum.net")
    min_text_length = 80

    def _main_text(self, soup: BeautifulSoup) -> str:
        article = soup.select_one(".article_view, #mArticle, article")
        if article:
            return article.get_text(" ", strip=True)
        return super()._main_text(soup)


class ClientRenderedStrategy(SiteStrategy):
    domains = ("instagram.com", "x.com", "twitter.com")
    prefers_dynamic = True
    min_text_length = 60


def default_strategies() -> list[SiteStrategy]:
    return [
        NaverNewsStrategy(),
        DaumNewsStrategy(),
        ClientRenderedStrategy(),
        GenericArticleStrategy(),
    ]
