"""
Project-root and project-path normalization (single source of truth).

AGENT MAP:
  resolve_root(project_root)  — explicit arg → WIKIFIER_PROJECT_ROOT → discovery.
                                An explicit root that does not exist raises
                                ProjectRootError (never silently falls back).
  to_rel(root, file)          — canonical project-relative POSIX key for a file
                                argument (absolute, ./relative, or backslashes).
  is_under(root, key)         — whether a stored key lives inside the project.

Every public entry point (library, CLI, MCP) goes through these two helpers so
health keys, pending items and journal entries always agree on a file's name.
"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
from typing import Optional, Union

from .project_root import discover_project_root

PathLike = Union[str, Path]


class ProjectRootError(ValueError):
    """An explicitly requested project root is missing or not a directory."""


class ProjectPathError(ValueError):
    """A file argument is empty or points outside the project root."""


def resolve_root(project_root: Optional[PathLike] = None) -> Path:
    """Return the absolute project root for an operation.

    Priority: explicit ``project_root`` → ``WIKIFIER_PROJECT_ROOT`` → marker
    discovery from the current directory. An explicit value (argument or env)
    that is not an existing directory raises ``ProjectRootError`` — writing
    state into some other directory is never an acceptable fallback.
    """
    if project_root not in (None, ""):
        candidate = Path(str(project_root)).expanduser()
        if not candidate.is_dir():
            raise ProjectRootError(
                f"project_root is not an existing directory: {project_root}"
            )
        return candidate.resolve()
    env_root = os.environ.get("WIKIFIER_PROJECT_ROOT")
    if env_root:
        candidate = Path(env_root).expanduser()
        if not candidate.is_dir():
            raise ProjectRootError(
                f"WIKIFIER_PROJECT_ROOT is not an existing directory: {env_root}"
            )
        return candidate.resolve()
    return Path(discover_project_root()).resolve()


def _lexical_rel(path: str) -> Optional[str]:
    """Collapse ``.``/``..`` segments without touching the filesystem.

    Returns None when the path climbs above its starting point.
    """
    parts = []
    for part in PurePosixPath(path).parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
            continue
        parts.append(part)
    return "/".join(parts) if parts else None


def to_rel(root: PathLike, file: PathLike) -> str:
    """Canonical project-relative POSIX key for ``file``.

    Accepts absolute paths (inside the root, with or without symlinks in the
    root itself, e.g. ``/tmp`` vs ``/private/tmp`` on macOS), ``./``-prefixed
    or plain relative paths, and Windows separators. Raises
    ``ProjectPathError`` for empty input or a path outside the root.
    """
    text = str(file).strip().replace("\\", "/")
    if not text:
        raise ProjectPathError("file path is empty")
    root_path = Path(root)
    if PurePosixPath(text).is_absolute() or Path(text).is_absolute():
        absolute = os.path.normpath(text)
        for base in (str(root_path), str(root_path.resolve())):
            try:
                rel = os.path.relpath(absolute, base)
            except ValueError:  # different drive on Windows
                continue
            rel = rel.replace("\\", "/")
            if rel != ".." and not rel.startswith("../") and rel != ".":
                return rel
        try:
            return Path(absolute).resolve().relative_to(root_path.resolve()).as_posix()
        except ValueError:
            raise ProjectPathError(f"{file} is outside project root {root_path}") from None
    rel = _lexical_rel(text)
    if rel is None:
        raise ProjectPathError(f"{file} is outside project root {root_path}")
    return rel


def is_under(root: PathLike, key: str) -> bool:
    """True when a stored health/cache key refers to a path inside ``root``."""
    try:
        to_rel(root, key)
        return True
    except ProjectPathError:
        return False
