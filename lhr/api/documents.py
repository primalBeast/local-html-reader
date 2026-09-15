from __future__ import annotations

import json
import mimetypes
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse

from lhr import documents
from lhr.paths import PathEscapeError

router = APIRouter(tags=["documents"])


@router.get("/api/documents")
def list_documents(
    q: str | None = Query(default=None),
    root_id: str | None = Query(default=None),
    project: str | None = Query(default=None),
) -> dict:
    try:
        return documents.list_documents(query=q, root_id=root_id, project=project)
    except (KeyError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/tree")
def document_tree(
    q: str | None = Query(default=None),
    root_id: str | None = Query(default=None),
    project: str | None = Query(default=None),
) -> dict:
    try:
        return documents.document_tree(query=q, root_id=root_id, project=project)
    except (KeyError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/tree/stream")
def document_tree_stream(
    q: str | None = Query(default=None),
    root_id: str | None = Query(default=None),
    project: str | None = Query(default=None),
):
    def events():
        hits: list = []
        try:
            yield f"event: progress\ndata: {json.dumps({'file_count': 0, 'truncated': False})}\n\n"
            for hit in documents.iter_matching_html(query=q, root_id=root_id, project=project):
                hits.append(hit)
                yield (
                    "event: progress\n"
                    f"data: {json.dumps({'file_count': len(hits), 'truncated': False})}\n\n"
                )
            hits.sort(key=lambda h: (h["root_path"].lower(), h["rel"].lower()))
            payload = {
                "tree": documents.tree_from_hits(hits),
                "file_count": len(hits),
                "truncated": len(hits) >= documents.MAX_LIST,
                "query": (q or "").strip(),
            }
            yield f"event: done\ndata: {json.dumps(payload)}\n\n"
        except (KeyError, FileNotFoundError, ValueError) as exc:
            yield f"event: fail\ndata: {json.dumps({'detail': str(exc)})}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/view/{root_id}/{rel_path:path}")
def view_file(root_id: str, rel_path: str, project: str | None = Query(default=None)):
    rel = unquote(rel_path or "")
    try:
        path = documents.resolve_document(root_id, rel, project=project)
    except (KeyError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PathEscapeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not path.is_file():
        raise HTTPException(status_code=404, detail="file not found")

    suffix = path.suffix.lower()
    if suffix in {".md", ".markdown"}:
        from lhr.md_view import markdown_to_html_page

        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise HTTPException(status_code=404, detail="file not found") from exc
        return HTMLResponse(markdown_to_html_page(path.name, raw))

    media, _enc = mimetypes.guess_type(str(path))
    if suffix in {".html", ".htm"}:
        media = "text/html; charset=utf-8"
    elif suffix == ".pdf":
        # No filename= — Edge treats Content-Disposition filename in an iframe/embed
        # as a download and shows "This page has been blocked by Microsoft Edge".
        return FileResponse(
            path,
            media_type="application/pdf",
            headers={"Content-Disposition": "inline"},
        )
    return FileResponse(
        path,
        media_type=media or "application/octet-stream",
        filename=path.name,
        content_disposition_type="inline",
    )
