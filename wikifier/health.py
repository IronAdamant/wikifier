"""
Wikifier Health Matrix - Scalable Implementation (M2-Rem-02 + Health B)

This module provides fast, scalable operations on the Documentation Health Matrix.
It is designed to work well from small projects (< 300 files) all the way to massive
monorepos (10k+ files). M2 Health B extensions add durable wiki freshness tracking
(wiki_content_hash + last_meaningful_edit correlated to journal semantic events),
policy-driven healing, stale detection, sharded views, and self-hosting hygiene —
all zero-dependency, observable, and production-safe under concurrency.

Architecture (Durable + Observable):
- `file_health.json` primary source (fast dict, versioned, additive migration).
- Contracts in contracts.py (HealthEntry_v1) are the single source of truth for shapes.
- Every mutation of freshness fields carries 'freshness_provenance' for explainability.
- `file_health.md` is a generated human-readable view (no freshness fields to keep readable).
- Small projects: full fidelity. Massive: summary/sharded + lazy full views preferred.

JSON Schema (v2 - additive from v1):
{
  "version": 2,
  "last_updated": "2026-05-27T12:34:56",
  "entries": {
    "relative/path/to/file.py": {
      "status": "🟢 Green",
      "last_updated": "2026-05-27 12:34:56",
      "reason": "Wiki summary verified accurate.",
      "wiki_content_hash": "sha256:9f86d08... (of .wiki.md at last mark-green)",
      "last_meaningful_edit": "2026-05-27 11:22:00",
      "last_wiki_refresh": "2026-05-27 12:34:56",
      "freshness_provenance": "mark-green via mcp; record-change journal ref"
    },
    ...
  }
}

Old v1 entries load safely (missing freshness fields default to absent/None).
"""

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable

# Import locking (M2-Rem-07)
try:
    from . import locking
except ImportError:
    locking = None

# M2 Health B durable contracts (HealthEntry + normalize for migration/observability)
try:
    from . import contracts
except ImportError:
    contracts = None

HEALTH_JSON = "file_health.json"
HEALTH_MD = "file_health.md"
PENDING_MD = "pending_updates.md"


