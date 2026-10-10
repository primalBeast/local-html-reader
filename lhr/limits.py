"""Document size and search caps.

Every cap below is four times the previous value. Help (`/api/help`) describes
the same numbers, per format.
"""

from __future__ import annotations

_MB = 1024 * 1024

# Was 128 MB. Files larger than this are not searched or opened.
SEARCH_BYTES = 512 * _MB
# Was 8,000. File-list badge and Find in page share this ceiling.
MATCH_CAP = 32_000
# Was 1,500,000. Viewer cutoff for generated pages (the file list still searches further).
VIEW_CHAR_CAP = 6_000_000
# Was 4,000 rows and 60 columns.
MAX_TABLE_ROWS = 16_000
MAX_TABLE_COLS = 240
# Was 32 MB. One uncompressed member inside a zip-based document.
MAX_MEMBER_BYTES = 128 * _MB
# Was 8 MB. Larger XML is treated as plain text instead of a parsed tree.
XML_PARSE_CAP = 32 * _MB
# Was 4,000. CSV/TSV cells shown in the page.
MAX_CELL_CHARS = 16_000
# Was 20. Blank columns marked as repeated in an OpenDocument table.
MAX_COLUMN_REPEAT = 80


def _exts(suffixes: set[str]) -> list[str]:
    return sorted(suffixes)


