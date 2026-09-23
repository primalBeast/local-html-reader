"""List and resolve HTML files under configured documents roots."""

from __future__ import annotations

import os
import threading
import time
from multiprocessing import get_context
from pathlib import Path
from queue import Empty, Queue
from typing import Any

from lhr.extract import (
    DOC_SUFFIXES,
    MAX_SEARCH_BYTES,
    extract_search_text,
    literal_might_match,
    count_text_matches,
    text_matches_query,
)
from lhr.paths import PathEscapeError, is_within, normalize_rel, resolve_under_root
from lhr.projects import (
    add_folder as project_add_folder,
    current_folders,
    remove_folder as project_remove_folder,
    set_folder_enabled,
)

MAX_LIST = 5000


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


def launch_in_default_app(path: Path) -> None:
    """Open a file with the operating system's default application."""
    import subprocess
    import sys

    target = str(path)
    if sys.platform == "win32":
        os.startfile(target)  # type: ignore[attr-defined]
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", target])
        return
    subprocess.Popen(["xdg-open", target])


def _rel_posix(root: Path, file_path: Path) -> str:
    rel = file_path.resolve().relative_to(root.resolve())
    return rel.as_posix()


def _content_contains(
    path: Path,
    needle: str,
    root: Path | None = None,
    *,
    regex: bool = False,
    match_case: bool = False,
    whole_word: bool = False,
) -> bool:
    """True if searchable document text contains needle."""
    return text_matches_query(
        extract_search_text(path, root=root, max_bytes=MAX_SEARCH_BYTES),
        needle,
        regex=regex,
        match_case=match_case,
        whole_word=whole_word,
    )


def _file_matches_query(
    path: Path,
    name: str,
    rel: str,
    needle: str,
    root: Path | None = None,
    *,
    regex: bool = False,
    match_case: bool = False,
    whole_word: bool = False,
) -> int | None:
    """Match count, or None when the file is not a hit. Empty queries return 0."""
    if not needle:
        return 0
    from lhr.text_index import lookup_text, schedule_save

    cached = lookup_text(path)
    if cached is None:
        if not regex and not literal_might_match(path, needle, match_case=match_case):
            return None
        text = extract_search_text(path, root=root, max_bytes=MAX_SEARCH_BYTES)
        schedule_save(path, text)
    else:
        text = cached
    count = count_text_matches(
        text,
        needle,
        regex=regex,
        match_case=match_case,
        whole_word=whole_word,
    )
    if count <= 0:
        return None
    return count


def _search_workers() -> int:
    cpu = os.cpu_count() or 4
    # Leave one logical processor free so the window can still be dragged.
    if cpu > 2:
        return cpu - 1
    return max(2, cpu)


def jobs_largest_first(sized: list[tuple[int, tuple[Any, ...]]]) -> list[tuple[Any, ...]]:
    """Largest files first so each worker takes the next biggest remaining file."""
    ordered = sorted(sized, key=lambda item: (-item[0], str(item[1][2]).lower()))
    return [job for _size, job in ordered]


_mp_lock = threading.Lock()
_mp_ctx = None
_mp_work = None
_mp_events = None
_mp_procs: list[Any] = []
_search_ids = 0


def _process_search_worker(slot: int, work, events) -> None:
    """Process-pool worker. Heavy parses stay off the UI process."""
    while True:
        item = work.get()
        if item is None:
            continue
        search_id, size, job = item
        events.put((search_id, "working", slot, {"slot": slot, "name": job[3], "size": int(size)}))
        try:
            hit = _hit_for_file(job)
        except Exception:
            hit = None
        events.put((search_id, "finished", slot, hit))


def prewarm_search_workers() -> None:
    """Start search processes on the main thread (required on Windows)."""
    _ensure_search_processes(_search_workers())


def _ensure_search_processes(count: int):
    global _mp_ctx, _mp_work, _mp_events
    with _mp_lock:
        if _mp_ctx is None:
            _mp_ctx = get_context("spawn")
            _mp_work = _mp_ctx.Queue()
            _mp_events = _mp_ctx.Queue()
        while len(_mp_procs) < count:
            slot = len(_mp_procs) + 1
            proc = _mp_ctx.Process(
                target=_process_search_worker,
                args=(slot, _mp_work, _mp_events),
                daemon=True,
                name=f"lhr-search-{slot}",
            )
            proc.start()
            _mp_procs.append(proc)
        return _mp_work, _mp_events


