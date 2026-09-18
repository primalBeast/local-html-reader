"""Render Word (.docx / .dotx) to an HTML page for the in-app viewer."""

from __future__ import annotations

import html as html_lib
import logging
from pathlib import Path

logger = logging.getLogger("lhr.docx_view")

_PAGE_CSS = (
    "body{font-family:Segoe UI,system-ui,sans-serif;max-width:48rem;"
    "margin:1.5rem auto;padding:0 1.25rem 3rem;line-height:1.55;color:#1a1a1a;}"
    "pre,code{font-family:Cascadia Mono,Consolas,monospace;font-size:.9em;}"
    "pre{background:#f4f4f5;padding:.85rem 1rem;overflow:auto;border-radius:8px;}"
    "table{border-collapse:collapse;} td,th{border:1px solid #ccc;padding:.35rem .55rem;}"
    "img{max-width:100%;height:auto;}"
    "p{margin:.55rem 0;}"
)


def docx_to_html_page(title: str, path: Path) -> str:
    safe_title = html_lib.escape(title)
    try:
        import mammoth
    except ImportError:
        body = "<p>mammoth is not installed; cannot render this Word document.</p>"
    else:
        try:
            with path.open("rb") as fh:
                result = mammoth.convert_to_html(fh)
            body = (result.value or "").strip() or "<p>(empty document)</p>"
        except Exception:
            logger.debug("DOCX render failed for %s", path, exc_info=True)
            body = "<p>Could not open this Word document.</p>"
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        f"<title>{safe_title}</title>"
        f"<style>{_PAGE_CSS}</style></head><body>"
        f"{body}</body></html>"
    )
