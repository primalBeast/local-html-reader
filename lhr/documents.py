"""List and resolve HTML files under configured documents roots."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from lhr.extract import DOC_SUFFIXES, extract_search_text, text_matches_query
from lhr.paths import PathEscapeError, is_within, normalize_rel, resolve_under_root
from lhr.projects import (
    add_folder as project_add_folder,
    current_folders,
    remove_folder as project_remove_folder,
    set_folder_enabled,
)

MAX_LIST = 5000
MAX_SEARCH_BYTES = 8 * 1024 * 1024


def _root_records(*, enabled_only: bool = True, project: str | None = None) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for rec in current_folders(enabled_only=enabled_only, project=project):
        rid = str(rec.get("id") or "").strip()
        path = str(rec.get("path") or "").strip()
        if rid and path:
            out.append({"id": rid, "path": path})
    return out


def list_roots(*, project: str | None = None) -> list[dict[str, Any]]:
    rows = []
    for rec in current_folders(enabled_only=False, project=project):
        rows.append(
            {
                "id": rec.get("id"),
                "path": rec.get("path"),
                "enabled": bool(rec.get("enabled", True)),
                "exists": bool(rec.get("exists")),
            }
        )
    return rows


def get_root(root_id: str, *, project: str | None = None) -> dict[str, str]:
    rid = (root_id or "").strip()
    for rec in _root_records(enabled_only=False, project=project):
        if rec["id"] == rid:
            return rec
    if project:
        raise KeyError(f"unknown documents root: {rid}")
    from lhr.projects import list_project_slugs

    for slug in list_project_slugs():
        for rec in _root_records(enabled_only=False, project=slug):
            if rec["id"] == rid:
                return rec
    raise KeyError(f"unknown documents root: {rid}")


def add_root(raw_path: str, *, project: str | None = None) -> dict[str, Any]:
    from lhr.projects import resolve_slug

    slug = resolve_slug(project)
    if not slug:
        raise ValueError("create a project before adding folders")
    rec = project_add_folder(slug, raw_path)
    return rec


def set_root(raw_path: str, *, project: str | None = None) -> dict[str, Any]:
    """Add a folder to the current project (kept for the Add folder dialog)."""
    return add_root(raw_path, project=project)


def remove_root(root_id: str, *, project: str | None = None) -> bool:
    from lhr.projects import resolve_slug

    slug = resolve_slug(project)
    if not slug:
        return False
    try:
        project_remove_folder(slug, root_id)
        return True
    except KeyError:
        return False


def set_root_enabled(root_id: str, enabled: bool, *, project: str | None = None) -> dict[str, Any]:
    from lhr.projects import resolve_slug

    slug = resolve_slug(project)
    if not slug:
        raise ValueError("no project selected")
    return set_folder_enabled(slug, root_id, enabled)


def root_dir(root_id: str, *, project: str | None = None) -> Path:
    rec = get_root(root_id, project=project)
    p = Path(rec["path"]).expanduser()
    try:
        resolved = p.resolve()
    except OSError as exc:
        raise PathEscapeError(f"cannot resolve documents root: {exc}") from exc
    if not resolved.is_dir():
        raise PathEscapeError("documents root is not a directory")
    return resolved


def resolve_document(root_id: str, rel: str, *, project: str | None = None) -> Path:
    return resolve_under_root(root_dir(root_id, project=project), rel)


def _rel_posix(root: Path, file_path: Path) -> str:
    rel = file_path.resolve().relative_to(root.resolve())
    return rel.as_posix()


def _content_contains(path: Path, needle: str, root: Path | None = None) -> bool:
    """True if searchable document text contains needle (case-insensitive)."""
    return text_matches_query(extract_search_text(path, root=root, max_bytes=MAX_SEARCH_BYTES), needle)


def _file_matches_query(path: Path, name: str, rel: str, needle: str, root: Path | None = None) -> bool:
    if not needle:
        return True
    return _content_contains(path, needle, root=root)


def iter_matching_html(
    query: str | None = None,
    root_id: str | None = None,
    limit: int = MAX_LIST,
    project: str | None = None,
):
    """Yield matching HTML file hits one at a time (for live search counts)."""
    needle = (query or "").strip().lower()
    records = _root_records(project=project)
    if root_id:
        records = [r for r in records if r["id"] == root_id]
        if not records:
            raise KeyError(f"unknown documents root: {root_id}")

    cap = max(1, min(int(limit), MAX_LIST))
    yielded = 0
    for rec in records:
        root = Path(rec["path"]).expanduser()
        try:
            root_r = root.resolve()
        except OSError:
            continue
        if not root_r.is_dir():
            continue
        try:
            walker = os.walk(root_r, onerror=lambda _exc: None, followlinks=False)
        except OSError:
            continue
        for dirpath, _dirnames, filenames in walker:
            dir_p = Path(dirpath)
            if not is_within(root_r, dir_p):
                continue
            for name in filenames:
                suffix = Path(name).suffix.lower()
                if suffix not in DOC_SUFFIXES:
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
                yield {
                    "root_id": rec["id"],
                    "root_path": str(root_r),
                    "rel": rel,
                    "name": name,
                    "size": size,
                    "mtime": mtime,
                }
                yielded += 1
                if yielded >= cap:
                    return


def list_documents(
    query: str | None = None,
    root_id: str | None = None,
    limit: int = MAX_LIST,
    project: str | None = None,
) -> dict[str, Any]:
    hits = list(iter_matching_html(query=query, root_id=root_id, limit=limit, project=project))
    truncated = len(hits) >= max(1, min(int(limit), MAX_LIST))
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


def tree_from_hits(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _tree_from_hits(hits)


def document_tree(
    query: str | None = None,
    root_id: str | None = None,
    limit: int = MAX_LIST,
    project: str | None = None,
) -> dict[str, Any]:
    listed = list_documents(query=query, root_id=root_id, limit=limit, project=project)
    hits = listed["documents"]
    return {
        "tree": _tree_from_hits(hits),
        "file_count": len(hits),
        "truncated": listed["truncated"],
        "query": (query or "").strip(),
    }
