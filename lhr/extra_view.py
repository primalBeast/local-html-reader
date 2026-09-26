"""List, search, and render the document types added after HTML, Markdown, PDF, and Word.

Plain text, CSV, JSON, XML, YAML, TOML, INI, RTF, OpenDocument, Excel, PowerPoint,
EPUB, and Jupyter notebooks. Zip-based formats are read with the standard library.
"""

from __future__ import annotations

import csv
import html as html_lib
import io
import json
import logging
import posixpath
import re
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import unquote
from zipfile import BadZipFile, ZipFile

from lhr.html_text import html_visible_text
from lhr.page_html import VIEW_CHAR_CAP, html_page, pre_block
from lhr.rtf_text import rtf_to_text

logger = logging.getLogger("lhr.extra_view")

PLAIN_PRE_SUFFIXES = {".txt", ".text", ".log", ".yaml", ".yml", ".toml", ".ini", ".cfg"}
TABLE_SUFFIXES = {".csv", ".tsv"}
JSON_SUFFIXES = {".json"}
XML_SUFFIXES = {".xml"}
RTF_SUFFIXES = {".rtf"}
ODT_SUFFIXES = {".odt"}
ODS_SUFFIXES = {".ods"}
XLSX_SUFFIXES = {".xlsx", ".xlsm"}
PPTX_SUFFIXES = {".pptx", ".ppsx"}
EPUB_SUFFIXES = {".epub"}
IPYNB_SUFFIXES = {".ipynb"}

EXTRA_SUFFIXES = (
    PLAIN_PRE_SUFFIXES
    | TABLE_SUFFIXES
    | JSON_SUFFIXES
    | XML_SUFFIXES
    | RTF_SUFFIXES
    | ODT_SUFFIXES
    | ODS_SUFFIXES
    | XLSX_SUFFIXES
    | PPTX_SUFFIXES
    | EPUB_SUFFIXES
    | IPYNB_SUFFIXES
)

# Visible text is a contiguous substring of the file bytes (no markup, no zip).
PLAIN_BYTE_SUFFIXES = PLAIN_PRE_SUFFIXES | TABLE_SUFFIXES | JSON_SUFFIXES | IPYNB_SUFFIXES

_MAX_TABLE_ROWS = 4000
_MAX_TABLE_COLS = 60
_MAX_MEMBER_BYTES = 32 * 1024 * 1024
_XML_PARSE_CAP = 8 * 1024 * 1024

_ODF_ROW_GROUPS = {"table-header-rows", "table-rows", "table-row-group"}


def extract_extra_text(path: Path, *, max_bytes: int) -> str:
    suffix = path.suffix.lower()
    if suffix not in EXTRA_SUFFIXES:
        return ""
    if not _within_size(path, max_bytes):
        return ""
    try:
        if suffix in PLAIN_PRE_SUFFIXES | TABLE_SUFFIXES | JSON_SUFFIXES:
            return _read_text(path)
        if suffix in XML_SUFFIXES:
            raw = _read_text(path)
            return _xml_text(raw) if raw else ""
        if suffix in RTF_SUFFIXES:
            return rtf_to_text(path.read_bytes())
        if suffix in ODT_SUFFIXES | ODS_SUFFIXES:
            return _odf_text(path)
        if suffix in XLSX_SUFFIXES:
            return _xlsx_text(path)
        if suffix in PPTX_SUFFIXES:
            return _pptx_text(path)
        if suffix in EPUB_SUFFIXES:
            return _epub_text(path)
        if suffix in IPYNB_SUFFIXES:
            return _notebook_text(_read_text(path))
    except Exception:
        logger.debug("Extract failed for %s", path, exc_info=True)
        return ""
    return ""


