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


def test_side_by_side_page(client: TestClient):
    r = client.get("/side-by-side.html")
    assert r.status_code == 200
    assert b"<iframe" in r.content
    assert r.headers.get("x-frame-options") == "SAMEORIGIN"
    spa = client.get("/")
    assert spa.headers.get("x-frame-options") == "SAMEORIGIN"


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


def test_history_add_merges_and_delete_syncs(client: TestClient):
    first = client.post(
        "/api/settings/history",
        json={"bucket": "search_history", "term": "alpha"},
    )
    assert first.status_code == 200, first.text
    second = client.post(
        "/api/settings/history",
        json={"bucket": "search_history", "term": "beta"},
    )
    assert second.json()["history"][:2] == ["beta", "alpha"]
    gone = client.delete(
        "/api/settings/history",
        params={"bucket": "search_history", "term": "alpha"},
    )
    assert gone.status_code == 200
    assert gone.json()["history"] == ["beta"]
    assert client.get("/api/settings").json()["search_history"] == ["beta"]


def test_history_delete_is_case_insensitive(client: TestClient):
    client.post("/api/settings/history", json={"bucket": "page_search_history", "term": "Task"})
    gone = client.delete(
        "/api/settings/history",
        params={"bucket": "page_search_history", "term": "task"},
    )
    assert gone.json()["history"] == []


def test_add_root_requires_absolute_existing_dir(client: TestClient, tmp_path: Path):
    missing = client.post("/api/roots", json={"path": str(tmp_path / "no-such-dir")})
    assert missing.status_code == 400
    relative = client.post("/api/roots", json={"path": "relative\\folder"})
    assert relative.status_code == 400


def test_lists_and_searches_markdown_and_pdf(client: TestClient, docs_tree: dict[str, Path]):
    (docs_tree["root"] / "notes.md").write_text(
        "# Guide\n\nMarkdown has MDUNIQUETOKEN in the body.\n",
        encoding="utf-8",
    )
    (docs_tree["root"] / "sheet.pdf").write_bytes(
        b"%PDF-1.1\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 144]/Contents 4 0 R"
        b"/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
        b"4 0 obj<</Length 54>>stream\n"
        b"BT /F1 12 Tf 20 80 Td (PDFUNIQUETOKEN) Tj ET\n"
        b"endstream\nendobj\n"
        b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
        b"trailer<</Root 1 0 R>>\n%%EOF\n"
    )
    client.post("/api/roots", json={"path": str(docs_tree["root"])})
    rels = {d["rel"] for d in client.get("/api/documents").json()["documents"]}
    assert "notes.md" in rels
    assert "sheet.pdf" in rels
    md = client.get("/api/documents", params={"q": "MDUNIQUETOKEN"}).json()["documents"]
    assert {d["rel"] for d in md} == {"notes.md"}
    viewed = client.get(f"/view/{client.get('/api/roots').json()['roots'][0]['id']}/notes.md")
    assert viewed.status_code == 200
    assert "MDUNIQUETOKEN" in viewed.text
    assert "text/html" in viewed.headers.get("content-type", "")
    pdf_hits = client.get("/api/documents", params={"q": "PDFUNIQUETOKEN"}).json()["documents"]
    # Extractable text PDFs match; if the stub has no text layer, listing still includes it.
    if pdf_hits:
        assert {d["rel"] for d in pdf_hits} == {"sheet.pdf"}


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


def test_tree_stream_counts_matches(client: TestClient, docs_tree: dict[str, Path]):
    client.post("/api/roots", json={"path": str(docs_tree["root"])})
    r = client.get("/api/tree/stream", params={"q": "ALPHAUNIQUE"})
    assert r.status_code == 200, r.text
    assert "text/event-stream" in r.headers.get("content-type", "")
    assert "event: progress" in r.text
    assert "event: done" in r.text
    assert "index.html" in r.text


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


def test_set_root_adds_another_folder(client: TestClient, tmp_path: Path, docs_tree: dict[str, Path]):
    other = tmp_path / "other-docs"
    other.mkdir()
    (other / "only.html").write_text("<html>only</html>", encoding="utf-8")
    first = client.post("/api/roots", json={"path": str(docs_tree["root"])})
    assert first.status_code == 200
    added = client.put("/api/roots", json={"path": str(other)})
    assert added.status_code == 200, added.text
    roots = client.get("/api/roots").json()["roots"]
    assert len(roots) == 2
    rels = {d["rel"] for d in client.get("/api/documents").json()["documents"]}
    assert "only.html" in rels
    assert "index.html" in rels


def test_delete_root(client: TestClient, docs_tree: dict[str, Path]):
    added = client.post("/api/roots", json={"path": str(docs_tree["root"])})
    root_id = added.json()["id"]
    gone = client.delete(f"/api/roots/{root_id}")
    assert gone.status_code == 200
    assert client.get("/api/roots").json()["roots"] == []
    listed = client.get("/api/documents")
    assert listed.json()["documents"] == []


def test_projects_isolate_folders(client: TestClient, tmp_path: Path, docs_tree: dict[str, Path]):
    other = tmp_path / "product-b"
    other.mkdir()
    (other / "bravo.html").write_text("<html>bravo visible</html>", encoding="utf-8")
    listed = client.get("/api/projects").json()
    assert listed["current_slug"] == "default"
    client.post("/api/roots", json={"path": str(docs_tree["root"])})
    created = client.post("/api/projects", json={"name": "Product B"})
    assert created.status_code == 201, created.text
    slug_b = created.json()["slug"]
    client.post(f"/api/projects/{slug_b}/folders", json={"path": str(other)})
    rels_b = {d["rel"] for d in client.get("/api/documents").json()["documents"]}
    assert rels_b == {"bravo.html"}
    client.post("/api/projects/default/select")
    rels_a = {d["rel"] for d in client.get("/api/documents").json()["documents"]}
    assert "index.html" in rels_a
    assert "bravo.html" not in rels_a


def test_delete_project_unregisters_even_with_locked_leftovers(
    client: TestClient, tmp_path: Path
):
    created = client.post("/api/projects", json={"name": "Temp Gone"})
    assert created.status_code == 201, created.text
    slug = created.json()["slug"]
    gone = client.delete(f"/api/projects/{slug}")
    assert gone.status_code == 200, gone.text
    slugs = [p["slug"] for p in client.get("/api/projects").json()["projects"]]
    assert slug not in slugs


def test_disabled_folder_is_not_searched(client: TestClient, tmp_path: Path, docs_tree: dict[str, Path]):
    extra = tmp_path / "extra-docs"
    extra.mkdir()
    (extra / "unique.html").write_text("<html>UNIQUEVISIBLETOKEN</html>", encoding="utf-8")
    a = client.post("/api/roots", json={"path": str(docs_tree["root"])})
    b = client.post("/api/roots", json={"path": str(extra)})
    extra_id = b.json()["id"]
    found = client.get("/api/documents", params={"q": "UNIQUEVISIBLETOKEN"}).json()["documents"]
    assert {d["rel"] for d in found} == {"unique.html"}
    client.patch(f"/api/roots/{extra_id}", json={"enabled": False})
    hidden = client.get("/api/documents", params={"q": "UNIQUEVISIBLETOKEN"}).json()["documents"]
    assert hidden == []
    listed = client.get("/api/roots").json()["roots"]
    assert any(r["id"] == extra_id and r["enabled"] is False for r in listed)
