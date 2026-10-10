"""Bookmarks, notes, recents, and scroll position stay inside the project."""

from __future__ import annotations

from pathlib import Path


def test_library_round_trip(client, docs_tree: dict[str, Path], monkeypatch) -> None:
    monkeypatch.setattr("lhr.documents.reveal_in_file_manager", lambda path: None)
    added = client.post("/api/roots", json={"path": str(docs_tree["root"])})
    assert added.status_code == 200
    root_id = added.json()["id"]
    rel = "index.html"

    recent = client.post("/api/library/recent", json={"root_id": root_id, "rel": rel})
    assert recent.status_code == 200
    assert recent.json()["recents"][0]["rel"] == rel

    saved = client.post("/api/library/bookmark", json={"root_id": root_id, "rel": rel})
    assert saved.status_code == 200
    assert saved.json()["bookmarks"][0]["rel"] == rel
    cleared = client.post("/api/library/bookmark", json={"root_id": root_id, "rel": rel})
    assert cleared.json()["bookmarks"] == []

    noted = client.put(
        "/api/library/note",
        json={"root_id": root_id, "rel": rel, "text": "remember the intro"},
    )
    assert noted.json()["notes"][f"{root_id}\t{rel}"] == "remember the intro"

    placed = client.put(
        "/api/library/position",
        json={"root_id": root_id, "rel": rel, "ratio": 0.42},
    )
    assert placed.json()["positions"][f"{root_id}\t{rel}"] == 0.42

    bad = client.put(
        "/api/library/position",
        json={"root_id": root_id, "rel": "../secret.html", "ratio": 0.2},
    )
    assert bad.status_code == 400

    reveal = client.post("/api/documents/reveal", json={"root_id": root_id, "rel": rel})
    assert reveal.status_code == 200
