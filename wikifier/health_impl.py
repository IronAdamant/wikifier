"""
Documentation health matrix (agent-first).

AGENT MAP:
  load_health / save_health / upsert_entry — file_health.json SSOT (+ regenerate .md)
  get_summary — 🟢🟡🔴 + stub_yellow/actionable_yellow + health_score (Map Ready|…)
  assess_autonomous_readiness / detect_scope_risks — long-horizon + dual-scope
  find_ghost_entries / validate_health — map-first gaps + ghosts (parseable sources only)
  seed_health_from_map — backfill 🟡 stubs from import_cache (warm-cache safe)
  prune_pending_to_monitored / prune_health_outside_monitored — lean-monitor hygiene
  mark_green / heal_stubs / apply_barrel_invalidation_reports — status mutations
  CLI: autonomous-status | seed-health | prune-pending | prune-health | validate
Agents: prefer MCP health / check_changes / mark_green; only open this for matrix policy.
  Map Ready ≠ wiki-done — never bulk-wiki Initial stubs.

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


def _coerce_root(root) -> Path:
    """Coerce str or Path to resolved Path. Supports direct lib calls with str (e.g. load_health('.')) and CLI/MCP which pass Path."""
    if isinstance(root, Path):
        return root.resolve()
    return Path(str(root)).expanduser().resolve()


# Post-v4.0 + M5.3 gate complete + cleanup hygiene:
# Aggressively prune superseded historical wiki-note entries (e.g. early "M5.3 Cycle1 evidence append …")
# that are free-form note keys, not real project paths. These pollute the health matrix that agents use.
# Keep real M5 docs (Progress, Milestones, Assessment, p6, M5.1-cross).
# Real path deletions via record-deletion (e.g. "src/foo.py" + 🔴 DELETED) stay as audit rows.
# Free-form DELETED non-path keys (e.g. accidental `record-deletion --help`) are always pruned.
SUPERSEDED_PATTERNS = ["m5.3 cycle1", "cycle1 evidence append", "early m5.3 launch note", "m5.3 cycle1 evidence"]

# Path-like health keys (real files we may keep as DELETED audits). Everything else that is
# already DELETED and not path-shaped is pollution.
_SOURCE_SUFFIXES = (
    ".py", ".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs", ".md", ".json",
    ".sh", ".toml", ".yaml", ".yml", ".html", ".css", ".rs", ".go", ".java",
    ".cs", ".c", ".h", ".cpp", ".hpp", ".cc",
)


def _looks_like_path_key(key: str) -> bool:
    """True if health key looks like a project-relative or absolute file path."""
    if not key or not isinstance(key, str):
        return False
    if key.startswith(("-", "--")):
        return False
    if "/" in key or "\\" in key:
        return True
    return key.endswith(_SOURCE_SUFFIXES)


def _is_pollution_health_key(key: str, entry: Optional[Dict[str, Any]] = None) -> bool:
    """Keys that must never remain in the agent-facing health matrix."""
    if not isinstance(key, str) or not key:
        return True
    kl = key.lower()
    if any(p in kl for p in SUPERSEDED_PATTERNS):
        return True
    ent = entry or {}
    reason = str(ent.get("reason") or "")
    status = str(ent.get("status") or "")
    # Accidental flag keys / free-form notes already marked DELETED (not real paths).
    if not _looks_like_path_key(key) and ("DELETED" in reason or "DELETED" in status):
        return True
    return False


def _prune_entries(root: Path, entries: Dict[str, Any]) -> Dict[str, Any]:
    """Drop out-of-tree pollution + superseded free-form note keys."""
    pruned: Dict[str, Any] = {}
    for k, v in (entries or {}).items():
        if not _entry_is_under_root(root, k):
            continue
        if _is_pollution_health_key(k, v if isinstance(v, dict) else None):
            continue
        pruned[k] = v
    return pruned


def _get_health_path(root: "str | Path") -> Path:
    root = _coerce_root(root)
    return root / HEALTH_JSON


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _normalize_to_relative(root: Path, file_key: str) -> str:
    """Return a canonical relative-to-root key if the path is under root; else the original key.
    Used to prevent persisting out-of-tree 'pollution' entries (from prior cross-cwd runs,
    relative monitored in wrong cwd, or MCP/CLI external dogfood). Makes external targets
    (recipelab_alt, consistencyhub, cloned_*) have clean scoped health immediately.
    """
    try:
        p = Path(file_key)
        r = root.resolve()
        if p.is_absolute():
            try:
                p = p.resolve()
            except Exception:
                pass
            if str(p).startswith(str(r)):
                return str(p.relative_to(r))
            return file_key  # outside -> will be filtered by _entry_is_under_root
        # relative key
        full = (root / p).resolve()
        if str(full).startswith(str(r)):
            return str(full.relative_to(r))
        return file_key
    except Exception:
        return file_key


def _entry_is_under_root(root: Path, file_key: str) -> bool:
    """Return True only for entries whose path (abs or rel) resolves under the project root.

    Filters pollution from other trees (worktrees, cross-project abs paths).
    Relative monorepo keys may be deep (e.g. a/b/c/d/e/f.py) — never treat depth alone
    as absolute (that broke seed_health_from_map on airflow/llvm-style trees).
    """
    try:
        p = Path(file_key)
        r = root.resolve()
        key_str = str(file_key)
        # Absolute-looking keys only (not "many path parts" — deep relative is valid).
        looks_abs = (
            p.is_absolute()
            or key_str.startswith((
                "home/", "/home/", "Users/", "/Users/",
                "/coding_projects/", "coding_projects/",
                "/var/", "/tmp/", "/private/",
            ))
        )
        if looks_abs:
            if not p.is_absolute():
                p = Path("/") / p
            try:
                p = p.resolve()
            except Exception:
                p = Path("/") / key_str.lstrip("/")
        else:
            p = (root / p).resolve()
        _ = p.relative_to(r)
        return True
    except Exception:
        return False  # not under -> drop (M5 external dogfood hygiene)


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
    for k in (
        "wiki_content_hash",
        "source_content_hash",
        "last_meaningful_edit",
        "last_wiki_refresh",
        "freshness_provenance",
    ):
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


def compute_source_content_hash(path: Optional[Path]) -> Optional[str]:
    """Sha256 of source file bytes for content-honest dirty detection (agent-first).

    Returns ``sha256:<hex>`` or None if unreadable. Used so mtime-only thrash does
    not auto-Yellow green files after mark-green captured a baseline.
    """
    if not path:
        return None
    try:
        p = Path(path)
        if not p.is_file():
            return None
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        return f"sha256:{digest}"
    except Exception:
        return None


def classify_content_dirty(
    path: Path,
    stored_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Classify whether *source* content differs from a stored baseline hash.

    Pure helper for check_changes / tests. Does not mutate health.

    Returns dict:
      content_dirty: bool — True if agent should treat as content change
      missing: bool
      hash: live hash or None
      reason: stable token (content_unchanged | content_changed | no_baseline | missing)
      seed_baseline: True when caller should record hash without Yellowing (first observe)
    """
    live = compute_source_content_hash(path)
    if live is None:
        return {
            "content_dirty": False,
            "missing": True,
            "hash": None,
            "reason": "missing",
            "seed_baseline": False,
        }
    if not stored_hash:
        # No trusted baseline (legacy Green / never mark-green): when this path is
        # under check_changes dirty observation, treat as needing attention so a
        # post-edit rewrite cannot silently re-seed the *new* bytes and stay Green.
        # Callers that only want to migrate baselines should use an explicit seed helper.
        return {
            "content_dirty": True,
            "missing": False,
            "hash": live,
            "reason": "no_baseline",
            "seed_baseline": False,
        }
    if stored_hash == live:
        return {
            "content_dirty": False,
            "missing": False,
            "hash": live,
            "reason": "content_unchanged",
            "seed_baseline": False,
        }
    return {
        "content_dirty": True,
        "missing": False,
        "hash": live,
        "reason": "content_changed",
        "seed_baseline": False,
    }


