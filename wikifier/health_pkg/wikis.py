"""
Where a file's wiki lives and how wiki/source bytes are fingerprinted.

Shared by ``freshness`` (mark-green, stale wikis) and ``verify`` (wiki vs code);
kept separate so neither imports the other at module level.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

from .store import RootLike

WIKI_DIRS = ("docs/wiki", "docs", "wiki", "documentation", ".wiki")


def _sha256_file(path: Optional[Path]) -> Optional[str]:
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    try:
        return "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()
    except OSError:
        return None


def _compute_wiki_content_hash(wiki_path: Optional[Path]) -> Optional[str]:
    """``sha256:<hex>`` of a wiki file, or None when absent/unreadable."""
    return _sha256_file(wiki_path)


def _find_existing_wiki_file(root: RootLike, rel_path: str) -> Optional[Path]:
    """Locate the wiki summary for a source file (sibling ``.wiki.md`` first)."""
    root = Path(root)
    rel = Path(rel_path)
    candidates = [root / f"{rel_path}.wiki.md", root / f"{rel_path}.md"]
    if rel.suffix:
        stem = rel.with_suffix("")
        candidates += [root / f"{stem}.wiki.md", root / f"{stem}.md"]
    for d in WIKI_DIRS:
        candidates += [root / d / f"{rel.name}.wiki.md", root / d / f"{rel.name}.md"]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None
