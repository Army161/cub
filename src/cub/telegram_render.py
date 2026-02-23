"""Telegram text rendering helpers (Markdown -> Telegram HTML)."""

from __future__ import annotations

import re
from typing import Literal

from telegram.constants import ParseMode

RenderMode = Literal["plain", "markdown"]


def split_message(content: str, max_len: int = 3900) -> list[str]:
    """Split long messages into Telegram-safe chunks."""
    text = content or ""
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= max_len:
            chunks.append(remaining)
            break

        cut = remaining[:max_len]
        pos = cut.rfind("\n")
        if pos == -1:
            pos = cut.rfind(" ")
        if pos == -1:
            pos = max_len

        chunks.append(remaining[:pos])
        remaining = remaining[pos:].lstrip()
    return chunks


def render_for_telegram(text: str, mode: RenderMode) -> tuple[str, str | None]:
    """Render assistant text for Telegram send APIs."""
    if mode == "plain":
        return text, None
    return markdown_to_telegram_html(text), ParseMode.HTML


def markdown_to_telegram_html(text: str) -> str:
    """Convert markdown-ish text to Telegram-safe HTML."""
    if not text:
        return ""

    code_blocks: list[tuple[str, str]] = []

    def save_code_block(match: re.Match[str]) -> str:
        lang = (match.group(1) or "").strip()
        code = match.group(2) or ""
        code_blocks.append((lang, code))
        return f"\x00CB{len(code_blocks) - 1}\x00"

    parsed = re.sub(r"```([a-zA-Z0-9_+-]*)\n?([\s\S]*?)```", save_code_block, text)

    inline_codes: list[str] = []

    def save_inline_code(match: re.Match[str]) -> str:
        inline_codes.append(match.group(1))
        return f"\x00IC{len(inline_codes) - 1}\x00"

    parsed = re.sub(r"`([^`]+)`", save_inline_code, parsed)

    parsed = re.sub(r"^#{1,6}\s+(.+)$", r"\1", parsed, flags=re.MULTILINE)
    parsed = re.sub(r"^>\s*(.*)$", r"\1", parsed, flags=re.MULTILINE)
    parsed = parsed.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    def replace_link(match: re.Match[str]) -> str:
        label = match.group(1)
        href = match.group(2)
        # The full string was already HTML-escaped above; only escape quotes
        # to keep href attribute boundaries safe.
        safe_href = href.replace('"', "&quot;")
        return f'<a href="{safe_href}">{label}</a>'

    parsed = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", replace_link, parsed)
    parsed = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", parsed)
    parsed = re.sub(r"__(.+?)__", r"<b>\1</b>", parsed)
    parsed = re.sub(r"(?<![a-zA-Z0-9])_([^_]+)_(?![a-zA-Z0-9])", r"<i>\1</i>", parsed)
    parsed = re.sub(r"~~(.+?)~~", r"<s>\1</s>", parsed)
    parsed = re.sub(r"^[-*]\s+", "• ", parsed, flags=re.MULTILINE)

    for idx, code in enumerate(inline_codes):
        escaped = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        parsed = parsed.replace(f"\x00IC{idx}\x00", f"<code>{escaped}</code>")

    for idx, (lang, code) in enumerate(code_blocks):
        escaped = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if lang:
            parsed = parsed.replace(
                f"\x00CB{idx}\x00",
                f'<pre><code class="language-{lang}">{escaped}</code></pre>',
            )
        else:
            parsed = parsed.replace(f"\x00CB{idx}\x00", f"<pre><code>{escaped}</code></pre>")

    return parsed
