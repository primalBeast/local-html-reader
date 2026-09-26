"""Search and viewer coverage for the extra document types."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from lhr.extract import DOC_SUFFIXES, extract_search_text, literal_might_match
from lhr.extra_view import render_extra
from lhr.rtf_text import rtf_to_text


def _zip(members: dict[str, str | bytes]) -> bytes:
    buf = BytesIO()
    with ZipFile(buf, "w") as zf:
        for name, payload in members.items():
            data = payload if isinstance(payload, bytes) else payload.encode("utf-8")
            zf.writestr(name, data)
    return buf.getvalue()


def test_suffix_set_includes_common_types() -> None:
    for suffix in (
        ".txt",
        ".csv",
        ".json",
        ".xml",
        ".yaml",
        ".rtf",
        ".odt",
        ".ods",
        ".xlsx",
        ".xlsm",
        ".pptx",
        ".epub",
        ".ipynb",
        ".xhtml",
    ):
        assert suffix in DOC_SUFFIXES
    assert ".bin" not in DOC_SUFFIXES
    assert ".doc" not in DOC_SUFFIXES


def test_plain_text_search_and_view(tmp_path: Path) -> None:
    path = tmp_path / "note.txt"
    path.write_text("alpha PLAINTEXTTOKEN omega\n", encoding="utf-8")
    assert "PLAINTEXTTOKEN" in extract_search_text(path)
    assert literal_might_match(path, "PLAINTEXTTOKEN") is True
    assert literal_might_match(path, "missing-token") is False
    page = render_extra(path)
    assert "PLAINTEXTTOKEN" in page
    assert page.startswith("<!doctype html>")


def test_csv_renders_a_table(tmp_path: Path) -> None:
    path = tmp_path / "sheet.csv"
    path.write_text('name,note\nAda,"CSVTOKEN, kept"\n', encoding="utf-8")
    assert "CSVTOKEN" in extract_search_text(path)
    page = render_extra(path)
    assert "<table>" in page
    assert "<th>name</th>" in page
    assert "CSVTOKEN, kept" in page


def test_json_is_pretty_and_searchable(tmp_path: Path) -> None:
    path = tmp_path / "data.json"
    path.write_text('{"label":"JSONTOKEN","n":2}', encoding="utf-8")
    assert "JSONTOKEN" in extract_search_text(path)
    page = render_extra(path)
    assert "JSONTOKEN" in page
    assert "\n" in page


def test_xml_search_uses_text_nodes(tmp_path: Path) -> None:
    path = tmp_path / "doc.xml"
    path.write_text("<note><body>XMLTOKEN</body></note>", encoding="utf-8")
    assert extract_search_text(path).strip() == "XMLTOKEN"
    assert "XMLTOKEN" in render_extra(path)


def test_xhtml_is_searched_as_html(tmp_path: Path) -> None:
    path = tmp_path / "page.xhtml"
    path.write_text("<html><body><p>XHTMLTOKEN</p></body></html>", encoding="utf-8")
    assert "XHTMLTOKEN" in extract_search_text(path)
    split = tmp_path / "split.xhtml"
    split.write_text("<html><body><p>XHT<b>MLTOKEN</b></p></body></html>", encoding="utf-8")
    assert literal_might_match(split, "XHTMLTOKEN") is True
    assert "XHTMLTOKEN" in extract_search_text(split)


def test_rtf_drops_control_words() -> None:
    raw = (
        r"{\rtf1\ansi{\fonttbl{\f0 Arial;}}Hello \b RTFTOKEN\b0.\par Second {\u8226\'b7} line.}"
    ).encode("latin-1")
    text = rtf_to_text(raw)
    assert "RTFTOKEN" in text
    assert "fonttbl" not in text
    assert "Second" in text
    assert "\u2022" in text


def test_rtf_file_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "note.rtf"
    path.write_bytes(br"{\rtf1\ansi RTFFILETOKEN on disk.\par}")
    assert "RTFFILETOKEN" in extract_search_text(path)
    assert "RTFFILETOKEN" in render_extra(path)
    assert literal_might_match(path, "RTFFILETOKEN") is True


def test_odt_paragraph(tmp_path: Path) -> None:
    content = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-content
 xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
 xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
 <office:body><office:text>
  <text:h text:outline-level="1">Title</text:h>
  <text:p>ODTTOKEN in the paragraph</text:p>
 </office:text></office:body>
</office:document-content>
"""
    path = tmp_path / "note.odt"
    path.write_bytes(_zip({"content.xml": content}))
    assert "ODTTOKEN" in extract_search_text(path)
    page = render_extra(path)
    assert "ODTTOKEN" in page
    assert "<h1>" in page


