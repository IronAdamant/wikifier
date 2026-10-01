"""
Scope hygiene: monitored_paths, ghosts, map-first seeding, pruning, validation.

monitored_paths.txt is the wiki/health *watch* surface (check-changes);
map_paths.txt is the import-map surface (update-maps). They are independent.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .. import locking
from ..candidates import SOURCE_EXTS
from .pending import _pending_item_lines, _read_pending_lines, _write_pending_lines, pending_item_path
from .store import (
    YELLOW,
    RootLike,
    _coerce_root,
    _do_save_health,
    _entry_is_under_root,
    _is_pollution_health_key,
    _looks_like_path_key,
    _normalize_to_relative,
    _timestamp,
    load_health,
    normalize_entry,
)

# Parseable source suffixes: everything update-maps collects, plus type stubs.
PARSEABLE_SOURCE_SUFFIXES = frozenset(SOURCE_EXTS | {".pyi"})

# Directories never walked for health purposes (tool state + vendored code).
_INTERNAL_SKIPS = frozenset({".git", ".wikifier_staging", "journal", "Logged_issues", "node_modules"})


def _build_simple_exclude_set(root: Path) -> set:
    """Basenames from exclude_patterns.txt (best-effort directory/file name filter)."""
    path = Path(root) / "exclude_patterns.txt"
    if not path.exists():
        return set()
    out = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.add(line.rstrip("/*").split("/")[-1])
    return out


def _read_monitored_rel_roots(root: Path) -> List[str]:
    """Active (non-comment) monitored_paths.txt lines, or ``["."]`` when absent/empty."""
    path = Path(root) / "monitored_paths.txt"
    if path.exists():
        roots = [
            ln.strip()
            for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        if roots:
            return roots
    return ["."]


def _under_monitored(rel: str, monitored_rels: List[str]) -> bool:
    """True if ``rel`` is inside any monitored root (or the monitor is bare ``.``)."""
    if not monitored_rels or monitored_rels == ["."]:
        return True
    rel_n = rel.replace("\\", "/")
    while rel_n.startswith("./"):
        rel_n = rel_n[2:]
    for monitored in monitored_rels:
        m = monitored.replace("\\", "/").rstrip("/")
        while m.startswith("./"):
            m = m[2:]
        if m in (".", ""):
            return True
        if rel_n == m or rel_n.startswith(m + "/"):
            return True
    return False


def _walk_parseable_sources(root: Path, monitored_roots: List[str]) -> List[str]:
    """Project-relative parseable sources under the monitored roots."""
    excludes = _build_simple_exclude_set(root)
    found: List[str] = []
    for monitored in monitored_roots:
        base = (root / monitored).resolve()
        if base.is_file():
            if base.suffix.lower() in PARSEABLE_SOURCE_SUFFIXES:
                found.append(base.relative_to(root).as_posix())
            continue
        if not base.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in _INTERNAL_SKIPS and d not in excludes]
            for name in filenames:
                path = Path(dirpath) / name
                if path.suffix.lower() not in PARSEABLE_SOURCE_SUFFIXES or name in excludes:
                    continue
                try:
                    found.append(path.relative_to(root).as_posix())
                except ValueError:
                    continue
    return sorted(set(found))


def find_ghost_entries(root: RootLike) -> List[str]:
    """Health keys that look like files but are missing on disk (DELETED audits excluded)."""
    root = _coerce_root(root)
    ghosts: List[str] = []
    for key, entry in (load_health(root).get("entries") or {}).items():
        reason = str((entry or {}).get("reason") or "")
        status = str((entry or {}).get("status") or "")
        if "DELETED" in reason or "DELETED" in status:
            continue
        if not _looks_like_path_key(key):
            continue
        if not (root / key).exists():
            ghosts.append(key)
    return sorted(set(ghosts))


def _load_map_file_keys(root: Path) -> List[str]:
    """Mapped source files (import-cache keys) without loading edge payloads."""
    from ..cache.io import load_mtime_index

    return [k for k in load_mtime_index(root) if isinstance(k, str) and _looks_like_path_key(k)]


def seed_health_from_map(
    root: RootLike,
    map_keys: Optional[List[str]] = None,
    max_new: int = 10000,
    only_monitored: Optional[bool] = None,
    reason: str = (
        "Initial stub — present in dependency map; "
        "agent should wiki + mark-green when editing"
    ),
) -> Dict[str, Any]:
    """Ensure mapped files have at least a 🟡 stub row (one batched save).

    ``only_monitored`` defaults to True when monitored_paths is lean (not bare
    ``.``) so the whole monorepo map is not seeded into health.
    """
    root = _coerce_root(root)
    keys = list(map_keys) if map_keys is not None else _load_map_file_keys(root)
    max_new = max(0, min(int(max_new), 100000))
    monitored = _read_monitored_rel_roots(root)
    if only_monitored is None:
        only_monitored = monitored not in (["."], [])
    if only_monitored:
        keys = [k for k in keys if _under_monitored(k, monitored)]

    with locking.file_lock(root):
        health = load_health(root)
        entries = health.setdefault("entries", {})
        before = len(entries)
        seeded = 0
        now = _timestamp()
        for rel in keys:
            if seeded >= max_new:
                break
            if not isinstance(rel, str) or not rel or rel.startswith("_"):
                continue
            if not _entry_is_under_root(root, rel) or _is_pollution_health_key(rel):
                continue
            rel = _normalize_to_relative(root, rel)
            if rel in entries:
                continue
            entries[rel] = normalize_entry({
                "status": YELLOW,
                "last_updated": now,
                "reason": reason,
                "freshness_provenance": "seed_health_from_map",
            })
            seeded += 1
        if seeded > 0 or before == 0:
            # Persist even when empty so file_health.json exists for agents.
            _do_save_health(root, health)
    return {
        "success": True,
        "seeded": seeded,
        "mapped_keys_considered": len(keys),
        "mapped_keys": len(keys),
        "only_monitored": only_monitored,
        "monitored": monitored,
        "health_entries_before": before,
        "health_entries_after": len(entries),
        "max_new": max_new,
        "root": str(root),
    }


def seed_health_for_monitored_sources(
    root: RootLike,
    max_new: int = 20000,
    reason: str = (
        "Initial stub — parseable source under monitored_paths; "
        "agent should wiki + mark-green when editing"
    ),
) -> Dict[str, Any]:
    """Stub every parseable source under monitored_paths that lacks a row."""
    root = _coerce_root(root)
    found = _walk_parseable_sources(root, _read_monitored_rel_roots(root))
    return seed_health_from_map(root, map_keys=found, max_new=max_new, only_monitored=False, reason=reason)


def prune_pending_to_monitored(
    root: RootLike,
    drop_auto_detected: bool = True,
    keep: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Drop pending items outside monitored_paths, the dependency map and ``keep``
    (and, optionally, auto-detected noise)."""
    root = _coerce_root(root)
    monitored = _read_monitored_rel_roots(root)
    keep_set = set(keep or ()) | set(_load_map_file_keys(root))
    with locking.file_lock(root):
        kept: List[str] = []
        removed = removed_auto = 0
        for line in _pending_item_lines(_read_pending_lines(root)):
            path = pending_item_path(line) or ""
            message = line.split(": ", 1)[1] if ": " in line else ""
            if drop_auto_detected and "auto-detected" in message.lower():
                removed += 1
                removed_auto += 1
            elif path in keep_set or _under_monitored(path, monitored):
                kept.append(line)
            else:
                removed += 1
        _write_pending_lines(root, kept)
    return {
        "success": True,
        "removed": removed,
        "removed_auto_detected": removed_auto,
        "kept": len(kept),
        "monitored": monitored,
        "root": str(root),
    }


