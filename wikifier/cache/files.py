"""File-level cache operations — entry shape, mtime, content hash, dirty set."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .io import load_mtime_index


def get_file_data(cache: Dict[str, Any], rel_path: str) -> Optional[Dict[str, Any]]:
    """Return cached data for a relative path, or None if not present."""
    return cache.get(rel_path)


def update_file_data(
    cache: Dict[str, Any],
    rel_path: str,
    mtime: int,
    imports: List[str],
    resolved: Optional[List[str]] = None,
    resolved_pairs: Optional[List[Dict[str, str]]] = None,
    dependents: Optional[List[str]] = None,
) -> None:
    """Update or insert data for a file in the cache. Preserves rich pair fields."""
    normalized_pairs = []
    for p in (resolved_pairs or []):
        if isinstance(p, dict):
            np = {
                "raw": p.get("raw", ""),
                "resolved": p.get("resolved", ""),
                "confidence": p.get("confidence", "medium"),
            }
            for k, v in p.items():
                if k not in np:
                    np[k] = v
            normalized_pairs.append(np)

    entry = {
        "mtime": mtime,
        "imports": imports,
        "resolved": resolved or [],
        "resolved_pairs": normalized_pairs,
    }
    if dependents is not None:
        entry["dependents"] = dependents
    cache[rel_path] = entry


def get_mtime(file_path: Path) -> int:
    """Whole-second mtime (0 when the file is missing)."""
    try:
        return int(Path(file_path).stat().st_mtime)
    except OSError:
        return 0


def get_mtime_ns(file_path: Path) -> int:
    """Nanosecond mtime — what the cache stores (0 when the file is missing)."""
    try:
        return int(Path(file_path).stat().st_mtime_ns)
    except OSError:
        return 0


# Cache rows written before nanosecond mtimes hold whole seconds (< ~1e10).
_LEGACY_SECONDS_MAX = 10 ** 12


def compute_file_content_hash(file_path: Path) -> Optional[str]:
    """Sha256 of source bytes. Returns ``sha256:<hex>`` or None if unreadable."""
    try:
        import hashlib
        p = Path(file_path)
        if not p.is_file():
            return None
        return "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()
    except Exception:
        return None


def compute_files_needing_reparse(
    root: Path,
    candidate_full_paths: List[Path],
    full_rebuild: bool = False,
    content_stable_mtime_updates: Optional[List[Tuple[str, int, str]]] = None,
) -> List[Path]:
    """Files whose content may have changed since they were last mapped.

    Uses the light mtime index (no payload load). An unchanged nanosecond mtime
    means clean without reading the file; a changed mtime with identical content
    hash is recorded in ``content_stable_mtime_updates`` instead of re-parsing.
    Indexed files that are not candidates (e.g. outside the current walk) are
    checked too, so edits there are never missed.
    """
    root = Path(root).resolve()
    if full_rebuild:
        out: List[Path] = []
        seen_full: set = set()
        for p in candidate_full_paths:
            if not p:
                continue
            resolved = Path(p).resolve()
            if resolved not in seen_full:
                seen_full.add(resolved)
                out.append(resolved)
        return out

    index = load_mtime_index(root)
    dirty: List[Path] = []
    seen: set = set()

    def check(path: Path, rel: str, data: Dict[str, Any]) -> None:
        try:
            current_ns = path.stat().st_mtime_ns
        except OSError:
            return
        cached = int(data.get("mtime", 0) or 0)
        stored_hash = data.get("content_hash")
        if cached >= _LEGACY_SECONDS_MAX:
            if current_ns == cached:
                return
        else:
            current_s = current_ns // 1_000_000_000
            if current_s < cached:
                return
            if current_s == cached and not stored_hash:
                return
        live_hash = compute_file_content_hash(path)
        if stored_hash and live_hash == stored_hash:
            if content_stable_mtime_updates is not None:
                content_stable_mtime_updates.append((rel, current_ns, live_hash))
            return
        dirty.append(path)

    for p in candidate_full_paths:
        if not p:
            continue
        path = Path(p).resolve()
        if path in seen:
            continue
        seen.add(path)
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            continue
        data = index.get(rel)
        if not data:
            dirty.append(path)
        else:
            check(path, rel, data)

    for rel, data in index.items():
        if not isinstance(rel, str) or not isinstance(data, dict):
            continue
        path = (root / rel).resolve()
        if path in seen or not path.exists():
            continue
        seen.add(path)
        check(path, rel, data)

    return dirty
