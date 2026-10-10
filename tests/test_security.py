"""Security checks: loopback, document CSP, sanitizer, regex, and data-dir sandbox."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
from starlette.datastructures import Headers

from lhr.extract import count_text_matches
from lhr.guard import request_allowed
from lhr.sanitize import sanitize_html


def test_guard_rejects_remote_host_and_cross_site() -> None:
    bad_host = request_allowed(
        method="GET",
        headers=Headers({"host": "evil.example"}),
        peer="127.0.0.1",
    )
    assert bad_host == "host is not loopback"
    cross = request_allowed(
        method="GET",
        headers=Headers({"host": "127.0.0.1:8766", "sec-fetch-site": "cross-site"}),
        peer="127.0.0.1",
    )
    assert cross == "cross-site request blocked"
    missing = request_allowed(
        method="POST",
        headers=Headers({"host": "127.0.0.1:8766", "sec-fetch-site": "same-origin"}),
        peer="127.0.0.1",
    )
    assert missing == "missing client header"
    ok = request_allowed(
        method="POST",
        headers=Headers(
            {
                "host": "127.0.0.1:8766",
                "sec-fetch-site": "same-origin",
                "origin": "http://127.0.0.1:8766",
                "x-lhr-client": "1",
            }
        ),
        peer="127.0.0.1",
    )
    assert ok is None


def test_mutation_without_client_header_is_forbidden(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("LHR_DATA_DIR", str(data))
    from lhr.config import AppConfig, set_config
    from lhr.settings import ensure_data_layout

    set_config(AppConfig(data_dir=data, host="127.0.0.1", port=8766))
    ensure_data_layout()
    from lhr.app import create_app

    app = create_app()

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8766") as client:
            blocked = await client.post("/api/projects", json={"name": "Nope"})
            assert blocked.status_code == 403
            allowed = await client.post(
                "/api/projects",
                json={"name": "Local"},
                headers={"X-LHR-Client": "1"},
            )
            assert allowed.status_code == 201
            remote = await client.get("/health", headers={"host": "evil.example"})
            assert remote.status_code == 403

    asyncio.run(run())


def test_html_view_csp_blocks_scripts(client, docs_tree: dict[str, Path]) -> None:
    added = client.post("/api/roots", json={"path": str(docs_tree["root"])})
    assert added.status_code == 200
    root_id = client.get("/api/roots").json()["roots"][0]["id"]
    viewed = client.get(f"/view/{root_id}/index.html")
    assert viewed.status_code == 200
    policy = viewed.headers["content-security-policy"]
    assert "script-src 'none'" in policy
    assert "connect-src 'none'" in policy
    assert viewed.headers.get("x-lhr-reader-page") is None
    opted = client.get(f"/view/{root_id}/index.html", params={"scripts": "true"})
    opted_policy = opted.headers["content-security-policy"]
    assert "script-src 'unsafe-inline'" in opted_policy
    assert "connect-src 'none'" in opted_policy


def test_markdown_script_is_stripped(client, docs_tree: dict[str, Path]) -> None:
    page = docs_tree["root"] / "bad.md"
    page.write_text(
        "# Title\n\n<script>alert(1)</script>\n\n[click](javascript:alert(1))\n\nOKTEXT\n",
        encoding="utf-8",
    )
    added = client.post("/api/roots", json={"path": str(docs_tree["root"])})
    root_id = added.json()["id"]
    viewed = client.get(f"/view/{root_id}/bad.md")
    assert viewed.status_code == 200
    assert "OKTEXT" in viewed.text
    assert "<script" not in viewed.text.lower()
    assert "javascript:" not in viewed.text.lower()
    assert viewed.headers.get("x-lhr-reader-page") == "generated"


def test_sanitizer_drops_active_html() -> None:
    cleaned = sanitize_html(
        '<p onclick="alert(1)">Hi</p><img src="https://cdn.example/a.png">'
        '<img src="javascript:alert(1)"><a href="javascript:alert(1)">x</a>'
    )
    assert "onclick" not in cleaned.lower()
    assert "javascript:" not in cleaned.lower()
    assert "Hi" in cleaned
    assert "https://cdn.example/a.png" in cleaned


def test_nested_regex_is_rejected() -> None:
    assert count_text_matches("aaa", r"(a+)+$", regex=True) == 0
    assert count_text_matches("alpha", "alp", regex=True) == 1


def test_data_directory_cannot_be_a_documents_folder(client, tmp_path: Path) -> None:
    from lhr.config import get_config

    added = client.post("/api/roots", json={"path": str(get_config().data_dir)})
    assert added.status_code == 400
    assert "data directory" in added.json()["detail"]


def test_cli_refuses_network_bind(tmp_path: Path) -> None:
    from lhr.cli import main

    code = main(["--data-dir", str(tmp_path), "serve", "--host", "0.0.0.0", "--port", "9"])
    assert code == 2
