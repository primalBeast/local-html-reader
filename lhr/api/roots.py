from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from lhr import documents

router = APIRouter(prefix="/api/roots", tags=["roots"])


class RootCreate(BaseModel):
    path: str = Field(min_length=1)


class RootEnabled(BaseModel):
    enabled: bool


@router.get("")
def get_roots(project: str | None = Query(default=None)) -> dict:
    try:
        return {"roots": documents.list_roots(project=project)}
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, FileNotFoundError) else 400, detail=str(exc)) from exc


@router.post("")
def create_root(body: RootCreate, project: str | None = Query(default=None)) -> dict:
    try:
        rec = documents.add_root(body.path, project=project)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return rec


@router.put("")
def replace_root(body: RootCreate, project: str | None = Query(default=None)) -> dict:
    """Set the single documents-root folder from the app menu."""
    try:
        rec = documents.set_root(body.path, project=project)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return rec


@router.patch("/{root_id}")
def patch_root(root_id: str, body: RootEnabled, project: str | None = Query(default=None)) -> dict:
    try:
        rec = documents.set_root_enabled(root_id, body.enabled, project=project)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError:
        raise HTTPException(status_code=404, detail="documents root not found") from None
    return rec


@router.delete("/{root_id}")
def delete_root(root_id: str, project: str | None = Query(default=None)) -> dict:
    if not documents.remove_root(root_id, project=project):
        raise HTTPException(status_code=404, detail="documents root not found")
    return {"ok": True, "id": root_id}