def seed_source_content_hashes(
    root: "str | Path",
    *,
    only_green: bool = True,
    force: bool = False,
    directory: Optional[str] = None,
    max_files: int = 50000,
) -> Dict[str, Any]:
    """Seed trusted ``source_content_hash`` for existing health entries without Yellow thrash.

    Migration helper for post-4.6.x content-honest dirty: legacy 🟢 entries without a
    baseline get the *current on-disk* hash recorded so subsequent mtime-only touches
    do not Yellow. Status/reason are left unchanged (no mass auto-Yellow).

    Args:
        only_green: if True, only seed entries whose status is Green.
        force: if True, re-hash even when a baseline already exists.
        directory: optional path prefix filter.
        max_files: safety cap.

    Returns structured stats (seeded, skipped_*, missing_on_disk, errors sample).
    """
    root = Path(root).resolve()
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
    try:
        data = load_health(root)
        entries = data.setdefault("entries", {})
        dirty = False
        dir_pref = (directory or "").rstrip("/")
        for rel, ent in list(entries.items()):
            if not isinstance(ent, dict):
                continue
            if dir_pref and not (str(rel) == dir_pref or str(rel).startswith(dir_pref + "/")):
                result["skipped_filter"] += 1
                continue
            st = str(ent.get("status") or "")
            if only_green and "Green" not in st and "🟢" not in st:
                result["skipped_not_green"] += 1
                continue
            if ent.get("source_content_hash") and not force:
                result["skipped_has_hash"] += 1
                continue
            src = root / rel
            if not src.is_file():
                result["skipped_missing"] += 1
                continue
            h = compute_source_content_hash(src)
            if not h:
                result["skipped_missing"] += 1
                continue
            ent["source_content_hash"] = h
            # Do not change status/reason — migration only
            entries[rel] = ent
            dirty = True
            result["seeded"] += 1
            if len(result["sample_seeded"]) < 8:
                result["sample_seeded"].append(rel)
            if result["seeded"] >= max_files:
                break
        if dirty:
            save_health(root, data)
        result["message"] = (
            f"Seeded {result['seeded']} source_content_hash baseline(s) "
            f"(skipped has_hash={result['skipped_has_hash']}, "
            f"not_green={result['skipped_not_green']}, missing={result['skipped_missing']})."
        )
    except Exception as e:
        result["success"] = False
        result["error"] = str(e)
        result["errors"].append(str(e))
    return result


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


def load_health(root: "str | Path") -> Dict[str, Any]:
    """
    Load the health matrix from file_health.json.
    Falls back to migrating from file_health.md if JSON does not exist.

    M2 Health B: Defensive additive migration for v1 -> v2 (freshness fields).
    Every entry is normalized via contracts.normalize_health_entry (or local equiv)
    so old data + new code is always safe and observable-ready.
    Top-level version bumped to 2 on next save.
    """
    root = _coerce_root(root)
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
        # M5 dogfood fix: drop out-of-tree + free-form superseded/DELETED pollution.
        # Views (get_*) are clean; next save persists pruned json.
        data["entries"] = _prune_entries(root, data.get("entries", {}) or {})
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
        migrated["entries"] = _prune_entries(root, migrated.get("entries", {}) or {})
        return migrated

    # Fresh project (start at v2 with Health B fields ready)
    return {
        "version": 2,
        "last_updated": _timestamp(),
        "entries": {}
    }


def save_health(root: "str | Path", health_data: Dict[str, Any]) -> None:
    """Save health data to file_health.json and regenerate the Markdown view.

    Uses file locking (M2-Rem-07) to prevent concurrent corruption.
    """
    root = _coerce_root(root)
    if locking:
        with locking.file_lock(root):
            _do_save_health(root, health_data)
    else:
        _do_save_health(root, health_data)