def render_extra(path: Path) -> str:
    """HTML page for the in-app viewer. Failures stay inside the page."""
    title = path.name
    suffix = path.suffix.lower()
    try:
        from lhr.extract import MAX_SEARCH_BYTES

        if not _within_size(path, MAX_SEARCH_BYTES):
            return html_page(title, "<p>This file is too large to open.</p>")
        if suffix in PLAIN_PRE_SUFFIXES:
            return html_page(title, pre_block(_read_text(path)))
        if suffix in TABLE_SUFFIXES:
            delim = "\t" if suffix == ".tsv" else None
            return html_page(title, _table_html(_read_text(path), delimiter=delim))
        if suffix in JSON_SUFFIXES:
            return html_page(title, _json_html(_read_text(path)))
        if suffix in XML_SUFFIXES:
            return html_page(title, _xml_html(_read_text(path)))
        if suffix in RTF_SUFFIXES:
            return html_page(title, _paragraphs_html(rtf_to_text(path.read_bytes())))
        if suffix in ODT_SUFFIXES:
            return html_page(title, _odt_html(path))
        if suffix in ODS_SUFFIXES:
            return html_page(title, _ods_html(path))
        if suffix in XLSX_SUFFIXES:
            return html_page(title, _xlsx_html(path))
        if suffix in PPTX_SUFFIXES:
            return html_page(title, _pptx_html(path))
        if suffix in EPUB_SUFFIXES:
            return html_page(title, _epub_html(path))
        if suffix in IPYNB_SUFFIXES:
            return html_page(title, _notebook_html(_read_text(path)))
    except Exception:
        logger.debug("Render failed for %s", path, exc_info=True)
        return html_page(title, "<p>Could not open this file.</p>")
    return html_page(title, "<p>This file type cannot be shown.</p>")


def _within_size(path: Path, max_bytes: int) -> bool:
    try:
        return path.stat().st_size <= max_bytes
    except OSError:
        return False


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""


def _paragraphs_html(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return "<p>(empty document)</p>"
    if len(stripped) > VIEW_CHAR_CAP:
        stripped = stripped[:VIEW_CHAR_CAP]
        note = "<p class='note'>Showing the first part of this file.</p>"
    else:
        note = ""
    blocks = re.split(r"\n{2,}", stripped)
    parts = [f"<p>{html_lib.escape(block).replace(chr(10), '<br>')}</p>" for block in blocks if block.strip()]
    return note + "".join(parts)


def _table_html(text: str, *, delimiter: str | None) -> str:
    if not text.strip():
        return "<p>(empty file)</p>"
    delim = delimiter or _sniff_delimiter(text)
    rows: list[list[str]] = []
    truncated = False
    try:
        reader = csv.reader(io.StringIO(text), delimiter=delim)
        for index, row in enumerate(reader):
            if index >= _MAX_TABLE_ROWS:
                truncated = True
                break
            rows.append([cell[:4000] for cell in row[:_MAX_TABLE_COLS]])
    except csv.Error:
        return pre_block(text)
    if not rows:
        return "<p>(empty file)</p>"
    note = "<p class='note'>Showing the first rows of this table.</p>" if truncated else ""
    header, body = rows[0], rows[1:]
    if not body:
        cells = "".join(f"<td>{html_lib.escape(cell)}</td>" for cell in header)
        return note + f"<table><tr>{cells}</tr></table>"
    head = "".join(f"<th>{html_lib.escape(cell)}</th>" for cell in header)
    body_html = []
    for row in body:
        padded = row + [""] * max(0, len(header) - len(row))
        cells = "".join(f"<td>{html_lib.escape(cell)}</td>" for cell in padded[: max(len(header), 1)])
        body_html.append(f"<tr>{cells}</tr>")
    return note + f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body_html)}</tbody></table>"


def _sniff_delimiter(text: str) -> str:
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        return ","
    delim = dialect.delimiter or ","
    return delim if delim in ",;\t|" else ","


def _json_html(text: str) -> str:
    if not text.strip():
        return "<p>(empty file)</p>"
    try:
        pretty = json.dumps(json.loads(text), indent=2, ensure_ascii=False)
    except json.JSONDecodeError:
        pretty = text
    return pre_block(pretty)


def _xml_text(raw: str) -> str:
    if len(raw.encode("utf-8", errors="replace")) > _XML_PARSE_CAP:
        return raw
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return raw
    parts = [chunk.strip() for chunk in root.itertext() if chunk and chunk.strip()]
    return "\n".join(parts)


