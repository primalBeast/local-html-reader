from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZipFile

from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from lhr.extract import extract_search_text, literal_might_match, text_matches_query


def docx_bytes_with_text(text: str) -> bytes:
    body = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>"
        f"{escape(text)}"
        "</w:t></w:r></w:p></w:body></w:document>"
    )
    types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        "</Relationships>"
    )
    buf = BytesIO()
    with ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", body)
    return buf.getvalue()


def test_text_matches_ignores_pdf_glyph_spacing() -> None:
    assert text_matches_query("Account 0 4 4 1 4 7 J TFSA", "044147J")
    assert text_matches_query("044147J - TD Waterhouse", "044147j")
    assert not text_matches_query("044147S", "044147J")


def test_search_jobs_run_largest_file_first() -> None:
    from lhr.documents import jobs_largest_first

    small = (10, ("root", "C:/docs", "a.html", "a.html", "q", False, False, False))
    big = (90, ("root", "C:/docs", "b.html", "b.html", "q", False, False, False))
    mid = (40, ("root", "C:/docs", "c.html", "c.html", "q", False, False, False))
    ordered = jobs_largest_first([small, mid, big])
    assert [job[2] for job in ordered] == ["b.html", "c.html", "a.html"]


def test_text_matches_does_not_join_tokens_across_lines() -> None:
    text = "the cash unit transport of cash unit\n\n\n65C0\n138E_ERROR\n1\n000DP0"
    assert not text_matches_query(text, "65C0138E")


def test_text_matches_regex() -> None:
    assert text_matches_query("error code 404 and 500", r"\d{3}", regex=True)
    assert not text_matches_query("no digits here", r"\d{3}", regex=True)
    assert not text_matches_query("abc", r"[", regex=True)


def test_text_matches_case_and_whole_word() -> None:
    assert text_matches_query("Alpha alpha", "Alpha", match_case=True)
    assert not text_matches_query("alpha", "Alpha", match_case=True)
    assert text_matches_query("the cat sat", "cat", whole_word=True)
    assert not text_matches_query("the catalog sat", "cat", whole_word=True)


def _pdf_with_token(token: str = "PDFUNIQUETOKEN", *, encrypt: bool = False) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=144)
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf 20 80 Td ({token}) Tj ET".encode("ascii"))
    font = DictionaryObject()
    font[NameObject("/Type")] = NameObject("/Font")
    font[NameObject("/Subtype")] = NameObject("/Type1")
    font[NameObject("/BaseFont")] = NameObject("/Helvetica")
    font_ref = writer._add_object(font)
    resources = DictionaryObject()
    resources[NameObject("/Font")] = DictionaryObject({NameObject("/F1"): font_ref})
    page[NameObject("/Resources")] = resources
    page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypt:
        writer.encrypt(user_password="", owner_password="owner", algorithm="AES-256")
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_extracts_text_from_aes_encrypted_pdf(tmp_path: Path) -> None:
    path = tmp_path / "locked.pdf"
    path.write_bytes(_pdf_with_token(encrypt=True))
    assert PdfReader(str(path), strict=False).is_encrypted
    text = extract_search_text(path)
    assert "PDFUNIQUETOKEN" in text
    assert text_matches_query(text, "pdfuniquetoken")


def test_literal_prefilter_skips_html_that_cannot_match(tmp_path: Path) -> None:
    path = tmp_path / "page.html"
    path.write_text("<html><body><p>nothing relevant</p></body></html>", encoding="utf-8")
    assert literal_might_match(path, "65C0138E") is False
    assert literal_might_match(path, "nothing") is True


def test_literal_prefilter_keeps_tag_split_html(tmp_path: Path) -> None:
    path = tmp_path / "split.html"
    path.write_text("<html><body><p>65C<b>0138E</b></p></body></html>", encoding="utf-8")
    assert literal_might_match(path, "65C0138E") is True
    assert "65C0138E" in extract_search_text(path)


def test_html_larger_than_8mb_is_still_searched(tmp_path: Path) -> None:
    path = tmp_path / "big.html"
    token = "65C0138E"
    pad = "x" * (8 * 1024 * 1024 + 64)
    path.write_text(f"<html><body><p>M_DATA : {token}</p>{pad}</body></html>", encoding="utf-8")
    assert path.stat().st_size > 8 * 1024 * 1024
    text = extract_search_text(path)
    assert token in text
    assert text_matches_query(text, token)


def test_extracts_text_from_docx(tmp_path: Path) -> None:
    path = tmp_path / "note.docx"
    path.write_bytes(docx_bytes_with_text("DOCXUNIQUETOKEN in the body"))
    text = extract_search_text(path)
    assert "DOCXUNIQUETOKEN" in text
    assert text_matches_query(text, "docxuniquetoken")