def _do_save_health(root: "str | Path", health_data: Dict[str, Any]) -> None:
    """Internal save without locking."""
    root = _coerce_root(root)
    json_path = _get_health_path(root)
    health_data["last_updated"] = _timestamp()
    health_data["version"] = 2  # B durable: ensure v2 on every save (additive fields)

    # M5: always prune out-of-tree + free-form pollution so file_health.json stays clean
    if "entries" in health_data:
        health_data["entries"] = _prune_entries(root, health_data.get("entries") or {})

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


def upsert_entry(root: "str | Path", file: str, status: str, reason: str = "") -> None:
    """Add or update a health entry for a file.

    Uses file locking (M2-Rem-07) to prevent race conditions when multiple
    agents or humans are writing at the same time.
    """
    root = _coerce_root(root)
    if locking:
        with locking.file_lock(root):
            _do_upsert_entry(root, file, status, reason)
    else:
        _do_upsert_entry(root, file, status, reason)


def _apply_upsert_to_health_dict(
    health: Dict[str, Any],
    root: "str | Path",
    file: str,
    status: str,
    reason: str = "",
) -> bool:
    """Mutate an in-memory health dict. Return True if an entry was written."""
    file = _normalize_to_relative(root, file)
    if not _entry_is_under_root(root, file):
        return False
    if _is_pollution_health_key(file, {"status": status, "reason": reason}):
        return False
    existing = health.setdefault("entries", {}).get(file, {})
    if contracts and hasattr(contracts, "normalize_health_entry"):
        base = contracts.normalize_health_entry(existing)
    else:
        base = _normalize_health_entry_local(existing)
    base.update({
        "status": status,
        "last_updated": _timestamp(),
        "reason": reason,
    })
    if not base.get("freshness_provenance"):
        base["freshness_provenance"] = f"upsert:{status} (non-freshness path)"
    health["entries"][file] = base
    return True


def _do_upsert_entry(root: "str | Path", file: str, status: str, reason: str = "") -> None:
    """Internal upsert without locking.

    M2 Health B durable: preserve existing wiki freshness fields (hash, meaningful_edit,
    wiki_refresh, provenance) on non-refresh upserts (e.g. barrel invalidation, auto Yellow).
    Only freshness-aware paths (mark-green, record via new helpers) mutate those.
    Always normalize to guarantee schema.
    """
    health = load_health(root)
    if _apply_upsert_to_health_dict(health, root, file, status, reason):
        _do_save_health(root, health)


def upsert_entries_batch(root: "str | Path", items, health_data: Optional[Dict[str, Any]] = None) -> int:
    """Apply many (file, status, reason) upserts with one load + one save.

    Caller should already hold the project lock (check_changes / daemon).
    """
    root = _coerce_root(root)
    health = health_data if isinstance(health_data, dict) else load_health(root)
    n = 0
    for item in items or []:
        if not item:
            continue
        if len(item) == 2:
            file, status = item
            reason = ""
        else:
            file, status, reason = item[0], item[1], item[2]
        if _apply_upsert_to_health_dict(health, root, file, status, reason):
            n += 1
    if n:
        _do_save_health(root, health)
    return n


# ----------------------------- Pending Updates Helpers (locked, idempotent) -----------------------------
# These ensure pending_updates.md mutations are atomic with health under the project lock
# (per locking.py contract). Eliminates races/duplicates with add_pending from shell/monitor.

_EMPTY_PENDING_MARKER = "(no pending items — run check-changes after making edits)"
_EMPTY_PENDING_LINES = [
    "# Pending Updates",
    "",
    _EMPTY_PENDING_MARKER,
]


def _get_pending_path(root: Path) -> Path:
    return root / PENDING_MD


def _is_pending_item_line(ln: str) -> bool:
    """True for real work-queue bullets (`- path: msg`), not headers/empty markers."""
    s = (ln or "").strip()
    return s.startswith("- ") and not s.startswith("- (")


def _is_empty_pending_marker(ln: str) -> bool:
    s = (ln or "").strip().lower()
    if not s or s.startswith("#"):
        return False
    return "no pending" in s or "no active items" in s or s == _EMPTY_PENDING_MARKER.lower()


def _pending_item_lines(lines: List[str]) -> List[str]:
    return [ln for ln in lines if _is_pending_item_line(ln)]


def _normalize_pending_lines(lines: List[str]) -> List[str]:
    """Canonical pending_updates.md: header + empty marker XOR bullet list (never both)."""
    items = _pending_item_lines(lines or [])
    if not items:
        return list(_EMPTY_PENDING_LINES)
    seen = set()
    uniq: List[str] = []
    for it in items:
        if it not in seen:
            seen.add(it)
            uniq.append(it)
    return ["# Pending Updates", ""] + uniq


def _read_pending_lines(root: Path) -> List[str]:
    """Read pending file as list of lines; return sensible default header if missing."""
    p = _get_pending_path(root)
    if not p.exists():
        return list(_EMPTY_PENDING_LINES)
    try:
        with open(p, "r", encoding="utf-8") as f:
            return f.read().splitlines(keepends=False)
    except Exception:
        return list(_EMPTY_PENDING_LINES)


def _write_pending_lines(root: Path, lines: List[str]) -> None:
    """Atomic-ish write of pending (tmp + mv). Always normalized (no dual empty+items)."""
    p = _get_pending_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    normalized = _normalize_pending_lines(lines)
    tmp = p.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("\n".join(normalized) + "\n")
        os.replace(tmp, p)
    except Exception:
        with open(p, "w", encoding="utf-8") as f:
            f.write("\n".join(normalized) + "\n")
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass


def count_pending(root: Path) -> int:
    """Count real pending work items (bullet lines only; empty markers ignored)."""
    return len(_pending_item_lines(_read_pending_lines(root)))


