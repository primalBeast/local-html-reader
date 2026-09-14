"""Plain-text extraction for search: HTML, Markdown, and PDF."""

from __future__ import annotations

from pathlib import Path

from lhr.html_text import html_visible_text

HTML_SUFFIXES = {".html", ".htm"}
MARKDOWN_SUFFIXES = {".md", ".markdown"}
PDF_SUFFIXES = {".pdf"}
DOC_SUFFIXES = HTML_SUFFIXES | MARKDOWN_SUFFIXES | PDF_SUFFIXES


def extract_search_text(path: Path, *, root: Path | None = None, max_bytes: int = 8 * 1024 * 1024) -> str:
    suffix = path.suffix.lower()
    if suffix in HTML_SUFFIXES:
        try:
            size = path.stat().st_size
        except OSError:
            return ""
        if size > max_bytes:
            return ""
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        return html_visible_text(raw, html_path=path, root=root)
    if suffix in MARKDOWN_SUFFIXES:
        try:
            size = path.stat().st_size
        except OSError:
            return ""
        if size > max_bytes:
            return ""
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
    if suffix in PDF_SUFFIXES:
        return _pdf_text(path, max_bytes=max_bytes)
    return ""


def _pdf_text(path: Path, *, max_bytes: int) -> str:
    try:
        size = path.stat().st_size
    except OSError:
        return ""
    if size > max_bytes:
        return ""
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    try:
        reader = PdfReader(str(path), strict=False)
        if getattr(reader, "is_encrypted", False):
            try:
                reader.decrypt("")
            except Exception:
                return ""
        parts: list[str] = []
        for page in reader.pages[:200]:
            try:
                parts.append(page.extract_text() or "")
            except Exception:
                continue
        return "\n".join(parts)
    except Exception:
        return ""
