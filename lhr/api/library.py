from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from lhr import library
from lhr.paths import PathEscapeError

router = APIRouter(prefix="/api/library", tags=["library"])


class DocumentRef(BaseModel):
    root_id: str = Field(min_length=1, max_length=64)
    rel: str = Field(min_length=1, max_length=2048)


class NoteBody(DocumentRef):
    text: str = Field(default="", max_length=20_000)


class PositionBody(DocumentRef):
    ratio: float


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (KeyError, FileNotFoundError)):
        return HTTPException(status_code=404, detail="file not found")
    if isinstance(exc, PathEscapeError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=400, detail="could not update library")


@router.get("")
def get_library(project: str | None = Query(default=None)) -> dict:
    try:
        return library.load_library(project)
    except (ValueError, FileNotFoundError) as exc:
        raise _map_error(exc) from exc


@router.post("/recent")
def post_recent(body: DocumentRef, project: str | None = Query(default=None)) -> dict:
    try:
        return library.touch_recent(body.root_id, body.rel, project=project)
    except (KeyError, FileNotFoundError, PathEscapeError, ValueError) as exc:
        raise _map_error(exc) from exc


@router.post("/bookmark")
def post_bookmark(body: DocumentRef, project: str | None = Query(default=None)) -> dict:
    try:
        return library.toggle_bookmark(body.root_id, body.rel, project=project)
    except (KeyError, FileNotFoundError, PathEscapeError, ValueError) as exc:
        raise _map_error(exc) from exc


@router.put("/note")
def put_note(body: NoteBody, project: str | None = Query(default=None)) -> dict:
    try:
        return library.set_note(body.root_id, body.rel, body.text, project=project)
    except (KeyError, FileNotFoundError, PathEscapeError, ValueError) as exc:
        raise _map_error(exc) from exc


@router.put("/position")
def put_position(body: PositionBody, project: str | None = Query(default=None)) -> dict:
    try:
        return library.set_position(body.root_id, body.rel, body.ratio, project=project)
    except (KeyError, FileNotFoundError, PathEscapeError, ValueError) as exc:
        raise _map_error(exc) from exc
