from io import BytesIO
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from lhr.extract import extract_search_text, text_matches_query


def test_text_matches_ignores_pdf_glyph_spacing() -> None:
    assert text_matches_query("Account 0 4 4 1 4 7 J TFSA", "044147J")
    assert text_matches_query("044147J - TD Waterhouse", "044147j")
    assert not text_matches_query("044147S", "044147J")


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
