"""Atomic JSON read/write helpers."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


def read_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    last_exc: OSError | None = None
    for attempt in range(10):
        try:
            os.replace(tmp, path)
            return
        except PermissionError as exc:
            last_exc = exc
            time.sleep(0.05 * (attempt + 1))
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                pass
            try:
                with tmp.open("r", encoding="utf-8") as src, path.open("w", encoding="utf-8") as dest:
                    dest.write(src.read())
                    dest.flush()
                    os.fsync(dest.fileno())
                tmp.unlink(missing_ok=True)
                return
            except OSError as copy_exc:
                last_exc = copy_exc
                time.sleep(0.05 * (attempt + 1))
    tmp.unlink(missing_ok=True)
    if last_exc:
        raise last_exc
    raise PermissionError(f"could not write {path}")
