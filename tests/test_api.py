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
    (root / "index.html").write_text(
        "<html><body>home ALPHAUNIQUE</body></html>", encoding="utf-8"
    )
    (nested / "intro.htm").write_text(
        "<html><body>intro BETAUNIQUE</body></html>", encoding="utf-8"
    )
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
    assert patched.json()["sidebar_width"] == 320
    width = client.patch("/api/settings", json={"sidebar_width": 420})
    assert width.status_code == 200
    assert width.json()["sidebar_width"] == 420
    assert client.get("/api/settings").json()["sidebar_width"] == 420
    clamped = client.patch("/api/settings", json={"sidebar_width": 12})
    assert clamped.json()["sidebar_width"] == 160
    hist = client.patch(
        "/api/settings",
        json={"search_history": ["noURLResponse", "  noURLResponse  ", "", "Cache"]},
    )
    assert hist.json()["search_history"] == ["noURLResponse", "Cache"]
    page_hist = client.patch(
        "/api/settings",
        json={"page_search_history": ["task", "task", ""]},
    )
    assert page_hist.json()["page_search_history"] == ["task"]


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


def test_content_search_uses_visible_text_not_tags(client: TestClient, docs_tree: dict[str, Path]):
    tagged = docs_tree["root"] / "tagged.html"
    tagged.write_text(
        '<html><head><title>TITLEONLYTOKEN</title></head><body>'
        '<div class="TAGONLYTOKEN">visible copy</div>'
        "<script>SCRIPTONLYTOKEN</script>"
        "<!-- COMMENTONLYTOKEN -->"
        '<div hidden>HIDDENONLYTOKEN</div>'
        "</body></html>",
        encoding="utf-8",
    )
    named = docs_tree["root"] / "FILENAMEONLYTOKEN.html"
    named.write_text("<html><body>nope</body></html>", encoding="utf-8")
    client.post("/api/roots", json={"path": str(docs_tree["root"])})
    for q in (
        "TAGONLYTOKEN",
        "SCRIPTONLYTOKEN",
        "TITLEONLYTOKEN",
        "COMMENTONLYTOKEN",
        "HIDDENONLYTOKEN",
        "FILENAMEONLYTOKEN",
        "guides",
        "tagged.html",
    ):
        assert client.get("/api/documents", params={"q": q}).json()["documents"] == [], q
    visible = client.get("/api/documents", params={"q": "visible copy"}).json()["documents"]
    assert {d["rel"] for d in visible} == {"tagged.html"}


def test_content_search_includes_css_collapsed_sections(client: TestClient, docs_tree: dict[str, Path]):
    root = docs_tree["root"]
    (root / "docs.css").write_text(".height-container { display: none; }", encoding="utf-8")
    (root / "open.html").write_text(
        "<html><head><link rel='stylesheet' href='docs.css'></head>"
        "<body><p>noURLResponse is visible here</p></body></html>",
        encoding="utf-8",
    )
    (root / "collapsed.html").write_text(
        "<html><head><link rel='stylesheet' href='docs.css'></head>"
        "<body><p>other</p><div class='height-container'>noURLResponse</div></body></html>",
        encoding="utf-8",
    )
    client.post("/api/roots", json={"path": str(root)})
    rels = {d["rel"] for d in client.get("/api/documents", params={"q": "nourlresponse"}).json()["documents"]}
    assert rels == {"open.html", "collapsed.html"}


def test_content_search_filters_html_files(client: TestClient, docs_tree: dict[str, Path]):
    client.post("/api/roots", json={"path": str(docs_tree["root"])})
    alpha = client.get("/api/documents", params={"q": "ALPHAUNIQUE"}).json()["documents"]
    assert {d["rel"] for d in alpha} == {"index.html"}
    beta = client.get("/api/documents", params={"q": "BETAUNIQUE"}).json()["documents"]
    assert {d["rel"] for d in beta} == {"guides/intro.htm"}
    none = client.get("/api/documents", params={"q": "NO_SUCH_TOKEN"}).json()["documents"]
    assert none == []


def test_tree_hides_folders_without_matches(client: TestClient, docs_tree: dict[str, Path]):
    client.post("/api/roots", json={"path": str(docs_tree["root"])})
    full = client.get("/api/tree").json()
    assert full["file_count"] == 2
    root_node = full["tree"][0]
    names = {c["name"] for c in root_node["children"]}
    assert "guides" in names
    assert "index.html" in names

    filtered = client.get("/api/tree", params={"q": "ALPHAUNIQUE"}).json()
    assert filtered["file_count"] == 1
    children = filtered["tree"][0]["children"]
    assert [c["name"] for c in children] == ["index.html"]


def test_set_root_replaces_previous(client: TestClient, tmp_path: Path, docs_tree: dict[str, Path]):
    other = tmp_path / "other-docs"
    other.mkdir()
    (other / "only.html").write_text("<html>only</html>", encoding="utf-8")
    first = client.post("/api/roots", json={"path": str(docs_tree["root"])})
    assert first.status_code == 200
    replaced = client.put("/api/roots", json={"path": str(other)})
    assert replaced.status_code == 200, replaced.text
    roots = client.get("/api/roots").json()["roots"]
    assert len(roots) == 1
    assert roots[0]["path"] == str(other.resolve())
    rels = {d["rel"] for d in client.get("/api/documents").json()["documents"]}
    assert rels == {"only.html"}


def test_delete_root(client: TestClient, docs_tree: dict[str, Path]):
    added = client.post("/api/roots", json={"path": str(docs_tree["root"])})
    root_id = added.json()["id"]
    gone = client.delete(f"/api/roots/{root_id}")
    assert gone.status_code == 200
    assert client.get("/api/roots").json()["roots"] == []
    listed = client.get("/api/documents")
    assert listed.json()["documents"] == []
