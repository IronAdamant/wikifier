"""Shared helpers for optional modular MCP tool modules (no FastMCP instance)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def _get_effective_root(project_root: Optional[str] = None) -> Path:
    try:
        from wikifier.api import _get_effective_root as _fn
        return _fn(project_root)
    except Exception:
        if project_root:
            return Path(project_root).expanduser().resolve()
        return Path.cwd().resolve()
