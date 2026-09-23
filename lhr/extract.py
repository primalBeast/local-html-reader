"""Plain-text extraction for search: HTML, Markdown, PDF, and Word."""

from __future__ import annotations

import html as html_lib
import logging
import re
from pathlib import Path

from lhr.html_text import html_visible_text

logger = logging.getLogger("lhr.extract")

# DocGen HTML exports are often 10–80 MiB. A lower cap made real pages unsearchable.
MAX_SEARCH_BYTES = 128 * 1024 * 1024

HTML_SUFFIXES = {".html", ".htm"}
MARKDOWN_SUFFIXES = {".md", ".markdown"}
PDF_SUFFIXES = {".pdf"}
DOCX_SUFFIXES = {".docx", ".dotx"}
DOC_SUFFIXES = HTML_SUFFIXES | MARKDOWN_SUFFIXES | PDF_SUFFIXES | DOCX_SUFFIXES

# Drop scripts, styles, comments, and tags so a literal can still match text split by markup.
_MARKUP_RE = re.compile(
    rb"(?is)<(script|style|noscript|template)\b[^>]*>.*?</\1>|<!--.*?-->|<[^>]+>"
)
# PDF text extractors often emit "0 4 4 1 4 7 J" for "044147J". Only those
# single-character runs are collapsed — not newlines between real tokens.
_GLYPH_RUN = re.compile(r"(?<!\w)(?:\w[ \t\r\n]+){1,}\w(?!\w)")


def _collapse_glyph_spaces(text: str) -> str:
    return _GLYPH_RUN.sub(lambda m: re.sub(r"[ \t\r\n]+", "", m.group(0)), text)


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
    return (
        count_text_matches(
            text,
            raw,
            regex=regex,
            match_case=match_case,
            whole_word=whole_word,
        )
        > 0
    )


def count_text_matches(
    text: str,
    needle: str,
    *,
    regex: bool = False,
    match_case: bool = False,
    whole_word: bool = False,
) -> int:
    """How many times the query occurs, using the same rules as a hit."""
    raw = (needle or "").strip()
    if not raw:
        return 0
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
        return 0
    return count_query_matches(
        text,
        raw,
        pat,
        regex=regex,
        match_case=match_case,
        whole_word=whole_word,
    )


def count_query_matches(
    text: str,
    raw: str,
    pat: re.Pattern[str],
    *,
    regex: bool,
    match_case: bool,
    whole_word: bool,
) -> int:
    """How many times the query occurs, using the same rules as a hit."""
    count = _count_pattern(pat, text)
    if count or whole_word:
        return count
    collapsed = _collapse_glyph_spaces(text)
    if collapsed != text:
        count = _count_pattern(pat, collapsed)
        if count:
            return count
    if regex:
        return 0
    compact_q = "".join(raw.split())
    if not compact_q or compact_q == raw:
        return 0
    hay = collapsed if match_case else collapsed.lower()
    probe = compact_q if match_case else compact_q.lower()
    return _count_substring(hay, probe)


def _count_pattern(pat: re.Pattern[str], text: str) -> int:
    count = 0
    for match in pat.finditer(text):
        if match.end() == match.start():
            continue
        count += 1
    return count


def _count_substring(hay: str, probe: str) -> int:
    if not probe:
        return 0
    count = 0
    start = 0
    step = max(1, len(probe))
    while True:
        found = hay.find(probe, start)
        if found < 0:
            return count
        count += 1
        start = found + step


def literal_might_match(path: Path, needle: str, *, match_case: bool = False) -> bool:
    """False only when a literal needle cannot be in this HTML or Markdown file.

    PDF and Word stay True: their text is compressed, so the raw bytes are not the document text.
    Large HTML is checked for the contiguous needle only. Smaller HTML also allows the needle
    to be split by tags.
    """
    raw = (needle or "").strip()
    if not raw or not raw.isascii():
        return True
    suffix = path.suffix.lower()
    if suffix not in HTML_SUFFIXES and suffix not in MARKDOWN_SUFFIXES:
        return True
    try:
        size = path.stat().st_size
    except OSError:
        return False
    if size > MAX_SEARCH_BYTES:
        return False
    try:
        data = path.read_bytes()
    except OSError:
        return False
    flags = 0 if match_case else re.IGNORECASE
    if re.search(re.escape(raw).encode("ascii", errors="ignore"), data, flags):
        return True
    if suffix not in HTML_SUFFIXES or size > 4 * 1024 * 1024:
        return False
    stripped = _MARKUP_RE.sub(b"", data)
    if re.search(re.escape(raw).encode("ascii", errors="ignore"), stripped, flags):
        return True
    if b"&" not in stripped:
        return False
    decoded = html_lib.unescape(stripped.decode("utf-8", errors="replace"))
    probe = raw if match_case else raw.lower()
    if not match_case:
        decoded = decoded.lower()
    return probe in decoded or probe in "".join(decoded.split())


def extract_search_text(path: Path, *, root: Path | None = None, max_bytes: int = MAX_SEARCH_BYTES) -> str:
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
    text = _pdf_text_pdfium(path)
    if text.strip():
        return text
    return _pdf_text_pypdf(path)


def _pdf_text_pdfium(path: Path) -> str:
    """Visible page text, using the same PDFium engine family as the viewer."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return ""
    pdf = None
    try:
        try:
            pdf = pdfium.PdfDocument(str(path))
        except Exception:
            pdf = pdfium.PdfDocument(str(path), password="")
        parts: list[str] = []
        for index in range(len(pdf)):
            page = pdf[index]
            try:
                textpage = page.get_textpage()
                try:
                    parts.append(textpage.get_text_bounded() or "")
                finally:
                    textpage.close()
            finally:
                page.close()
        return "\n".join(parts)
    except Exception:
        logger.debug("PDFium extract failed for %s", path, exc_info=True)
        return ""
    finally:
        if pdf is not None:
            pdf.close()


def _pdf_text_pypdf(path: Path) -> str:
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
        for page in reader.pages:
            try:
                chunks: list[str] = []

                def visitor(text: str, _cm: object, _tm: object, _font: object, _size: object) -> None:
                    if text:
                        chunks.append(text)

                page.extract_text(visitor_text=visitor) or ""
                parts.append("".join(chunks) or page.extract_text() or "")
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
