"""Inter-process exclusive lock for settings.json writes."""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def exclusive_file_lock(path: Path, timeout: float = 5.0) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = path.open("a+b")
    try:
        if fh.tell() == 0:
            fh.write(b"\0")
            fh.flush()
        _acquire(fh, timeout)
        try:
            yield
        finally:
            _release(fh)
    finally:
        fh.close()


def _acquire(fh, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    if os.name == "nt":
        import msvcrt

        while True:
            try:
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"timed out locking {fh.name}")
                time.sleep(0.02)
    import fcntl

    while True:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except OSError:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"timed out locking {fh.name}")
            time.sleep(0.02)


def _release(fh) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