def _xml_html(text: str) -> str:
    if not text.strip():
        return "<p>(empty file)</p>"
    if len(text.encode("utf-8", errors="replace")) > _XML_PARSE_CAP:
        return pre_block(text)
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return pre_block(text)
    try:
        ET.indent(root)
    except AttributeError:
        pass
    pretty = ET.tostring(root, encoding="unicode")
    return pre_block(pretty)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if tag else ""


def _attr(el: ET.Element, name: str) -> str | None:
    for key, value in el.attrib.items():
        if _local(key) == name:
            return value
    return None


@contextmanager
def _open_zip(path: Path):
    zf: ZipFile | None = None
    try:
        zf = ZipFile(path)
    except (BadZipFile, OSError):
        yield None
        return
    try:
        yield zf
    finally:
        zf.close()


def _member_bytes(zf: ZipFile, name: str) -> bytes | None:
    norm = posixpath.normpath(name.replace("\\", "/").lstrip("/"))
    if norm.startswith("../") or norm == "..":
        return None
    info = None
    key = norm
    try:
        info = zf.getinfo(norm)
    except KeyError:
        try:
            info = zf.getinfo(name)
            key = name
        except KeyError:
            return None
    if info.file_size > _MAX_MEMBER_BYTES:
        return None
    try:
        return zf.read(key)
    except (OSError, BadZipFile, RuntimeError):
        return None


def _read_xml_member(zf: ZipFile, name: str) -> ET.Element | None:
    data = _member_bytes(zf, name)
    if not data:
        return None
    try:
        return ET.fromstring(data)
    except ET.ParseError:
        return None


def _member_text(zf: ZipFile, name: str) -> str:
    data = _member_bytes(zf, name)
    if not data:
        return ""
    return data.decode("utf-8", errors="replace")


def _inline(el: ET.Element) -> str:
    bits: list[str] = []
    if el.text:
        bits.append(html_lib.escape(el.text))
    for child in list(el):
        name = _local(child.tag)
        if name == "tab":
            bits.append("&nbsp;&nbsp;")
        elif name in {"line-break", "s"}:
            bits.append("<br>" if name == "line-break" else " ")
        else:
            bits.append(_inline(child))
        if child.tail:
            bits.append(html_lib.escape(child.tail))
    return "".join(bits)


def _render_blocks(el: ET.Element) -> str:
    chunks: list[str] = []
    for child in list(el):
        name = _local(child.tag)
        if name == "h":
            try:
                level = min(6, max(1, int(_attr(child, "outline-level") or "1")))
            except ValueError:
                level = 1
            chunks.append(f"<h{level}>{_inline(child)}</h{level}>")
        elif name == "p":
            inner = _inline(child)
            if inner.strip():
                chunks.append(f"<p>{inner}</p>")
        elif name == "list":
            chunks.append("<ul>" + _render_list(child) + "</ul>")
        elif name == "table":
            chunks.append(_render_odf_table(child))
        else:
            chunks.append(_render_blocks(child))
    return "".join(chunks)


def _render_list(el: ET.Element) -> str:
    items: list[str] = []
    for child in list(el):
        if _local(child.tag) != "list-item":
            continue
        items.append("<li>" + _render_blocks(child) + "</li>")
    return "".join(items)


def _odf_rows(table_el: ET.Element) -> list[ET.Element]:
    rows: list[ET.Element] = []

    def take(el: ET.Element) -> None:
        for child in list(el):
            name = _local(child.tag)
            if name == "table-row":
                rows.append(child)
            elif name in _ODF_ROW_GROUPS:
                take(child)

    take(table_el)
    return rows


def _render_odf_table(table_el: ET.Element) -> str:
    body: list[str] = []
    truncated = False
    for index, row_el in enumerate(_odf_rows(table_el)):
        if index >= _MAX_TABLE_ROWS:
            truncated = True
            break
        cells: list[str] = []
        for cell in list(row_el):
            if _local(cell.tag) not in {"table-cell", "covered-table-cell"}:
                continue
            try:
                repeat = min(20, max(1, int(_attr(cell, "number-columns-repeated") or "1")))
            except ValueError:
                repeat = 1
            if _local(cell.tag) == "covered-table-cell":
                inner = ""
            else:
                inner = _render_blocks(cell) or html_lib.escape(_attr(cell, "value") or _attr(cell, "string-value") or "")
            for _ in range(repeat):
                cells.append(f"<td>{inner}</td>")
                if len(cells) >= _MAX_TABLE_COLS:
                    break
            if len(cells) >= _MAX_TABLE_COLS:
                break
        body.append("<tr>" + "".join(cells) + "</tr>")
    note = "<p class='note'>Showing the first rows of this sheet.</p>" if truncated else ""
    return note + "<table>" + "".join(body) + "</table>"