def _get_health_path(root: Path) -> Path:
    return root / HEALTH_JSON


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _normalize_health_entry_local(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Local fallback (when contracts import unavailable) for B1 durable additive migration.
    Mirrors contracts.normalize_health_entry exactly. Idempotent."""
    if not isinstance(entry, dict):
        entry = {}
    core = {
        "status": str(entry.get("status", "🟡 Yellow"))[:120],
        "last_updated": str(entry.get("last_updated", _timestamp()))[:50],
        "reason": str(entry.get("reason", ""))[:3000],
    }
    for k in ("wiki_content_hash", "last_meaningful_edit", "last_wiki_refresh", "freshness_provenance"):
        v = entry.get(k)
        if isinstance(v, str) and v:
            core[k] = v
    return core


def _compute_wiki_content_hash(wiki_path: Optional[Path]) -> Optional[str]:
    """Durable content hash (sha256 of bytes) for wiki summary. Zero-dep stdlib.
    Used to detect actual content drift vs mtime-only. Returns 'sha256:<hex>' or None."""
    if not wiki_path or not wiki_path.exists() or not wiki_path.is_file():
        return None
    try:
        data = wiki_path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        return f"sha256:{digest}"
    except Exception:
        return None


def _is_stale_wiki(root: Path, file: str, entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Core durable stale wiki detector (B3).
    Returns rich diagnostic dict if the wiki summary is stale w.r.t code intent
    (last_meaningful_edit from journal record-change after last wiki hash capture),
    or if content hash has drifted (out-of-band edit).
    Returns None if fresh or insufficient data.
    Observable: full provenance + confidence + actionable rec.
    Zero-dep, O(1) per file (uses precomputed fields + cheap hash of wiki if present).
    """
    if not isinstance(entry, dict):
        return None
    wiki_path = _find_existing_wiki_file(root, file)
    live_hash = _compute_wiki_content_hash(wiki_path)
    stored_hash = entry.get("wiki_content_hash")
    last_mean = entry.get("last_meaningful_edit")
    last_wiki_r = entry.get("last_wiki_refresh")

    reasons: List[str] = []
    details: Dict[str, Any] = {}
    conf = 0.0

    # Primary durable signal: intent changed after wiki was last marked trusted
    if last_mean and last_wiki_r:
        try:
            if last_mean > last_wiki_r:  # lexical sort works for our YYYY-MM-DD HH:MM:SS
                reasons.append("meaningful_edit_after_wiki_refresh (journal semantic post-dates last mark-green)")
                conf += 0.75
                details["intent_vs_wiki_delta"] = f"{last_mean} > {last_wiki_r}"
        except Exception:
            pass

    # Content drift robustness (detects wiki edited without going through mark-green tools)
    if live_hash and stored_hash and live_hash != stored_hash:
        reasons.append("wiki_content_hash_mismatch (current wiki bytes != hash at last trusted mark-green)")
        conf += 0.6
        details["hash_mismatch"] = {"stored": stored_hash[:32] + "...", "live": live_hash[:32] + "..."}

    if not reasons:
        return None

    if not wiki_path or not live_hash:
        reasons.append("wiki_file_absent_or_unreadable_after_intent_change")
        conf = max(conf, 0.5)

    status = entry.get("status", "")
    provenance = entry.get("freshness_provenance", "")

    return {
        "file": file,
        "is_stale": True,
        "confidence": round(min(1.0, conf), 2),
        "reasons": reasons,
        "last_meaningful_edit": last_mean,
        "last_wiki_refresh": last_wiki_r,
        "stored_wiki_hash": stored_hash,
        "live_wiki_hash": live_hash,
        "current_status": status,
        "wiki_file": str(wiki_path.relative_to(root)) if wiki_path else None,
        "freshness_provenance": provenance,
        "diagnostics": details,
        "recommendation": "Refresh the wiki summary to reflect latest recorded intent, then run mark-green to re-capture hash + promote."
    }


def get_stale_wikis(root: Path, directory: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
    """
    Public: list of files with stale wikis (rich, explainable, filterable by dir for scale).
    Bounded + directory scoped for >10k file repos. Ready for MCP + CLI + health(json).
    """
    health = load_health(root)
    results: List[Dict[str, Any]] = []
    for f, e in list(health.get("entries", {}).items()):
        if directory:
            if not f.startswith(directory.rstrip("/") + "/"):
                continue
        diag = _is_stale_wiki(root, f, e)
        if diag:
            results.append(diag)
            if len(results) >= limit:
                break
    return sorted(results, key=lambda x: (-x.get("confidence", 0.0), x["file"]))


def load_health(root: Path) -> Dict[str, Any]:
    """
    Load the health matrix from file_health.json.
    Falls back to migrating from file_health.md if JSON does not exist.

    M2 Health B: Defensive additive migration for v1 -> v2 (freshness fields).
    Every entry is normalized via contracts.normalize_health_entry (or local equiv)
    so old data + new code is always safe and observable-ready.
    Top-level version bumped to 2 on next save.
    """
    json_path = _get_health_path(root)

    if json_path.exists():
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        version = data.get("version", 1)
        entries = data.get("entries", {}) or {}
        normalized_entries = {}
        for k, v in entries.items():
            if contracts and hasattr(contracts, "normalize_health_entry"):
                normalized_entries[k] = contracts.normalize_health_entry(v)
            else:
                normalized_entries[k] = _normalize_health_entry_local(v)
        data["entries"] = normalized_entries
        if version < 2:
            data["version"] = 2  # mark for future save; additive, no breakage
        return data

    # Migration path: if JSON doesn't exist but MD does
    md_path = root / HEALTH_MD
    if md_path.exists():
        migrated = _migrate_from_markdown(md_path)
        # Normalize migrated entries too (B1 durable)
        entries = migrated.get("entries", {})
        norm = {}
        for k, v in entries.items():
            if contracts and hasattr(contracts, "normalize_health_entry"):
                norm[k] = contracts.normalize_health_entry(v)
            else:
                norm[k] = _normalize_health_entry_local(v)
        migrated["entries"] = norm
        migrated["version"] = 2
        return migrated

    # Fresh project (start at v2 with Health B fields ready)
    return {
        "version": 2,
        "last_updated": _timestamp(),
        "entries": {}
    }


def save_health(root: Path, health_data: Dict[str, Any]) -> None:
    """Save health data to file_health.json and regenerate the Markdown view.

    Uses file locking (M2-Rem-07) to prevent concurrent corruption.
    """
    if locking:
        with locking.file_lock(root):
            _do_save_health(root, health_data)
    else:
        _do_save_health(root, health_data)


def _do_save_health(root: Path, health_data: Dict[str, Any]) -> None:
    """Internal save without locking."""
    json_path = _get_health_path(root)
    health_data["last_updated"] = _timestamp()
    health_data["version"] = 2  # B durable: ensure v2 on every save (additive fields)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(health_data, f, indent=2, ensure_ascii=False)

    # Also regenerate human-readable Markdown
    _generate_markdown(root, health_data)


def _migrate_from_markdown(md_path: Path) -> Dict[str, Any]:
    """Migrate existing file_health.md into the new JSON format."""
    entries = {}
    with open(md_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("|") or line.startswith("|---") or "File" in line:
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 5:
                continue
            file_path = parts[1]
            status = parts[2]
            last_updated = parts[3]
            reason = parts[4] if len(parts) > 4 else ""
            if file_path:
                entries[file_path] = {
                    "status": status,
                    "last_updated": last_updated,
                    "reason": reason
                }

    health_data = {
        "version": 2,  # B1: start emitting v2 (additive Health B fields ready via normalize)
        "last_updated": _timestamp(),
        "entries": entries
    }
    return health_data


def _generate_markdown(root: Path, health_data: Dict[str, Any]) -> None:
    """Generate a human-friendly file_health.md from the JSON data."""
    md_path = root / HEALTH_MD
    entries = health_data.get("entries", {})

    lines = [
        "# Documentation Health Matrix\n",
        "| File | Status | Last Updated | Reason / Intent |",
        "|------|--------|--------------|-----------------|"
    ]

    # Sort for consistent output
    for file_path in sorted(entries.keys()):
        entry = entries[file_path]
        line = f"| {file_path} | {entry.get('status', '🟡 Yellow')} | {entry.get('last_updated', '')} | {entry.get('reason', '')} |"
        lines.append(line)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def upsert_entry(root: Path, file: str, status: str, reason: str = "") -> None:
    """Add or update a health entry for a file.

    Uses file locking (M2-Rem-07) to prevent race conditions when multiple
    agents or humans are writing at the same time.
    """
    if locking:
        with locking.file_lock(root):
            _do_upsert_entry(root, file, status, reason)
    else:
        _do_upsert_entry(root, file, status, reason)


def _do_upsert_entry(root: Path, file: str, status: str, reason: str = "") -> None:
    """Internal upsert without locking.

    M2 Health B durable: preserve existing wiki freshness fields (hash, meaningful_edit,
    wiki_refresh, provenance) on non-refresh upserts (e.g. barrel invalidation, auto Yellow).
    Only freshness-aware paths (mark-green, record via new helpers) mutate those.
    Always normalize to guarantee schema.
    """
    health = load_health(root)
    existing = health.get("entries", {}).get(file, {})
    # Start from normalized existing to keep B fields
    if contracts and hasattr(contracts, "normalize_health_entry"):
        base = contracts.normalize_health_entry(existing)
    else:
        base = _normalize_health_entry_local(existing)

    base.update({
        "status": status,
        "last_updated": _timestamp(),
        "reason": reason
    })
    # Ensure provenance note if a non-freshness update (observability)
    if not base.get("freshness_provenance"):
        base["freshness_provenance"] = f"upsert:{status} (non-freshness path)"
    health["entries"][file] = base
    _do_save_health(root, health)


# ----------------------------- Pending Updates Helpers (locked, idempotent) -----------------------------
# These ensure pending_updates.md mutations are atomic with health under the project lock
# (per locking.py contract). Eliminates races/duplicates with add_pending from shell/monitor.

def _get_pending_path(root: Path) -> Path:
    return root / PENDING_MD


def _read_pending_lines(root: Path) -> List[str]:
    """Read pending file as list of lines; return sensible default header if missing."""
    p = _get_pending_path(root)
    if not p.exists():
        return [
            "# Pending Updates",
            "",
            "(no pending items — run check-changes after making edits)"
        ]
    try:
        with open(p, "r", encoding="utf-8") as f:
            return f.read().splitlines(keepends=False)
    except Exception:
        # On read error, conservative: return current content best effort or default
        return ["# Pending Updates", "", "(no pending items — run check-changes after making edits)"]


def _write_pending_lines(root: Path, lines: List[str]) -> None:
    """Atomic-ish write of pending (tmp + mv for safety on most FS)."""
    p = _get_pending_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        os.replace(tmp, p)  # atomic rename on POSIX
    except Exception:
        # Fallback direct write
        with open(p, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass


def _do_remove_from_pending(root: Path, file: str) -> int:
    """Internal: idempotent remove of any lines containing file (fixed-string, like grep -vF)."""
    lines = _read_pending_lines(root)
    new_lines = [ln for ln in lines if file not in ln]
    removed = len(lines) - len(new_lines)
    if removed > 0:
        _write_pending_lines(root, new_lines)
    return removed


def remove_from_pending(root: Path, file: str) -> int:
    """Public: remove references to file from pending_updates.md. Idempotent. Under lock."""
    if locking:
        with locking.file_lock(root):
            return _do_remove_from_pending(root, file)
    else:
        return _do_remove_from_pending(root, file)


def _do_add_to_pending(root: Path, file: str, msg: str) -> None:
    """Internal add (idempotent: no exact dup entry)."""
    lines = _read_pending_lines(root)
    entry = f"- {file}: {msg}"
    if entry not in lines:
        lines.append(entry)
        _write_pending_lines(root, lines)


def add_to_pending(root: Path, file: str, msg: str) -> None:
    """Public: append to pending (idempotent). Under lock."""
    if locking:
        with locking.file_lock(root):
            _do_add_to_pending(root, file, msg)
    else:
        _do_add_to_pending(root, file, msg)


# ----------------------------- M2 Health B: Durable Freshness Paths (wiki_content_hash + last_meaningful_edit) -----------------------------
# These tie wiki state to journal semantic events (record-change etc.) for reliable stale detection.
# All mutations under project lock. Every change emits freshness_provenance for full observability.
# Designed for 10k-50k file monorepos: O(1) per file, no full scans in hot paths.

def _do_record_meaningful_edit(root: Path, file: str, reason: str = "", ts: Optional[str] = None, journal_ref: Optional[str] = None) -> None:
    """Internal (locked caller): record a semantic/journal-backed edit for the file.
    Sets last_meaningful_edit (for stale correlation) + Yellow + provenance.
    Used by record_change/record_deletion paths (shell + MCP + future library).
    """
    health = load_health(root)
    existing = health.get("entries", {}).get(file, {})
    if contracts and hasattr(contracts, "normalize_health_entry"):
        base = contracts.normalize_health_entry(existing)
    else:
        base = _normalize_health_entry_local(existing)

    now = ts or _timestamp()
    prov = f"record-meaningful-edit:{now}"
    if journal_ref:
        prov += f"; journal_ref={journal_ref}"
    if reason:
        prov += f" | {reason[:120]}"
    base.update({
        "status": "🟡 Yellow",
        "last_updated": now,
        "reason": reason or base.get("reason", "Semantic change recorded (correlates to journal)"),
        "last_meaningful_edit": now,
        "freshness_provenance": prov
    })
    health["entries"][file] = base
    _do_save_health(root, health)


def record_meaningful_edit(root: Path, file: str, reason: str = "", ts: Optional[str] = None, journal_ref: Optional[str] = None) -> None:
    """Public: locked record of meaningful (journal semantic) edit. Updates last_meaningful_edit for B3 detector."""
    if locking:
        with locking.file_lock(root):
            _do_record_meaningful_edit(root, file, reason, ts, journal_ref)
    else:
        _do_record_meaningful_edit(root, file, reason, ts, journal_ref)


def _do_mark_wiki_refresh(root: Path, file: str, wiki_hash: Optional[str], reason: str = "", ts: Optional[str] = None, provenance: Optional[str] = None) -> None:
    """Internal: persist the captured wiki_content_hash + last_wiki_refresh after a trusted wiki summary write.
    Called from enhanced mark-green. Enables exact content-based staleness vs intent change.
    """
    health = load_health(root)
    existing = health.get("entries", {}).get(file, {})
    if contracts and hasattr(contracts, "normalize_health_entry"):
        base = contracts.normalize_health_entry(existing)
    else:
        base = _normalize_health_entry_local(existing)

    now = ts or _timestamp()
    prov_parts = [p for p in (base.get("freshness_provenance"), provenance or "mark-wiki-refresh") if p]
    new_prov = "; ".join(prov_parts)[:500]
    base.update({
        "last_updated": now,
        "last_wiki_refresh": now,
        "freshness_provenance": new_prov
    })
    if wiki_hash:
        base["wiki_content_hash"] = wiki_hash
    if reason:
        base["reason"] = reason
    health["entries"][file] = base
    _do_save_health(root, health)


def mark_wiki_refresh(root: Path, file: str, reason: str = "", ts: Optional[str] = None) -> None:
    """Public locked: explicit wiki content hash capture + refresh stamp (for advanced callers or direct wiki tooling)."""
    if locking:
        with locking.file_lock(root):
            wiki_file = _find_existing_wiki_file(root, file)
            h = _compute_wiki_content_hash(wiki_file)
            _do_mark_wiki_refresh(root, file, h, reason, ts, provenance=f"explicit mark_wiki_refresh; wiki={wiki_file.name if wiki_file else 'none'}")
    else:
        wiki_file = _find_existing_wiki_file(root, file)
        h = _compute_wiki_content_hash(wiki_file)
        _do_mark_wiki_refresh(root, file, h, reason, ts, provenance=f"explicit mark_wiki_refresh; wiki={wiki_file.name if wiki_file else 'none'}")


def _do_mark_green(root: Path, file: str, reason: str = "") -> None:
    """Internal combined op (health + pending) without re-acquiring lock.

    M2 Health B: On mark-green (the canonical 'wiki now trusted' action), also capture
    the current wiki_content_hash (durable content not mtime) + last_wiki_refresh + provenance.
    This powers the reliable stale wiki detector. Ties the Green state to a specific wiki snapshot.
    """
    effective_reason = reason or "Wiki summary verified accurate after change."
    # B2: capture wiki hash for freshness correlation (durable, observable)
    wiki_file = _find_existing_wiki_file(root, file)
    wiki_hash = _compute_wiki_content_hash(wiki_file)
    prov = f"mark-green:{_timestamp()} (wiki hash captured)"
    if wiki_file:
        prov += f"; wiki={wiki_file.name}"
    # First ensure Green + basic (preserves other fields via enhanced upsert)
    _do_upsert_entry(root, file, "🟢 Green", effective_reason)
    # Now layer the wiki refresh fields (separate durable step)
    _do_mark_wiki_refresh(root, file, wiki_hash, effective_reason, provenance=prov)
    _do_remove_from_pending(root, file)


def mark_green(root: Path, file: str, reason: str = "") -> None:
    """
    Mark file Green + atomically clear any pending entries for it.
    Single lock acquisition for the combined mutation. Fully idempotent.
    This is the reliable helper that shell (and MCP via sh) should call.
    """
    if locking:
        with locking.file_lock(root):
            _do_mark_green(root, file, reason)
    else:
        _do_mark_green(root, file, reason)


# ----------------------------- Validate (reliable Python, no subshell bugs) -----------------------------
def _build_simple_exclude_set(root: Path) -> set:
    """Parse exclude_patterns.txt into simple basenames/globs for filtering (best-effort)."""
    exc = set()
    ep = root / "exclude_patterns.txt"
    if ep.exists():
        try:
            for line in ep.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    # take basename or last segment for simple contains check
                    exc.add(line.rstrip("/*").split("/")[-1])
        except Exception:
            pass
    return exc


def validate_health(root: Path) -> Dict[str, Any]:
    """
    Reliable, subshell-free implementation of 'validate'.
    Scans monitored paths (respecting excludes + internal skips), reports files
    missing from the health matrix (JSON or migrated MD).
    Returns structured result for shell/Python/MCP callers.
    Always succeeds (exit code driven by caller); never mutates state.
    """
    health = load_health(root)
    entries = health.get("entries", {})
    known = set(entries.keys())

    monitored_file = root / "monitored_paths.txt"
    if monitored_file.exists():
        try:
            monitored_roots = [ln.strip() for ln in monitored_file.read_text(encoding="utf-8").splitlines()
                               if ln.strip() and not ln.strip().startswith("#")]
        except Exception:
            monitored_roots = ["."]
    else:
        monitored_roots = ["."]

    excludes = _build_simple_exclude_set(root)
    internal_skips = {".git", ".wikifier_staging", "journal", "Logged_issues"}

    missing: List[str] = []
    total_scanned = 0

    for r in monitored_roots:
        if not r:
            continue
        base = (root / r).resolve()
        if not base.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            # prune internal dirs
            dirnames[:] = [d for d in dirnames if d not in internal_skips]
            for fname in filenames:
                fpath = Path(dirpath) / fname
                total_scanned += 1
                try:
                    rel = str(fpath.relative_to(root))
                except Exception:
                    rel = str(fpath)
                # skip if any exclude component matches
                parts = Path(rel).parts
                if any(p in excludes or p in internal_skips for p in parts):
                    continue
                if rel not in known:
                    missing.append(rel)

    missing = sorted(set(missing))  # dedup + stable
    return {
        "missing_count": len(missing),
        "missing": missing,
        "total_scanned": total_scanned,
        "health_entries": len(known),
        "root": str(root)
    }


# ----------------------------- apply_barrel... (continues) -----------------------------

def apply_barrel_invalidation_reports(
    root: Path, reports: List[Dict[str, Any]]
) -> int:
    """Apply structured BRC invalidation reports to the health matrix.

    Marks (or updates) each affected importer as 🟡 Yellow with a precise explanation
    containing the triggering barrel(s), chain_ids, reason, detector, partial flag.
    This is the key wiring that lets `check-changes` (and therefore the daemon monitor)
    surface barrel-driven staleness automatically, even when the importer file's own mtime
    is unchanged.

    Idempotent / safe; uses the existing upsert_entry (locked + json+md).
    Returns number of importers that received a (new or updated) Yellow barrel note.
    Zero-dep, scalable (reports are small).
    """
    if not reports:
        return 0
    updated = 0
    for r in reports:
        try:
            if isinstance(r, dict):
                imp = r.get("importer")
                trig = r.get("triggering_barrels") or []
                cids = r.get("chain_ids") or []
                reason = r.get("reason") or "barrel staleness"
                det = r.get("detector_used") or "bree"
                part = r.get("is_partial", False)
            else:
                # dataclass or object
                imp = getattr(r, "importer", None)
                trig = getattr(r, "triggering_barrels", []) or []
                cids = getattr(r, "chain_ids", []) or []
                reason = getattr(r, "reason", "barrel staleness")
                det = getattr(r, "detector_used", "bree")
                part = getattr(r, "is_partial", False)
            if not imp:
                continue
            trig_str = ", ".join(sorted(set(str(t) for t in trig if t))) or "unknown barrel"
            cid_str = ", ".join(sorted(set(str(c) for c in cids if c)))[:80]
            part_str = " (partial)" if part else ""
            expl = (
                f"stale via barrel re-export from {trig_str}{part_str} "
                f"(detector={det}, chains={cid_str or 'n/a'}): {reason}"
            )
            upsert_entry(root, str(imp), "🟡 Yellow", expl)
            updated += 1
        except Exception:
            # never let one bad report kill the batch
            continue
    return updated


def get_summary(root: Path, directory: Optional[str] = None, include_stale: bool = False) -> Dict[str, Any]:
    """Return a summary of the health matrix (fast even for large repos; sharded by dir).

    If directory is provided, only counts files under that subdirectory.
    This enables scalable views in massive monorepos (e.g. health per package).
    M2 B: include_stale=True adds bounded stale_wiki count (via B3 detector) for
    practical summary-only views without full materialization.
    """
    health = load_health(root)
    # Phase 5e (66): health.get_summary (format=summary path) promoted as first-class default/recommended for 20k+ creative monorepos (O(k) sharded, complements compute_acs_summary + ACS/CIABRE/BRC bounded via deque; per crit2/5 + 48/58).
    entries = health.get("entries", {})

    green = yellow = red = 0
    total = 0

    for file_path, entry in entries.items():
        if directory:
            # Normalize paths for comparison
            if not file_path.startswith(directory.rstrip('/') + '/'):
                continue

        total += 1
        status = entry.get("status", "")
        if "🟢" in status:
            green += 1
        elif "🟡" in status:
            yellow += 1
        elif "🔴" in status:
            red += 1

    out = {
        "total": total,
        "green": green,
        "yellow": yellow,
        "red": red,
        "pending_updates": 0,
        "directory": directory or ".",
        "version": health.get("version", 2),
        "last_updated": health.get("last_updated")
    }
    if include_stale:
        try:
            stales = get_stale_wikis(root, directory=directory, limit=1000)  # bounded for practicality
            out["stale_count"] = len(stales)
            out["stale_sample"] = [s["file"] for s in stales[:3]]
        except Exception:
            out["stale_count"] = -1
    return out


def _is_self_hosting_meta_file(rel_path: str) -> bool:
    """B6 self-hosting hygiene predicate.
    These files frequently receive auto Yellow from mtime (own edits to health/journal/templates).
    Suppress from 'needing attention' unless genuinely 🔴 Red for *content* reasons (not mtime drift).
    Prevents noise/pollution when dogfooding or running on the wikifier repo itself.
    """
    p = rel_path.lower()
    metas = [
        "file_health.json", "file_health.md",
        "wikifier/health.py",  # the impl itself
        ".github/issue_template/wiki_health.md",
        "logged_issues", "journal/", "pending_updates.md",
        "health.py.wiki.md", "server.py.wiki.md",  # self docs
        "exclude_patterns.txt", "monitored_paths.txt"  # config often touched
    ]
    return any(m in p for m in metas)


def get_files_needing_attention(root: Path, status_filter: Optional[str] = None, directory: Optional[str] = None, include_meta: bool = False) -> List[str]:
    """Return list of files that need attention, optionally filtered by status and/or directory.

    Directory filtering + B6 self-hosting hygiene (default: suppress wikifier meta files unless truly Red)
    are key for scalability and clean dogfood on the project itself.
    include_meta=True overrides hygiene filter for debugging.
    """
    health = load_health(root)
    result = []

    for file_path, entry in health.get("entries", {}).items():
        if directory:
            if not file_path.startswith(directory.rstrip('/') + '/'):
                continue

        status = entry.get("status", "")
        if status_filter and status_filter not in status:
            continue
        if "🟡" in status or "🔴" in status:
            if not include_meta and _is_self_hosting_meta_file(file_path) and "🔴" not in status:
                # Self-hosting hygiene (durable/observable): skip mtime-only Yellows on our own state
                # (reason logged via provenance in health entry; visible in health(json) or diagnostics)
                continue
            result.append(file_path)

    return sorted(result)


def _find_existing_wiki_file(root: Path, rel_path: str) -> Optional[Path]:
    """
    Try to locate a wiki summary file for a given source file.
    Mirrors the discovery logic used by get_file_wiki in the MCP server.
    """
    candidates = []

    # 1. Direct .wiki.md next to the source
    candidates.append(root / f"{rel_path}.wiki.md")
    candidates.append(root / f"{rel_path}.md")

    # 2. Same directory, without extension
    base = Path(rel_path)
    if base.suffix:
        base_no_ext = base.with_suffix("")
        candidates.append(root / f"{base_no_ext}.wiki.md")
        candidates.append(root / f"{base_no_ext}.md")

    # 3. Common wiki directories
    wiki_dirs = ["docs/wiki", "docs", "wiki", "documentation", ".wiki"]
    for d in wiki_dirs:
        wiki_dir = root / d
        candidates.append(wiki_dir / f"{Path(rel_path).name}.wiki.md")
        candidates.append(wiki_dir / f"{Path(rel_path).name}.md")

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate

    return None


def _assess_wiki_quality(wiki_path: Path) -> Dict[str, Any]:
    """
    Analyze a wiki file and return a detailed quality assessment.
    This is used both for healing decisions and for exposing statistics to agents.
    """
    try:
        text = wiki_path.read_text(encoding="utf-8", errors="ignore").strip()
    except Exception:
        return {"score": 0, "quality": "low", "length": 0, "word_count": 0, "reason": "unreadable"}

    if not text:
        return {"score": 0, "quality": "low", "length": 0, "word_count": 0, "reason": "empty"}

    length = len(text)
    word_count = len(text.split())
    line_count = text.count("\n") + 1

    # Structural signals
    heading_matches = re.findall(r'^#{1,6}\s+.+$', text, re.MULTILINE)
    heading_count = len(heading_matches)
    has_headings = heading_count >= 2
    has_deep_headings = any(len(h) - len(h.lstrip('#')) >= 3 for h in heading_matches)

    has_bullets = bool(re.search(r'^\s*[-*+]\s+', text, re.MULTILINE))
    bullet_count = len(re.findall(r'^\s*[-*+]\s+', text, re.MULTILINE))

    has_code_block = bool(re.search(r'```|`[^`]+`', text))
    has_numbered_list = bool(re.search(r'^\s*\d+\.\s+', text, re.MULTILINE))

    # Semantic / high-value section signals
    lower_text = text.lower()
    important_sections = [
        "purpose", "role", "overview", "responsibilities", "summary",
        "dependencies", "usage", "api", "interface", "examples",
        "notes", "implementation details", "how it works"
    ]
    section_hits = sum(1 for kw in important_sections if kw in lower_text)
    has_purpose_section = any(kw in lower_text for kw in ["purpose", "role", "overview", "summary"])

    # Scoring (0–15 range, then normalized)
    score = 0

    # Length & substance
    if word_count > 250: score += 4
    elif word_count > 120: score += 3
    elif word_count > 60: score += 2
    elif word_count > 30: score += 1

    # Structure
    if heading_count >= 4: score += 3
    elif heading_count >= 2: score += 2
    elif heading_count >= 1: score += 1

    if has_deep_headings: score += 1
    if bullet_count >= 4: score += 2
    elif has_bullets: score += 1
    if has_numbered_list: score += 1
    if has_code_block: score += 1

    # Semantic value
    if has_purpose_section: score += 2
    score += min(section_hits, 3)  # up to +3 for good sections

    # Quality tiers
    if score >= 11:
        quality = "high"
    elif score >= 7:
        quality = "medium"
    else:
        quality = "low"

    return {
        "score": min(score, 15),
        "quality": quality,
        "length": length,
        "word_count": word_count,
        "line_count": line_count,
        "heading_count": heading_count,
        "has_headings": has_headings,
        "has_bullets": has_bullets,
        "has_code_block": has_code_block,
        "has_purpose_section": has_purpose_section,
        "important_sections_found": section_hits
    }


# ----------------------------- M2 Wave 3 B: Policy-Driven Heal Engine (rich diagnostics + provenance) -----------------------------
# Configurable, observable, zero-dep. Supports current stubs + future stale/wiki-drift policies.
# Every decision emits structured diagnostics + freshness_provenance tag for audit (ties to HealthEntry).
# Scalable: O(1) per candidate (reuses _assess + _is_stale_wiki + bounded walks).

def heal_with_policy(
    root: Path,
    policy: Optional[Dict[str, Any]] = None,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Policy-driven heal engine (B completion).
    policy dict (all optional, safe defaults):
      {
        "targets": ["stubs"],  # "stubs" | "stale" (extensible)
        "stub": {
          "min_wiki_length": 350,
          "auto_green_on": "high",   # "high" | "medium" | "never"
          "auto_yellow_on": "medium"
        },
        "stale": {
          "min_confidence": 0.65,
          "action": "mark_yellow_with_note"  # or "log_only"
        },
        "provenance_tag": "policy-heal-v1"
      }
    Returns rich diagnostics (not just count): per-file changes with old/new/reason/quality/diag,
    policy used, summary stats, actionable recommendation. Fully durable (calls mark paths for hash/provenance).
    """
    policy = policy or {}
    targets = policy.get("targets", ["stubs"])
    stub_p = policy.get("stub", {})
    min_len = int(stub_p.get("min_wiki_length", 350))
    green_q = stub_p.get("auto_green_on", "high")
    yellow_q = stub_p.get("auto_yellow_on", "medium")
    stale_p = policy.get("stale", {})
    stale_conf = float(stale_p.get("min_confidence", 0.65))
    prov_tag = policy.get("provenance_tag", "policy-heal-v1")

    health = load_health(root)
    changes: List[Dict[str, Any]] = []
    healed = 0
    stale_checked = 0
    stale_healed = 0

    entries = list(health.get("entries", {}).items())
    for rel_path, entry in entries:
        status = entry.get("status", "")
        reason = entry.get("reason", "")
        diag: Dict[str, Any] = {}

        # Stubs target (existing behavior generalized)
        if "stubs" in targets:
            is_stub = "Initial stub" in status or ("🔴" in status and "stub" in reason.lower())
            if is_stub:
                wiki_file = _find_existing_wiki_file(root, rel_path)
                if wiki_file:
                    quality = _assess_wiki_quality(wiki_file)
                    diag["wiki_quality"] = quality
                    do_heal = False
                    new_status = status
                    new_r = reason
                    if quality["quality"] == "high" and green_q != "never":
                        new_status = "🟢 Green"
                        new_r = f"Auto-healed via policy (high-quality wiki, was {status})"
                        do_heal = True
                    elif quality["quality"] == "medium" and quality["length"] >= min_len and yellow_q == "medium":
                        new_status = "🟡 Yellow"
                        new_r = f"Auto-healed via policy (meaningful wiki now exists, was {status})"
                        do_heal = True

                    if do_heal:
                        if not dry_run:
                            # preserve B fields, layer provenance
                            base = contracts.normalize_health_entry(entry) if (contracts and hasattr(contracts, "normalize_health_entry")) else _normalize_health_entry_local(entry)
                            base.update({
                                "status": new_status,
                                "last_updated": _timestamp(),
                                "reason": new_r,
                                "freshness_provenance": (base.get("freshness_provenance") or "") + f"; {prov_tag}:stub target=stub q={quality['quality']}"
                            })
                            health["entries"][rel_path] = base
                        changes.append({
                            "file": rel_path, "old_status": status, "new_status": new_status,
                            "quality": quality["quality"], "wiki_size": quality["length"],
                            "diagnostics": diag, "policy_target": "stubs"
                        })
                        healed += 1

        # Stale target (uses B3 detector for policy heal of drift)
        if "stale" in targets:
            stale_diag = _is_stale_wiki(root, rel_path, entry)
            if stale_diag and stale_diag.get("confidence", 0) >= stale_conf:
                stale_checked += 1
                if stale_p.get("action", "mark_yellow_with_note") == "mark_yellow_with_note":
                    if not dry_run:
                        base = contracts.normalize_health_entry(entry) if (contracts and hasattr(contracts, "normalize_health_entry")) else _normalize_health_entry_local(entry)
                        new_r = f"Policy-healed stale wiki (conf={stale_diag['confidence']}; reasons: {'; '.join(stale_diag['reasons'])})"
                        base.update({
                            "status": "🟡 Yellow",
                            "last_updated": _timestamp(),
                            "reason": new_r,
                            "freshness_provenance": (base.get("freshness_provenance") or "") + f"; {prov_tag}:stale conf={stale_diag['confidence']}"
                        })
                        health["entries"][rel_path] = base
                    changes.append({
                        "file": rel_path, "old_status": status, "new_status": "🟡 Yellow",
                        "diagnostics": {"stale": stale_diag}, "policy_target": "stale"
                    })
                    stale_healed += 1
                    healed += 1  # count for compat too

    if (healed > 0 or stale_healed > 0) and not dry_run:
        save_health(root, health)

    rec = f"Healed {healed} under policy (stubs:{healed - stale_healed}, stale-involved:{stale_healed}). Review changes + run stale-wikis again."
    if not changes:
        rec = "No healable items matched current policy."

    return {
        "healed_count": healed,
        "stale_checked": stale_checked,
        "stale_healed": stale_healed,
        "changes": changes[:100],  # bound for large
        "policy_used": policy or {"targets": ["stubs"]},
        "diagnostics": {"total_candidates_considered": len(entries)},
        "recommendation": rec,
        "dry_run": dry_run
    }


def heal_outdated_stubs(root: Path, min_wiki_length: int = 350, dry_run: bool = False) -> int:
    """Backward-compat wrapper over the policy engine (stubs target only). Returns count for existing callers (MCP/CLI)."""
    res = heal_with_policy(root, policy={"targets": ["stubs"], "stub": {"min_wiki_length": min_wiki_length}}, dry_run=dry_run)
    # Print rich for CLI visibility (existing behavior + more)
    for ch in res.get("changes", []):
        print(f"  Healed: {ch['file']}  [{ch.get('quality', '?')}]  {ch['old_status']} → {ch['new_status']}")
    return int(res.get("healed_count", 0))


def get_healable_stubs(root: Path, min_wiki_length: int = 350, directory: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Return a list of files that are currently marked as 'Initial stub' (or equivalent 🔴)
    but have a substantial wiki summary and are therefore eligible for auto-healing.

    Returns rich quality metadata so agents can make smart decisions:
    - Heal to 🟡 Yellow for medium-quality wikis
    - Heal directly to 🟢 Green for high-quality, well-structured wikis
    """
    health = load_health(root)
    candidates = []

    for rel_path, entry in health.get("entries", {}).items():
        if directory:
            if not rel_path.startswith(directory.rstrip('/') + '/'):
                continue

        status = entry.get("status", "")
        is_stub = "Initial stub" in status or ("🔴" in status and "stub" in entry.get("reason", "").lower())
        if not is_stub:
            continue

        wiki_file = _find_existing_wiki_file(root, rel_path)
        if not wiki_file:
            continue

        quality = _assess_wiki_quality(wiki_file)

        if quality["length"] >= min_wiki_length and quality["quality"] != "low":
            candidates.append({
                "file": rel_path,
                "current_status": status,
                "wiki_file": str(wiki_file.relative_to(root)),
                "wiki_size": quality["length"],
                "quality": quality["quality"],
                "quality_score": quality["score"],
                "has_headings": quality["has_headings"],
                "has_purpose": quality["has_purpose"],
                "reason": entry.get("reason", "")
            })

    return sorted(candidates, key=lambda x: (-x["quality_score"], x["file"]))


def get_healing_statistics(root: Path) -> Dict[str, Any]:
    """
    Return statistics about the current state of stub healing.
    This is very useful for agents to understand wiki coverage and decide
    whether to run healing or focus on documentation.
    """
    health = load_health(root)
    entries = health.get("entries", {})

    total_entries = len(entries)
    initial_stubs = 0
    healable_high = 0
    healable_medium = 0
    healable_low = 0
    already_green_with_good_wiki = 0

    for rel_path, entry in entries.items():
        status = entry.get("status", "")
        is_initial_stub = "Initial stub" in status

        if not is_initial_stub:
            continue

        initial_stubs += 1

        wiki_file = _find_existing_wiki_file(root, rel_path)
        if not wiki_file:
            continue

        quality = _assess_wiki_quality(wiki_file)

        if quality["quality"] == "high":
            healable_high += 1
        elif quality["quality"] == "medium":
            healable_medium += 1
        else:
            healable_low += 1

        # Also track files that are already Green but had good wikis (for awareness)
        if "🟢" in status and quality["quality"] in ("high", "medium"):
            already_green_with_good_wiki += 1

    total_healable = healable_high + healable_medium + healable_low

    return {
        "total_health_entries": total_entries,
        "current_initial_stubs": initial_stubs,
        "healable_stubs": {
            "total": total_healable,
            "high_quality": healable_high,
            "medium_quality": healable_medium,
            "low_quality": healable_low
        },
        "already_green_but_well_documented": already_green_with_good_wiki,
        "stub_pollution_ratio": round(initial_stubs / max(total_entries, 1), 3),
        "recommendation": _generate_healing_recommendation(initial_stubs, healable_high, healable_medium)
    }


def _generate_healing_recommendation(initial_stubs: int, high: int, medium: int) -> str:
    if initial_stubs == 0:
        return "Excellent — no Initial stubs remaining."
    if high >= 5:
        return f"Strong opportunity: {high} high-quality wikis can be promoted to Green immediately."
    if high + medium >= 8:
        return f"Good opportunity: {high + medium} stubs can be healed (run heal-stubs)."
    if initial_stubs > 15:
        return "Significant stub pollution detected. Consider running heal-stubs + focused documentation."
    return "Mild stub pollution. Low urgency but worth cleaning up."


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m wikifier.health <command> [args]")
        print("Commands:")
        print("  summary                  Show counts")
        print("  upsert <file> <status> [reason]   Add/update a file")
        print("  needs-attention [dir] [--include-meta]  List needing (B6: meta files like file_health.* suppressed by default unless 🔴)")
        print("  heal-stubs [--dry-run]   Auto-heal outdated 'Initial stub' entries")
        print("  healable-stubs [dir]     List entries that can be auto-healed")
        print("  healing-stats            Show stub pollution + healing opportunities")
        print("  prune-barrels [max_days] [ --dry-run ]   Lightweight age-based BRC pruning (default 90d)")
        print("  mark-green <file> [reason]   Idempotent Green + clear pending + wiki hash capture (B2)")
        print("  mark-wiki-refresh <file> [reason]  Explicit wiki_content_hash + last_wiki_refresh capture (locked)")
        print("  record-meaningful <file> [reason] [journal_ref]  Set last_meaningful_edit (ties to journal semantic; for record-change)")
        print("  stale-wikis [dir] [limit]    List files with stale wikis (B3 detector; rich diags + confidence)")
        print("  remove-pending <file>        Idempotent remove from pending_updates (locked)")
        print("  add-pending <file> <msg>     Idempotent add to pending (locked)")
        print("  validate                     Report files missing health entries (no subshell)")
        sys.exit(1)

    root = Path(".")
    cmd = sys.argv[1]

    if cmd == "summary":
        directory = sys.argv[2] if len(sys.argv) > 2 else None
        summary = get_summary(root, directory)
        dir_str = f" (in {summary['directory']})" if directory else ""
        print(f"Health Summary{dir_str}:")
        print(f"  🟢 Green: {summary['green']}")
        print(f"  🟡 Yellow: {summary['yellow']}")
        print(f"  🔴 Red:   {summary['red']}")
        print(f"  Total:    {summary['total']}")

    elif cmd == "upsert":
        if len(sys.argv) < 4:
            print("Usage: python -m wikifier.health upsert <file> <status> [reason]")
            sys.exit(1)
        file = sys.argv[2]
        status = sys.argv[3]
        reason = " ".join(sys.argv[4:]) if len(sys.argv) > 4 else ""
        upsert_entry(root, file, status, reason)
        print(f"Updated: {file} → {status}")

    elif cmd == "needs-attention":
        directory = None
        include = False
        for a in sys.argv[2:]:
            if a == "--include-meta":
                include = True
            elif not a.startswith("--"):
                directory = a
        files = get_files_needing_attention(root, directory=directory, include_meta=include)
        for f in files:
            print(f)

    elif cmd in ("heal-stubs", "auto-heal"):
        dry_run = "--dry-run" in sys.argv
        count = heal_outdated_stubs(root, dry_run=dry_run)
        if dry_run:
            print(f"\nDry run complete. Would have healed {count} stub entries.")
        else:
            print(f"\nHealed {count} outdated stub entries.")

    elif cmd == "healable-stubs":
        directory = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else None
        stubs = get_healable_stubs(root, directory=directory)
        if not stubs:
            print("No healable stub entries found.")
        else:
            print(f"Found {len(stubs)} healable stub entries:\n")
            for s in stubs:
                q = s.get("quality", "?")
                score = s.get("quality_score", 0)
                print(f"  {s['file']}")
                print(f"     Quality: {q} (score={score}) | Wiki: {s['wiki_size']} bytes")
                print(f"     Current: {s['current_status']}")
                if s.get("has_headings"):
                    print("     + Has headings")
                if s.get("has_purpose"):
                    print("     + Has purpose/overview section")
                print()

    elif cmd in ("healing-stats", "stub-stats", "stats"):
        stats = get_healing_statistics(root)
        print("=== Healing Statistics ===")
        print(f"Total health entries:          {stats['total_health_entries']}")
        print(f"Current Initial stubs:         {stats['current_initial_stubs']}")
        print(f"  → High quality (Green-ready): {stats['healable_stubs']['high_quality']}")
        print(f"  → Medium quality (Yellow):    {stats['healable_stubs']['medium_quality']}")
        print(f"  → Low quality:                {stats['healable_stubs']['low_quality']}")
        print(f"Stub pollution ratio:          {stats['stub_pollution_ratio']:.1%}")
        print(f"\nRecommendation: {stats['recommendation']}")

    elif cmd in ("prune-barrels", "prune-brc", "gc-barrels"):
        max_days = 90.0
        dry = False
        for a in sys.argv[2:]:
            if a == "--dry-run":
                dry = True
            else:
                try:
                    max_days = float(a)
                except Exception:
                    pass
        try:
            from . import import_cache as _ic
            root_for_prune = Path(".")
            # respect WIKIFIER_PROJECT_ROOT if present (for daemon / packaged runs)
            proj = os.environ.get("WIKIFIER_PROJECT_ROOT")
            if proj:
                root_for_prune = Path(proj).expanduser().resolve()
            res = _ic.prune_barrel_resolutions(root_for_prune, max_age_days=max_days, dry_run=dry)
            p = res.get("pruned", 0)
            if dry:
                print(f"Prune dry-run (max_age={max_days}d): would prune {p} aged BRC chains.")
            else:
                print(f"Pruned {p} aged BRC chains (max_age={max_days}d). saved={res.get('saved', False)}")
            if "error" in res:
                print(f"  (note: {res['error']})")
        except Exception as ex:
            print(f"Prune-barrels error: {ex}")

    elif cmd == "mark-green":
        if len(sys.argv) < 3:
            print("Usage: python -m wikifier.health mark-green <file> [reason]")
            sys.exit(1)
        file = sys.argv[2]
        reason = " ".join(sys.argv[3:]) if len(sys.argv) > 3 else ""
        try:
            mark_green(root, file, reason)
            print(f"🟢 Marked Green (and pending cleared if present; wiki hash captured for B2 freshness): {file}")
        except Exception as e:
            print(f"mark-green error: {e}")
            sys.exit(1)

    elif cmd == "mark-wiki-refresh":
        if len(sys.argv) < 3:
            print("Usage: python -m wikifier.health mark-wiki-refresh <file> [reason]")
            sys.exit(1)
        file = sys.argv[2]
        reason = " ".join(sys.argv[3:]) if len(sys.argv) > 3 else ""
        try:
            mark_wiki_refresh(root, file, reason)
            print(f"Wiki refresh captured (content hash + last_wiki_refresh set): {file}")
        except Exception as e:
            print(f"mark-wiki-refresh error: {e}")
            sys.exit(1)

    elif cmd == "record-meaningful":
        if len(sys.argv) < 3:
            print("Usage: python -m wikifier.health record-meaningful <file> [reason] [journal_ref]")
            sys.exit(1)
        file = sys.argv[2]
        reason = sys.argv[3] if len(sys.argv) > 3 else ""
        journal_ref = sys.argv[4] if len(sys.argv) > 4 else None
        try:
            record_meaningful_edit(root, file, reason, journal_ref=journal_ref)
            print(f"Meaningful edit recorded (last_meaningful_edit + provenance set for stale detector): {file}")
        except Exception as e:
            print(f"record-meaningful error: {e}")
            sys.exit(1)

    elif cmd in ("stale-wikis", "stale-wiki", "detect-stale"):
        directory = None
        limit = 200
        for a in sys.argv[2:]:
            if a.isdigit():
                limit = int(a)
            elif not a.startswith("--"):
                directory = a
        stales = get_stale_wikis(root, directory=directory, limit=limit)
        if not stales:
            print("No stale wikis detected (all wikis are in sync with recorded meaningful edits).")
        else:
            print(f"Detected {len(stales)} stale wiki(s){' (limited)' if len(stales)==limit else ''}:")
            for s in stales:
                print(f"  {s['file']} (conf={s['confidence']})")
                print(f"     Reasons: {'; '.join(s['reasons'])}")
                if s.get("wiki_file"):
                    print(f"     Wiki: {s['wiki_file']}")
                if s.get("last_meaningful_edit"):
                    print(f"     Last intent: {s['last_meaningful_edit']} | Last wiki refresh: {s.get('last_wiki_refresh')}")
                print(f"     Rec: {s['recommendation']}")
                print()

    elif cmd == "remove-pending":
        if len(sys.argv) < 3:
            print("Usage: python -m wikifier.health remove-pending <file>")
            sys.exit(1)
        file = sys.argv[2]
        try:
            n = remove_from_pending(root, file)
            print(f"Removed {n} pending line(s) for: {file}")
        except Exception as e:
            print(f"remove-pending error: {e}")
            sys.exit(1)

    elif cmd == "add-pending":
        if len(sys.argv) < 4:
            print("Usage: python -m wikifier.health add-pending <file> <msg>")
            sys.exit(1)
        file = sys.argv[2]
        msg = " ".join(sys.argv[3:])
        try:
            add_to_pending(root, file, msg)
            print(f"Added to pending: {file}")
        except Exception as e:
            print(f"add-pending error: {e}")
            sys.exit(1)

    elif cmd == "validate":
        # Always exit 0 (informational); use the returned count for logic if calling directly
        try:
            res = validate_health(root)
            if res["missing_count"] == 0:
                print("✅ All monitored files have health entries.")
            else:
                print(f"⚠️  {res['missing_count']} file(s) lack wiki/health entries (scanned {res['total_scanned']}):")
                for m in res["missing"][:50]:  # bound output
                    print(f"  🔴 MISSING: {m}")
                if len(res["missing"]) > 50:
                    print(f"  ... and {len(res['missing'])-50} more")
            # Structured for callers: print JSON-ish last line for easy parse if needed
            print(f"VALIDATE_RESULT missing={res['missing_count']} scanned={res['total_scanned']}")
        except Exception as e:
            print(f"validate error: {e}")
            sys.exit(1)

    else:
        print(f"Unknown command: {cmd}")
