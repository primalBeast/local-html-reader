"""API integration tests using a temporary data dir and documents root."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def docs_tree(tmp_path: Path) -> dict[str, Path]:
    root = tmp_path / "html-docs"
    nested = root / "guides"
    nested.mkdir(parents=True)
    (root / "index.html").write_text("<html><body>home</body></html>", encoding="utf-8")
    (nested / "intro.htm").write_text("<html><body>intro</body></html>", encoding="utf-8")
    (nested / "notes.txt").write_text("not html", encoding="utf-8")
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


def test_health(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_settings_round_trip(client: TestClient):
    r = client.get("/api/settings")
    assert r.status_code == 200
    assert r.json()["roots"] == []
    patched = client.patch("/api/settings", json={"last_document": {"root_id": "x", "rel": "a.html"}})
    assert patched.status_code == 200
    assert patched.json()["last_document"]["rel"] == "a.html"


def test_add_root_requires_absolute_existing_dir(client: TestClient, tmp_path: Path):
    missing = client.post("/api/roots", json={"path": str(tmp_path / "no-such-dir")})
    assert missing.status_code == 400
    relative = client.post("/api/roots", json={"path": "relative\\folder"})
    assert relative.status_code == 400


def test_list_and_view_html_under_root(client: TestClient, docs_tree: dict[str, Path]):
    added = client.post("/api/roots", json={"path": str(docs_tree["root"])})
    assert added.status_code == 200, added.text
    root_id = added.json()["id"]

    listed = client.get("/api/documents")
    assert listed.status_code == 200
    docs = listed.json()["documents"]
    rels = {d["rel"] for d in docs}
    assert "index.html" in rels
    assert "guides/intro.htm" in rels
    assert all(not d["rel"].endswith(".txt") for d in docs)

    search = client.get("/api/documents", params={"q": "intro"})
    hits = search.json()["documents"]
    assert len(hits) == 1
    assert hits[0]["rel"] == "guides/intro.htm"

    viewed = client.get(f"/view/{root_id}/guides/intro.htm")
    assert viewed.status_code == 200
    assert "intro" in viewed.text
    assert "text/html" in viewed.headers.get("content-type", "")


def test_rejects_path_traversal(client: TestClient, docs_tree: dict[str, Path]):
    added = client.post("/api/roots", json={"path": str(docs_tree["root"])})
    root_id = added.json()["id"]

    attacks = [
        f"/view/{root_id}/../secret.html",
        f"/view/{root_id}/guides/../../secret.html",
        f"/view/{root_id}/%2e%2e/secret.html",
        f"/view/{root_id}/guides/%2e%2e/%2e%2e/secret.html",
    ]
    for url in attacks:
        r = client.get(url)
        assert r.status_code in (400, 404), f"{url} -> {r.status_code} {r.text}"
        if r.status_code == 200:
            raise AssertionError(f"traversal succeeded for {url}")
        assert b"secret" not in r.content

    # Absolute path as relative segment
    abs_win = str(docs_tree["outside"]).replace("\\", "/")
    r = client.get(f"/view/{root_id}/{abs_win}")
    assert r.status_code in (400, 404)


def test_delete_root(client: TestClient, docs_tree: dict[str, Path]):
    added = client.post("/api/roots", json={"path": str(docs_tree["root"])})
    root_id = added.json()["id"]
    gone = client.delete(f"/api/roots/{root_id}")
    assert gone.status_code == 200
    assert client.get("/api/roots").json()["roots"] == []
    listed = client.get("/api/documents")
    assert listed.json()["documents"] == []
