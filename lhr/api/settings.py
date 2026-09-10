from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from lhr.settings import load_settings, patch_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])

ALLOWED = {
    "last_document",
    "window",
    "roots",
    "sidebar_width",
    "search_history",
    "page_search_history",
}


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
