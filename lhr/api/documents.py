from __future__ import annotations

import mimetypes
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from lhr import documents
from lhr.paths import PathEscapeError

router = APIRouter(tags=["documents"])


@router.get("/api/documents")
def list_documents(
    q: str | None = Query(default=None),
    root_id: str | None = Query(default=None),
) -> dict:
    try:
        return documents.list_documents(query=q, root_id=root_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/view/{root_id}/{rel_path:path}")
def view_file(root_id: str, rel_path: str):
    rel = unquote(rel_path or "")
    try:
        path = documents.resolve_document(root_id, rel)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PathEscapeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not path.is_file():
        raise HTTPException(status_code=404, detail="file not found")

    media, _enc = mimetypes.guess_type(str(path))
    if path.suffix.lower() in {".html", ".htm"}:
        media = "text/html; charset=utf-8"
    return FileResponse(
        path,
        media_type=media or "application/octet-stream",
        filename=path.name,
        content_disposition_type="inline",
    )