def _next_search_id() -> int:
    global _search_ids
    with _mp_lock:
        _search_ids += 1
        return _search_ids


def _drain_queue(q) -> None:
    while True:
        try:
            q.get_nowait()
        except Empty:
            return


def _hit_for_file(
    job: tuple[str, str, str, str, str, bool, bool, bool],
) -> dict[str, Any] | None:
    root_id, root_path, rel, name, needle, regex, match_case, whole_word = job
    path = Path(root_path) / rel
    try:
        matches = _file_matches_query(
            path,
            name,
            rel,
            needle,
            root=Path(root_path),
            regex=regex,
            match_case=match_case,
            whole_word=whole_word,
        )
        if matches is None:
            return None
        try:
            st = path.stat()
            size = int(st.st_size)
            mtime = float(st.st_mtime)
        except OSError:
            size = 0
            mtime = 0.0
        hit: dict[str, Any] = {
            "root_id": root_id,
            "root_path": root_path,
            "rel": rel,
            "name": name,
            "size": size,
            "mtime": mtime,
        }
        if needle and matches > 0:
            hit["match_count"] = matches
        return hit
    except Exception:
        return None


def iter_search_activity(
    query: str | None = None,
    root_id: str | None = None,
    limit: int = MAX_LIST,
    project: str | None = None,
    regex: bool = False,
    match_case: bool = False,
    whole_word: bool = False,
):
    """Yield ("hit", hit) and ("workers", rows) while search threads run."""
    from lhr.text_index import set_searching

    set_searching(True)
    try:
        yield from _iter_search_activity(
            query=query,
            root_id=root_id,
            limit=limit,
            project=project,
            regex=regex,
            match_case=match_case,
            whole_word=whole_word,
        )
    finally:
        set_searching(False)


def _iter_search_activity(
    query: str | None = None,
    root_id: str | None = None,
    limit: int = MAX_LIST,
    project: str | None = None,
    regex: bool = False,
    match_case: bool = False,
    whole_word: bool = False,
):
    needle = (query or "").strip()
    records = _root_records(project=project)
    if root_id:
        records = [r for r in records if r["id"] == root_id]
        if not records:
            raise KeyError(f"unknown documents root: {root_id}")

    cap = max(1, min(int(limit), MAX_LIST))
    jobs: list[tuple[int, tuple[Any, ...]]] = []
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
                try:
                    size = int(file_path.stat().st_size)
                except OSError:
                    size = 0
                jobs.append(
                    (
                        size,
                        (rec["id"], str(root_r), rel, name, needle, regex, match_case, whole_word),
                    )
                )

    sized = sorted(jobs, key=lambda item: (-item[0], str(item[1][2]).lower())) if needle else jobs
    ordered = [job for _size, job in sized]

    if not needle or len(ordered) < 2:
        yielded = 0
        for job in ordered:
            hit = _hit_for_file(job)
            if hit is None:
                continue
            yield ("hit", hit)
            yielded += 1
            if yielded >= cap:
                return
        return

    if _mp_procs:
        yield from _search_with_processes(sized, cap)
    else:
        yield from _search_with_threads(sized, cap)


def _apply_search_batch(
    batch: list[tuple],
    active: dict[int, dict[str, Any]],
    *,
    stopped: bool,
    yielded: int,
    cap: int,
) -> tuple[bool, int, list[dict[str, Any]], int]:
    """Apply worker events. Returns stopped, yielded, new hits, alive delta."""
    hits: list[dict[str, Any]] = []
    exited = 0
    for kind, slot, payload in batch:
        if kind == "working" and not stopped:
            active[slot] = payload
        elif kind == "finished":
            active.pop(slot, None)
            if payload is not None and not stopped:
                yielded += 1
                hits.append(payload)
                if yielded >= cap:
                    stopped = True
        elif kind == "exit":
            active.pop(slot, None)
            exited += 1
    return stopped, yielded, hits, exited


def _batched(events, first):
    batch = [first]
    while True:
        try:
            batch.append(events.get_nowait())
        except Empty:
            return batch


