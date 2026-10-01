"""
pending_updates.md — the agent work queue (one ``- path: message`` bullet per item).

Mutations run under the project lock and always rewrite a normalized file:
header + either the empty marker or a de-duplicated bullet list, never both.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from .. import locking
from .store import PENDING_MD, RootLike, _coerce_root, _normalize_to_relative

_EMPTY_PENDING_MARKER = "(no pending items — run check-changes after making edits)"
_EMPTY_PENDING_LINES = ["# Pending Updates", "", _EMPTY_PENDING_MARKER]


def _get_pending_path(root: Path) -> Path:
    return Path(root) / PENDING_MD


def _is_pending_item_line(line: str) -> bool:
    """True for real work-queue bullets (``- path: msg``), not headers or markers."""
    s = (line or "").strip()
    return s.startswith("- ") and not s.startswith("- (")


def _pending_item_lines(lines: List[str]) -> List[str]:
    return [ln.strip() for ln in lines if _is_pending_item_line(ln)]


def pending_item_path(line: str) -> Optional[str]:
    """The file path of a ``- path: message`` bullet, or None for non-items."""
    if not _is_pending_item_line(line):
        return None
    body = line.strip()[2:]
    path, sep, _msg = body.partition(": ")
    if not sep:
        path = body.split(":", 1)[0]
    return path.strip() or None


def _normalize_pending_lines(lines: List[str]) -> List[str]:
    items = _pending_item_lines(lines or [])
    if not items:
        return list(_EMPTY_PENDING_LINES)
    seen = set()
    unique: List[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return ["# Pending Updates", ""] + unique


def _read_pending_lines(root: Path) -> List[str]:
    path = _get_pending_path(root)
    if not path.exists():
        return list(_EMPTY_PENDING_LINES)
    with open(path, "r", encoding="utf-8") as f:
        return f.read().splitlines()


def _write_pending_lines(root: Path, lines: List[str]) -> None:
    path = _get_pending_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(_normalize_pending_lines(lines)) + "\n")
    os.replace(tmp, path)


def count_pending(root: RootLike) -> int:
    """Number of real pending work items."""
    return len(_pending_item_lines(_read_pending_lines(_coerce_root(root))))


def _do_remove_from_pending(root: RootLike, file: str) -> int:
    """Remove every item whose path is exactly ``file`` (caller holds the lock)."""
    root = _coerce_root(root)
    target = _normalize_to_relative(root, file)
    items = _pending_item_lines(_read_pending_lines(root))
    kept = [ln for ln in items if _normalize_to_relative(root, pending_item_path(ln) or "") != target]
    _write_pending_lines(root, kept)
    return len(items) - len(kept)


def remove_from_pending(root: RootLike, file: str) -> int:
    """Remove all pending items for ``file``. Idempotent; returns the count removed."""
    root = _coerce_root(root)
    with locking.file_lock(root):
        return _do_remove_from_pending(root, file)


def _do_add_to_pending(root: RootLike, file: str, msg: str) -> None:
    """Append an item (idempotent; caller holds the lock)."""
    root = _coerce_root(root)
    entry = f"- {_normalize_to_relative(root, file)}: {msg}"
    items = _pending_item_lines(_read_pending_lines(root))
    if entry not in items:
        items.append(entry)
    _write_pending_lines(root, items)


def add_to_pending(root: RootLike, file: str, msg: str) -> None:
    """Append an item to pending_updates.md (locked, idempotent)."""
    root = _coerce_root(root)
    with locking.file_lock(root):
        _do_add_to_pending(root, file, msg)