def test_ods_sheet(tmp_path: Path) -> None:
    content = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-content
 xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
 xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
 xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
 <office:body><office:spreadsheet>
  <table:table table:name="Budget">
   <table:table-row>
    <table:table-cell office:value-type="string"><text:p>ODSTOKEN</text:p></table:table-cell>
   </table:table-row>
  </table:table>
 </office:spreadsheet></office:body>
</office:document-content>
"""
    path = tmp_path / "book.ods"
    path.write_bytes(_zip({"content.xml": content}))
    assert "ODSTOKEN" in extract_search_text(path)
    page = render_extra(path)
    assert "Budget" in page
    assert "ODSTOKEN" in page
    assert page.count("ODSTOKEN") == 1


def test_xlsx_shared_string(tmp_path: Path) -> None:
    shared = """<?xml version="1.0" encoding="UTF-8"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
 <si><t>XLSXTOKEN</t></si>
</sst>
"""
    sheet = """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
 <sheetData><row r="1"><c r="B1" t="s"><v>0</v></c></row></sheetData>
</worksheet>
"""
    workbook = """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
 <sheets><sheet name="Sales" sheetId="1" r:id="rId1"/></sheets>
</workbook>
"""
    rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Id="rId1"
  Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"
  Target="worksheets/sheet1.xml"/>
</Relationships>
"""
    path = tmp_path / "book.xlsx"
    path.write_bytes(
        _zip(
            {
                "xl/sharedStrings.xml": shared,
                "xl/worksheets/sheet1.xml": sheet,
                "xl/workbook.xml": workbook,
                "xl/_rels/workbook.xml.rels": rels,
            }
        )
    )
    assert "XLSXTOKEN" in extract_search_text(path)
    page = render_extra(path)
    assert "Sales" in page
    assert "XLSXTOKEN" in page
    assert "<td></td>" in page  # column A is empty because the value sits in B


def test_pptx_slide_text(tmp_path: Path) -> None:
    slide = """<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
 xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
 <p:cSld><p:spTree><p:sp><p:txBody>
  <a:p><a:r><a:t>PPTX</a:t></a:r><a:r><a:t>TOKEN</a:t></a:r></a:p>
 </p:txBody></p:sp></p:spTree></p:cSld>
</p:sld>
"""
    path = tmp_path / "deck.pptx"
    path.write_bytes(_zip({"ppt/slides/slide1.xml": slide}))
    text = extract_search_text(path)
    assert "PPTXTOKEN" in text
    page = render_extra(path)
    assert "Slide 1" in page
    assert "PPTXTOKEN" in page


def test_epub_spine(tmp_path: Path) -> None:
    container = """<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
 <rootfiles>
  <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
 </rootfiles>
</container>
"""
    opf = """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
 <manifest>
  <item id="c1" href="chap.xhtml" media-type="application/xhtml+xml"/>
 </manifest>
 <spine><itemref idref="c1"/></spine>
</package>
"""
    chapter = """<?xml version="1.0"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>One</title></head>
<body><p>EPUBTOKEN in the chapter</p><script>secret()</script></body></html>
"""
    path = tmp_path / "book.epub"
    path.write_bytes(
        _zip(
            {
                "META-INF/container.xml": container,
                "OEBPS/content.opf": opf,
                "OEBPS/chap.xhtml": chapter,
            }
        )
    )
    assert "EPUBTOKEN" in extract_search_text(path)
    page = render_extra(path)
    assert "EPUBTOKEN" in page
    assert "secret()" not in page


def test_ipynb_cells(tmp_path: Path) -> None:
    path = tmp_path / "demo.ipynb"
    path.write_text(
        '{"nbformat":4,"nbformat_minor":5,"cells":['
        '{"cell_type":"markdown","metadata":{},"source":["See IPYNBTOKEN here"]},'
        '{"cell_type":"code","metadata":{},"source":["print(1)"],'
        '"outputs":[{"output_type":"stream","name":"stdout","text":["OUTTOKEN\\n"]}]}'
        "]}",
        encoding="utf-8",
    )
    text = extract_search_text(path)
    assert "IPYNBTOKEN" in text
    assert "OUTTOKEN" in text
    page = render_extra(path)
    assert "IPYNBTOKEN" in page
    assert "print(1)" in page
    assert "OUTTOKEN" in page