def _first_local(root: ET.Element, name: str) -> ET.Element | None:
    for el in root.iter():
        if _local(el.tag) == name:
            return el
    return None


def _odt_html(path: Path) -> str:
    with _open_zip(path) as zf:
        if zf is None:
            return "<p>Could not open this OpenDocument file.</p>"
        root = _read_xml_member(zf, "content.xml")
    if root is None:
        return "<p>Could not read this OpenDocument file.</p>"
    body = _first_local(root, "text")
    if body is None:
        return "<p>(empty document)</p>"
    rendered = _render_blocks(body)
    return rendered or "<p>(empty document)</p>"


def _ods_html(path: Path) -> str:
    with _open_zip(path) as zf:
        if zf is None:
            return "<p>Could not open this spreadsheet.</p>"
        root = _read_xml_member(zf, "content.xml")
    if root is None:
        return "<p>Could not read this spreadsheet.</p>"
    sheet = _first_local(root, "spreadsheet")
    tables = [child for child in list(sheet) if _local(child.tag) == "table"] if sheet is not None else []
    if not tables:
        return "<p>(empty spreadsheet)</p>"
    parts: list[str] = []
    for table in tables:
        name = _attr(table, "name")
        if name:
            parts.append(f"<h2>{html_lib.escape(name)}</h2>")
        parts.append(_render_odf_table(table))
    return "".join(parts)


def _odf_text(path: Path) -> str:
    with _open_zip(path) as zf:
        if zf is None:
            return ""
        root = _read_xml_member(zf, "content.xml")
    if root is None:
        return ""
    parts = [chunk.strip() for chunk in root.itertext() if chunk and chunk.strip()]
    values: list[str] = []
    for el in root.iter():
        if _local(el.tag) != "table-cell":
            continue
        for key in ("value", "string-value", "date-value"):
            raw = _attr(el, key)
            if raw:
                values.append(raw)
    return "\n".join(parts + values)


def _shared_strings(zf: ZipFile) -> list[str]:
    root = _read_xml_member(zf, "xl/sharedStrings.xml")
    if root is None:
        return []
    strings: list[str] = []
    for si in list(root):
        if _local(si.tag) != "si":
            continue
        bits = [node.text or "" for node in si.iter() if _local(node.tag) == "t"]
        strings.append("".join(bits))
    return strings


def _sheet_targets(zf: ZipFile) -> list[tuple[str, str]]:
    workbook = _read_xml_member(zf, "xl/workbook.xml")
    rels = _read_xml_member(zf, "xl/_rels/workbook.xml.rels")
    id_to_target: dict[str, str] = {}
    if rels is not None:
        for rel in rels.iter():
            if _local(rel.tag) != "Relationship":
                continue
            rid = _attr(rel, "Id")
            target = _attr(rel, "Target")
            if not rid or not target:
                continue
            target = unquote(target.split("#", 1)[0]).lstrip("/")
            if not target.startswith("xl/"):
                target = "xl/" + target.lstrip("/")
            id_to_target[rid] = posixpath.normpath(target)
    named: list[tuple[str, str]] = []
    if workbook is not None:
        for el in workbook.iter():
            if _local(el.tag) != "sheet":
                continue
            title = _attr(el, "name") or f"Sheet {len(named) + 1}"
            target = id_to_target.get(_attr(el, "id") or "")
            if target:
                named.append((title, target))
    if named:
        return named
    members = [
        name
        for name in zf.namelist()
        if re.search(r"(?:^|/)worksheets/sheet\d+\.xml$", name.replace("\\", "/"))
    ]
    members.sort(key=_trailing_number)
    return [(f"Sheet {index + 1}", name) for index, name in enumerate(members)]


