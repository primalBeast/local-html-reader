from __future__ import annotations

from fastapi import APIRouter

from lhr.limits import help_document

router = APIRouter(tags=["help"])


@router.get("/api/help")
def get_help() -> dict:
    return help_document()
