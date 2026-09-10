"""Extract searchable document text (page body, including collapsed sections)."""

from __future__ import annotations

from html.parser import HTMLParser

SKIP_TAGS = frozenset({"script", "style", "noscript", "template", "head"})
VOID_TAGS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)


def _is_inert_hidden(tag: str, attrs: list[tuple[str, str | None]]) -> bool:
    """True for non-collapsible hidden nodes (not CSS-collapsed sections)."""
    ad = {k.lower(): (v or "") for k, v in attrs}
    if tag == "input" and ad.get("type", "").lower() == "hidden":
        return True
    if "hidden" in ad:
        return True
    if ad.get("aria-hidden", "").lower() == "true":
        return True
    return False


class VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._stack: list[tuple[str, bool, bool]] = []
        self.chunks: list[str] = []

    def _blocked(self) -> bool:
        return any(skip or hid for _tag, skip, hid in self._stack)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in VOID_TAGS:
            return
        skip = tag in SKIP_TAGS
        hid = _is_inert_hidden(tag, attrs)
        self._stack.append((tag, skip, hid))

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                del self._stack[i:]
                return

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        return

    def handle_data(self, data: str) -> None:
        if data and not self._blocked():
            self.chunks.append(data)

    def handle_comment(self, _data: str) -> None:
        return


def html_visible_text(raw: str, html_path: object | None = None, root: object | None = None) -> str:
    """Body text including collapsed/disclosure sections; not scripts, tags, or comments."""
    parser = VisibleTextParser()
    try:
        parser.feed(raw)
        parser.close()
    except Exception:
        return ""
    return "".join(parser.chunks)