def _col_index(ref: str) -> int:
    col = 0
    for ch in ref:
        if not ch.isalpha():
            break
        col = col * 26 + (ord(ch.upper()) - 64)
    return max(0, col - 1)


def _direct_child_text(el: ET.Element, name: str) -> str:
    for child in list(el):
        if _local(child.tag) == name:
            return child.text or ""
    return ""


def _cell_text(cell: ET.Element, strings: list[str]) -> str:
    kind = _attr(cell, "t") or ""
    if kind == "s":
        raw = _direct_child_text(cell, "v")
        try:
            return strings[int(raw)]
        except (ValueError, IndexError):
            return ""
    if kind == "inlineStr":
        return "".join(node.text or "" for node in cell.iter() if _local(node.tag) == "t")
    if kind == "b":
        return "TRUE" if _direct_child_text(cell, "v") == "1" else "FALSE"
    if kind == "e":
        return ""
    return _direct_child_text(cell, "v")


def _sheet_rows(zf: ZipFile, member: str, strings: list[str]) -> list[list[str]]:
    root = _read_xml_member(zf, member)
    if root is None:
        return []
    rows: list[list[str]] = []
    for row_el in root.iter():
        if _local(row_el.tag) != "row":
            continue
        if len(rows) >= _MAX_TABLE_ROWS:
            break
        slots: dict[int, str] = {}
        for cell in list(row_el):
            if _local(cell.tag) != "c":
                continue
            ref = _attr(cell, "r") or ""
            index = _col_index(ref) if ref else len(slots)
            if index >= _MAX_TABLE_COLS:
                continue
            slots[index] = _cell_text(cell, strings)
        if not slots:
            continue
        width = min(_MAX_TABLE_COLS, max(slots) + 1)
        rows.append([slots.get(col, "") for col in range(width)])
    return rows


def _xlsx_sheets(path: Path) -> list[tuple[str, list[list[str]]]]:
    with _open_zip(path) as zf:
        if zf is None:
            return []
        strings = _shared_strings(zf)
        sheets = []
        for title, member in _sheet_targets(zf):
            sheets.append((title, _sheet_rows(zf, member, strings)))
        return sheets


def _rows_text(rows: list[list[str]]) -> str:
    lines: list[str] = []
    for row in rows:
        cells = [cell.strip() for cell in row if cell and cell.strip()]
        if cells:
            lines.append("\t".join(cells))
    return "\n".join(lines)


def _xlsx_text(path: Path) -> str:
    parts: list[str] = []
    for title, rows in _xlsx_sheets(path):
        body = _rows_text(rows)
        if body:
            parts.append(title + "\n" + body)
    return "\n".join(parts)


def _xlsx_html(path: Path) -> str:
    sheets = _xlsx_sheets(path)
    if not sheets:
        return "<p>Could not open this spreadsheet.</p>"
    chunks: list[str] = []
    for title, rows in sheets:
        chunks.append(f"<h2>{html_lib.escape(title)}</h2>")
        if not rows:
            chunks.append("<p>(empty sheet)</p>")
            continue
        body = []
        for row in rows:
            cells = "".join(f"<td>{html_lib.escape(cell)}</td>" for cell in row)
            body.append(f"<tr>{cells}</tr>")
        chunks.append("<table>" + "".join(body) + "</table>")
    return "".join(chunks)


def _trailing_number(name: str) -> int:
    match = re.search(r"(\d+)\.xml$", name.replace("\\", "/"))
    if not match:
        return 0
    try:
        return int(match.group(1))
    except ValueError:
        return 0


def _slide_members(zf: ZipFile, folder: str) -> list[str]:
    root = _read_xml_member(zf, "ppt/presentation.xml")
    rels = _read_xml_member(zf, "ppt/_rels/presentation.xml.rels")
    id_to_target: dict[str, str] = {}
    if rels is not None:
        for rel in rels.iter():
            if _local(rel.tag) != "Relationship":
                continue
            rid = _attr(rel, "Id")
            target = _attr(rel, "Target")
            if rid and target:
                target = unquote(target.split("#", 1)[0]).lstrip("/")
                if not target.startswith("ppt/"):
                    target = "ppt/" + target
                id_to_target[rid] = posixpath.normpath(target)
    ordered: list[str] = []
    if root is not None and folder == "slides":
        for el in root.iter():
            if _local(el.tag) != "sldId":
                continue
            target = id_to_target.get(_attr(el, "id") or "")
            if target:
                ordered.append(target)
    if ordered:
        return ordered
    pattern = re.compile(rf"(?:^|/){re.escape(folder)}/slide\d+\.xml$")
    if folder == "notesSlides":
        pattern = re.compile(r"(?:^|/)notesSlides/notesSlide\d+\.xml$")
    found = [name.replace("\\", "/") for name in zf.namelist() if pattern.search(name.replace("\\", "/"))]
    found.sort(key=_trailing_number)
    return found


