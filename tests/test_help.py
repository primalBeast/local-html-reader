"""Help catalog stays tied to the format list and the quadrupled caps."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lhr.extract import DOC_SUFFIXES
from lhr.limits import (
    MATCH_CAP,
    MAX_CELL_CHARS,
    MAX_COLUMN_REPEAT,
    MAX_MEMBER_BYTES,
    MAX_TABLE_COLS,
    MAX_TABLE_ROWS,
    SEARCH_BYTES,
    VIEW_CHAR_CAP,
    XML_PARSE_CAP,
    help_document,
)

_MB = 1024 * 1024


def test_caps_are_four_times_the_previous_values() -> None:
    assert SEARCH_BYTES == 512 * _MB
    assert MATCH_CAP == 32_000
    assert VIEW_CHAR_CAP == 6_000_000
    assert MAX_TABLE_ROWS == 16_000
    assert MAX_TABLE_COLS == 240
    assert MAX_MEMBER_BYTES == 128 * _MB
    assert XML_PARSE_CAP == 32 * _MB
    assert MAX_CELL_CHARS == 16_000
    assert MAX_COLUMN_REPEAT == 80


def test_help_lists_every_supported_extension_once() -> None:
    body = help_document()
    listed: list[str] = []
    for fmt in body["formats"]:
        assert fmt["name"]
        assert fmt["limits"]
        listed.extend(fmt["extensions"])
    assert sorted(listed) == sorted(DOC_SUFFIXES)
    assert len(listed) == len(set(listed))
    text = " ".join(line for fmt in body["formats"] for line in fmt["limits"])
    text += " ".join(item["detail"] for item in body["shared"])
    for phrase in ("512 MB", "32,000", "6,000,000", "16,000 rows", "240 columns", "128 MB", "32 MB", "80 times"):
        assert phrase in text
    assert ".doc" in body["skipped"]


def test_frontend_find_cap_matches() -> None:
    src = Path("frontend/src/lib/findMatch.ts").read_text(encoding="utf-8")
    assert f"export const FIND_HIT_CAP = {MATCH_CAP}" in src


def test_help_route(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("LHR_DATA_DIR", str(data))
    from lhr.config import AppConfig, set_config
    from lhr.settings import ensure_data_layout

    set_config(AppConfig(data_dir=data, host="127.0.0.1", port=8766))
    ensure_data_layout()
    from lhr.app import create_app

    with TestClient(create_app()) as client:
        response = client.get("/api/help")
    assert response.status_code == 200
    names = {item["name"] for item in response.json()["formats"]}
    assert "HTML" in names
    assert "Excel" in names
