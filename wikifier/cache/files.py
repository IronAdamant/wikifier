"""
File-level cache operations - get/update file data, mtime, content hashing.
"""
import hashlib
import os
from pathlib import Path
from typing import Dict, Any, Optional, List, Set, Tuple


def get_file_data(cache: Dict[str, Any], rel_path: str) -> Optional[Dict[str, Any]]:
    """Return cached data for a relative path, or None if not present."""
    return cache.get(rel_path)


def update_file_data(
    cache: Dict[str, Any],
    rel_path: str,
    mtime: int,
    resolved_pairs: Optional[List[Dict[str, Any]]] = None,
    content_hash: Optional[str] = None
) -> None:
    """
    Update or create an entry for a file in the cache.
    
    Preserves existing barrel resolution metadata and rich pair fields when updating.
    Only overwrites mtime, resolved_pairs if provided, and optionally content_hash.
    """
    existing = cache.get(rel_path, {})
    if not isinstance(existing, dict):
        existing = {}
    
    updated = {
        "mtime": mtime,
    }
    
    if resolved_pairs is not None:
        updated["resolved_pairs"] = resolved_pairs
    elif "resolved_pairs" in existing:
        updated["resolved_pairs"] = existing["resolved_pairs"]
    
    if content_hash is not None:
        updated["content_hash"] = content_hash
    elif "content_hash" in existing:
        updated["content_hash"] = existing["content_hash"]
    
    # Preserve barrel metadata if present
    for key in ["barrel_chains", "barrel_metadata"]:
        if key in existing:
            updated[key] = existing[key]
    
    cache[rel_path] = updated


def get_mtime(file_path: Path) -> int:
    """Return file modification time as integer timestamp, or 0 if file doesn't exist."""
    try:
        return int(file_path.stat().st_mtime)
    except (OSError, ValueError):
        return 0


def compute_file_content_hash(file_path: Path) -> Optional[str]:
    """
    Compute SHA256 hash of file content for content-based dirty detection.
    
    Returns hex digest string or None if file is unreadable.
    Used to distinguish real content changes from mtime-only updates.
    """
    try:
        if not file_path.is_file():
            return None
        data = file_path.read_bytes()
        return hashlib.sha256(data).hexdigest()
    except Exception:
        return None


def compute_files_needing_reparse(
    root: Path,
    cache: Dict[str, Any],
    changed_files: Set[str],
    include_stale_importers: bool = True
) -> Tuple[Set[str], Dict[str, Any]]:
    """
    Determine which files need reparsing based on changes and barrel invalidation.
    
    Args:
        root: Project root path
        cache: The import cache dict
        changed_files: Set of files known to have changed (mtime/content)
        include_stale_importers: If True, include files that import changed barrel files
    
    Returns:
        Tuple of (files_to_reparse, diagnostics)
    """
    from .barrel import invalidate_stale_barrel_entries
    
    files_to_reparse = set(changed_files)
    diagnostics: Dict[str, Any] = {
        "direct_changes": len(changed_files),
        "stale_barrel_importers": 0,
        "total_reparse": 0
    }
    
    if include_stale_importers and changed_files:
        # Check if any changed files are barrel files that would invalidate importers
        stale_importers = invalidate_stale_barrel_entries(
            root, cache, list(changed_files)
        )
        if stale_importers:
            files_to_reparse.update(stale_importers)
            diagnostics["stale_barrel_importers"] = len(stale_importers)
    
    diagnostics["total_reparse"] = len(files_to_reparse)
    return files_to_reparse, diagnostics
