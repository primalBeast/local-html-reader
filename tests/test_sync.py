"""Shared-settings broadcast used by live windows."""

from __future__ import annotations

import asyncio

from lhr.sync import broadcast, clear_subscribers, set_loop, subscribe, unsubscribe


def test_broadcast_reaches_subscriber() -> None:
    async def _run() -> None:
        clear_subscribers()
        set_loop(asyncio.get_running_loop())
        queue = subscribe()
        try:
            broadcast({"search_history": ["alpha"]})
            payload = await asyncio.wait_for(queue.get(), timeout=1)
            assert payload["search_history"] == ["alpha"]
        finally:
            unsubscribe(queue)
            clear_subscribers()
            set_loop(None)

    asyncio.run(_run())
