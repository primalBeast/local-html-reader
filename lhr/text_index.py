"""Background cache of extracted document text.

Stored under the app data directory in ``text-index/``, not next to the
original files. A search uses the cache when the file's size and modified
time still match. The checksum is recorded when the text is saved so a later
change can be detected; it is not recomputed on the search path.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import queue
import threading
import time
from pathlib import Path

logger = logging.getLogger("lhr.text_index")

_SAVE_QUEUE: queue.Queue[tuple[Path, str]] = queue.Queue()
_WRITER_LOCK = threading.Lock()
_SEARCH_LOCK = threading.Lock()
_SEARCHING = 0
_CRAWLER_STARTED = False
_WRITER_STARTED = False


def index_dir() -> Path:
    from lhr.paths import data_root

    root = data_root() / "text-index"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _key(path: Path) -> str:
    try:
        resolved = str(path.resolve())
    except OSError:
        resolved = str(path)
    if os.name == "nt":
        resolved = resolved.casefold()
    return hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:32]


def _meta_path(path: Path) -> Path:
    return index_dir() / f"{_key(path)}.json"


def _text_path(path: Path) -> Path:
    return index_dir() / f"{_key(path)}.txt"


def _stat(path: Path) -> os.stat_result | None:
    try:
        return path.stat()
    except OSError:
        return None


def _sha256(path: Path) -> str | None:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def _read_meta(path: Path) -> dict | None:
    meta_path = _meta_path(path)
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _fresh(path: Path, meta: dict, st: os.stat_result) -> bool:
    return int(meta.get("size") or -1) == int(st.st_size) and int(meta.get("mtime_ns") or -1) == int(
        st.st_mtime_ns
    )


def lookup_text(path: Path) -> str | None:
    """Return cached visible text when the original file is unchanged.

    Size and modified time are always compared. The stored checksum is checked
    too when the file is small enough that hashing it is cheap. Larger files
    trust size and mtime so a search does not re-read them.
    """
    st = _stat(path)
    if st is None:
        return None
    meta = _read_meta(path)
    if not meta or not _fresh(path, meta, st):
        return None
    if st.st_size <= 2 * 1024 * 1024:
        digest = _sha256(path)
        if not digest or digest != meta.get("sha256"):
            return None
    try:
        return _text_path(path).read_text(encoding="utf-8")
    except OSError:
        return None


def save_extracted(path: Path, text: str) -> None:
    """Write text plus size, mtime, and checksum. Skips the write if the file changed mid-hash."""
    st = _stat(path)
    if st is None:
        return
    if st.st_size > _max_bytes():
        return
    meta = _read_meta(path)
    if meta and _fresh(path, meta, st) and _text_path(path).is_file():
        return
    digest = _sha256(path)
    if digest is None:
        return
    again = _stat(path)
    if again is None or not _fresh(path, {"size": st.st_size, "mtime_ns": st.st_mtime_ns}, again):
        return
    key = _key(path)
    folder = index_dir()
    text_tmp = folder / f"{key}.txt.tmp"
    meta_tmp = folder / f"{key}.json.tmp"
    payload = {
        "path": str(path),
        "size": int(again.st_size),
        "mtime_ns": int(again.st_mtime_ns),
        "sha256": digest,
    }
    try:
        text_tmp.write_text(text, encoding="utf-8")
        meta_tmp.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(text_tmp, _text_path(path))
        os.replace(meta_tmp, _meta_path(path))
    except OSError:
        logger.debug("Could not write text index for %s", path, exc_info=True)
        text_tmp.unlink(missing_ok=True)
        meta_tmp.unlink(missing_ok=True)


def _max_bytes() -> int:
    from lhr.extract import MAX_SEARCH_BYTES

    return MAX_SEARCH_BYTES


def schedule_save(path: Path, text: str) -> None:
    """Queue a cache write on a background thread in this process."""
    _ensure_writer()
    _SAVE_QUEUE.put((path, text))


def _ensure_writer() -> None:
    global _WRITER_STARTED
    with _WRITER_LOCK:
        if _WRITER_STARTED:
            return
        _WRITER_STARTED = True
        threading.Thread(target=_writer_loop, name="lhr-text-index-write", daemon=True).start()


def _writer_loop() -> None:
    while True:
        path, text = _SAVE_QUEUE.get()
        try:
            save_extracted(path, text)
        except Exception:
            logger.debug("Text index save failed for %s", path, exc_info=True)


def set_searching(active: bool) -> None:
    global _SEARCHING
    with _SEARCH_LOCK:
        _SEARCHING += 1 if active else -1
        if _SEARCHING < 0:
            _SEARCHING = 0


def _search_in_progress() -> bool:
    with _SEARCH_LOCK:
        return _SEARCHING > 0


def start_background_indexer() -> None:
    """Index project documents one at a time, off the search path."""
    global _CRAWLER_STARTED
    with _WRITER_LOCK:
        if _CRAWLER_STARTED:
            return
        _CRAWLER_STARTED = True
    threading.Thread(target=_crawler_loop, name="lhr-text-index", daemon=True).start()


def _crawler_loop() -> None:
    time.sleep(3)
    while True:
        try:
            _index_stale_files()
        except Exception:
            logger.exception("Text index crawl failed")
        time.sleep(60)


def _index_stale_files() -> None:
    from lhr.extract import DOC_SUFFIXES, extract_search_text
    from lhr.projects import list_projects

    for project in list_projects():
        for folder in project.get("folders") or []:
            if not folder.get("enabled", True):
                continue
            root = Path(str(folder.get("path") or ""))
            if not root.is_dir():
                continue
            for dirpath, _dirs, names in os.walk(root, followlinks=False):
                for name in names:
                    if Path(name).suffix.lower() not in DOC_SUFFIXES:
                        continue
                    while _search_in_progress():
                        time.sleep(0.4)
                    path = Path(dirpath) / name
                    if lookup_text(path) is not None:
                        continue
                    try:
                        text = extract_search_text(path)
                    except Exception:
                        logger.debug("Index extract failed for %s", path, exc_info=True)
                        continue
                    save_extracted(path, text)
                    time.sleep(0.2)
