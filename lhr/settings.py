"""settings.json load/save. App settings/index only — HTML files stay on disk."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from typing import Any

from lhr.filelock import exclusive_file_lock
from lhr.json_io import read_json, write_json
from lhr.paths import data_root, settings_path

_thread_lock = threading.RLock()

SIDEBAR_WIDTH_DEFAULT = 320
SIDEBAR_WIDTH_MIN = 160
SIDEBAR_WIDTH_MAX = 1600
SEARCH_HISTORY_MAX = 25

DEFAULT_SETTINGS: dict[str, Any] = {
    "schema_version": 1,
    "roots": [],
    "last_document": None,
    "last_project_slug": None,
    "projects_epoch": 0,
    "backup_retention_days": 30,
    "sidebar_width": SIDEBAR_WIDTH_DEFAULT,
    "search_history": [],
    "page_search_history": [],
    "window": {"last_host": "127.0.0.1", "last_port": 8766},
}


def normalize_search_history(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in value:
        regex = False
        match_case = False
        whole_word = False
        text = ""
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            raw = item.get("term")
            if not isinstance(raw, str):
                continue
            text = raw.strip()
            regex = bool(item.get("regex"))
            match_case = bool(item.get("match_case") or item.get("matchCase"))
            whole_word = bool(item.get("whole_word") or item.get("wholeWord"))
        else:
            continue
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "term": text,
                "regex": regex,
                "match_case": match_case,
                "whole_word": whole_word,
            }
        )
        if len(out) >= SEARCH_HISTORY_MAX:
            break
    return out


def clamp_sidebar_width(value: Any) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return SIDEBAR_WIDTH_DEFAULT
    return max(SIDEBAR_WIDTH_MIN, min(SIDEBAR_WIDTH_MAX, n))


def _lock():
    data_root().mkdir(parents=True, exist_ok=True)
    return exclusive_file_lock(data_root() / ".settings.lock")


@contextmanager
def settings_write_lock() -> Iterator[None]:
    with _thread_lock:
        with _lock():
            yield


def ensure_data_layout() -> None:
    data_root().mkdir(parents=True, exist_ok=True)
    if not settings_path().exists():
        save_settings(deepcopy(DEFAULT_SETTINGS))
    from lhr.projects import ensure_projects_dir, migrate_legacy_roots

    ensure_projects_dir()
    migrate_legacy_roots()


def load_settings() -> dict[str, Any]:
    path = settings_path()
    if not path.exists():
        data = deepcopy(DEFAULT_SETTINGS)
        write_json(path, data)
        return data
    data = read_json(path)
    out = deepcopy(DEFAULT_SETTINGS)
    if isinstance(data, dict):
        out.update(data)
    if not isinstance(out.get("roots"), list):
        out["roots"] = []
    out["sidebar_width"] = clamp_sidebar_width(out.get("sidebar_width"))
    out["search_history"] = normalize_search_history(out.get("search_history"))
    out["page_search_history"] = normalize_search_history(out.get("page_search_history"))
    return out


def save_settings(data: dict[str, Any]) -> dict[str, Any]:
    write_json(settings_path(), data)
    try:
        from lhr.sync import broadcast

        broadcast(deepcopy(data))
    except Exception:
        pass
    return data


def patch_settings(updates: dict[str, Any], *, project: str | None = None) -> dict[str, Any]:
    with settings_write_lock():
        data = load_settings()
        for k, v in updates.items():
            if k == "window" and isinstance(v, dict) and isinstance(data.get("window"), dict):
                data["window"] = {**data["window"], **v}
            elif k == "roots" and isinstance(v, list):
                data["roots"] = v
            elif k == "last_document":
                data["last_document"] = v
                slug = project or data.get("last_project_slug")
                if isinstance(slug, str) and slug:
                    try:
                        from lhr.projects import write_last_document

                        write_last_document(slug, v)
                    except Exception:
                        pass
            elif k == "last_project_slug":
                data["last_project_slug"] = v
            elif k == "projects_epoch":
                try:
                    data["projects_epoch"] = int(v)
                except (TypeError, ValueError):
                    pass
            elif k == "sidebar_width":
                data["sidebar_width"] = clamp_sidebar_width(v)
            elif k == "search_history":
                data["search_history"] = normalize_search_history(v)
            elif k == "page_search_history":
                data["page_search_history"] = normalize_search_history(v)
            elif k in DEFAULT_SETTINGS:
                data[k] = v
        return save_settings(data)


def add_search_term(
    bucket: str,
    term: str,
    *,
    regex: bool = False,
    match_case: bool = False,
    whole_word: bool = False,
) -> list[dict[str, Any]]:
    if bucket not in ("search_history", "page_search_history"):
        raise ValueError("unknown history list")
    with settings_write_lock():
        data = load_settings()
        data[bucket] = normalize_search_history(
            [
                {
                    "term": term,
                    "regex": regex,
                    "match_case": match_case,
                    "whole_word": whole_word,
                },
                *(data.get(bucket) or []),
            ]
        )
        save_settings(data)
        return list(data[bucket])


def remove_search_term(bucket: str, term: str) -> list[dict[str, Any]]:
    if bucket not in ("search_history", "page_search_history"):
        raise ValueError("unknown history list")
    needle = (term or "").strip().lower()
    with settings_write_lock():
        data = load_settings()
        current = data.get(bucket) or []
        kept: list[Any] = []
        for item in current:
            if isinstance(item, str) and item.strip().lower() == needle:
                continue
            if isinstance(item, dict) and str(item.get("term") or "").strip().lower() == needle:
                continue
            kept.append(item)
        data[bucket] = normalize_search_history(kept)
        save_settings(data)
        return list(data[bucket])
