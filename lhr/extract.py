"""Plain-text extraction for search: HTML, Markdown, PDF, and Word."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from lhr.html_text import html_visible_text

logger = logging.getLogger("lhr.extract")

HTML_SUFFIXES = {".html", ".htm"}
MARKDOWN_SUFFIXES = {".md", ".markdown"}
PDF_SUFFIXES = {".pdf"}
DOCX_SUFFIXES = {".docx", ".dotx"}
DOC_SUFFIXES = HTML_SUFFIXES | MARKDOWN_SUFFIXES | PDF_SUFFIXES | DOCX_SUFFIXES


def text_matches_query(
    text: str,
    needle: str,
    *,
    regex: bool = False,
    match_case: bool = False,
    whole_word: bool = False,
) -> bool:
    """Match needle in extracted document text."""
    raw = (needle or "").strip()
    if not raw:
        return True
    flags = re.UNICODE
    if not match_case:
        flags |= re.IGNORECASE
    if regex:
        source = raw
        flags |= re.DOTALL
    else:
        source = re.escape(raw)
    if whole_word:
        source = rf"(?<![\w])(?:{source})(?![\w])"
    try:
        pat = re.compile(source, flags)
    except re.error:
        return False
    if pat.search(text):
        return True
    if whole_word:
        return False
    compact = "".join(text.split())
    if pat.search(compact):
        return True
    if not regex:
        compact_q = "".join(raw.split())
        if not compact_q:
            return False
        if match_case:
            return compact_q in compact
        return compact_q.lower() in compact.lower()
    return False


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
    if suffix in DOCX_SUFFIXES:
        return _docx_text(path, max_bytes=max_bytes)
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
        from pypdf.errors import DependencyError
    except ImportError:
        return ""
    try:
        reader = PdfReader(str(path), strict=False)
        if getattr(reader, "is_encrypted", False):
            try:
                reader.decrypt("")
            except DependencyError:
                logger.warning("PDF %s is encrypted; cryptography is required to search it", path)
                return ""
            except Exception:
                logger.debug("Could not decrypt PDF %s", path, exc_info=True)
                return ""
        parts: list[str] = []
        for page in reader.pages[:200]:
            try:
                parts.append(page.extract_text() or "")
            except DependencyError:
                logger.warning("PDF %s needs cryptography to extract text", path)
                return ""
            except Exception:
                continue
        return "\n".join(parts)
    except Exception:
        logger.debug("PDF extract failed for %s", path, exc_info=True)
        return ""


def _docx_text(path: Path, *, max_bytes: int) -> str:
    try:
        size = path.stat().st_size
    except OSError:
        return ""
    if size > max_bytes:
        return ""
    try:
        import mammoth
    except ImportError:
        return ""
    try:
        with path.open("rb") as fh:
            return mammoth.extract_raw_text(fh).value or ""
    except Exception:
        logger.debug("DOCX extract failed for %s", path, exc_info=True)
        return ""
