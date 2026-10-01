"""
Freshness: content hashes, stale-wiki detection, record-change / mark-green state.

- ``source_content_hash`` is captured only by mark-green (the trusted baseline);
  check-changes compares live bytes against it so mtime-only touches stay Green.
- ``wiki_content_hash`` + ``last_wiki_refresh`` are captured by mark-green;
  ``last_meaningful_edit`` by record-change. A record-change newer than the last
  wiki refresh, or wiki bytes that drifted from the stored hash, mark a wiki stale.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from .. import locking
from .pending import _do_remove_from_pending
from .wikis import WIKI_DIRS, _compute_wiki_content_hash, _find_existing_wiki_file, _sha256_file  # noqa: F401
from .store import (
    GREEN,
    YELLOW,
    RootLike,
    _coerce_root,
    _do_save_health,
    _normalize_to_relative,
    _timestamp,
    load_health,
    normalize_entry,
)

def compute_source_content_hash(path: Optional[Path]) -> Optional[str]:
    """``sha256:<hex>`` of source bytes, or None when absent/unreadable."""
    return _sha256_file(path)


def source_mtime_ns(path: Optional[Path]) -> Optional[str]:
    """Nanosecond mtime as stored next to ``source_content_hash`` (string; None if missing)."""
    try:
        return str(Path(path).stat().st_mtime_ns) if path else None
    except OSError:
        return None


def classify_content_dirty(path: Path, stored_hash: Optional[str] = None) -> Dict[str, Any]:
    """Whether source bytes differ from a stored baseline (pure; no mutation).

    ``reason`` is one of: content_unchanged | content_changed | no_baseline | missing.
    A missing baseline counts as dirty so a post-edit rewrite can never silently
    seed new bytes and stay Green.
    """
    live = compute_source_content_hash(path)
    if live is None:
        return {"content_dirty": False, "missing": True, "hash": None, "reason": "missing", "seed_baseline": False}
    if not stored_hash:
        return {"content_dirty": True, "missing": False, "hash": live, "reason": "no_baseline", "seed_baseline": False}
    if stored_hash == live:
        return {"content_dirty": False, "missing": False, "hash": live, "reason": "content_unchanged", "seed_baseline": False}
    return {"content_dirty": True, "missing": False, "hash": live, "reason": "content_changed", "seed_baseline": False}


def seed_source_content_hashes(
    root: RootLike,
    *,
    only_green: bool = True,
    force: bool = False,
    directory: Optional[str] = None,
    max_files: int = 50000,
) -> Dict[str, Any]:
    """Record the current on-disk hash as the baseline for existing entries.

    Migration helper: status and reason are left unchanged (no mass Yellow).
    """
    root = _coerce_root(root)
    result: Dict[str, Any] = {
        "success": True,
        "project_root": str(root),
        "seeded": 0,
        "skipped_has_hash": 0,
        "skipped_not_green": 0,
        "skipped_missing": 0,
        "skipped_filter": 0,
        "errors": [],
        "sample_seeded": [],
    }
    prefix = (directory or "").rstrip("/")
    with locking.file_lock(root):
        data = load_health(root)
        entries = data.setdefault("entries", {})
        for rel, ent in list(entries.items()):
            if prefix and not (rel == prefix or rel.startswith(prefix + "/")):
                result["skipped_filter"] += 1
                continue
            if only_green and "🟢" not in str(ent.get("status") or ""):
                result["skipped_not_green"] += 1
                continue
            if ent.get("source_content_hash") and not force:
                result["skipped_has_hash"] += 1
                continue
            digest = compute_source_content_hash(root / rel)
            if not digest:
                result["skipped_missing"] += 1
                continue
            ent["source_content_hash"] = digest
            mtime = source_mtime_ns(root / rel)
            if mtime:
                ent["source_mtime_ns"] = mtime
            result["seeded"] += 1
            if len(result["sample_seeded"]) < 8:
                result["sample_seeded"].append(rel)
            if result["seeded"] >= max_files:
                break
        if result["seeded"]:
            _do_save_health(root, data)
    result["message"] = (
        f"Seeded {result['seeded']} source_content_hash baseline(s) "
        f"(skipped has_hash={result['skipped_has_hash']}, "
        f"not_green={result['skipped_not_green']}, missing={result['skipped_missing']})."
    )
    return result


def _is_stale_wiki(root: Path, file: str, entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Diagnostic dict when ``file``'s wiki is stale, else None."""
    if not isinstance(entry, dict):
        return None
    wiki_path = _find_existing_wiki_file(root, file)
    live_hash = _compute_wiki_content_hash(wiki_path)
    stored_hash = entry.get("wiki_content_hash")
    last_edit = entry.get("last_meaningful_edit")
    last_refresh = entry.get("last_wiki_refresh")

    reasons: List[str] = []
    details: Dict[str, Any] = {}
    confidence = 0.0
    # Timestamps are "YYYY-MM-DD HH:MM:SS" so lexical order is chronological.
    if last_edit and last_refresh and last_edit > last_refresh:
        reasons.append("meaningful_edit_after_wiki_refresh (record-change post-dates last mark-green)")
        confidence += 0.75
        details["intent_vs_wiki_delta"] = f"{last_edit} > {last_refresh}"
    if live_hash and stored_hash and live_hash != stored_hash:
        reasons.append("wiki_content_hash_mismatch (wiki edited since last mark-green)")
        confidence += 0.6
        details["hash_mismatch"] = {"stored": stored_hash[:32] + "...", "live": live_hash[:32] + "..."}
    if not reasons:
        return None
    if not live_hash:
        reasons.append("wiki_file_absent_or_unreadable_after_intent_change")
        confidence = max(confidence, 0.5)
    return {
        "file": file,
        "is_stale": True,
        "confidence": round(min(1.0, confidence), 2),
        "reasons": reasons,
        "last_meaningful_edit": last_edit,
        "last_wiki_refresh": last_refresh,
        "stored_wiki_hash": stored_hash,
        "live_wiki_hash": live_hash,
        "current_status": entry.get("status", ""),
        "wiki_file": str(wiki_path.relative_to(root)) if wiki_path else None,
        "freshness_provenance": entry.get("freshness_provenance", ""),
        "diagnostics": details,
        "recommendation": "Refresh the wiki summary to reflect the latest recorded intent, then run mark-green.",
    }


