"""Daily per-project backups, matching Local Issue Tracker's folder-per-day layout."""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timedelta
from typing import Any

from lhr.json_io import write_json
from lhr.paths import project_dir
from lhr.projects import list_project_slugs
from lhr.settings import load_settings

logger = logging.getLogger("lhr.backup")

INCLUDE_FILES = ("project.json",)


def local_today() -> str:
    return datetime.now().astimezone().date().isoformat()


def backup_project(slug: str, *, force: bool = False) -> dict[str, Any] | None:
    proj = project_dir(slug)
    if not (proj / "project.json").exists():
        raise FileNotFoundError(slug)

    day = local_today()
    backups_root = proj / "backups"
    dest = backups_root / day
    if dest.exists() and not force:
        logger.info("Backup for %s already exists at %s; skip", slug, dest)
        return None

    partial = backups_root / f"{day}.partial"
    if partial.exists():
        shutil.rmtree(partial)
    partial.mkdir(parents=True, exist_ok=True)
    for name in INCLUDE_FILES:
        src = proj / name
        if src.is_file():
            shutil.copy2(src, partial / name)

    manifest = {
        "created_at": datetime.now().astimezone().replace(microsecond=0).isoformat(),
        "local_date": day,
        "project_slug": slug,
        "schema_version": 1,
    }
    write_json(partial / "backup_manifest.json", manifest)
    if dest.exists() and force:
        shutil.rmtree(dest)
    partial.rename(dest)
    logger.info("Created backup %s for project %s", dest, slug)
    _apply_retention(slug)
    return manifest


def _apply_retention(slug: str) -> None:
    days = int(load_settings().get("backup_retention_days") or 30)
    backups_root = project_dir(slug) / "backups"
    if not backups_root.exists():
        return
    cutoff = datetime.now().astimezone().date() - timedelta(days=days)
    for p in backups_root.iterdir():
        if not p.is_dir() or p.name.endswith(".partial"):
            continue
        try:
            d = datetime.strptime(p.name, "%Y-%m-%d").date()
        except ValueError:
            continue
        if d < cutoff:
            shutil.rmtree(p)
            logger.info("Pruned old backup %s", p)


def backup_all_projects(*, force: bool = False) -> list[dict[str, Any]]:
    results = []
    for slug in list_project_slugs():
        try:
            m = backup_project(slug, force=force)
            if m:
                results.append(m)
        except Exception:
            logger.exception("Backup failed for %s", slug)
    return results