def _do_remove_from_pending(root: Path, file: str) -> int:
    """Internal: idempotent remove of any item lines containing file (fixed-string)."""
    lines = _read_pending_lines(root)
    items_before = _pending_item_lines(lines)
    new_items = [ln for ln in items_before if file not in ln]
    removed = len(items_before) - len(new_items)
    # Always rewrite so dual "(no active)" + items and stale markers get fixed.
    _write_pending_lines(root, new_items)
    return removed


def remove_from_pending(root: Path, file: str) -> int:
    """Public: remove references to file from pending_updates.md. Idempotent. Under lock."""
    if locking:
        with locking.file_lock(root):
            return _do_remove_from_pending(root, file)
    else:
        return _do_remove_from_pending(root, file)


def _do_add_to_pending(root: Path, file: str, msg: str) -> None:
    """Internal add (idempotent). Strips empty markers when real items exist."""
    lines = _read_pending_lines(root)
    entry = f"- {file}: {msg}"
    items = _pending_item_lines(lines)
    if entry not in items:
        items.append(entry)
    _write_pending_lines(root, items)


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
    # Agent-first: baseline *source* bytes so mtime-only thrash does not re-Yellow
    try:
        src = Path(root) / file
        if not src.is_file():
            src = Path(file) if Path(file).is_file() else src
        src_hash = compute_source_content_hash(src)
        if src_hash:
            data = load_health(root)
            ent = data.setdefault("entries", {}).get(file)
            if isinstance(ent, dict):
                ent["source_content_hash"] = src_hash
                data["entries"][file] = ent
                save_health(root, data)
    except Exception:
        pass
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


# Parseable / deep-map source suffixes (align with update-maps collectors).
# validate map-first only requires health for these — not every README/png under monitored.
PARSEABLE_SOURCE_SUFFIXES = frozenset({
    ".py", ".pyi",
    ".js", ".jsx", ".mjs", ".cjs",
    ".ts", ".tsx",
    ".rs",
    ".go",
    ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh",
    ".cs",
    ".java",
})


def _read_monitored_rel_roots(root: Path) -> List[str]:
    monitored_file = root / "monitored_paths.txt"
    if monitored_file.exists():
        try:
            roots = [
                ln.strip()
                for ln in monitored_file.read_text(encoding="utf-8").splitlines()
                if ln.strip() and not ln.strip().startswith("#")
            ]
            if roots:
                return roots
        except Exception:
            pass
    return ["."]


def _under_monitored(rel: str, monitored_rels: List[str]) -> bool:
    """True if rel is inside any monitored relative root (or monitor is '.')."""
    if not monitored_rels or monitored_rels == ["."]:
        return True
    rel_n = rel.replace("\\", "/").lstrip("./")
    for m in monitored_rels:
        m_n = m.replace("\\", "/").rstrip("/")
        if m_n in (".", ""):
            return True
        if rel_n == m_n or rel_n.startswith(m_n + "/"):
            return True
    return False


def find_ghost_entries(root: Path) -> List[str]:
    """G7: Health keys that look like project files but no longer exist on disk.

    Skips explicit DELETED audit rows and non-path historical note keys (no slash /
    no common source suffix). Used by check_changes + validate.
    """
    root = Path(root).resolve()
    health = load_health(root)
    ghosts: List[str] = []
    source_suffixes = tuple(PARSEABLE_SOURCE_SUFFIXES) + (
        ".md", ".json", ".sh", ".toml", ".yaml", ".yml", ".html",
    )
    for key, entry in (health.get("entries") or {}).items():
        if not isinstance(key, str) or not key or key.startswith("/"):
            # absolute keys are pollution; treat as ghost-like for cleanup lists
            if isinstance(key, str) and key.startswith("/"):
                ghosts.append(key)
            continue
        reason = str((entry or {}).get("reason") or "")
        status = str((entry or {}).get("status") or "")
        if "DELETED" in reason or "DELETED" in status:
            continue
        # Skip free-form historical notes without a path shape
        if "/" not in key and not key.endswith(source_suffixes):
            continue
        p = root / key
        try:
            if not p.exists():
                ghosts.append(key)
        except Exception:
            ghosts.append(key)
    return sorted(set(ghosts))


def _load_map_file_keys(root: Path) -> List[str]:
    """Non-reserved import_cache keys (mapped source files)."""
    try:
        from . import import_cache as ic
        cache = ic.load_cache(root) or {}
    except Exception:
        cache = {}
        cache_path = root / ".wikifier_staging" / "import_cache.json"
        if cache_path.exists():
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    cache = json.load(f) or {}
            except Exception:
                cache = {}
    keys = []
    for k in cache:
        if not isinstance(k, str) or not k or k.startswith("_"):
            continue
        if _looks_like_path_key(k):
            keys.append(k)
    return keys


def seed_health_from_map(
    root: Path,
    map_keys: Optional[List[str]] = None,
    max_new: int = 10000,
    only_monitored: Optional[bool] = None,
    reason: str = (
        "Initial stub — present in dependency map; "
        "agent should wiki + mark-green when editing"
    ),
) -> Dict[str, Any]:
    """Map-first: ensure mapped files have at least a 🟡 health stub.

    Fixes warm-cache projects where update-maps never re-parses (0 dirty) and
    therefore never creates file_health.json. Batched single save (no N locks).

    only_monitored: default True when monitored_paths is lean (not bare '.'),
    so we do not seed the entire monorepo map into health then fight prune.
    """
    root = _coerce_root(root)
    keys = list(map_keys) if map_keys is not None else _load_map_file_keys(root)
    max_new = max(0, min(int(max_new), 100000))
    monitored = _read_monitored_rel_roots(root)
    if only_monitored is None:
        only_monitored = not (monitored == ["."] or monitored == [])
    if only_monitored:
        keys = [k for k in keys if _under_monitored(k, monitored)]

    def _work() -> Dict[str, Any]:
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
            if rel in entries:
                continue
            if not _entry_is_under_root(root, rel) or _is_pollution_health_key(rel):
                continue
            base = {
                "status": "🟡 Yellow",
                "last_updated": now,
                "reason": reason,
                "freshness_provenance": "seed_health_from_map",
            }
            if contracts and hasattr(contracts, "normalize_health_entry"):
                base = contracts.normalize_health_entry(base)
            else:
                base = _normalize_health_entry_local(base)
            entries[rel] = base
            seeded += 1
        if seeded > 0 or before == 0:
            # Always persist when empty health so file_health.json exists for agents
            health["entries"] = entries
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

    if locking:
        with locking.file_lock(root):
            return _work()
    return _work()