def _paragraphs_in(root: ET.Element) -> list[str]:
    lines: list[str] = []
    for el in root.iter():
        if _local(el.tag) != "p":
            continue
        if any(node is not el and _local(node.tag) == "p" for node in el.iter()):
            continue
        bits = [node.text for node in el.iter() if node is not el and _local(node.tag) == "t" and node.text]
        line = "".join(bits).strip()
        if line:
            lines.append(line)
    return lines


def _pptx_blocks(path: Path) -> tuple[list[list[str]], list[str]]:
    with _open_zip(path) as zf:
        if zf is None:
            return [], []
        slides: list[list[str]] = []
        for member in _slide_members(zf, "slides"):
            root = _read_xml_member(zf, member)
            slides.append(_paragraphs_in(root) if root is not None else [])
        notes: list[str] = []
        for member in _slide_members(zf, "notesSlides"):
            root = _read_xml_member(zf, member)
            if root is not None:
                notes.extend(_paragraphs_in(root))
        return slides, notes


def _pptx_text(path: Path) -> str:
    slides, notes = _pptx_blocks(path)
    parts = ["\n".join(lines) for lines in slides if lines]
    if notes:
        parts.append("\n".join(notes))
    return "\n".join(parts)


def _pptx_html(path: Path) -> str:
    slides, notes = _pptx_blocks(path)
    if not slides and not notes:
        return "<p>Could not open this presentation.</p>"
    chunks: list[str] = []
    for index, lines in enumerate(slides, start=1):
        body = "".join(f"<p>{html_lib.escape(line)}</p>" for line in lines) or "<p>(empty slide)</p>"
        chunks.append(f"<section class='slide'><h2>Slide {index}</h2>{body}</section>")
    if notes:
        body = "".join(f"<p>{html_lib.escape(line)}</p>" for line in notes)
        chunks.append(f"<section class='slide'><h2>Notes</h2>{body}</section>")
    return "".join(chunks)


def _epub_chapter_paths(zf: ZipFile) -> list[str]:
    container = _read_xml_member(zf, "META-INF/container.xml")
    opf_path = "content.opf"
    if container is not None:
        for el in container.iter():
            if _local(el.tag) == "rootfile":
                full = _attr(el, "full-path")
                if full:
                    opf_path = unquote(full)
                break
    opf_path = posixpath.normpath(opf_path.replace("\\", "/").lstrip("/"))
    opf = _read_xml_member(zf, opf_path)
    if opf is None:
        return [
            name
            for name in zf.namelist()
            if name.lower().endswith((".xhtml", ".html", ".htm"))
        ]
    base = posixpath.dirname(opf_path)
    manifest: dict[str, str] = {}
    for el in opf.iter():
        if _local(el.tag) != "item":
            continue
        item_id = _attr(el, "id")
        href = _attr(el, "href")
        if item_id and href:
            manifest[item_id] = unquote(href.split("#", 1)[0])
    ordered: list[str] = []
    for el in opf.iter():
        if _local(el.tag) != "itemref":
            continue
        href = manifest.get(_attr(el, "idref") or "")
        if not href:
            continue
        member = posixpath.normpath(posixpath.join(base, href))
        if not member.startswith("../"):
            ordered.append(member)
    return ordered


_BODY_RE = re.compile(r"(?is)<body[^>]*>(.*)</body>")
_SCRIPT_RE = re.compile(r"(?is)<(script|style|iframe|object|embed)\b[^>]*>.*?</\1>")
_TITLE_RE = re.compile(r"(?is)<title[^>]*>(.*?)</title>")


