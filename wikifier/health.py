"""
Wikifier Health Matrix - Scalable Implementation (M2-Rem-02)

This module provides fast, scalable operations on the Documentation Health Matrix.
It is designed to work well from small projects (< 300 files) all the way to massive
monorepos (10k+ files).

Architecture:
- `file_health.json` is the primary source of truth (fast dict lookups).
- `file_health.md` is a generated human-readable view.
- Small projects can continue using the simple Markdown workflow.
- Larger projects benefit from significantly faster queries and updates.

JSON Schema (v1):
{
  "version": 1,
  "last_updated": "2026-05-16T12:34:56",
  "entries": {
    "relative/path/to/file.py": {
      "status": "🟢 Green",
      "last_updated": "2026-05-16 12:34:56",
      "reason": "Wiki summary verified accurate."
    },
    ...
  }
}
"""

import json
import os
<<<<<<< HEAD
=======
import re
>>>>>>> agent-3-health-reliability
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

# Import locking (M2-Rem-07)
try:
    from . import locking
except ImportError:
    locking = None

HEALTH_JSON = "file_health.json"
HEALTH_MD = "file_health.md"
PENDING_MD = "pending_updates.md"


def _get_health_path(root: Path) -> Path:
    return root / HEALTH_JSON


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_health(root: Path) -> Dict[str, Any]:
    """
    Load the health matrix from file_health.json.
    Falls back to migrating from file_health.md if JSON does not exist.
    """
    json_path = _get_health_path(root)

    if json_path.exists():
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if data.get("version") != 1:
                # Future version handling can go here
                pass
            return data

    # Migration path: if JSON doesn't exist but MD does
    md_path = root / HEALTH_MD
    if md_path.exists():
        return _migrate_from_markdown(md_path)

    # Fresh project
    return {
        "version": 1,
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
        "version": 1,
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
    """Internal upsert without locking."""
    health = load_health(root)
    health["entries"][file] = {
        "status": status,
        "last_updated": _timestamp(),
        "reason": reason
    }
    _do_save_health(root, health)


<<<<<<< HEAD
=======
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


def _do_mark_green(root: Path, file: str, reason: str = "") -> None:
    """Internal combined op (health + pending) without re-acquiring lock."""
    effective_reason = reason or "Wiki summary verified accurate after change."
    _do_upsert_entry(root, file, "🟢 Green", effective_reason)
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

>>>>>>> agent-3-health-reliability
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


def get_summary(root: Path, directory: Optional[str] = None) -> Dict[str, Any]:
    """Return a summary of the health matrix (fast even for large repos).

    If directory is provided, only counts files under that subdirectory.
    This enables scalable views in massive monorepos (e.g. health per package).
    """
    health = load_health(root)
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

    return {
        "total": total,
        "green": green,
        "yellow": yellow,
        "red": red,
        "pending_updates": 0,
        "directory": directory or "."
    }


def get_files_needing_attention(root: Path, status_filter: Optional[str] = None, directory: Optional[str] = None) -> List[str]:
    """Return list of files that need attention, optionally filtered by status and/or directory.

    Directory filtering is key for scalability in large monorepos.
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


def heal_outdated_stubs(root: Path, min_wiki_length: int = 350, dry_run: bool = False) -> int:
    """
    Automatically heal entries that are still marked as "Initial stub" (or equivalent 🔴 Red)
    but now have a substantial wiki summary.

    Uses improved quality heuristics:
    - Raw length
    - Presence of markdown headings
    - Presence of bullet points / lists
    - Semantic signals ("Purpose", "Role", "Overview", "Responsibilities")
    - Code blocks

    This allows differentiated healing:
    - Medium quality → 🟡 Yellow ("Needs review")
    - High quality → 🟢 Green (auto-trusted)

    Returns the number of entries that were healed.
    """
    health = load_health(root)
    healed = 0
    changes: List[tuple] = []

    for rel_path, entry in list(health.get("entries", {}).items()):
        status = entry.get("status", "")
        reason = entry.get("reason", "")

        # Only heal true "Initial stub" style entries
        is_stub = "Initial stub" in status or ("🔴" in status and "stub" in reason.lower())
        if not is_stub:
            continue

        wiki_file = _find_existing_wiki_file(root, rel_path)
        if not wiki_file:
            continue

        quality = _assess_wiki_quality(wiki_file)

        # Decision logic based on quality
        if quality["quality"] == "high":
            new_status = "🟢 Green"
            new_reason = f"Auto-healed: high-quality wiki summary detected (was {status})"
        elif quality["quality"] == "medium" and quality["length"] >= min_wiki_length:
            new_status = "🟡 Yellow"
            new_reason = f"Auto-healed: meaningful wiki summary now exists (was {status})"
        else:
            # Low quality or too short — do not heal
            continue

        if not dry_run:
            health["entries"][rel_path] = {
                "status": new_status,
                "last_updated": _timestamp(),
                "reason": new_reason
            }

        changes.append((rel_path, status, new_status, quality["quality"]))
        healed += 1

    if healed > 0 and not dry_run:
        save_health(root, health)

    for item in changes:
        rel, old, new, q = item
        print(f"  Healed: {rel}  [{q} quality]  {old} → {new}")

    return healed


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
        print("  needs-attention          List files needing work")
        print("  heal-stubs [--dry-run]   Auto-heal outdated 'Initial stub' entries")
        print("  healable-stubs [dir]     List entries that can be auto-healed")
        print("  healing-stats            Show stub pollution + healing opportunities")
        print("  prune-barrels [max_days] [ --dry-run ]   Lightweight age-based BRC pruning (default 90d)")
<<<<<<< HEAD
=======
        print("  mark-green <file> [reason]   Idempotent Green + clear pending (locked)")
        print("  remove-pending <file>        Idempotent remove from pending_updates (locked)")
        print("  add-pending <file> <msg>     Idempotent add to pending (locked)")
        print("  validate                     Report files missing health entries (no subshell)")
>>>>>>> agent-3-health-reliability
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
        directory = sys.argv[2] if len(sys.argv) > 2 else None
        files = get_files_needing_attention(root, directory=directory)
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

<<<<<<< HEAD
=======
    elif cmd == "mark-green":
        if len(sys.argv) < 3:
            print("Usage: python -m wikifier.health mark-green <file> [reason]")
            sys.exit(1)
        file = sys.argv[2]
        reason = " ".join(sys.argv[3:]) if len(sys.argv) > 3 else ""
        try:
            mark_green(root, file, reason)
            print(f"🟢 Marked Green (and pending cleared if present): {file}")
        except Exception as e:
            print(f"mark-green error: {e}")
            sys.exit(1)

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

>>>>>>> agent-3-health-reliability
    else:
        print(f"Unknown command: {cmd}")
