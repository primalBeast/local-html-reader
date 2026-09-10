from __future__ import annotations

import asyncio
import json
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from lhr.settings import add_search_term, load_settings, patch_settings, remove_search_term
from lhr.sync import subscribe, unsubscribe

router = APIRouter(prefix="/api/settings", tags=["settings"])

ALLOWED = {
    "last_document",
    "window",
    "roots",
    "sidebar_width",
    "search_history",
    "page_search_history",
}

HistoryBucket = Literal["search_history", "page_search_history"]


class HistoryChange(BaseModel):
    bucket: HistoryBucket
    term: str = Field(min_length=1)


@router.get("")
def get_settings() -> dict[str, Any]:
    return load_settings()


@router.patch("")
async def update_settings(request: Request) -> dict[str, Any]:
    raw = await request.json()
    if not isinstance(raw, dict):
        return load_settings()
    updates = {k: v for k, v in raw.items() if k in ALLOWED}
    return patch_settings(updates)


@router.post("/history")
def post_history(body: HistoryChange) -> dict[str, Any]:
    history = add_search_term(body.bucket, body.term)
    return {"bucket": body.bucket, "history": history}


@router.delete("/history")
def delete_history(
    bucket: HistoryBucket = Query(...),
    term: str = Query(..., min_length=1),
) -> dict[str, Any]:
    try:
        history = remove_search_term(bucket, term)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"bucket": bucket, "history": history}


@router.get("/events")
async def settings_events():
    queue = subscribe()

    async def gen():
        try:
            yield f"data: {json.dumps(load_settings(), ensure_ascii=False)}\n\n"
            while True:
                payload = await queue.get()
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        except asyncio.CancelledError:
            raise
        finally:
            unsubscribe(queue)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
