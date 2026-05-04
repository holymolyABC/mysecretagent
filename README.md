# mysecretagent

OOP crawler scaffold with static HTML crawling, optional Playwright fallback for
client-rendered pages, and replaceable site strategies.

## Install

```bash
pip install -e .
```

For dynamic fallback:

```bash
pip install -e ".[dynamic]"
playwright install
```

## CLI

```bash
mysecretagent "https://example.com" --dynamic
```

## Python

```python
from mysecretagent import SecretAgentCrawler

crawler = SecretAgentCrawler(allow_dynamic=True)
result = crawler.crawl("https://example.com")

print(result.title)
print(result.text)
```

## Design

- `StaticFetcher` fetches ordinary HTML with `requests`.
- `DynamicFetcher` renders JavaScript-heavy pages with Playwright only when
  fallback is needed.
- `SiteStrategy` subclasses isolate site-specific extraction rules.
- `SecretAgentCrawler` coordinates strategy selection and fallback behavior.
