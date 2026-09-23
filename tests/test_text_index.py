from __future__ import annotations

import time
from pathlib import Path

import pytest

from lhr.config import AppConfig, set_config
from lhr.text_index import lookup_text, save_extracted, schedule_save


@pytest.fixture()
def indexed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data = tmp_path / "data"
    data.mkdir()
    set_config(AppConfig(data_dir=data, host="127.0.0.1", port=8766))
    return tmp_path


def test_index_remembers_text_until_the_file_changes(indexed: Path):
    path = indexed / "page.html"
    path.write_text("<html><body>ALPHAUNIQUE token</body></html>", encoding="utf-8")
    save_extracted(path, "ALPHAUNIQUE token")
    assert lookup_text(path) == "ALPHAUNIQUE token"
    meta = next((indexed / "data" / "text-index").glob("*.json")).read_text(encoding="utf-8")
    assert "sha256" in meta
    assert "mtime_ns" in meta
    path.write_text("<html><body>CHANGED token</body></html>", encoding="utf-8")
    assert lookup_text(path) is None


def test_schedule_save_writes_in_the_background(indexed: Path):
    path = indexed / "later.html"
    path.write_text("<html><body>BACKGROUND</body></html>", encoding="utf-8")
    schedule_save(path, "BACKGROUND")
    found = None
    for _ in range(50):
        found = lookup_text(path)
        if found is not None:
            break
        time.sleep(0.05)
    assert found == "BACKGROUND"