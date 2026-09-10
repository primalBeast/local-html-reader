"""settings.json load/save. App settings/index only — HTML files stay on disk."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from lhr.json_io import read_json, write_json
from lhr.paths import data_root, settings_path

SIDEBAR_WIDTH_DEFAULT = 320
SIDEBAR_WIDTH_MIN = 160
SIDEBAR_WIDTH_MAX = 1600
SEARCH_HISTORY_MAX = 25

DEFAULT_SETTINGS: dict[str, Any] = {
    "schema_version": 1,
    "roots": [],
    "last_document": None,
    "sidebar_width": SIDEBAR_WIDTH_DEFAULT,
    "search_history": [],
    "page_search_history": [],
    "window": {"last_host": "127.0.0.1", "last_port": 8766},
}


def normalize_search_history(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= SEARCH_HISTORY_MAX:
            break
    return out


def clamp_sidebar_width(value: Any) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return SIDEBAR_WIDTH_DEFAULT
    return max(SIDEBAR_WIDTH_MIN, min(SIDEBAR_WIDTH_MAX, n))


def ensure_data_layout() -> None:
    data_root().mkdir(parents=True, exist_ok=True)
    if not settings_path().exists():
        save_settings(deepcopy(DEFAULT_SETTINGS))


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
    return data


def patch_settings(updates: dict[str, Any]) -> dict[str, Any]:
    data = load_settings()
    for k, v in updates.items():
        if k == "window" and isinstance(v, dict) and isinstance(data.get("window"), dict):
            data["window"] = {**data["window"], **v}
        elif k == "roots" and isinstance(v, list):
            data["roots"] = v
        elif k == "last_document":
            data["last_document"] = v
        elif k == "sidebar_width":
            data["sidebar_width"] = clamp_sidebar_width(v)
        elif k == "search_history":
            data["search_history"] = normalize_search_history(v)
        elif k == "page_search_history":
            data["page_search_history"] = normalize_search_history(v)
        elif k in DEFAULT_SETTINGS:
            data[k] = v
    return save_settings(data)
