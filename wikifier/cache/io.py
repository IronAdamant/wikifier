"""Cache I/O — SQLite store (``wikifier.cache_store``) behind the historical dict API."""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path
from typing import Any, Dict

from .. import cache_store as cs
from .. import locking

CACHE_FILE = ".wikifier_staging/import_cache.json"  # legacy path, read when no database exists


def load_cache(root: Path) -> Dict[str, Any]:
    """Full cache dict (file entries + reserved ``_*`` keys)."""
    return cs.load_cache_dict(Path(root))


def load_mtime_index(root: Path) -> Dict[str, Dict[str, Any]]:
    """Light dirty-detection index: ``rel → {mtime, content_hash}``."""
    return cs.load_mtime_index(Path(root))


def save_cache(root: Path, cache: Dict[str, Any]) -> None:
    """Persist the cache under the project lock."""
    if os.environ.get("WIKIFIER_DEBUG_SAVES"):
        frames = "".join(traceback.format_stack()[-4:-1])
        print(f"[save_cache] root={root}\n{frames}", file=sys.stderr)
    with locking.file_lock(Path(root)):
        _do_save_cache(root, cache)


def _do_save_cache(root: Path, cache: Dict[str, Any]) -> None:
    """Persist without taking the lock (caller holds it)."""
    cs.save_cache_dict(Path(root), cache)