def help_document() -> dict:
    """Formats the reader opens, and the limits that apply to each one."""
    from lhr.extra_view import (
        EPUB_SUFFIXES,
        IPYNB_SUFFIXES,
        JSON_SUFFIXES,
        ODT_SUFFIXES,
        ODS_SUFFIXES,
        PLAIN_PRE_SUFFIXES,
        PPTX_SUFFIXES,
        RTF_SUFFIXES,
        TABLE_SUFFIXES,
        XLSX_SUFFIXES,
        XML_SUFFIXES,
    )
    from lhr.extract import DOCX_SUFFIXES, HTML_SUFFIXES, MARKDOWN_SUFFIXES, PDF_SUFFIXES

    file_mb = SEARCH_BYTES // _MB
    member_mb = MAX_MEMBER_BYTES // _MB
    xml_mb = XML_PARSE_CAP // _MB
    hits = f"{MATCH_CAP:,}"
    view = f"{VIEW_CHAR_CAP:,}"
    rows = f"{MAX_TABLE_ROWS:,}"
    cols = f"{MAX_TABLE_COLS:,}"
    cell = f"{MAX_CELL_CHARS:,}"
    repeat = f"{MAX_COLUMN_REPEAT:,}"

    return {
        "shared": [
            {
                "label": "File size",
                "detail": f"A file larger than {file_mb} MB is not searched or opened.",
            },
            {
                "label": "Search hits",
                "detail": f"The file list and Find in page both stop at {hits} hits.",
            },
        ],
        "formats": [
            {
                "name": "HTML",
                "extensions": _exts(HTML_SUFFIXES),
                "limits": [
                    f"Searched and shown up to {file_mb} MB. The page is the file itself, with no shorter cutoff.",
                    "Search uses the visible text, not scripts or tags.",
                    "Scripts in the file do not run. Allow scripts on that file only if you trust it; the file still cannot call the app.",
                ],
            },
            {
                "name": "Markdown",
                "extensions": _exts(MARKDOWN_SUFFIXES),
                "limits": [
                    f"Searched as the source file, up to {file_mb} MB.",
                    "The page is rendered, so markup characters such as # and * can match the file list and not Find in page.",
                ],
            },
            {
                "name": "PDF",
                "extensions": _exts(PDF_SUFFIXES),
                "limits": [
                    f"Searched and opened up to {file_mb} MB.",
                    "Find in page uses the PDF text layer.",
                ],
            },
            {
                "name": "Word",
                "extensions": _exts(DOCX_SUFFIXES),
                "limits": [
                    f"Searched and opened up to {file_mb} MB.",
                    "Legacy .doc files are not opened.",
                ],
            },
            {
                "name": "Plain text",
                "extensions": _exts(PLAIN_PRE_SUFFIXES),
                "limits": [
                    f"Searched up to {file_mb} MB.",
                    f"The open page shows the first {view} characters. The file list can still match text past that.",
                ],
            },
            {
                "name": "CSV and TSV",
                "extensions": _exts(TABLE_SUFFIXES),
                "limits": [
                    f"The file list searches the raw file, up to {file_mb} MB, including quotes and rows the page does not show.",
                    f"The page shows the first {rows} rows and {cols} columns.",
                    f"A cell on the page is cut off after {cell} characters.",
                ],
            },
            {
                "name": "JSON",
                "extensions": _exts(JSON_SUFFIXES),
                "limits": [
                    f"The file list searches the file as stored, up to {file_mb} MB.",
                    f"The page is pretty-printed and stops at {view} characters, so spacing can differ from the file list.",
                ],
            },
            {
                "name": "XML",
                "extensions": _exts(XML_SUFFIXES),
                "limits": [
                    f"Up to {xml_mb} MB, the file list searches the text inside tags and the page shows the markup.",
                    f"The page stops at {view} characters.",
                    f"A larger file, up to {file_mb} MB, is treated as plain text instead of a parsed document.",
                ],
            },
            {
                "name": "Rich text",
                "extensions": _exts(RTF_SUFFIXES),
                "limits": [
                    "The file list and the page use the same extracted words.",
                    f"The page stops at {view} characters.",
                    f"The file itself must be within {file_mb} MB.",
                ],
            },
            {
                "name": "OpenDocument text",
                "extensions": _exts(ODT_SUFFIXES),
                "limits": [
                    f"The file must be within {file_mb} MB, and each file inside it within {member_mb} MB.",
                    "The file list includes document text plus stored table values, so a value can be counted when the page does not show it the same way.",
                    f"Tables stop at {rows} rows and {cols} columns. A repeated blank column expands at most {repeat} times.",
                ],
            },
            {
                "name": "OpenDocument spreadsheet",
                "extensions": _exts(ODS_SUFFIXES),
                "limits": [
                    f"The file must be within {file_mb} MB, and each file inside it within {member_mb} MB.",
                    f"Each sheet stops at {rows} rows and {cols} columns in both search and the page.",
                    "The file list also counts stored cell values, so a number can count twice.",
                    f"A repeated blank column expands at most {repeat} times.",
                ],
            },
            {
                "name": "Excel",
                "extensions": _exts(XLSX_SUFFIXES),
                "limits": [
                    f"The file must be within {file_mb} MB, and each file inside it within {member_mb} MB.",
                    f"Search and the page both stop at {rows} rows and {cols} columns per sheet.",
                    "Dates are the stored number, not the formatted date. Legacy .xls files are not opened.",
                ],
            },
            {
                "name": "PowerPoint",
                "extensions": _exts(PPTX_SUFFIXES),
                "limits": [
                    f"The file must be within {file_mb} MB, and each file inside it within {member_mb} MB.",
                    "Slide text is searched and shown, with no row cutoff. Legacy .ppt files are not opened.",
                ],
            },
            {
                "name": "EPUB",
                "extensions": _exts(EPUB_SUFFIXES),
                "limits": [
                    f"The book must be within {file_mb} MB, and each chapter file inside it within {member_mb} MB.",
                    "The file list searches the visible chapter text. Scripts are not run.",
                    f"The page stops at {view} characters and adds a chapter heading.",
                ],
            },
            {
                "name": "Jupyter notebook",
                "extensions": _exts(IPYNB_SUFFIXES),
                "limits": [
                    f"Searched as the raw cell source and text output, up to {file_mb} MB.",
                    "The page renders Markdown, so markup characters can match the file list and not Find in page.",
                ],
            },
        ],
        "skipped": "Any other extension is hidden. Legacy binary Office files (.doc, .xls, .ppt) are not opened.",
    }