def _body_inner(raw: str) -> str:
    match = _BODY_RE.search(raw)
    chunk = match.group(1) if match else raw
    return _SCRIPT_RE.sub("", chunk)


def _html_title(raw: str) -> str:
    match = _TITLE_RE.search(raw)
    if not match:
        return ""
    return re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", "", match.group(1)))).strip()


def _epub_chapters(path: Path) -> list[tuple[str, str, str]]:
    """(title, body html, searchable text) for each spine item."""
    with _open_zip(path) as zf:
        if zf is None:
            return []
        chapters: list[tuple[str, str, str]] = []
        for member in _epub_chapter_paths(zf):
            raw = _member_text(zf, member)
            if not raw.strip():
                continue
            title = _html_title(raw) or f"Chapter {len(chapters) + 1}"
            chapters.append((title, _body_inner(raw), html_visible_text(raw)))
        return chapters


def _epub_text(path: Path) -> str:
    return "\n".join(text for _title, _body, text in _epub_chapters(path) if text.strip())


def _epub_html(path: Path) -> str:
    chapters = _epub_chapters(path)
    if not chapters:
        return "<p>Could not open this book.</p>"
    parts: list[str] = []
    used = 0
    for title, body, _text in chapters:
        block = f"<article class='slide'><h2>{html_lib.escape(title)}</h2>{body}</article>"
        if used + len(block) > VIEW_CHAR_CAP:
            parts.append("<p class='note'>Showing the first part of this book.</p>")
            break
        parts.append(block)
        used += len(block)
    return "".join(parts)


def _cell_source(cell: dict) -> str:
    source = cell.get("source") or ""
    if isinstance(source, list):
        return "".join(str(part) for part in source)
    return str(source)


def _output_text(output: dict) -> str:
    if output.get("output_type") == "stream":
        text = output.get("text") or ""
        if isinstance(text, list):
            return "".join(str(part) for part in text)
        return str(text)
    data = output.get("data")
    if isinstance(data, dict) and "text/plain" in data:
        plain = data["text/plain"]
        if isinstance(plain, list):
            return "".join(str(part) for part in plain)
        return str(plain)
    text = output.get("text")
    if isinstance(text, list):
        return "".join(str(part) for part in text)
    if isinstance(text, str):
        return text
    return ""


def _notebook_cells(text: str) -> list[dict] | None:
    try:
        notebook = json.loads(text)
    except json.JSONDecodeError:
        return None
    cells = notebook.get("cells")
    if not isinstance(cells, list):
        return []
    return [cell for cell in cells if isinstance(cell, dict)]


def _markdown_html(source: str) -> str:
    try:
        import markdown
    except ImportError:
        return f"<pre>{html_lib.escape(source)}</pre>"
    return markdown.markdown(source, extensions=["fenced_code", "tables", "nl2br", "sane_lists"])


def _notebook_text(text: str) -> str:
    cells = _notebook_cells(text)
    if cells is None:
        return text
    parts: list[str] = []
    for cell in cells:
        source = _cell_source(cell).strip()
        if source:
            parts.append(source)
        for output in cell.get("outputs") or []:
            if isinstance(output, dict):
                shown = _output_text(output).strip()
                if shown:
                    parts.append(shown)
    return "\n".join(parts)


def _notebook_html(text: str) -> str:
    if not text.strip():
        return "<p>(empty notebook)</p>"
    cells = _notebook_cells(text)
    if cells is None:
        return pre_block(text)
    if not cells:
        return "<p>(empty notebook)</p>"
    chunks: list[str] = []
    for cell in cells:
        source = _cell_source(cell)
        kind = str(cell.get("cell_type") or "code")
        if kind == "markdown":
            chunks.append(f"<div class='cell'>{_markdown_html(source)}</div>")
        elif source.strip():
            chunks.append(f"<pre>{html_lib.escape(source)}</pre>")
        for output in cell.get("outputs") or []:
            if not isinstance(output, dict):
                continue
            shown = _output_text(output)
            if shown.strip():
                chunks.append(f"<pre class='out'>{html_lib.escape(shown)}</pre>")
    return "".join(chunks) or "<p>(empty notebook)</p>"
