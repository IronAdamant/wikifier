"""Cache I/O — SQLite-primary load/save (legacy JSON dual-read)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

try:
    from .. import locking
except ImportError:
    locking = None

CACHE_FILE = ".wikifier_staging/import_cache.json"


def _get_cache_path(root: Path) -> Path:
    """Legacy JSON path (still used for dual-read / optional dual-write)."""
    return Path(root) / CACHE_FILE


def load_cache(root: Path) -> Dict[str, Any]:
    """Load the import cache (SQLite primary, legacy JSON dual-read)."""
    try:
        from .. import cache_store as cs
        return cs.load_cache_dict(Path(root)) or {}
    except Exception:
        pass
    cache_path = _get_cache_path(Path(root))
    if not cache_path.exists():
        return {}
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_mtime_index(root: Path) -> Dict[str, Dict[str, Any]]:
    """Light dirty index: rel → {mtime, content_hash}."""
    try:
        from .. import cache_store as cs
        return cs.load_mtime_index(Path(root))
    except Exception:
        cache = load_cache(root) or {}
        out: Dict[str, Dict[str, Any]] = {}
        for k, v in cache.items():
            if isinstance(k, str) and not k.startswith("_") and isinstance(v, dict):
                out[k] = {
                    "mtime": int(v.get("mtime", 0) or 0),
                    "content_hash": v.get("content_hash"),
                }
        return out


def save_cache(root: Path, cache: Dict[str, Any]) -> None:
    """Save the import cache (SQLite primary; optional JSON dual-write)."""
    if os.environ.get("WIKIFIER_DEBUG_SAVES"):
        import sys as _sys
        import traceback
        frames = "".join(traceback.format_stack()[-4:-1])
        print(f"[save_cache] root={root}\n{frames}", file=_sys.stderr)
    if locking:
        with locking.file_lock(root):
            _do_save_cache(root, cache)
    else:
        _do_save_cache(root, cache)


def _do_save_cache(root: Path, cache: Dict[str, Any]) -> None:
    """Internal save without locking — SQLite via cache_store."""
    try:
        from .. import cache_store as cs
        cs.save_cache_dict(Path(root), cache)
        return
    except Exception:
        pass
    cache_path = _get_cache_path(Path(root))
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, separators=(",", ":"))
