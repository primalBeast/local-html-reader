"""List and resolve HTML files under configured documents roots."""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Any

from lhr.html_text import html_visible_text
from lhr.paths import PathEscapeError, is_within, normalize_rel, resolve_under_root
from lhr.settings import load_settings, save_settings

HTML_SUFFIXES = {".html", ".htm"}
MAX_LIST = 5000
MAX_SEARCH_BYTES = 8 * 1024 * 1024


def _root_records() -> list[dict[str, str]]:
    settings = load_settings()
    out: list[dict[str, str]] = []
    for raw in settings.get("roots") or []:
        if not isinstance(raw, dict):
            continue
        rid = str(raw.get("id") or "").strip()
        path = str(raw.get("path") or "").strip()
        if rid and path:
            out.append({"id": rid, "path": path})
    return out


def list_roots() -> list[dict[str, Any]]:
    rows = []
    for rec in _root_records():
        p = Path(rec["path"])
        exists = False
        try:
            exists = p.expanduser().is_dir()
        except OSError:
            exists = False
        rows.append({**rec, "exists": exists})
    return rows


def get_root(root_id: str) -> dict[str, str]:
    rid = (root_id or "").strip()
    for rec in _root_records():
        if rec["id"] == rid:
            return rec
    raise KeyError(f"unknown documents root: {rid}")


def add_root(raw_path: str) -> dict[str, Any]:
    text = (raw_path or "").strip()
    if not text:
        raise ValueError("path is required")
    p = Path(text).expanduser()
    if not p.is_absolute():
        raise ValueError("path must be an absolute folder path")
    try:
        resolved = p.resolve()
    except OSError as exc:
        raise ValueError(f"cannot resolve path: {exc}") from exc
    if not resolved.is_dir():
        raise ValueError("path is not an existing directory")

    settings = load_settings()
    roots = [r for r in (settings.get("roots") or []) if isinstance(r, dict)]
    for rec in roots:
        existing = str(rec.get("path") or "")
        if not existing:
            continue
        try:
            if Path(existing).expanduser().resolve() == resolved:
                return {"id": str(rec.get("id")), "path": str(resolved), "exists": True}
        except OSError:
            continue

    rec = {"id": secrets.token_hex(6), "path": str(resolved)}
    roots.append(rec)
    settings["roots"] = roots
    save_settings(settings)
    return {**rec, "exists": True}


def set_root(raw_path: str) -> dict[str, Any]:
    """Replace configured roots with a single documents-root folder."""
    text = (raw_path or "").strip()
    if not text:
        raise ValueError("path is required")
    p = Path(text).expanduser()
    if not p.is_absolute():
        raise ValueError("path must be an absolute folder path")
    try:
        resolved = p.resolve()
    except OSError as exc:
        raise ValueError(f"cannot resolve path: {exc}") from exc
    if not resolved.is_dir():
        raise ValueError("path is not an existing directory")

    settings = load_settings()
    keep_id: str | None = None
    for rec in settings.get("roots") or []:
        if not isinstance(rec, dict):
            continue
        existing = str(rec.get("path") or "")
        if not existing:
            continue
        try:
            if Path(existing).expanduser().resolve() == resolved:
                keep_id = str(rec.get("id") or "") or None
                break
        except OSError:
            continue

    rec = {"id": keep_id or secrets.token_hex(6), "path": str(resolved)}
    last = settings.get("last_document")
    if not (isinstance(last, dict) and str(last.get("root_id")) == rec["id"]):
        settings["last_document"] = None
    settings["roots"] = [rec]
    save_settings(settings)
    return {**rec, "exists": True}


def remove_root(root_id: str) -> bool:
    rid = (root_id or "").strip()
    settings = load_settings()
    roots = [r for r in (settings.get("roots") or []) if isinstance(r, dict)]
    kept = [r for r in roots if str(r.get("id")) != rid]
    if len(kept) == len(roots):
        return False
    settings["roots"] = kept
    last = settings.get("last_document")
    if isinstance(last, dict) and str(last.get("root_id")) == rid:
        settings["last_document"] = None
    save_settings(settings)
    return True


def root_dir(root_id: str) -> Path:
    rec = get_root(root_id)
    p = Path(rec["path"]).expanduser()
    try:
        resolved = p.resolve()
    except OSError as exc:
        raise PathEscapeError(f"cannot resolve documents root: {exc}") from exc
    if not resolved.is_dir():
        raise PathEscapeError("documents root is not a directory")
    return resolved


def resolve_document(root_id: str, rel: str) -> Path:
    return resolve_under_root(root_dir(root_id), rel)


def _rel_posix(root: Path, file_path: Path) -> str:
    rel = file_path.resolve().relative_to(root.resolve())
    return rel.as_posix()