def seed_health_for_monitored_sources(
    root: Path,
    max_new: int = 20000,
    reason: str = (
        "Initial stub — parseable source under monitored_paths; "
        "agent should wiki + mark-green when editing"
    ),
) -> Dict[str, Any]:
    """Walk monitored parseable sources and stub any missing health rows.

    Complements seed_health_from_map when the map is scoped/partial but
    monitored_paths still contains on-disk sources (e.g. rust std tree).
    """
    root = _coerce_root(root)
    monitored_roots = _read_monitored_rel_roots(root)
    excludes = _build_simple_exclude_set(root)
    internal_skips = {".git", ".wikifier_staging", "journal", "Logged_issues", "node_modules"}
    found: List[str] = []
    for r in monitored_roots:
        base = (root / r).resolve()
        if not base.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in internal_skips and d not in excludes]
            for fname in filenames:
                fpath = Path(dirpath) / fname
                if fpath.suffix.lower() not in PARSEABLE_SOURCE_SUFFIXES:
                    continue
                try:
                    rel = str(fpath.relative_to(root))
                except Exception:
                    continue
                parts = Path(rel).parts
                if any(p in excludes or p in internal_skips for p in parts):
                    continue
                found.append(rel)
    return seed_health_from_map(
        root,
        map_keys=found,
        max_new=max_new,
        only_monitored=False,
        reason=reason,
    )


def prune_pending_to_monitored(root: Path, drop_auto_detected: bool = True) -> Dict[str, Any]:
    """Drop pending bullets outside monitored_paths (and optional auto-detected noise).

    drop_auto_detected: remove check-changes thrash lines ("Auto-detected modification").
    Map-first stubs live as 🟡 health rows; they do not need a huge pending flood.
    """
    root = _coerce_root(root)
    monitored = _read_monitored_rel_roots(root)

    def _work() -> Dict[str, Any]:
        lines = _read_pending_lines(root)
        items = _pending_item_lines(lines)
        kept: List[str] = []
        removed = 0
        removed_auto = 0
        for ln in items:
            body = ln[2:] if ln.startswith("- ") else ln
            fpath = body.split(":", 1)[0].strip()
            msg = body.split(":", 1)[1] if ":" in body else ""
            if drop_auto_detected and "auto-detected" in msg.lower():
                removed += 1
                removed_auto += 1
                continue
            if _under_monitored(fpath, monitored):
                kept.append(ln)
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

    if locking:
        with locking.file_lock(root):
            return _work()
    return _work()


def prune_health_outside_monitored(
    root: Path,
    keep_deleted_audits: bool = True,
) -> Dict[str, Any]:
    """Remove health rows outside lean monitored_paths (cuts yellow floods).

    Keeps 🔴 DELETED audit rows when keep_deleted_audits=True.
    """
    root = _coerce_root(root)
    monitored = _read_monitored_rel_roots(root)

    def _work() -> Dict[str, Any]:
        health = load_health(root)
        entries = health.get("entries") or {}
        kept: Dict[str, Any] = {}
        removed = 0
        for k, v in entries.items():
            ent = v if isinstance(v, dict) else {}
            status = str(ent.get("status") or "")
            reason = str(ent.get("reason") or "")
            if keep_deleted_audits and ("DELETED" in reason or "DELETED" in status):
                if _looks_like_path_key(k):
                    kept[k] = v
                    continue
            if _under_monitored(str(k), monitored):
                kept[k] = v
            else:
                removed += 1
        health["entries"] = kept
        _do_save_health(root, health)
        return {
            "success": True,
            "removed": removed,
            "kept": len(kept),
            "monitored": monitored,
            "root": str(root),
        }

    if locking:
        with locking.file_lock(root):
            return _work()
    return _work()


def validate_health(root: Path) -> Dict[str, Any]:
    """
    Map-first health validation (agent-friendly).

    - Scans **parseable source files** under monitored_paths only (not every
      README/asset). Non-source files never count as missing.
    - Also reports mapped files (import_cache) lacking a health row — the true
      map-first gap when warm cache never re-parsed.
    - G7: ghost_entries (health keys with missing disk paths).

    Never mutates state. Exit code is caller-driven.
    """
    root = _coerce_root(root)
    health = load_health(root)
    entries = health.get("entries", {})
    known = set(entries.keys())

    monitored_roots = _read_monitored_rel_roots(root)
    excludes = _build_simple_exclude_set(root)
    internal_skips = {".git", ".wikifier_staging", "journal", "Logged_issues", "node_modules"}

    missing: List[str] = []
    total_scanned = 0
    non_source_skipped = 0

    for r in monitored_roots:
        if not r:
            continue
        base = (root / r).resolve()
        if not base.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in internal_skips and d not in excludes]
            for fname in filenames:
                fpath = Path(dirpath) / fname
                suf = fpath.suffix.lower()
                if suf not in PARSEABLE_SOURCE_SUFFIXES:
                    non_source_skipped += 1
                    continue
                total_scanned += 1
                try:
                    rel = str(fpath.relative_to(root))
                except Exception:
                    rel = str(fpath)
                parts = Path(rel).parts
                if any(p in excludes or p in internal_skips for p in parts):
                    continue
                if rel not in known:
                    missing.append(rel)

    missing = sorted(set(missing))
    ghosts = find_ghost_entries(root)

    mapped_keys = _load_map_file_keys(root)
    mapped_without_health = sorted(k for k in mapped_keys if k not in known)
    # In-scope map gaps only (respect lean monitored_paths)
    mapped_in_scope = [k for k in mapped_keys if _under_monitored(k, monitored_roots)]
    mapped_in_scope_without_health = sorted(k for k in mapped_in_scope if k not in known)
    # Primary agent signal: monitored parseable missing ∪ in-scope mapped missing
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
        "total_scanned": total_scanned,
        "non_source_skipped": non_source_skipped,
        "health_entries": len(known),
        "mapped_files": len(mapped_keys),
        "monitored_roots": monitored_roots,
        "map_first": True,
        "note": (
            "Map-first validate: missing_count = parseable sources under monitored_paths "
            "plus mapped files under those paths lacking health. Full-map gaps outside "
            "lean monitors are informational (mapped_without_health_count). Non-source "
            "files are ignored."
        ),
        "root": str(root),
    }


