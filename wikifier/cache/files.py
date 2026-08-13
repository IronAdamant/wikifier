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
    """Get the mtime of a file (cross-platform)."""
    try:
        return int(file_path.stat().st_mtime)
    except Exception:
        return 0


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
    """Light-index dirty detection (no pair-payload deserialize)."""
    if full_rebuild:
        seen: set = set()
        out: List[Path] = []
        for p in candidate_full_paths:
            pr = Path(p).resolve() if p else None
            if pr and pr not in seen:
                seen.add(pr)
                out.append(pr)
        return out

    index = load_mtime_index(root)
    to_reparse: List[Path] = []
    seen: set = set()
    try:
        root_res = root.resolve()
    except Exception:
        root_res = root

    def _rel_of(p_res: Path) -> str:
        rel = None
        try:
            rel = str(p_res.relative_to(root_res))
        except Exception:
            pass
        if rel is None:
            try:
                rp = str(p_res)
                rr = str(root_res)
                if rp.startswith(rr):
                    rel = rp[len(rr):].lstrip("/\\")
            except Exception:
                pass
        if not rel:
            rel = p_res.name or str(p_res)
        return rel

    def _content_stable(p_res: Path, data: Dict[str, Any], rel: str, curr_mtime: int) -> bool:
        stored = data.get("content_hash")
        if not stored or not isinstance(stored, str):
            return False
        live = compute_file_content_hash(p_res)
        if not live or live != stored:
            return False
        if content_stable_mtime_updates is not None:
            content_stable_mtime_updates.append((rel, curr_mtime, live))
        return True

    for p in candidate_full_paths:
        if not p:
            continue
        try:
            p_res = Path(p).resolve()
        except Exception:
            p_res = Path(p)
        if p_res in seen:
            continue
        seen.add(p_res)
        rel = _rel_of(p_res)
        data = index.get(rel) or {}
        cached_mtime = int(data.get("mtime", 0) or 0)
        curr_mtime = 0
        if p_res.exists():
            try:
                curr_mtime = int(p_res.stat().st_mtime)
            except Exception:
                curr_mtime = 0
        if not data:
            to_reparse.append(p_res)
            continue
        if curr_mtime > cached_mtime:
            if _content_stable(p_res, data, rel, curr_mtime):
                continue
            to_reparse.append(p_res)
        elif curr_mtime == cached_mtime:
            # Same-second writes (tests + fast agent loops) do not bump int mtime.
            stored = data.get("content_hash")
            if stored:
                live = compute_file_content_hash(p_res)
                if live and live != stored:
                    to_reparse.append(p_res)

    for rel, data in list(index.items()):
        if not isinstance(rel, str) or not isinstance(data, dict):
            continue
        try:
            full = (root / rel).resolve()
            if full in seen:
                continue
            if full.exists():
                curr = int(full.stat().st_mtime)
                cached = int(data.get("mtime", 0) or 0)
                if curr > cached:
                    if _content_stable(full, data, rel, curr):
                        seen.add(full)
                        continue
                    to_reparse.append(full)
                    seen.add(full)
                elif curr == cached:
                    stored = data.get("content_hash")
                    if stored:
                        live = compute_file_content_hash(full)
                        if live and live != stored:
                            to_reparse.append(full)
                            seen.add(full)
        except Exception:
            pass

    return to_reparse
