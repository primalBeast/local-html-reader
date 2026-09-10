"""Live settings fan-out so every open window stays in sync."""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

logger = logging.getLogger("lhr.sync")

_subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
_sub_lock = threading.Lock()
_loop: asyncio.AbstractEventLoop | None = None


def set_loop(loop: asyncio.AbstractEventLoop | None) -> None:
    global _loop
    _loop = loop


def subscribe() -> asyncio.Queue[dict[str, Any]]:
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=8)
    with _sub_lock:
        _subscribers.add(queue)
    return queue


def unsubscribe(queue: asyncio.Queue[dict[str, Any]]) -> None:
    with _sub_lock:
        _subscribers.discard(queue)


def clear_subscribers() -> None:
    with _sub_lock:
        _subscribers.clear()


def broadcast(payload: dict[str, Any]) -> None:
    with _sub_lock:
        queues = list(_subscribers)
    if not queues:
        return
    loop = _loop

    def _enqueue(queue: asyncio.Queue[dict[str, Any]], data: dict[str, Any]) -> None:
        try:
            queue.put_nowait(data)
        except asyncio.QueueFull:
            try:
                queue.get_nowait()
            except Exception:
                pass
            try:
                queue.put_nowait(data)
            except Exception:
                pass

    for queue in queues:
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(_enqueue, queue, payload)
        else:
            _enqueue(queue, payload)


async def run_poller(interval: float = 0.25) -> None:
    """Watch settings.json so other processes' writes reach this server's windows."""
    from lhr.paths import settings_path

    last: tuple[int, int] | None = None
    path = settings_path()
    while True:
        await asyncio.sleep(interval)
        with _sub_lock:
            if not _subscribers:
                last = None
                continue
        try:
            st = path.stat()
            sig = (st.st_mtime_ns, st.st_size)
        except OSError:
            continue
        if last is None:
            last = sig
            continue
        if sig == last:
            continue
        last = sig
        try:
            from lhr.settings import load_settings

            broadcast(load_settings())
        except Exception:
            logger.exception("settings poll failed")
