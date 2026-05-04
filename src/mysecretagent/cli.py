from __future__ import annotations

import argparse
import json

from .crawler import SecretAgentCrawler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Crawl a URL with static-to-dynamic fallback.")
    parser.add_argument("url", help="Target URL to crawl.")
    parser.add_argument(
        "--dynamic",
        action="store_true",
        help="Allow Playwright fallback when static HTML is not enough.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="Request/render timeout in seconds.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    crawler = SecretAgentCrawler(allow_dynamic=args.dynamic, timeout=args.timeout)
    result = crawler.crawl(args.url)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
