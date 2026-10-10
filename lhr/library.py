"""Bookmarks, recents, notes, and scroll positions. Stored in the project directory."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lhr import documents
from lhr.filelock import exclusive_file_lock
from lhr.json_io import read_json, write_json
from lhr.paths import PathEscapeError, normalize_rel, project_dir
from lhr.projects import resolve_slug

MAX_BOOKMARKS = 200
MAX_RECENTS = 40
MAX_NOTES = 400
MAX_NOTE_CHARS = 20_000
MAX_POSITIONS = 500
_EMPTY = {"bookmarks": [], "recents": [], "notes": {}, "positions": {}}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _path(slug: str) -> Path:
    return project_dir(slug) / "library.json"


def _key(root_id: str, rel: str) -> str:
    return f"{root_id}\t{rel}"


def _clean(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {**_EMPTY, "notes": {}, "positions": {}}
    bookmarks = [row for row in data.get("bookmarks") or [] if isinstance(row, dict)]
    recents = [row for row in data.get("recents") or [] if isinstance(row, dict)]
    notes = data.get("notes") if isinstance(data.get("notes"), dict) else {}
    positions = data.get("positions") if isinstance(data.get("positions"), dict) else {}
    return {
        "bookmarks": bookmarks[:MAX_BOOKMARKS],
        "recents": recents[:MAX_RECENTS],
        "notes": {str(k): str(v)[:MAX_NOTE_CHARS] for k, v in list(notes.items())[:MAX_NOTES]},
        "positions": {
            str(k): float(v)
            for k, v in list(positions.items())[:MAX_POSITIONS]
            if isinstance(v, (int, float))
        },
    }


def load_library(project: str | None = None) -> dict[str, Any]:
    slug = resolve_slug(project)
    if not slug:
        raise ValueError("no project selected")
    path = _path(slug)
    if not path.exists():
        return _clean(_EMPTY)
    return _clean(read_json(path, default=_EMPTY))


def _save(slug: str, data: dict[str, Any]) -> dict[str, Any]:
    cleaned = _clean(data)
    dest = _path(slug)
    lock = dest.with_suffix(".lock")
    with exclusive_file_lock(lock):
        write_json(dest, cleaned)
    return cleaned


def _require_file(root_id: str, rel: str, *, project: str | None) -> dict[str, str]:
    norm = normalize_rel(rel)
    path = documents.resolve_document(root_id, norm, project=project)
    if not path.is_file():
        raise FileNotFoundError(norm)
    root = documents.get_root(root_id, project=project)
    title = Path(norm).name or norm
    return {
        "root_id": root_id,
        "rel": norm,
        "title": title[:200],
        "root_path": str(root.get("path") or ""),
    }


def _item(info: dict[str, str], *, at: str) -> dict[str, str]:
    return {**info, "at": at}


def touch_recent(root_id: str, rel: str, *, project: str | None = None) -> dict[str, Any]:
    slug = resolve_slug(project)
    if not slug:
        raise ValueError("no project selected")
    info = _require_file(root_id, rel, project=slug)
    data = load_library(slug)
    key = (info["root_id"], info["rel"])
    recents = [
        row
        for row in data["recents"]
        if (str(row.get("root_id")), str(row.get("rel"))) != key
    ]
    recents.insert(0, _item(info, at=_now()))
    data["recents"] = recents[:MAX_RECENTS]
    return _save(slug, data)


def toggle_bookmark(root_id: str, rel: str, *, project: str | None = None) -> dict[str, Any]:
    slug = resolve_slug(project)
    if not slug:
        raise ValueError("no project selected")
    info = _require_file(root_id, rel, project=slug)
    data = load_library(slug)
    key = (info["root_id"], info["rel"])
    kept = [
        row
        for row in data["bookmarks"]
        if (str(row.get("root_id")), str(row.get("rel"))) != key
    ]
    if len(kept) == len(data["bookmarks"]):
        kept.insert(0, _item(info, at=_now()))
    data["bookmarks"] = kept[:MAX_BOOKMARKS]
    return _save(slug, data)


def set_note(root_id: str, rel: str, text: str, *, project: str | None = None) -> dict[str, Any]:
    slug = resolve_slug(project)
    if not slug:
        raise ValueError("no project selected")
    info = _require_file(root_id, rel, project=slug)
    data = load_library(slug)
    key = _key(info["root_id"], info["rel"])
    notes = dict(data["notes"])
    body = (text or "")[:MAX_NOTE_CHARS]
    if body.strip():
        notes[key] = body
    else:
        notes.pop(key, None)
    data["notes"] = notes
    return _save(slug, data)


def set_position(root_id: str, rel: str, ratio: float, *, project: str | None = None) -> dict[str, Any]:
    slug = resolve_slug(project)
    if not slug:
        raise ValueError("no project selected")
    info = _require_file(root_id, rel, project=slug)
    data = load_library(slug)
    key = _key(info["root_id"], info["rel"])
    positions = dict(data["positions"])
    try:
        value = float(ratio)
    except (TypeError, ValueError) as exc:
        raise ValueError("position must be a number") from exc
    if value < 0 or value > 1:
        raise ValueError("position must be between 0 and 1")
    if value <= 0.001:
        positions.pop(key, None)
    else:
        positions[key] = round(value, 4)
    data["positions"] = positions
    return _save(slug, data)


def note_key(root_id: str, rel: str) -> str:
    try:
        norm = normalize_rel(rel)
    except PathEscapeError:
        norm = rel
    return _key(root_id, norm)
