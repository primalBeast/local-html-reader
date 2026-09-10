from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from lhr import documents

router = APIRouter(prefix="/api/roots", tags=["roots"])


class RootCreate(BaseModel):
    path: str = Field(min_length=1)


@router.get("")
def get_roots() -> dict:
    return {"roots": documents.list_roots()}


@router.post("")
def create_root(body: RootCreate) -> dict:
    try:
        rec = documents.add_root(body.path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return rec


@router.put("")
def replace_root(body: RootCreate) -> dict:
    """Set the single documents-root folder from the app menu."""
    try:
        rec = documents.set_root(body.path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return rec


@router.delete("/{root_id}")
def delete_root(root_id: str) -> dict:
    if not documents.remove_root(root_id):
        raise HTTPException(status_code=404, detail="documents root not found")
    return {"ok": True, "id": root_id}