def prune_health_outside_monitored(root: RootLike, keep_deleted_audits: bool = True) -> Dict[str, Any]:
    """Remove health rows that are neither under monitored_paths nor on the
    dependency map (DELETED audit rows optionally kept)."""
    root = _coerce_root(root)
    monitored = _read_monitored_rel_roots(root)
    mapped = set(_load_map_file_keys(root))
    with locking.file_lock(root):
        health = load_health(root)
        kept: Dict[str, Any] = {}
        removed = 0
        for key, value in (health.get("entries") or {}).items():
            ent = value if isinstance(value, dict) else {}
            deleted = "DELETED" in str(ent.get("reason") or "") or "DELETED" in str(ent.get("status") or "")
            if (keep_deleted_audits and deleted and _looks_like_path_key(key)) or key in mapped or _under_monitored(key, monitored):
                kept[key] = value
            else:
                removed += 1
        health["entries"] = kept
        _do_save_health(root, health)
    return {"success": True, "removed": removed, "kept": len(kept), "monitored": monitored, "root": str(root)}


def find_deleted_missing(root: RootLike) -> List[str]:
    """DELETED-audit keys whose paths are gone (retired by prune_deleted_missing)."""
    root = _coerce_root(root)
    missing: List[str] = []
    for key, entry in (load_health(root).get("entries") or {}).items():
        ent = entry if isinstance(entry, dict) else {}
        if "DELETED" not in str(ent.get("reason") or "") and "DELETED" not in str(ent.get("status") or ""):
            continue
        if not (root / key).exists():
            missing.append(key)
    return sorted(set(missing))


