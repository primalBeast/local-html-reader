"""Shared API fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def docs_tree(tmp_path: Path) -> dict[str, Path]:
    root = tmp_path / "html-docs"
    nested = root / "guides"
    nested.mkdir(parents=True)
    (root / "index.html").write_text(
        "<html><body>home ALPHAUNIQUE</body></html>", encoding="utf-8"
    )
    (nested / "intro.htm").write_text(
        "<html><body>intro BETAUNIQUE</body></html>", encoding="utf-8"
    )
    (nested / "notes.bin").write_text("not html", encoding="utf-8")
    outside = tmp_path / "secret.html"
    outside.write_text("<html>secret</html>", encoding="utf-8")
    return {"root": root, "outside": outside, "tmp": tmp_path}


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, docs_tree: dict[str, Path]):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("LHR_DATA_DIR", str(data))

    from lhr.config import AppConfig, set_config
    from lhr.settings import ensure_data_layout

    set_config(AppConfig(data_dir=data, host="127.0.0.1", port=8766))
    ensure_data_layout()

    from lhr.app import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c
