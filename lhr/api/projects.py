from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from lhr import projects

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1)


class ProjectPatch(BaseModel):
    name: str | None = None


class FolderCreate(BaseModel):
    path: str = Field(min_length=1)


class FolderPatch(BaseModel):
    enabled: bool


@router.get("")
def list_projects() -> dict[str, Any]:
    return {"current_slug": projects.current_slug(), "projects": projects.list_projects()}


@router.post("", status_code=201)
def create_project(body: ProjectCreate) -> dict[str, Any]:
    try:
        return projects.create_project(body.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=503,
            detail="Could not save project data (file in use). Try again.",
        ) from exc


@router.post("/{slug}/select")
def select_project(slug: str) -> dict[str, Any]:
    try:
        return projects.select_project(slug)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="project not found") from None


@router.patch("/{slug}")
def patch_project(slug: str, body: ProjectPatch) -> dict[str, Any]:
    try:
        if body.name is not None:
            return projects.rename_project(slug, body.name)
        return projects.load_project(slug)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="project not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{slug}")
def delete_project(slug: str) -> dict[str, Any]:
    try:
        projects.delete_project(slug)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="project not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=503,
            detail="Could not delete project files (file in use). Try again.",
        ) from exc
    return {"ok": True, "current_slug": projects.current_slug()}


@router.post("/{slug}/folders")
def add_folder(slug: str, body: FolderCreate) -> dict[str, Any]:
    try:
        return projects.add_folder(slug, body.path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="project not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/{slug}/folders/{folder_id}")
def patch_folder(slug: str, folder_id: str, body: FolderPatch) -> dict[str, Any]:
    try:
        rec = projects.set_folder_enabled(slug, folder_id, body.enabled)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="project not found") from None
    except KeyError:
        raise HTTPException(status_code=404, detail="folder not found") from None
    return rec


@router.delete("/{slug}/folders/{folder_id}")
def delete_folder(slug: str, folder_id: str) -> dict[str, Any]:
    try:
        projects.remove_folder(slug, folder_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="project not found") from None
    except KeyError:
        raise HTTPException(status_code=404, detail="folder not found") from None
    return {"ok": True, "id": folder_id}