def prune_deleted_missing(root: RootLike) -> Dict[str, Any]:
    """Drop DELETED rows whose files are gone."""
    root = _coerce_root(root)
    with locking.file_lock(root):
        health = load_health(root)
        entries = health.get("entries") or {}
        to_drop = find_deleted_missing(root)
        removed = 0
        for key in to_drop:
            if entries.pop(key, None) is not None:
                removed += 1
        health["entries"] = entries
        _do_save_health(root, health)
    return {"success": True, "removed": removed, "removed_paths": to_drop, "kept": len(entries), "root": str(root)}


def validate_health(root: RootLike) -> Dict[str, Any]:
    """Map-first validation (read-only).

    ``missing`` = parseable sources under monitored_paths without a health row,
    plus mapped files under those paths without one. Non-source files never count.
    """
    root = _coerce_root(root)
    known = set(load_health(root).get("entries", {}))
    monitored_roots = _read_monitored_rel_roots(root)
    sources = _walk_parseable_sources(root, monitored_roots)
    missing = sorted(rel for rel in sources if rel not in known)
    ghosts = find_ghost_entries(root)
    mapped_keys = _load_map_file_keys(root)
    mapped_without_health = sorted(k for k in mapped_keys if k not in known)
    mapped_in_scope = [k for k in mapped_keys if _under_monitored(k, monitored_roots)]
    mapped_in_scope_without_health = sorted(k for k in mapped_in_scope if k not in known)
    primary_missing = sorted(set(missing) | set(mapped_in_scope_without_health))
    return {
        "missing_count": len(primary_missing),
        "missing": primary_missing[:200],
        "missing_monitored_source_count": len(missing),
        "missing_monitored_source": missing[:200],
        "mapped_without_health_count": len(mapped_without_health),
        "mapped_without_health": mapped_without_health[:50],
        "mapped_in_scope_without_health_count": len(mapped_in_scope_without_health),
        "mapped_in_scope_without_health": mapped_in_scope_without_health[:200],
        "mapped_in_scope_count": len(mapped_in_scope),
        "ghost_count": len(ghosts),
        "ghosts": ghosts[:200],
        "total_scanned": len(sources),
        "health_entries": len(known),
        "mapped_files": len(mapped_keys),
        "monitored_roots": monitored_roots,
        "map_first": True,
        "note": (
            "missing_count = parseable sources under monitored_paths plus mapped files under "
            "those paths lacking health. mapped_without_health_count (outside lean monitors) "
            "is informational. Non-source files are ignored."
        ),
        "root": str(root),
    }


def detect_scope_risks(root: RootLike) -> Dict[str, Any]:
    """Warn about bare ``.`` monitors and multi-project container roots."""
    root = _coerce_root(root)
    warnings: List[str] = []
    monitored = _read_monitored_rel_roots(root)
    bare_dot = monitored in (["."], [])
    if bare_dot:
        warnings.append(
            "monitored_paths is bare '.' — check-changes will thrash on large trees. "
            "Prefer lean package roots (e.g. src/, library/std/src)."
        )
    child_projects = 0
    sample_children: List[str] = []
    for child in root.iterdir():
        if not child.is_dir() or child.name.startswith("."):
            continue
        if (child / ".git").exists() or (child / "file_health.json").exists() or (child / ".wikifier_staging").is_dir():
            child_projects += 1
            if len(sample_children) < 8:
                sample_children.append(child.name)
    if child_projects >= 3:
        warnings.append(
            f"project_root looks like a multi-project container ({child_projects} child "
            f"projects e.g. {sample_children}). Target a single child project instead."
        )
    return {
        "monitored_roots": monitored,
        "bare_dot_monitor": bare_dot,
        "child_project_count": child_projects,
        "child_project_sample": sample_children,
        "warnings": warnings,
        "ok": not warnings,
    }
