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
    use_regex: bool = Query(default=False),
    match_case: bool = Query(default=False),
    whole_word: bool = Query(default=False),
) -> dict:
    try:
        return documents.list_documents(
            query=q,
            root_id=root_id,
            project=project,
            regex=use_regex,
            match_case=match_case,
            whole_word=whole_word,
        )
    except (KeyError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/tree")
def document_tree(
    q: str | None = Query(default=None),
    root_id: str | None = Query(default=None),
    project: str | None = Query(default=None),
    use_regex: bool = Query(default=False),
    match_case: bool = Query(default=False),
    whole_word: bool = Query(default=False),
) -> dict:
    try:
        return documents.document_tree(
            query=q,
            root_id=root_id,
            project=project,
            regex=use_regex,
            match_case=match_case,
            whole_word=whole_word,
        )
    except (KeyError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/tree/stream")
def document_tree_stream(
    q: str | None = Query(default=None),
    root_id: str | None = Query(default=None),
    project: str | None = Query(default=None),
    use_regex: bool = Query(default=False),
    match_case: bool = Query(default=False),
    whole_word: bool = Query(default=False),
):
    def events():
        hits: list = []
        try:
            for kind, payload in documents.iter_search_activity(
                query=q,
                root_id=root_id,
                project=project,
                regex=use_regex,
                match_case=match_case,
                whole_word=whole_word,
            ):
                if kind == "hit":
                    hits.append(payload)
                    data = {
                        "file_count": len(hits),
                        "truncated": False,
                        "tree": documents.tree_from_hits(hits),
                    }
                else:
                    data = {
                        "file_count": len(hits),
                        "truncated": False,
                        "workers": payload,
                    }
                yield f"event: progress\ndata: {json.dumps(data)}\n\n"
            hits.sort(key=lambda h: (h["root_path"].lower(), h["rel"].lower()))
            payload = {
                "tree": documents.tree_from_hits(hits),
                "file_count": len(hits),
                "truncated": len(hits) >= documents.MAX_LIST,
                "query": (q or "").strip(),
                "workers": [],
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

    if suffix in {".docx", ".dotx"}:
        from lhr.docx_view import docx_to_html_page

        return HTMLResponse(docx_to_html_page(path.name, path))

    media, _enc = mimetypes.guess_type(str(path))
    if suffix in {".html", ".htm"}:
        # No filename= — Edge blocks iframe documents with Content-Disposition filename
        # ("This page has been blocked by Microsoft Edge"), so in-page search sees no text.
        return FileResponse(
            path,
            media_type="text/html; charset=utf-8",
            headers={"Content-Disposition": "inline"},
        )
    if suffix == ".pdf":
        return FileResponse(
            path,
            media_type="application/pdf",
            headers={"Content-Disposition": "inline"},
        )
    return FileResponse(
        path,
        media_type=media or "application/octet-stream",
        content_disposition_type="inline",
    )