def get_stale_wikis(root: RootLike, directory: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
    """Files whose wiki is stale, most confident first (bounded, directory-scoped)."""
    root = _coerce_root(root)
    prefix = directory.rstrip("/") + "/" if directory else None
    results: List[Dict[str, Any]] = []
    for file, entry in load_health(root).get("entries", {}).items():
        if prefix and not file.startswith(prefix):
            continue
        diag = _is_stale_wiki(root, file, entry)
        if diag:
            results.append(diag)
            if len(results) >= limit:
                break
    return sorted(results, key=lambda x: (-x.get("confidence", 0.0), x["file"]))


def _do_record_meaningful_edit(
    root: RootLike,
    file: str,
    reason: str = "",
    ts: Optional[str] = None,
    journal_ref: Optional[str] = None,
) -> None:
    """Mark ``file`` Yellow and stamp ``last_meaningful_edit`` (caller holds the lock)."""
    root = _coerce_root(root)
    file = _normalize_to_relative(root, file)
    health = load_health(root)
    base = normalize_entry(health.get("entries", {}).get(file, {}))
    now = ts or _timestamp()
    provenance = f"record-meaningful-edit:{now}"
    if journal_ref:
        provenance += f"; journal_ref={journal_ref}"
    if reason:
        provenance += f" | {reason[:120]}"
    base.update({
        "status": YELLOW,
        "last_updated": now,
        "reason": reason or base.get("reason") or "Semantic change recorded",
        "last_meaningful_edit": now,
        "freshness_provenance": provenance,
    })
    health.setdefault("entries", {})[file] = base
    _do_save_health(root, health)


def record_meaningful_edit(
    root: RootLike,
    file: str,
    reason: str = "",
    ts: Optional[str] = None,
    journal_ref: Optional[str] = None,
) -> None:
    """Locked :func:`_do_record_meaningful_edit`."""
    root = _coerce_root(root)
    with locking.file_lock(root):
        _do_record_meaningful_edit(root, file, reason, ts, journal_ref)


def _do_mark_wiki_refresh(
    root: RootLike,
    file: str,
    wiki_hash: Optional[str],
    reason: str = "",
    ts: Optional[str] = None,
    provenance: Optional[str] = None,
) -> None:
    """Persist ``wiki_content_hash`` + ``last_wiki_refresh`` (caller holds the lock)."""
    root = _coerce_root(root)
    file = _normalize_to_relative(root, file)
    health = load_health(root)
    base = normalize_entry(health.get("entries", {}).get(file, {}))
    now = ts or _timestamp()
    parts = [p for p in (base.get("freshness_provenance"), provenance or "mark-wiki-refresh") if p]
    base.update({
        "last_updated": now,
        "last_wiki_refresh": now,
        "freshness_provenance": "; ".join(parts)[:500],
    })
    if wiki_hash:
        base["wiki_content_hash"] = wiki_hash
    if reason:
        base["reason"] = reason
    health.setdefault("entries", {})[file] = base
    _do_save_health(root, health)


def mark_wiki_refresh(root: RootLike, file: str, reason: str = "", ts: Optional[str] = None) -> None:
    """Capture the current wiki hash + refresh stamp for ``file`` (locked)."""
    root = _coerce_root(root)
    with locking.file_lock(root):
        wiki_file = _find_existing_wiki_file(root, _normalize_to_relative(root, file))
        _do_mark_wiki_refresh(
            root,
            file,
            _compute_wiki_content_hash(wiki_file),
            reason,
            ts,
            provenance=f"explicit mark_wiki_refresh; wiki={wiki_file.name if wiki_file else 'none'}",
        )


def _do_mark_green_checked(root: RootLike, file: str, reason: str = "", force: bool = False) -> Dict[str, Any]:
    """Verify the wiki against the code, then mark ``file`` Green in one load/save.

    Raises ``WikiVerificationError`` when the public surface changed and the
    wiki does not reflect it (unless ``force``: then ``verification`` is
    ``forced``), and ``FileNotFoundError`` for a missing path. Captures the
    wiki hash, source hash/mtime and public symbols as the next baseline.
    Returns the verification report with ``file`` set to the canonical key.
    Caller holds the lock.
    """
    from .verify import FORCED, WikiVerificationError, symbols_field, verify_wiki

    root = _coerce_root(root)
    rel = _normalize_to_relative(root, file)
    source = root / rel
    if not source.exists():
        raise FileNotFoundError(f"cannot mark a missing path Green: {rel}")
    now = _timestamp()
    wiki_file = _find_existing_wiki_file(root, rel)
    health = load_health(root)
    base = normalize_entry(health.get("entries", {}).get(rel, {}))
    check = verify_wiki(root, rel, base)
    if not check["ok"] and not force:
        raise WikiVerificationError(rel, check)
    check["verification"] = FORCED if not check["ok"] else check["verification"]
    base["verification"] = check["verification"]
    symbols = symbols_field(check["symbols"])
    if symbols is not None:
        base["public_symbols"] = symbols
    provenance = f"mark-green:{now}" + (f"; wiki={wiki_file.name}" if wiki_file else "")
    base.update({
        "status": GREEN,
        "last_updated": now,
        "reason": reason or "Wiki summary verified accurate after change.",
        "last_wiki_refresh": now,
        "freshness_provenance": provenance,
    })
    wiki_hash = _compute_wiki_content_hash(wiki_file)
    if wiki_hash:
        base["wiki_content_hash"] = wiki_hash
    source_hash = compute_source_content_hash(source)
    if source_hash:
        base["source_content_hash"] = source_hash
        mtime = source_mtime_ns(source)
        if mtime:
            base["source_mtime_ns"] = mtime
    health.setdefault("entries", {})[rel] = base
    _do_save_health(root, health)
    _do_remove_from_pending(root, rel)
    check["file"] = rel
    return check


def _do_mark_green(root: RootLike, file: str, reason: str = "", force: bool = False) -> str:
    """:func:`_do_mark_green_checked`, returning only the canonical key."""
    return _do_mark_green_checked(root, file, reason, force)["file"]


def mark_green(root: RootLike, file: str, reason: str = "", force: bool = False) -> str:
    """Locked :func:`_do_mark_green`. Returns the canonical key."""
    root = _coerce_root(root)
    with locking.file_lock(root):
        return _do_mark_green(root, file, reason, force)


__all__ = [
    "classify_content_dirty",
    "compute_source_content_hash",
    "get_stale_wikis",
    "mark_green",
    "mark_wiki_refresh",
    "record_meaningful_edit",
    "seed_source_content_hashes",
    "source_mtime_ns",
]
