from telegram.constants import ParseMode

from cub.telegram_render import (
    markdown_to_telegram_html,
    render_for_telegram,
    split_message,
)


def test_render_for_telegram_plain_mode() -> None:
    text, parse_mode = render_for_telegram("hello", "plain")
    assert text == "hello"
    assert parse_mode is None


def test_render_for_telegram_markdown_mode() -> None:
    text, parse_mode = render_for_telegram("**bold** `code`", "markdown")
    assert parse_mode == ParseMode.HTML
    assert "<b>bold</b>" in text
    assert "<code>code</code>" in text


def test_markdown_to_html_handles_links_and_code_blocks() -> None:
    source = "See [docs](https://example.com)\n```python\nprint('x')\n```"
    html = markdown_to_telegram_html(source)
    assert '<a href="https://example.com">docs</a>' in html
    assert '<pre><code class="language-python">print(\'x\')\n</code></pre>' in html


def test_split_message_respects_limit() -> None:
    parts = split_message("a " * 5000, max_len=1000)
    assert len(parts) > 1
    assert all(len(part) <= 1000 for part in parts)


def test_markdown_to_html_escapes_link_href_quotes() -> None:
    source = '[x](https://example.com/?q="abc"&z=1)'
    html = markdown_to_telegram_html(source)
    assert '<a href="https://example.com/?q=&quot;abc&quot;&amp;z=1">x</a>' in html
