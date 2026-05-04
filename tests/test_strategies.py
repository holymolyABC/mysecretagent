from mysecretagent.strategies import GenericArticleStrategy, NaverNewsStrategy


def test_generic_article_extracts_title_text_and_links() -> None:
    html = """
    <html>
      <head><title>Example</title><script>ignore()</script></head>
      <body>
        <nav>menu</nav>
        <article><h1>Hello</h1><p>This is a useful article body with enough text.</p></article>
        <a href="/next">Next</a>
      </body>
    </html>
    """

    payload = GenericArticleStrategy().extract(html, "https://example.com/post")

    assert payload.title == "Example"
    assert "useful article body" in payload.text
    assert "menu" not in payload.text
    assert payload.links == ["https://example.com/next"]


def test_naver_news_uses_article_area() -> None:
    html = """
    <html>
      <body>
        <div>outside text</div>
        <div id="dic_area">naver article text</div>
      </body>
    </html>
    """

    payload = NaverNewsStrategy().extract(html, "https://news.naver.com/article/001/1")

    assert payload.text == "naver article text"
