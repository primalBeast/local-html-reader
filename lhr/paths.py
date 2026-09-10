"""Path helpers and sandboxing for documents-root folders."""

from __future__ import annotations

from pathlib import Path

from lhr.config import get_config


class PathEscapeError(ValueError):
    """Raised when a path would escape a configured documents root."""


def data_root() -> Path:
    return get_config().data_dir


def settings_path() -> Path:
    return data_root() / "settings.json"


def is_within(root: Path, candidate: Path) -> bool:
    """True if candidate is root or a descendant after resolving symlinks."""
    try:
        root_r = root.resolve()
        cand_r = candidate.resolve()
    except OSError:
        return False
    try:
        cand_r.relative_to(root_r)
    except ValueError:
        return False
    return True


def normalize_rel(rel: str) -> str:
    """Normalize a relative path; reject traversal, absolute paths, and NUL."""
    if rel is None:
        raise PathEscapeError("empty path")
    text = str(rel).strip()
    if not text:
        raise PathEscapeError("empty path")
    if "\x00" in text:
        raise PathEscapeError("invalid path")

    p = Path(text)
    if p.is_absolute() or p.drive:
        raise PathEscapeError("absolute path not allowed")
    if text.startswith(("/", "\\")):
        raise PathEscapeError("absolute path not allowed")

    parts: list[str] = []
    for part in p.parts:
        if part in ("/", "\\"):
            raise PathEscapeError("absolute path not allowed")
        if part == "..":
            raise PathEscapeError("path traversal is not allowed")
        if part in (".", ""):
            continue
        parts.append(part)
    if not parts:
        raise PathEscapeError("empty path")
    return "/".join(parts)


def resolve_under_root(root: Path, rel: str) -> Path:
    """Resolve rel under root, or raise PathEscapeError if it escapes."""
    if not root:
        raise PathEscapeError("missing documents root")
    try:
        root_r = root.expanduser().resolve()
    except OSError as exc:
        raise PathEscapeError(f"cannot resolve documents root: {exc}") from exc
    if not root_r.is_dir():
        raise PathEscapeError("documents root is not a directory")

    norm = normalize_rel(rel)
    candidate = (root_r / Path(*norm.split("/"))).resolve()
    if not is_within(root_r, candidate):
        raise PathEscapeError("path escapes documents root")
    return candidate
