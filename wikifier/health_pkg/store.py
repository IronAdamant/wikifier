"""
Health matrix persistence: file_health.json (source of truth) + file_health.md (view).

Every key is a canonical project-relative POSIX path (see ``wikifier.paths``).
Keys outside the project root and free-form note keys are pruned on load/save.

JSON schema (v2):
{
  "version": 2,
  "last_updated": "2026-05-27 12:34:56",
  "entries": {
    "relative/path/to/file.py": {
      "status": "🟢 Green",
      "last_updated": "2026-05-27 12:34:56",
      "reason": "Wiki summary verified accurate.",
      "wiki_content_hash": "sha256:…",       # wiki bytes at last mark-green
      "source_content_hash": "sha256:…",     # source bytes at last mark-green
      "source_mtime_ns": "1727…",            # source mtime when that hash was verified
      "public_symbols": "load save Store",    # public names at last mark-green ("" = none)
      "verification": "verified",            # verified | no_wiki | unchecked | forced
      "last_meaningful_edit": "…",           # last record-change
      "last_wiki_refresh": "…",              # last mark-green
      "freshness_provenance": "…"
    }
  }
}
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple, Union

from .. import locking
from ..paths import ProjectPathError, to_rel

HEALTH_JSON = "file_health.json"
HEALTH_MD = "file_health.md"
PENDING_MD = "pending_updates.md"

GREEN = "🟢 Green"
YELLOW = "🟡 Yellow"
RED = "🔴 Red"

RootLike = Union[str, Path]

# Free-form note keys from early dogfood runs that are not project paths.
SUPERSEDED_PATTERNS = [
    "m5.3 cycle1", "cycle1 evidence append", "early m5.3 launch note", "m5.3 cycle1 evidence",
]

# Suffixes that make a slash-less key look like a real file (e.g. "README.md").
_SOURCE_SUFFIXES = (
    ".py", ".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs", ".md", ".json",
    ".sh", ".toml", ".yaml", ".yml", ".html", ".css", ".rs", ".go", ".java",
    ".cs", ".c", ".h", ".cpp", ".hpp", ".cc",
)

_FRESHNESS_FIELDS = (
    "wiki_content_hash",
    "source_content_hash",
    "source_mtime_ns",
    "public_symbols",
    "verification",
    "last_meaningful_edit",
    "last_wiki_refresh",
    "freshness_provenance",
)


def _coerce_root(root: RootLike) -> Path:
    return Path(str(root)).expanduser().resolve()


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _get_health_path(root: RootLike) -> Path:
    return _coerce_root(root) / HEALTH_JSON


def _looks_like_path_key(key: str) -> bool:
    """True if a health key looks like a file path rather than a free-form note."""
    if not key or not isinstance(key, str) or key.startswith("-"):
        return False
    if "/" in key or "\\" in key:
        return True
    return key.endswith(_SOURCE_SUFFIXES)


def _is_pollution_health_key(key: str, entry: Optional[Dict[str, Any]] = None) -> bool:
    """Keys that must never remain in the agent-facing health matrix."""
    if not isinstance(key, str) or not key:
        return True
    lowered = key.lower()
    if any(p in lowered for p in SUPERSEDED_PATTERNS):
        return True
    ent = entry or {}
    deleted = "DELETED" in str(ent.get("reason") or "") or "DELETED" in str(ent.get("status") or "")
    # Accidental flag keys / free-form notes already marked DELETED.
    return deleted and not _looks_like_path_key(key)


def _normalize_to_relative(root: RootLike, file_key: str) -> str:
    """Canonical relative key; keys outside the root are returned unchanged (and later pruned)."""
    try:
        return to_rel(root, file_key)
    except ProjectPathError:
        return file_key


def _entry_is_under_root(root: RootLike, file_key: str) -> bool:
    """True for keys that are relative (and do not climb out) or absolute inside the root."""
    if not isinstance(file_key, str) or not file_key:
        return False
    try:
        to_rel(root, file_key)
        return True
    except ProjectPathError:
        return False


def _prune_entries(root: RootLike, entries: Dict[str, Any]) -> Dict[str, Any]:
    """Drop out-of-tree keys and free-form note pollution; canonicalize the rest."""
    pruned: Dict[str, Any] = {}
    for key, value in (entries or {}).items():
        if not _entry_is_under_root(root, key):
            continue
        if _is_pollution_health_key(key, value if isinstance(value, dict) else None):
            continue
        canonical = _normalize_to_relative(root, key)
        existing = pruned.get(canonical)
        if existing is None or str((value or {}).get("last_updated", "")) >= str(existing.get("last_updated", "")):
            pruned[canonical] = value
    return pruned


def normalize_entry(entry: Any) -> Dict[str, Any]:
    """Return a schema-complete copy of a health entry (idempotent)."""
    if not isinstance(entry, dict):
        entry = {}
    core: Dict[str, Any] = {
        "status": str(entry.get("status", YELLOW))[:120],
        "last_updated": str(entry.get("last_updated", _timestamp()))[:50],
        "reason": str(entry.get("reason", ""))[:3000],
    }
    for key in _FRESHNESS_FIELDS:
        value = entry.get(key)
        if isinstance(value, str) and (value or key == "public_symbols"):
            core[key] = value
    return core


# Kept for callers that used the old private name.
_normalize_health_entry_local = normalize_entry


def load_health(root: RootLike) -> Dict[str, Any]:
    """Load file_health.json (migrating from file_health.md when only the view exists)."""
    root = _coerce_root(root)
    json_path = _get_health_path(root)
    if json_path.exists():
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        md_path = root / HEALTH_MD
        if not md_path.exists():
            return {"version": 2, "last_updated": _timestamp(), "entries": {}}
        data = _migrate_from_markdown(md_path)
    entries = {k: normalize_entry(v) for k, v in (data.get("entries") or {}).items()}
    data["entries"] = _prune_entries(root, entries)
    data["version"] = 2
    return data


def save_health(root: RootLike, health_data: Dict[str, Any]) -> None:
    """Save health data (locked) and regenerate the Markdown view."""
    root = _coerce_root(root)
    with locking.file_lock(root):
        _do_save_health(root, health_data)


def _do_save_health(root: RootLike, health_data: Dict[str, Any]) -> None:
    """Save without taking the lock (caller holds it). Atomic replace."""
    root = _coerce_root(root)
    health_data["last_updated"] = _timestamp()
    health_data["version"] = 2
    if "entries" in health_data:
        health_data["entries"] = _prune_entries(root, health_data.get("entries") or {})
    _atomic_write(_get_health_path(root), json.dumps(health_data, indent=2, ensure_ascii=False))
    _generate_markdown(root, health_data)


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def _migrate_from_markdown(md_path: Path) -> Dict[str, Any]:
    """Parse a legacy file_health.md table into the JSON shape."""
    entries: Dict[str, Any] = {}
    with open(md_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("|") or line.startswith("|---") or "File" in line:
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 5 or not parts[1]:
                continue
            entries[parts[1]] = {
                "status": parts[2],
                "last_updated": parts[3],
                "reason": parts[4],
            }
    return {"version": 2, "last_updated": _timestamp(), "entries": entries}


def _generate_markdown(root: Path, health_data: Dict[str, Any]) -> None:
    """Regenerate the human-readable file_health.md from the JSON data."""
    entries = health_data.get("entries", {})
    lines = [
        "# Documentation Health Matrix\n",
        "| File | Status | Last Updated | Reason / Intent |",
        "|------|--------|--------------|-----------------|",
    ]
    for file_path in sorted(entries):
        entry = entries[file_path]
        reason = str(entry.get("reason", "")).replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {file_path} | {entry.get('status', YELLOW)} | {entry.get('last_updated', '')} | {reason} |"
        )
    _atomic_write(root / HEALTH_MD, "\n".join(lines) + "\n")


def _apply_upsert_to_health_dict(
    health: Dict[str, Any],
    root: RootLike,
    file: str,
    status: str,
    reason: str = "",
) -> bool:
    """Mutate an in-memory health dict. Returns True if an entry was written.

    Freshness fields of an existing entry are preserved.
    """
    if not _entry_is_under_root(root, file):
        return False
    file = _normalize_to_relative(root, file)
    if _is_pollution_health_key(file, {"status": status, "reason": reason}):
        return False
    base = normalize_entry(health.setdefault("entries", {}).get(file, {}))
    base.update({"status": status, "last_updated": _timestamp(), "reason": reason})
    base.setdefault("freshness_provenance", f"upsert:{status}")
    health["entries"][file] = base
    return True


def upsert_entry(root: RootLike, file: str, status: str, reason: str = "") -> None:
    """Add or update a health entry (locked)."""
    root = _coerce_root(root)
    with locking.file_lock(root):
        _do_upsert_entry(root, file, status, reason)


def _do_upsert_entry(root: RootLike, file: str, status: str, reason: str = "") -> None:
    """Upsert without taking the lock (caller holds it)."""
    health = load_health(root)
    if _apply_upsert_to_health_dict(health, root, file, status, reason):
        _do_save_health(root, health)


def upsert_entries_batch(
    root: RootLike,
    items: Iterable[Tuple[str, ...]],
    health_data: Optional[Dict[str, Any]] = None,
) -> int:
    """Apply many ``(file, status[, reason])`` upserts with one load and one save.

    The caller must already hold the project lock.
    """
    root = _coerce_root(root)
    health = health_data if isinstance(health_data, dict) else load_health(root)
    written = 0
    for item in items or []:
        if not item:
            continue
        file, status = item[0], item[1]
        reason = item[2] if len(item) > 2 else ""
        if _apply_upsert_to_health_dict(health, root, file, status, reason):
            written += 1
    if written:
        _do_save_health(root, health)
    return written