def detect_scope_risks(root: Path) -> Dict[str, Any]:
    """Dual-scope + multi-project root misuse detector (agent hygiene)."""
    root = _coerce_root(root)
    warnings: List[str] = []
    monitored = _read_monitored_rel_roots(root)
    bare_dot = monitored == ["."] or monitored == []
    if bare_dot:
        warnings.append(
            "monitored_paths is bare '.' — check-changes will thrash on large trees. "
            "Prefer lean package roots (e.g. src/, library/std/src)."
        )

    # Parent multi-project container heuristic
    child_projects = 0
    sample_children: List[str] = []
    try:
        for p in root.iterdir():
            if not p.is_dir() or p.name.startswith("."):
                continue
            if (p / ".git").exists() or (p / "file_health.json").exists() or (
                p / ".wikifier_staging" / "import_cache.json"
            ).exists():
                child_projects += 1
                if len(sample_children) < 8:
                    sample_children.append(p.name)
    except Exception:
        pass
    if child_projects >= 3:
        warnings.append(
            f"project_root looks like a multi-project container ({child_projects} child "
            f"projects e.g. {sample_children}). Always target a *child* project path, "
            "never the parent folder (e.g. cloned_sample_projects)."
        )
    name = root.name.lower()
    if name in ("cloned_sample_projects", "coding_projects", "repos", "samples"):
        warnings.append(
            f"Directory name '{root.name}' often holds many repos — confirm project_root "
            "is a single project, not the container."
        )

    return {
        "monitored_roots": monitored,
        "bare_dot_monitor": bare_dot,
        "child_project_count": child_projects,
        "child_project_sample": sample_children,
        "warnings": warnings,
        "ok": len(warnings) == 0,
    }


def _staging_byte_total(staging: Path, cache_path: Path) -> int:
    if not staging.exists():
        return 0
    total = 0
    try:
        for p in staging.rglob("*"):
            if p.is_file():
                try:
                    total += p.stat().st_size
                except Exception:
                    pass
    except Exception:
        try:
            return cache_path.stat().st_size if cache_path.exists() else 0
        except Exception:
            return 0
    return total