def _content_contains(path: Path, needle: str, root: Path | None = None) -> bool:
    """True if on-screen HTML text contains needle (case-insensitive)."""
    try:
        size = path.stat().st_size
    except OSError:
        return False
    if size > MAX_SEARCH_BYTES:
        return False
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return needle in html_visible_text(raw, html_path=path, root=root).lower()


def _file_matches_query(path: Path, name: str, rel: str, needle: str, root: Path | None = None) -> bool:
    if not needle:
        return True
    return _content_contains(path, needle, root=root)


def _collect_html(
    rec: dict[str, str],
    needle: str,
    cap: int,
    hits: list[dict[str, Any]],
) -> bool:
    """Append matching HTML files. Returns True if the cap was hit."""
    root = Path(rec["path"]).expanduser()
    try:
        root_r = root.resolve()
    except OSError:
        return False
    if not root_r.is_dir():
        return False
    try:
        walker = os.walk(root_r, onerror=lambda _exc: None, followlinks=False)
    except OSError:
        return False
    for dirpath, _dirnames, filenames in walker:
        dir_p = Path(dirpath)
        if not is_within(root_r, dir_p):
            continue
        for name in filenames:
            suffix = Path(name).suffix.lower()
            if suffix not in HTML_SUFFIXES:
                continue
            file_path = dir_p / name
            if not file_path.is_file() or not is_within(root_r, file_path):
                continue
            try:
                rel = _rel_posix(root_r, file_path)
                normalize_rel(rel)
            except (OSError, ValueError, PathEscapeError):
                continue
            if not _file_matches_query(file_path, name, rel, needle, root=root_r):
                continue
            try:
                st = file_path.stat()
                size = int(st.st_size)
                mtime = float(st.st_mtime)
            except OSError:
                size = 0
                mtime = 0.0
            hits.append(
                {
                    "root_id": rec["id"],
                    "root_path": str(root_r),
                    "rel": rel,
                    "name": name,
                    "size": size,
                    "mtime": mtime,
                }
            )
            if len(hits) >= cap:
                return True
    return False


def list_documents(
    query: str | None = None,
    root_id: str | None = None,
    limit: int = MAX_LIST,
) -> dict[str, Any]:
    needle = (query or "").strip().lower()
    records = _root_records()
    if root_id:
        records = [r for r in records if r["id"] == root_id]
        if not records:
            raise KeyError(f"unknown documents root: {root_id}")

    hits: list[dict[str, Any]] = []
    cap = max(1, min(int(limit), MAX_LIST))
    truncated = False
    for rec in records:
        if _collect_html(rec, needle, cap, hits):
            truncated = True
            break

    hits.sort(key=lambda h: (h["root_path"].lower(), h["rel"].lower()))
    return {"documents": hits, "truncated": truncated}


def _sort_tree(nodes: list[dict[str, Any]]) -> None:
    nodes.sort(key=lambda n: (0 if n.get("kind") == "dir" else 1, str(n.get("name", "")).lower()))
    for n in nodes:
        children = n.get("children")
        if isinstance(children, list):
            _sort_tree(children)


def _tree_from_hits(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build a folder tree from HTML file hits. Empty folders are omitted."""
    roots: dict[str, dict[str, Any]] = {}
    index: dict[tuple[str, str], dict[str, Any]] = {}

    for hit in hits:
        root_id = str(hit["root_id"])
        root_path = str(hit["root_path"])
        if root_id not in roots:
            name = Path(root_path).name or root_path
            node = {
                "name": name,
                "rel": "",
                "kind": "dir",
                "root_id": root_id,
                "root_path": root_path,
                "children": [],
            }
            roots[root_id] = node
            index[(root_id, "")] = node

        parts = str(hit["rel"]).split("/")
        parent_rel = ""
        acc: list[str] = []
        for i, part in enumerate(parts):
            acc.append(part)
            rel = "/".join(acc)
            is_file = i == len(parts) - 1
            key = (root_id, rel)
            if key not in index:
                node: dict[str, Any] = {
                    "name": part,
                    "rel": rel,
                    "kind": "file" if is_file else "dir",
                    "root_id": root_id,
                    "root_path": root_path,
                }
                if is_file:
                    node["size"] = hit.get("size", 0)
                    node["mtime"] = hit.get("mtime", 0)
                else:
                    node["children"] = []
                index[key] = node
                parent = index[(root_id, parent_rel)]
                parent.setdefault("children", []).append(node)
            parent_rel = rel

    tree = list(roots.values())
    _sort_tree(tree)
    return tree


def document_tree(
    query: str | None = None,
    root_id: str | None = None,
    limit: int = MAX_LIST,
) -> dict[str, Any]:
    listed = list_documents(query=query, root_id=root_id, limit=limit)
    hits = listed["documents"]
    return {
        "tree": _tree_from_hits(hits),
        "file_count": len(hits),
        "truncated": listed["truncated"],
        "query": (query or "").strip(),
    }
