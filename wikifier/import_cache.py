"""
Import Cache for Incremental update-maps (M2-Rem-03)

Stores parsed import information per file so that only changed files
need to be re-parsed on subsequent update-maps runs.

This design is intended to scale from small projects to massive monorepos.
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional

# Import locking (M2-Rem-07)
try:
    from . import locking
except ImportError:
    locking = None

CACHE_FILE = ".wikifier_staging/import_cache.json"


def _get_cache_path(root: Path) -> Path:
    return root / CACHE_FILE


def load_cache(root: Path) -> Dict[str, Any]:
    """Load the import cache. Returns empty dict if not present."""
    cache_path = _get_cache_path(root)
    if not cache_path.exists():
        return {}
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_cache(root: Path, cache: Dict[str, Any]) -> None:
    """Save the import cache to disk.

    Uses file locking (M2-Rem-07) to prevent corruption when multiple
    agents are running update-maps or health operations concurrently.
    """
    if locking:
        with locking.file_lock(root):
            _do_save_cache(root, cache)
    else:
        _do_save_cache(root, cache)


def _do_save_cache(root: Path, cache: Dict[str, Any]) -> None:
    """Internal save without locking."""
    cache_path = _get_cache_path(root)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def get_file_data(cache: Dict[str, Any], rel_path: str) -> Optional[Dict[str, Any]]:
    """Return cached data for a relative path, or None if not present."""
    return cache.get(rel_path)


def get_reverse_dependencies(cache: Dict[str, Any]) -> Dict[str, List[str]]:
    """
    Return the reverse dependency map: target_path -> list of source files that import it.
    Stored under a reserved top-level key to avoid colliding with file entries.
    """
    return cache.get("_reverse_dependencies", {})


def set_reverse_dependencies(cache: Dict[str, Any], reverse_deps: Dict[str, List[str]]) -> None:
    """
    Store the reverse dependency map.
    This allows get_dependents() to work efficiently even in incremental mode.
    """
    if reverse_deps:
        cache["_reverse_dependencies"] = reverse_deps
    else:
        cache.pop("_reverse_dependencies", None)


def update_file_data(
    cache: Dict[str, Any],
    rel_path: str,
    mtime: int,
    imports: List[str],
    resolved: Optional[List[str]] = None,
    resolved_pairs: Optional[List[Dict[str, str]]] = None,
    dependents: Optional[List[str]] = None
) -> None:
    """
    Update or insert data for a file in the cache.

    resolved_pairs (preferred for table + Mermaid generation):
        List of {"raw": "...", "resolved": "...", "confidence": "high|medium|low"}

    dependents: List of files that import this file (reverse dependencies).
    This enables fast per-file "who depends on me" queries and richer Mermaid graphs.
    """
    # Normalize resolved_pairs to always include confidence (for backward compat)
    normalized_pairs = []
    for p in (resolved_pairs or []):
        if isinstance(p, dict):
            normalized_pairs.append({
                "raw": p.get("raw", ""),
                "resolved": p.get("resolved", ""),
                "confidence": p.get("confidence", "medium")
            })

    entry = {
        "mtime": mtime,
        "imports": imports,
        "resolved": resolved or [],
        "resolved_pairs": normalized_pairs
    }

    if dependents is not None:
        entry["dependents"] = dependents

    cache[rel_path] = entry


def get_mtime(file_path: Path) -> int:
    """Get the mtime of a file (cross-platform)."""
    try:
        return int(file_path.stat().st_mtime)
    except Exception:
        return 0


if __name__ == "__main__":
    import sys
    print("Wikifier Import Cache module. Import it from Python or use via shell helpers.")
