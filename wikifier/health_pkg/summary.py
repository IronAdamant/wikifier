"""
Health summaries and attention lists (map-first aware).

Map-first taxonomy:
  stub_yellow        — "Initial stub" rows seeded from the map (lookup OK; wiki on edit)
  actionable_yellow  — real work (content change, record-change, barrel staleness)
  health_score       — "Map Ready" | "Good" | "Needs Attention" | "Critical"
Agents must not treat stub_yellow as "I understand this file".
green_breakdown splits Green by how it was earned: verified (wiki checked
against the code), no_wiki, unchecked (no symbol extractor for the language),
forced (agent overrode a failed check), legacy (marked before verification).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .. import locking
from .freshness import get_stale_wikis
from .pending import count_pending
from .store import YELLOW, RootLike, _coerce_root, _do_upsert_entry, load_health

_STUB_MARKERS = (
    "initial stub",
    "seed_health_from_map",
    "seed_health_for_monitored",
    "present in dependency map",
    "parseable source under monitored",
)


def _is_map_first_stub_entry(entry: Dict[str, Any]) -> bool:
    """True for map-first stubs (not agent work items)."""
    if not isinstance(entry, dict):
        return False
    blob = f"{entry.get('reason') or ''} {entry.get('freshness_provenance') or ''}".lower()
    return any(marker in blob for marker in _STUB_MARKERS)


def _in_directory(path: str, directory: Optional[str]) -> bool:
    if not directory:
        return True
    prefix = directory.rstrip("/")
    return path == prefix or path.startswith(prefix + "/")


def _compute_health_score(red: int, yellow: int, stub_yellow: int, actionable_yellow: int) -> str:
    """Agent-facing readiness label (map-first aware)."""
    if red >= 3:
        return "Critical"
    if red > 0 or actionable_yellow > 0:
        return "Needs Attention"
    if yellow > 0 and stub_yellow >= yellow:
        return "Map Ready"
    if yellow < 5:
        return "Good"
    return "Needs Attention"


def get_summary(root: RootLike, directory: Optional[str] = None, include_stale: bool = False) -> Dict[str, Any]:
    """Counts by status plus the map-first taxonomy (O(entries))."""
    root = _coerce_root(root)
    health = load_health(root)
    green = yellow = red = stub_yellow = actionable_yellow = total = 0
    green_breakdown = {"verified": 0, "no_wiki": 0, "unchecked": 0, "forced": 0, "legacy": 0}
    for file_path, entry in health.get("entries", {}).items():
        if not _in_directory(file_path, directory):
            continue
        total += 1
        status = entry.get("status", "") if isinstance(entry, dict) else ""
        if "🟢" in status:
            green += 1
            kind = entry.get("verification") if isinstance(entry, dict) else None
            green_breakdown[kind if kind in green_breakdown else "legacy"] += 1
        elif "🟡" in status:
            yellow += 1
            if _is_map_first_stub_entry(entry):
                stub_yellow += 1
            else:
                actionable_yellow += 1
        elif "🔴" in status:
            red += 1
    out: Dict[str, Any] = {
        "total": total,
        "green": green,
        "green_breakdown": green_breakdown,
        "yellow": yellow,
        "red": red,
        "stub_yellow": stub_yellow,
        "actionable_yellow": actionable_yellow,
        "pending_updates": count_pending(root),
        "health_score": _compute_health_score(red, yellow, stub_yellow, actionable_yellow),
        "map_first_note": (
            "Yellow Initial stubs = map coverage only; wiki prose is optional until you edit. "
            "Prefer actionable_yellow / red for work. health_score Map Ready ≠ wiki-done."
        ),
        "directory": directory or ".",
        "version": health.get("version", 2),
        "last_updated": health.get("last_updated"),
    }
    if include_stale:
        stale = get_stale_wikis(root, directory=directory, limit=1000)
        out["stale_count"] = len(stale)
        out["stale_sample"] = [s["file"] for s in stale[:3]]
    return out


# Wikifier's own state files: mtime churn on these is not documentation debt.
_SELF_HOSTING_META = (
    "file_health.json", "file_health.md", "pending_updates.md",
    "logged_issues", "journal/",
    "exclude_patterns.txt", "monitored_paths.txt", "map_paths.txt",
)


def _is_self_hosting_meta_file(rel_path: str) -> bool:
    lowered = rel_path.lower()
    return any(marker in lowered for marker in _SELF_HOSTING_META)


def get_files_needing_attention(
    root: RootLike,
    status_filter: Optional[str] = None,
    directory: Optional[str] = None,
    include_meta: bool = False,
) -> List[str]:
    """Red/Yellow files, optionally filtered by status emoji and directory.

    Yellow rows on Wikifier's own state files are hidden unless ``include_meta``.
    """
    root = _coerce_root(root)
    result = []
    for file_path, entry in load_health(root).get("entries", {}).items():
        if not _in_directory(file_path, directory):
            continue
        status = entry.get("status", "")
        if status_filter and status_filter not in status:
            continue
        if "🟡" not in status and "🔴" not in status:
            continue
        if not include_meta and "🔴" not in status and _is_self_hosting_meta_file(file_path):
            continue
        result.append(file_path)
    return sorted(result)


def _report_field(report: Any, name: str, default: Any = None) -> Any:
    if isinstance(report, dict):
        return report.get(name, default)
    return getattr(report, name, default)


def apply_barrel_invalidation_reports(root: RootLike, reports: List[Any]) -> int:
    """Mark each importer named by a barrel invalidation report 🟡 with an explanation.

    Lets check-changes surface barrel-driven staleness when the importer itself
    did not change. Returns the number of importers updated (one save per report).
    """
    if not reports:
        return 0
    root = _coerce_root(root)
    updated = 0
    with locking.file_lock(root):
        for report in reports:
            importer = _report_field(report, "importer")
            if not importer:
                continue
            triggers = ", ".join(sorted({str(t) for t in (_report_field(report, "triggering_barrels") or []) if t}))
            chains = ", ".join(sorted({str(c) for c in (_report_field(report, "chain_ids") or []) if c}))[:80]
            partial = " (partial)" if _report_field(report, "is_partial", False) else ""
            explanation = (
                f"stale via barrel re-export from {triggers or 'unknown barrel'}{partial} "
                f"(detector={_report_field(report, 'detector_used') or 'bree'}, chains={chains or 'n/a'}): "
                f"{_report_field(report, 'reason') or 'barrel staleness'}"
            )
            _do_upsert_entry(root, str(importer), YELLOW, explanation)
            updated += 1
    return updated
