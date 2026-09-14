"""Named projects, each with its own folder list. Data lives under data_dir/projects/<slug>/."""

from __future__ import annotations

import os
import re
import secrets
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lhr.json_io import read_json, write_json
from lhr.paths import project_dir, projects_dir, validate_slug
from lhr.settings import load_settings, patch_settings

DEFAULT_PROJECT = {
    "schema_version": 1,
    "name": "Default",
    "slug": "default",
    "folders": [],
    "last_document": None,
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_projects_dir() -> Path:
    root = projects_dir()
    root.mkdir(parents=True, exist_ok=True)
    return root


def slugify(name: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    text = text[:62]
    if not text or not text[0].isalnum():
        text = "project-" + secrets.token_hex(3)
    validate_slug(text)
    return text


def list_project_slugs() -> list[str]:
    root = projects_dir()
    if not root.exists():
        return []
    return sorted(
        p.name
        for p in root.iterdir()
        if p.is_dir() and not p.name.startswith(".") and (p / "project.json").exists()
    )


def _folder_exists(path: str) -> bool:
    try:
        return Path(path).expanduser().is_dir()
    except OSError:
        return False


def _decorate(data: dict[str, Any]) -> dict[str, Any]:
    slug = str(data.get("slug") or "")
    folders = []
    for raw in data.get("folders") or []:
        if not isinstance(raw, dict):
            continue
        fid = str(raw.get("id") or "").strip()
        path = str(raw.get("path") or "").strip()
        if not fid or not path:
            continue
        folders.append(
            {
                "id": fid,
                "path": path,
                "enabled": bool(raw.get("enabled", True)),
                "exists": _folder_exists(path),
            }
        )
    out = deepcopy(data)
    out["slug"] = slug
    out["folders"] = folders
    out["data_path"] = str(project_dir(slug)) if slug else ""
    return out


def load_project(slug: str) -> dict[str, Any]:
    path = project_dir(slug) / "project.json"
    if not path.exists():
        raise FileNotFoundError(slug)
    data = read_json(path)
    if not isinstance(data, dict):
        data = {}
    data["slug"] = slug
    return _decorate(data)


def save_project(slug: str, data: dict[str, Any]) -> dict[str, Any]:
    data = deepcopy(data)
    data.pop("data_path", None)
    folders = []
    for raw in data.get("folders") or []:
        if not isinstance(raw, dict):
            continue
        fid = str(raw.get("id") or "").strip()
        path = str(raw.get("path") or "").strip()
        if not fid or not path:
            continue
        folders.append({"id": fid, "path": path, "enabled": bool(raw.get("enabled", True))})
    data["folders"] = folders
    data["slug"] = slug
    data["updated_at"] = _now()
    dest = project_dir(slug)
    dest.mkdir(parents=True, exist_ok=True)
    write_json(dest / "project.json", data)
    bump_projects_epoch()
    return _decorate(data)


def bump_projects_epoch() -> None:
    settings = load_settings()
    epoch = int(settings.get("projects_epoch") or 0) + 1
    patch_settings({"projects_epoch": epoch})


def list_projects() -> list[dict[str, Any]]:
    return [load_project(s) for s in list_project_slugs()]


def current_slug() -> str | None:
    slug = load_settings().get("last_project_slug")
    if isinstance(slug, str) and slug and slug in list_project_slugs():
        return slug
    slugs = list_project_slugs()
    return slugs[0] if slugs else None


def load_current() -> dict[str, Any] | None:
    slug = current_slug()
    if not slug:
        return None
    try:
        return load_project(slug)
    except FileNotFoundError:
        return None


def select_project(slug: str) -> dict[str, Any]:
    proj = load_project(slug)
    last = proj.get("last_document")
    patch_settings({"last_project_slug": slug, "last_document": last})
    return proj


def create_project(name: str) -> dict[str, Any]:
    label = (name or "").strip() or "Untitled"
    base = slugify(label)
    slug = base
    n = 2
    while (project_dir(slug) / "project.json").exists():
        slug = f"{base}-{n}"[:63]
        n += 1
        validate_slug(slug)
    data = {
        "schema_version": 1,
        "name": label,
        "slug": slug,
        "created_at": _now(),
        "updated_at": _now(),
        "folders": [],
        "last_document": None,
    }
    dest = project_dir(slug)
    dest.mkdir(parents=True, exist_ok=True)
    write_json(dest / "project.json", data)
    settings = load_settings()
    epoch = int(settings.get("projects_epoch") or 0) + 1
    patch_settings({"last_project_slug": slug, "last_document": None, "projects_epoch": epoch})
    return _decorate(data)


def rename_project(slug: str, name: str) -> dict[str, Any]:
    proj = load_project(slug)
    label = (name or "").strip()
    if not label:
        raise ValueError("name is required")
    proj["name"] = label
    return save_project(slug, proj)


def _unlink_with_retry(path: Path) -> None:
    import stat
    import time

    last: OSError | None = None
    for attempt in range(8):
        try:
            path.unlink()
            return
        except FileNotFoundError:
            return
        except OSError as exc:
            last = exc
            try:
                os.chmod(path, stat.S_IWRITE)
            except OSError:
                pass
            time.sleep(0.05 * (attempt + 1))
    if last:
        raise last


def _rmtree_best_effort(path: Path) -> None:
    import shutil
    import stat
    import time

    def _onexc(func, p, _exc) -> None:
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except OSError:
            pass

    for attempt in range(5):
        if not path.exists():
            return
        try:
            shutil.rmtree(path, onexc=_onexc)
            return
        except OSError:
            time.sleep(0.05 * (attempt + 1))
    # Leave locked leftovers (OneDrive backups). Project is already unregistered.


def delete_project(slug: str) -> None:
    validate_slug(slug)
    dest = project_dir(slug)
    marker = dest / "project.json"
    if not marker.exists():
        raise FileNotFoundError(slug)
    # Drop the listing file first so the UI unregisters even if OneDrive
    # locks backup folders and rmtree cannot finish.
    _unlink_with_retry(marker)
    _rmtree_best_effort(dest)
    remaining = list_project_slugs()
    nxt = remaining[0] if remaining else None
    last_doc = None
    if nxt:
        try:
            last_doc = load_project(nxt).get("last_document")
        except FileNotFoundError:
            nxt = None
    settings = load_settings()
    epoch = int(settings.get("projects_epoch") or 0) + 1
    patch_settings({"last_project_slug": nxt, "last_document": last_doc, "projects_epoch": epoch})


def _validate_abs_dir(raw_path: str) -> Path:
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
    return resolved


def add_folder(slug: str, raw_path: str) -> dict[str, Any]:
    resolved = _validate_abs_dir(raw_path)
    proj = load_project(slug)
    folders = [f for f in proj.get("folders") or [] if isinstance(f, dict)]
    for rec in folders:
        existing = str(rec.get("path") or "")
        if not existing:
            continue
        try:
            if Path(existing).expanduser().resolve() == resolved:
                rec["enabled"] = True
                rec["path"] = str(resolved)
                save_project(slug, proj)
                return {**rec, "exists": True}
        except OSError:
            continue
    rec = {"id": secrets.token_hex(6), "path": str(resolved), "enabled": True}
    folders.append(rec)
    proj["folders"] = folders
    save_project(slug, proj)
    return {**rec, "exists": True}


def set_folder_enabled(slug: str, folder_id: str, enabled: bool) -> dict[str, Any]:
    proj = load_project(slug)
    found = None
    for rec in proj.get("folders") or []:
        if str(rec.get("id")) == folder_id:
            rec["enabled"] = bool(enabled)
            found = rec
            break
    if found is None:
        raise KeyError(folder_id)
    save_project(slug, proj)
    return found


def remove_folder(slug: str, folder_id: str) -> None:
    proj = load_project(slug)
    folders = [f for f in (proj.get("folders") or []) if isinstance(f, dict)]
    kept = [f for f in folders if str(f.get("id")) != folder_id]
    if len(kept) == len(folders):
        raise KeyError(folder_id)
    proj["folders"] = kept
    last = proj.get("last_document")
    if isinstance(last, dict) and str(last.get("root_id")) == folder_id:
        proj["last_document"] = None
        patch_settings({"last_document": None})
    save_project(slug, proj)


def write_last_document(slug: str, last: dict[str, Any] | None) -> None:
    path = project_dir(slug) / "project.json"
    if not path.exists():
        return
    data = read_json(path)
    if not isinstance(data, dict):
        return
    data["last_document"] = last
    data["updated_at"] = _now()
    write_json(path, data)


def set_project_last_document(slug: str, last: dict[str, Any] | None) -> None:
    write_last_document(slug, last)


def current_folders(*, enabled_only: bool = False) -> list[dict[str, Any]]:
    proj = load_current()
    if not proj:
        return []
    folders = [f for f in proj.get("folders") or [] if isinstance(f, dict)]
    if enabled_only:
        folders = [f for f in folders if f.get("enabled", True)]
    return folders


def migrate_legacy_roots() -> None:
    """Move settings.roots into projects/<slug>/project.json once."""
    ensure_projects_dir()
    if list_project_slugs():
        return
    settings = load_settings()
    raw_roots = settings.get("roots") or []
    folders = []
    for rec in raw_roots:
        if not isinstance(rec, dict):
            continue
        fid = str(rec.get("id") or secrets.token_hex(6)).strip()
        path = str(rec.get("path") or "").strip()
        if fid and path:
            folders.append({"id": fid, "path": path, "enabled": True})
    data = {
        "schema_version": 1,
        "name": "Default",
        "slug": "default",
        "created_at": _now(),
        "updated_at": _now(),
        "folders": folders,
        "last_document": settings.get("last_document"),
    }
    write_json(project_dir("default") / "project.json", data)
    patch_settings({"last_project_slug": "default"})