def _search_with_threads(sized: list[tuple[int, tuple[Any, ...]]], cap: int):
    work: Queue = Queue()
    for item in sized:
        work.put(item)
    worker_count = min(_search_workers(), len(sized))
    for _ in range(worker_count):
        work.put(None)
    events: Queue = Queue()

    def worker(slot: int) -> None:
        try:
            while True:
                item = work.get()
                if item is None:
                    return
                size, job = item
                events.put(("working", slot, {"slot": slot, "name": job[3], "size": int(size)}))
                hit = _hit_for_file(job)
                events.put(("finished", slot, hit))
        finally:
            events.put(("exit", slot, None))

    threads = [
        threading.Thread(target=worker, args=(slot,), daemon=True) for slot in range(1, worker_count + 1)
    ]
    for thread in threads:
        thread.start()

    active: dict[int, dict[str, Any]] = {}
    alive = worker_count
    yielded = 0
    stopped = False
    last_emit = 0.0
    try:
        while alive:
            batch = _batched(events, events.get())
            stopped, yielded, hits, exited = _apply_search_batch(
                batch, active, stopped=stopped, yielded=yielded, cap=cap
            )
            alive -= exited
            for hit in hits:
                yield ("hit", hit)
            if stopped:
                _drop_queued_jobs(work)
            now = time.monotonic()
            if (active or alive == 0) and (alive == 0 or now - last_emit >= 0.2 or hits):
                last_emit = now
                yield ("workers", _worker_rows(active))
            if stopped and not active:
                break
    finally:
        _drop_queued_jobs(work)
        for _ in range(worker_count):
            work.put(None)


def _search_with_processes(sized: list[tuple[int, tuple[Any, ...]]], cap: int):
    """One size-sorted queue. Processes pull the next largest file until it is empty."""
    work, events = _ensure_search_processes(min(_search_workers(), len(sized)))
    _drain_queue(work)
    _drain_queue(events)
    search_id = _next_search_id()
    for size, job in sized:
        work.put((search_id, size, job))
    active: dict[int, dict[str, Any]] = {}
    remaining = len(sized)
    yielded = 0
    stopped = False
    last_emit = 0.0
    while remaining:
        first = events.get()
        batch = _batched(events, first)
        owned = [item[1:] for item in batch if item[0] == search_id]
        if not owned:
            continue
        stopped, yielded, hits, _exited = _apply_search_batch(
            owned, active, stopped=stopped, yielded=yielded, cap=cap
        )
        finished = sum(1 for kind, _slot, _payload in owned if kind == "finished")
        remaining -= finished
        for hit in hits:
            yield ("hit", hit)
        if stopped:
            _drain_queue(work)
            yield ("workers", [])
            return
        now = time.monotonic()
        if active and (now - last_emit >= 0.2 or hits):
            last_emit = now
            yield ("workers", _worker_rows(active))
    yield ("workers", [])


def _worker_rows(active: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        active.values(),
        key=lambda row: (-int(row.get("size") or 0), int(row.get("slot") or 0)),
    )


def _drop_queued_jobs(work: Queue) -> None:
    """Leave worker stop markers. Drop files still waiting."""
    markers = 0
    while True:
        try:
            item = work.get_nowait()
        except Empty:
            break
        if item is None:
            markers += 1
    for _ in range(markers):
        work.put(None)


def iter_matching_html(
    query: str | None = None,
    root_id: str | None = None,
    limit: int = MAX_LIST,
    project: str | None = None,
    regex: bool = False,
    match_case: bool = False,
    whole_word: bool = False,
):
    """Yield matching file hits. Search workers take the largest files first."""
    for kind, payload in iter_search_activity(
        query=query,
        root_id=root_id,
        limit=limit,
        project=project,
        regex=regex,
        match_case=match_case,
        whole_word=whole_word,
    ):
        if kind == "hit":
            yield payload


def list_documents(
    query: str | None = None,
    root_id: str | None = None,
    limit: int = MAX_LIST,
    project: str | None = None,
    regex: bool = False,
    match_case: bool = False,
    whole_word: bool = False,
) -> dict[str, Any]:
    hits = list(
        iter_matching_html(
            query=query,
            root_id=root_id,
            limit=limit,
            project=project,
            regex=regex,
            match_case=match_case,
            whole_word=whole_word,
        )
    )
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
                    if hit.get("match_count"):
                        node["match_count"] = int(hit["match_count"])
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
    regex: bool = False,
    match_case: bool = False,
    whole_word: bool = False,
) -> dict[str, Any]:
    listed = list_documents(
        query=query,
        root_id=root_id,
        limit=limit,
        project=project,
        regex=regex,
        match_case=match_case,
        whole_word=whole_word,
    )
    hits = listed["documents"]
    return {
        "tree": _tree_from_hits(hits),
        "file_count": len(hits),
        "truncated": listed["truncated"],
        "query": (query or "").strip(),
    }