def write_metrics_snapshot(
    root: Path,
    source: str = "manual",
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Append a long-horizon metrics sample under .wikifier_staging/.

    Files:
      - metrics_latest.json  (last sample, overwrite)
      - metrics_history.jsonl (append-only; pruned to last 500 lines)

    Call from CLI, readiness assessment, or daemon periodic ticks.
    Does not claim multi-day soak; enables measurable growth over calendar time.
    """
    root = _coerce_root(root)
    staging = root / ".wikifier_staging"
    staging.mkdir(parents=True, exist_ok=True)
    cache_path = staging / "import_cache.json"
    summary = get_summary(root)
    scope = detect_scope_risks(root)
    ghosts = find_ghost_entries(root)
    cache_bytes = cache_path.stat().st_size if cache_path.exists() else 0
    staging_bytes = _staging_byte_total(staging, cache_path)
    journal_files = 0
    journal_root = root / "journal"
    if journal_root.exists():
        journal_files = sum(1 for _ in journal_root.rglob("*.md"))

    heartbeat = None
    hb_path = staging / "daemon_heartbeat.json"
    if hb_path.exists():
        try:
            heartbeat = json.loads(hb_path.read_text(encoding="utf-8"))
        except Exception:
            heartbeat = {"error": "unreadable"}

    snap: Dict[str, Any] = {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": source,
        "root": str(root),
        "health_score": summary.get("health_score"),
        "total": summary.get("total"),
        "green": summary.get("green"),
        "yellow": summary.get("yellow"),
        "red": summary.get("red"),
        "stub_yellow": summary.get("stub_yellow"),
        "actionable_yellow": summary.get("actionable_yellow"),
        "pending_updates": summary.get("pending_updates"),
        "ghost_count": len(ghosts),
        "cache_bytes": cache_bytes,
        "staging_bytes": staging_bytes,
        "journal_files": journal_files,
        "bare_dot_monitor": scope.get("bare_dot_monitor"),
        "scope_ok": scope.get("ok"),
        "daemon_heartbeat_ok": (heartbeat or {}).get("ok") if isinstance(heartbeat, dict) else None,
        "daemon_fail_streak": (heartbeat or {}).get("consecutive_failures")
        if isinstance(heartbeat, dict)
        else None,
    }
    if extra:
        snap["extra"] = extra

    latest_path = staging / "metrics_latest.json"
    hist_path = staging / "metrics_history.jsonl"
    try:
        latest_path.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")
        with open(hist_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(snap, ensure_ascii=False) + "\n")
        # Bound history (last 500 samples)
        try:
            lines = hist_path.read_text(encoding="utf-8").splitlines()
            if len(lines) > 500:
                hist_path.write_text("\n".join(lines[-500:]) + "\n", encoding="utf-8")
        except Exception:
            pass
        snap["success"] = True
        snap["metrics_latest_path"] = str(latest_path)
        snap["metrics_history_path"] = str(hist_path)
    except Exception as e:
        snap["success"] = False
        snap["error"] = str(e)
    return snap


def read_metrics_history(root: Path, limit: int = 20) -> List[Dict[str, Any]]:
    """Return up to `limit` most recent metrics samples (newest last)."""
    root = _coerce_root(root)
    hist_path = root / ".wikifier_staging" / "metrics_history.jsonl"
    if not hist_path.exists():
        return []
    out: List[Dict[str, Any]] = []
    try:
        lines = hist_path.read_text(encoding="utf-8").splitlines()
        for ln in lines[-max(1, min(limit, 500)) :]:
            ln = ln.strip()
            if not ln:
                continue
            try:
                out.append(json.loads(ln))
            except Exception:
                continue
    except Exception:
        return []
    return out


def assess_autonomous_readiness(
    root: Path,
    write_metrics: bool = True,
) -> Dict[str, Any]:
    """Long-horizon autonomous ops checklist (map + daemon + scope + state).

    Does not replace multi-day soak evidence; surfaces *whether* a target is
    configured safely enough for unattended check-changes/daemon loops.
    Optionally appends a metrics snapshot for growth tracking over calendar time.
    """
    root = _coerce_root(root)
    summary = get_summary(root)
    scope = detect_scope_risks(root)
    ghosts = find_ghost_entries(root)
    pending_n = count_pending(root)

    staging = root / ".wikifier_staging"
    cache_path = staging / "import_cache.json"
    lock_path = staging / ".lock"
    pid_path = staging / "wikifier.pid"
    heartbeat_path = staging / "daemon_heartbeat.json"
    log_path = staging / "daemon.log"
    metrics_latest_path = staging / "metrics_latest.json"

    cache_bytes = cache_path.stat().st_size if cache_path.exists() else 0
    staging_bytes = _staging_byte_total(staging, cache_path)

    journal_root = root / "journal"
    journal_days = 0
    journal_files = 0
    if journal_root.exists():
        for p in journal_root.rglob("*.md"):
            journal_files += 1
        try:
            journal_days = len({p.parent for p in journal_root.rglob("*.md")})
        except Exception:
            pass

    daemon_running = False
    daemon_pid = None
    if pid_path.exists():
        try:
            daemon_pid = int(pid_path.read_text(encoding="utf-8").strip())
            os.kill(daemon_pid, 0)
            daemon_running = True
        except Exception:
            daemon_running = False

    heartbeat = None
    if heartbeat_path.exists():
        try:
            with open(heartbeat_path, "r", encoding="utf-8") as f:
                heartbeat = json.load(f)
        except Exception:
            heartbeat = {"error": "unreadable"}

    has_health = (root / "file_health.json").exists() or (root / "file_health.md").exists()
    has_library = (root / "library.md").exists()
    has_cache = cache_path.exists()

    metrics_snap = None
    if write_metrics:
        try:
            metrics_snap = write_metrics_snapshot(root, source="autonomous-status")
        except Exception as e:
            metrics_snap = {"success": False, "error": str(e)}

    history = read_metrics_history(root, limit=5)
    growth_note = None
    if len(history) >= 2:
        try:
            a, b = history[0], history[-1]
            da = int(b.get("staging_bytes") or 0) - int(a.get("staging_bytes") or 0)
            growth_note = {
                "samples": len(history),
                "staging_bytes_delta": da,
                "first_ts": a.get("ts"),
                "last_ts": b.get("ts"),
            }
        except Exception:
            growth_note = None

    blockers: List[str] = []
    recs: List[str] = []
    if not has_cache and not has_library:
        blockers.append("No import map (run update-maps first).")
    if not has_health:
        blockers.append("No file_health — run seed-health or update-maps.")
    if scope["warnings"]:
        recs.extend(scope["warnings"])
    if len(ghosts) > 50:
        blockers.append(f"Many ghost health keys ({len(ghosts)}); run record-deletion / prune.")
    elif ghosts:
        recs.append(f"{len(ghosts)} ghost health entries — clean with record-deletion.")
    if pending_n > 500:
        recs.append(
            f"pending_updates={pending_n} is large; run prune-pending (auto-detected noise)."
        )
    if cache_bytes > 200 * 1024 * 1024:
        recs.append(
            f"import_cache is large ({cache_bytes // (1024*1024)}MB); "
            "prefer scoped update-maps and lean monitors for long runs."
        )
    if staging_bytes > 500 * 1024 * 1024:
        recs.append(f".wikifier_staging ~{staging_bytes // (1024*1024)}MB — watch disk growth.")
    if not daemon_running:
        recs.append(
            "Daemon not running. For long-horizon: "
            "`WIKIFIER_PROJECT_ROOT=… wikifier daemon start` "
            "(maps interval default 600s; WIKIFIER_DAEMON_MAPS=0 for check-only)."
        )
    else:
        recs.append(f"Daemon running (PID {daemon_pid}).")
    recs.append(
        "Metrics: write_metrics_snapshot / `wikifier metrics-snapshot`; "
        "history at .wikifier_staging/metrics_history.jsonl for soak growth."
    )

    score = summary.get("health_score") or "Unknown"
    # Readiness tier for unattended ops (not M5 95% soak claim)
    if blockers:
        readiness = "blocked"
    elif scope["warnings"] and summary.get("actionable_yellow", 0) == 0 and summary.get("red", 0) == 0:
        readiness = "map_ok_scope_risk"
    elif score in ("Map Ready", "Good") and not scope["bare_dot_monitor"]:
        readiness = "ready_for_daemon"
    elif score == "Needs Attention" and summary.get("red", 0) == 0:
        readiness = "ready_with_agent_wiki_work"
    else:
        readiness = "not_ready"

    return {
        "success": True,
        "root": str(root),
        "readiness": readiness,
        "health_score": score,
        "health_summary": summary,
        "scope": scope,
        "ghost_count": len(ghosts),
        "pending_updates": pending_n,
        "artifacts": {
            "has_health": has_health,
            "has_library": has_library,
            "has_cache": has_cache,
            "cache_bytes": cache_bytes,
            "staging_bytes": staging_bytes,
            "journal_files": journal_files,
            "journal_day_dirs": journal_days,
            "metrics_latest": str(metrics_latest_path) if metrics_latest_path.exists() else None,
        },
        "daemon": {
            "running": daemon_running,
            "pid": daemon_pid,
            "heartbeat": heartbeat,
            "log": str(log_path) if log_path.exists() else None,
            "maps_env": {
                "WIKIFIER_DAEMON_MAPS": os.environ.get("WIKIFIER_DAEMON_MAPS", "1"),
                "WIKIFIER_DAEMON_MAPS_INTERVAL": os.environ.get(
                    "WIKIFIER_DAEMON_MAPS_INTERVAL", "600"
                ),
            },
        },
        "metrics": metrics_snap,
        "metrics_growth": growth_note,
        "lock_path": str(lock_path),
        "blockers": blockers,
        "recommendations": recs,
        "long_horizon_note": (
            "ready_for_daemon = safe config for unattended check-changes/maps heartbeat. "
            "It is NOT a multi-day 0-corruption soak proof (M5.3). "
            "For soak: run daemon on 1–3 lean-monitored targets, append metrics-snapshot "
            "periodically, watch staging_bytes delta in metrics_history.jsonl, "
            "daemon_heartbeat consecutive_failures, and journal continuity over >=72h."
        ),
        "map_first_note": summary.get("map_first_note"),
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


def _is_map_first_stub_entry(entry: Dict[str, Any]) -> bool:
    """True for map-first Initial stubs (not agent-action work items)."""
    if not isinstance(entry, dict):
        return False
    reason = str(entry.get("reason") or "")
    prov = str(entry.get("freshness_provenance") or "")
    blob = (reason + " " + prov).lower()
    if "initial stub" in blob:
        return True
    if "seed_health_from_map" in blob or "seed_health_for_monitored" in blob:
        return True
    if "present in dependency map" in blob:
        return True
    if "parseable source under monitored" in blob:
        return True
    return False


def _compute_health_score(
    red: int,
    yellow: int,
    stub_yellow: int,
    actionable_yellow: int,
) -> str:
    """Agent-facing readiness label (map-first aware).

    Map Ready  — no reds, only map-first stubs (or empty); do NOT treat as unfinished wiki.
    Good       — clean green-heavy tree, few actionable yellows
    Needs Attention — actionable yellows / pending work (not mere stubs)
    Critical   — reds
    """
    if red >= 3:
        return "Critical"
    if red > 0:
        return "Needs Attention"
    if actionable_yellow > 0:
        return "Needs Attention"
    if yellow > 0 and stub_yellow >= yellow and actionable_yellow == 0:
        return "Map Ready"
    if yellow == 0:
        return "Good"
    if yellow < 5:
        return "Good"
    return "Needs Attention"


def get_summary(root: Path, directory: Optional[str] = None, include_stale: bool = False) -> Dict[str, Any]:
    """Return a summary of the health matrix (fast even for large repos; sharded by dir).

    Map-first taxonomy (additive fields):
      stub_yellow — Initial stub / map-seed rows (lookup OK; wiki on edit)
      actionable_yellow — real work (mtime, record-change, barrel stale, …)
      health_score — \"Map Ready\" | \"Good\" | \"Needs Attention\" | \"Critical\"

    Agents must not treat stub_yellow as \"I understand this file.\"
    """
    health = load_health(root)
    entries = health.get("entries", {})

    green = yellow = red = 0
    stub_yellow = actionable_yellow = 0
    total = 0

    for file_path, entry in entries.items():
        if directory:
            if not file_path.startswith(directory.rstrip('/') + '/'):
                continue

        total += 1
        status = entry.get("status", "") if isinstance(entry, dict) else ""
        if "🟢" in status:
            green += 1
        elif "🟡" in status:
            yellow += 1
            if _is_map_first_stub_entry(entry if isinstance(entry, dict) else {}):
                stub_yellow += 1
            else:
                actionable_yellow += 1
        elif "🔴" in status:
            red += 1

    try:
        pending_n = count_pending(root)
    except Exception:
        pending_n = 0
    score = _compute_health_score(red, yellow, stub_yellow, actionable_yellow)
    out = {
        "total": total,
        "green": green,
        "yellow": yellow,
        "red": red,
        "stub_yellow": stub_yellow,
        "actionable_yellow": actionable_yellow,
        "pending_updates": pending_n,
        "health_score": score,
        "map_first_note": (
            "Yellow Initial stubs = map coverage only; wiki prose is optional until you edit. "
            "Prefer actionable_yellow / red for work. health_score Map Ready ≠ wiki-done."
        ),
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
        if not _entry_is_under_root(root, file_path):
            continue
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
            is_stub = _is_map_first_stub_entry(entry) or (
                "Initial stub" in status or ("🔴" in status and "stub" in reason.lower())
            )
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
        if not _entry_is_under_root(root, rel_path):
            continue
        if directory:
            if not rel_path.startswith(directory.rstrip('/') + '/'):
                continue

        status = entry.get("status", "")
        is_stub = _is_map_first_stub_entry(entry) or (
            "Initial stub" in status or ("🔴" in status and "stub" in entry.get("reason", "").lower())
        )
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
                "has_purpose": quality["has_purpose_section"],
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
        if not _entry_is_under_root(root, rel_path):
            continue
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
