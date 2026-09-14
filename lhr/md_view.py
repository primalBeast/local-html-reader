"""Render Markdown to a simple HTML page for the in-app viewer."""

from __future__ import annotations

import html as html_lib


def markdown_to_html_page(title: str, source: str) -> str:
    try:
        import markdown
    except ImportError:
        body = f"<pre>{html_lib.escape(source)}</pre>"
    else:
        body = markdown.markdown(
            source,
            extensions=["fenced_code", "tables", "nl2br", "sane_lists"],
        )
    safe_title = html_lib.escape(title)
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        f"<title>{safe_title}</title>"
        "<style>"
        "body{font-family:Segoe UI,system-ui,sans-serif;max-width:48rem;"
        "margin:1.5rem auto;padding:0 1.25rem 3rem;line-height:1.55;color:#1a1a1a;}"
        "pre,code{font-family:Cascadia Mono,Consolas,monospace;font-size:.9em;}"
        "pre{background:#f4f4f5;padding:.85rem 1rem;overflow:auto;border-radius:8px;}"
        "table{border-collapse:collapse;} td,th{border:1px solid #ccc;padding:.35rem .55rem;}"
        "img{max-width:100%;}"
        "</style></head><body>"
        f"{body}</body></html>"
    )
