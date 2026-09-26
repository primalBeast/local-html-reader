"""Shared HTML shell for formats the viewer renders itself."""

from __future__ import annotations

import html as html_lib

PAGE_CSS = (
    "body{font-family:Segoe UI,system-ui,sans-serif;max-width:52rem;"
    "margin:1.5rem auto;padding:0 1.25rem 3rem;line-height:1.55;color:#1a1a1a;}"
    "pre,code{font-family:Cascadia Mono,Consolas,monospace;font-size:.9em;}"
    "pre{background:#f4f4f5;padding:.85rem 1rem;overflow:auto;border-radius:8px;white-space:pre-wrap;}"
    "table{border-collapse:collapse;margin:.75rem 0;}"
    "td,th{border:1px solid #ccc;padding:.35rem .55rem;vertical-align:top;}"
    "th{background:#f4f4f5;text-align:left;}"
    "img{max-width:100%;height:auto;}"
    "p{margin:.55rem 0;}"
    "h1,h2,h3{line-height:1.25;}"
    ".note{color:#555;font-size:.9rem;}"
    ".slide{border-top:1px solid #e4e4e7;margin-top:1.25rem;padding-top:.85rem;}"
    ".cell{margin:0 0 1rem;}"
    ".out{color:#333;}"
)

# Keep the iframe responsive. Search still reads the whole file up to the extract cap.
VIEW_CHAR_CAP = 1_500_000


def html_page(title: str, body: str) -> str:
    safe = html_lib.escape(title)
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        f"<title>{safe}</title><style>{PAGE_CSS}</style></head><body>{body}</body></html>"
    )


def pre_block(text: str) -> str:
    note = ""
    shown = text
    if len(shown) > VIEW_CHAR_CAP:
        shown = shown[:VIEW_CHAR_CAP]
        note = "<p class='note'>Showing the first part of this file.</p>"
    return note + f"<pre>{html_lib.escape(shown)}</pre>"
