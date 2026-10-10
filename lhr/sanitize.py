"""Remove active content from HTML the reader generates (Markdown, Word, EPUB)."""

from __future__ import annotations

import html as html_lib
from html.parser import HTMLParser

_DROP = frozenset(
    {
        "script",
        "iframe",
        "object",
        "embed",
        "form",
        "input",
        "button",
        "textarea",
        "select",
        "option",
        "link",
        "meta",
        "base",
        "svg",
        "math",
        "applet",
        "frame",
        "frameset",
        "noscript",
        "template",
        "style",
    }
)
_VOID = frozenset({"br", "hr", "img", "wbr", "col", "source", "track", "area"})
_URL_ATTRS = frozenset({"href", "src", "poster", "cite"})
_KEEP_ATTRS = frozenset(
    {
        "alt",
        "title",
        "colspan",
        "rowspan",
        "span",
        "width",
        "height",
        "align",
        "start",
        "reversed",
        "open",
        "id",
        "class",
        "headers",
        "scope",
        "abbr",
    }
)


def _safe_url(value: str) -> str | None:
    text = (value or "").replace("\x00", "").strip()
    if not text:
        return None
    folded = "".join(text.lower().split())
    if folded.startswith(("javascript:", "vbscript:")):
        return None
    if folded.startswith("data:"):
        if folded.startswith(("data:image/png", "data:image/jpeg", "data:image/gif", "data:image/webp")):
            return text
        return None
    if folded.startswith(("http://", "https://", "mailto:", "#", "/", "./", "../")):
        return text
    head = folded.split("/", 1)[0]
    if ":" in head:
        return None
    return text


class _Clean(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._start(tag, attrs, close=False)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._start(tag, attrs, close=True)

    def _start(self, tag: str, attrs: list[tuple[str, str | None]], *, close: bool) -> None:
        name = tag.lower()
        if self._skip:
            if name in _DROP and not close:
                self._skip += 1
            return
        if name in _DROP:
            if not close:
                self._skip += 1
            return
        if not name.isidentifier() and not name.replace("-", "").isalnum():
            return
        kept: list[str] = []
        for key, raw in attrs:
            attr = key.lower()
            if attr.startswith("on") or attr in {"style", "srcdoc", "formaction"}:
                continue
            value = "" if raw is None else str(raw)
            if attr in _URL_ATTRS:
                safe = _safe_url(value)
                if not safe:
                    continue
                value = safe
            elif attr not in _KEEP_ATTRS:
                continue
            kept.append(f' {attr}="{html_lib.escape(value, quote=True)}"')
        if name in _VOID or close:
            self.parts.append(f"<{name}{''.join(kept)}>")
            return
        self.parts.append(f"<{name}{''.join(kept)}>")

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        if self._skip:
            if name in _DROP:
                self._skip -= 1
            return
        if name in _DROP or name in _VOID:
            return
        self.parts.append(f"</{name}>")

    def handle_data(self, data: str) -> None:
        if self._skip or not data:
            return
        self.parts.append(html_lib.escape(data))

    def handle_entityref(self, name: str) -> None:
        if self._skip:
            return
        self.parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self._skip:
            return
        self.parts.append(f"&#{name};")


def sanitize_html(fragment: str) -> str:
    """Return a fragment with scripts, handlers, and dangerous URLs removed."""
    cleaner = _Clean()
    try:
        cleaner.feed(fragment or "")
        cleaner.close()
    except Exception:
        return html_lib.escape(fragment or "")
    return "".join(cleaner.parts)
