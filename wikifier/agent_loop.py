"""
Agent session helpers: bootstrap, preflight, journal search, dispatchable actions.

  session_bootstrap(root)    — one-shot session snapshot (+ root folder card)
  prepare_edit(file, root)   — status, wiki, dependencies, dependents, cycle flag
  search_journal(...)        — free-text / file-filtered journal search
  why_file(file, root)       — health reason + recent journal entries
  build_structured_actions() — dispatchable work items for suggest / bootstrap
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from . import cache_store as cs
from . import health_pkg as health_mod
from .paths import resolve_root, to_rel

PathArg = Union[str, Path]

CORE_DAILY_TOOLS: List[Dict[str, str]] = [
    {"name": "session_bootstrap", "role": "one-shot root + health + attention + actions[]"},
    {"name": "check_changes", "role": "content-honest dirty / ghosts"},
    {"name": "prepare_edit", "role": "single-file preflight wiki/status/deps/dependents"},
    {"name": "suggest_next_actions", "role": "selective work + dispatchable actions[]"},
    {"name": "record_change", "role": "semantic why after edits (record_changes for many files)"},
    {"name": "mark_green", "role": "wiki checked against the code, then trusted + baselined"},
]
CORE_DAILY_NAMES: List[str] = [t["name"] for t in CORE_DAILY_TOOLS]
ADVANCED_INTEL_TOOLS: List[str] = [
    "list_paths",
    "get_dependencies",
    "get_dependents",
    "get_cycles",
    "get_barrel_reports",
    "get_resolution_diagnostics",
    "health",
    "get_project_status",
    "get_files_needing_attention",
    "search_journal",
    "why_file",
    "update_maps",
    "validate",
    "record_changes",
    "verify_wikis",
]


def list_core_tools() -> Dict[str, Any]:
    """Core daily vs advanced tool metadata (agents should prefer Core)."""
    return {
        "success": True,
        "core_daily": list(CORE_DAILY_TOOLS),
        "core_names": list(CORE_DAILY_NAMES),
        "advanced_intel": list(ADVANCED_INTEL_TOOLS),
        "core_count": len(CORE_DAILY_NAMES),
        "note": "Use Core every session; advanced tools remain available.",
    }


def _error(project_root: Optional[PathArg], exc: BaseException, **extra: Any) -> Dict[str, Any]:
    out = {"success": False, "project_root": str(project_root or ""), "error": str(exc), "error_type": type(exc).__name__}
    out.update(extra)
    return out


def resolve_dependents_from_cache(cache: Dict[str, Any], rel: str) -> List[str]:
    """Importers of ``rel`` from an in-memory cache dict.

    Accepts the reverse-index shapes older writers produced (flat list,
    ``{"index": {...}}``, ``{rel: {"importers": [...]}}``); falls back to an
    exact-match scan of resolved_pairs.
    """
    if not rel or not isinstance(cache, dict):
        return []

    def as_list(value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(x) for x in value if x]
        if isinstance(value, dict):
            for key in ("importers", "sources", "dependents", "files", "from"):
                if isinstance(value.get(key), list):
                    return [str(x) for x in value[key] if x]
            return [str(k) for k in value if k and not str(k).startswith("_")]
        if isinstance(value, str) and value:
            return [value]
        return []

    reverse = cache.get("_reverse_dependencies") or {}
    if isinstance(reverse, dict):
        if rel in reverse and as_list(reverse[rel]):
            return as_list(reverse[rel])[:80]
        for nest_key in ("index", "dependents", "map", "by_target", "targets"):
            nested = reverse.get(nest_key)
            if isinstance(nested, dict) and rel in nested and as_list(nested[rel]):
                return as_list(nested[rel])[:80]
    found: List[str] = []
    for src, data in cache.items():
        if not isinstance(src, str) or src.startswith("_") or not isinstance(data, dict):
            continue
        for pair in data.get("resolved_pairs") or []:
            if isinstance(pair, dict) and (pair.get("resolved") or pair.get("resolved_path")) == rel:
                if src not in found:
                    found.append(src)
                break
    return found[:80]


# ---------------------------------------------------------------------------
# Dispatchable actions
# ---------------------------------------------------------------------------

def build_structured_actions(
    *,
    red_files: Optional[List[str]] = None,
    actionable_yellow_files: Optional[List[str]] = None,
    stub_yellow: int = 0,
    actionable_yellow: int = 0,
    red: int = 0,
    acs_actionable: int = 0,
    scope_warnings: Optional[List[str]] = None,
    blockers: Optional[List[str]] = None,
    clean: bool = False,
    max_file_actions: int = 12,
    map_coverage: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Dispatchable action objects: ``{action, file, priority (1=highest), reason, preflight}``.

    Priorities 1–2 are reserved for readiness blockers (scope, missing map/health).
    """
    actions: List[Dict[str, Any]] = []
    coverage = map_coverage if isinstance(map_coverage, dict) else {}
    remaining = int(coverage.get("files_remaining_dirty") or 0)
    complete = coverage.get("complete")
    blocker_list = [str(b) for b in (blockers or []) if b]

    def add(action: str, file: Optional[str], priority: int, reason: str, preflight: List[str], **extra: Any) -> None:
        item = {"action": action, "file": file, "priority": priority, "reason": reason, "preflight": preflight}
        item.update(extra)
        actions.append(item)

    for blocker in blocker_list:
        lowered = blocker.lower()
        if "file_health" in lowered or "seed-health" in lowered or "seed_health" in lowered:
            add("seed_health", None, 1, blocker, ["seed_health", "update_maps"])
        elif "import map" in lowered or "update-maps" in lowered or "update_maps" in lowered:
            add("update_maps", None, 1, blocker, ["update_maps"])
        else:
            add("fix_blocker", None, 2, blocker, [])
    for warning in (scope_warnings or [])[:3]:
        add("fix_scope", None, 2, str(warning), [])
    if complete is False or remaining > 0:
        add(
            "update_maps_until_complete", None, 2,
            f"Map incomplete: files_remaining_dirty={remaining}. Re-run update_maps with the same "
            "directory/max_files until map_coverage.complete=true — success alone does not mean the map is done.",
            ["update_maps"],
            map_coverage={
                "complete": complete,
                "files_remaining_dirty": remaining,
                "files_skipped": coverage.get("files_skipped"),
                "budget_max_files": coverage.get("budget_max_files"),
            },
        )
    priority = 3
    for file in (red_files or [])[:max_file_actions]:
        add("investigate_red", file, priority, "Red health entry — restore, record-deletion, or fix the missing path", ["prepare_edit"])
        priority = min(priority + 1, 9)
    for file in (actionable_yellow_files or [])[:max_file_actions]:
        add("wiki_refresh", file, priority, "Actionable yellow — refresh this file's wiki, then mark-green", ["prepare_edit", "why_file"])
        add("mark_green", file, priority, "Close the loop after the wiki refresh", ["prepare_edit"])
        priority = min(priority + 1, 9)
    if red == 0 and actionable_yellow == 0 and clean and remaining == 0 and not blocker_list:
        add("lookup_only", None, 5, "Health clean — do not re-summarize the tree; use prepare_edit for lookup", [])
    if stub_yellow > 0 and actionable_yellow == 0 and red == 0:
        add(
            "map_first_ok", None, 6,
            f"{stub_yellow} Initial stubs are map coverage only — wiki a file when you edit it, then mark-green.",
            [],
        )
    if acs_actionable > 0:
        add(
            "review_acs", None, 4,
            f"{acs_actionable} actionable low-confidence project edges (see get_dependencies)",
            ["get_dependencies"],
        )
    if not any(a["action"] in ("update_maps", "update_maps_until_complete") for a in actions):
        add("update_maps_if_structure", None, 8, "Run update_maps only if imports/structure changed", [])
    actions.sort(key=lambda a: int(a.get("priority") or 9))
    return actions


# ---------------------------------------------------------------------------
# Journal search
# ---------------------------------------------------------------------------

_ENTRY_SPLIT = re.compile(r"(?=^## \[)", re.M)


def search_journal(
    project_root: Optional[PathArg] = None,
    query: Optional[str] = None,
    file: Optional[str] = None,
    max_results: int = 20,
) -> Dict[str, Any]:
    """Journal entries matching ``query`` (case-insensitive) and/or ``file``, newest first."""
    try:
        root = resolve_root(project_root)
        rel_filter = to_rel(root, file) if file else None
    except ValueError as exc:
        return _error(project_root, exc, matches=[])
    result: Dict[str, Any] = {
        "success": True,
        "project_root": str(root),
        "query": query,
        "file": rel_filter,
        "matches": [],
        "scanned_files": 0,
    }
    journal_root = root / "journal"
    if not journal_root.is_dir():
        result["message"] = "no journal directory"
        return result
    needle = (query or "").strip().lower() or None
    day_files = sorted(journal_root.rglob("*.md"), key=lambda p: p.as_posix(), reverse=True)
    for day_file in day_files:
        text = day_file.read_text(encoding="utf-8", errors="replace")
        result["scanned_files"] += 1
        for chunk in reversed(_ENTRY_SPLIT.split(text)):
            chunk = chunk.strip()
            if not chunk.startswith("## ["):
                continue
            file_m = re.search(r"\*\*File:\*\*\s*(.+)", chunk)
            entry_file = file_m.group(1).strip() if file_m else ""
            if rel_filter and entry_file != rel_filter:
                continue
            if needle and needle not in chunk.lower():
                continue
            reason_m = re.search(r"\*\*Reason:\*\*\s*(.+)", chunk)
            action_m = re.search(r"^## \[[^\]]+\]\s*(\S+)", chunk, re.M)
            result["matches"].append({
                "journal_file": day_file.relative_to(root).as_posix(),
                "action": action_m.group(1).strip() if action_m else "",
                "file": entry_file,
                "reason": reason_m.group(1).strip() if reason_m else "",
                "snippet": chunk[:500],
            })
            if len(result["matches"]) >= max_results:
                return result
    return result


def why_file(file: str, project_root: Optional[PathArg] = None, max_results: int = 10) -> Dict[str, Any]:
    """Current health status/reason plus recent journal entries for ``file``."""
    try:
        root = resolve_root(project_root)
        rel = to_rel(root, file)
    except ValueError as exc:
        return _error(project_root, exc, file=file, journal_matches=[])
    entry = health_mod.load_health(root).get("entries", {}).get(rel) or {}
    return {
        "success": True,
        "project_root": str(root),
        "file": rel,
        "health_status": entry.get("status"),
        "health_reason": entry.get("reason"),
        "source_content_hash": entry.get("source_content_hash"),
        "journal_matches": search_journal(project_root=root, file=rel, max_results=max_results).get("matches") or [],
    }


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

def prepare_edit(file: str, project_root: Optional[PathArg] = None) -> Dict[str, Any]:
    """Single-file preflight: status, wiki, dependencies, dependents, cycle flag."""
    try:
        root = resolve_root(project_root)
        rel = to_rel(root, file)
    except ValueError as exc:
        return _error(project_root, exc, file=file)
    out: Dict[str, Any] = {
        "success": True,
        "project_root": str(root),
        "file": rel,
        "status": None,
        "reason": None,
        "wiki": None,
        "dependencies": [],
        "dependents": [],
        "in_cycle": False,
        "low_conf_edges": 0,
        "next_step": "Edit if needed → record_change → refresh wiki → mark_green",
    }
    entry = health_mod.load_health(root).get("entries", {}).get(rel) or {}
    out["status"] = entry.get("status")
    out["reason"] = entry.get("reason")
    out["source_content_hash"] = entry.get("source_content_hash")
    if not (root / rel).is_file():
        out.update({
            "success": False,
            "error": f"file not found: {rel}",
            "next_step": "Pass an existing project-relative source path",
        })
        if entry:
            out["ghost"] = True
        return out

    wiki_path = health_mod._find_existing_wiki_file(root, rel)
    if wiki_path and wiki_path.resolve() != (root / rel).resolve():
        out["wiki"] = wiki_path.read_text(encoding="utf-8", errors="replace")[:4000]
        out["wiki_path"] = wiki_path.relative_to(root).as_posix()

    from .cache.acs import _edge_is_non_actionable_noise

    cache_entry = cs.load_file_entry(root, rel) or {}
    dependencies = []
    low = 0
    for pair in cache_entry.get("resolved_pairs") or []:
        if not isinstance(pair, dict):
            continue
        score = pair.get("confidence_score")
        if isinstance(score, (int, float)) and score < 0.65 and not _edge_is_non_actionable_noise(pair):
            low += 1
        dependencies.append({
            "raw": pair.get("raw"),
            "resolved_path": pair.get("resolved") or pair.get("resolved_path") or None,
            "confidence": pair.get("confidence"),
            "confidence_score": score,
        })
    out["dependencies"] = dependencies[:80]
    out["dependencies_total"] = len(dependencies)
    out["low_conf_edges"] = low
    out["mapped"] = bool(cache_entry)
    out["dependents"] = cs.load_dependents(root, rel)[:80]
    cycles = cs.load_meta(root, keys=("_cycles",)).get("_cycles") or {}
    out["in_cycle"] = rel in set(cycles.get("all_cycle_files") or [])
    out["recent_why"] = why_file(rel, project_root=root, max_results=5).get("journal_matches") or []
    return out


# ---------------------------------------------------------------------------
# Session bootstrap
# ---------------------------------------------------------------------------

def session_bootstrap(
    project_root: Optional[PathArg] = None,
    directory: Optional[str] = None,
    max_attention_files: int = 15,
    map_index_file_budget: Optional[int] = None,
) -> Dict[str, Any]:
    """One-shot session snapshot (Core daily surface).

    ``map_index`` is the root folder card (depth-1 names). Expand with
    ``list_paths``; follow file-to-file links with ``prepare_edit``.
    """
    try:
        root = resolve_root(project_root)
    except ValueError as exc:
        return _error(project_root, exc)
    out: Dict[str, Any] = {
        "success": True,
        "project_root": str(root),
        "core_surface": list(CORE_DAILY_NAMES),
        "core_daily": list(CORE_DAILY_TOOLS),
        "core_count": len(CORE_DAILY_NAMES),
        "advanced_intel": list(ADVANCED_INTEL_TOOLS),
    }
    prefix = directory.rstrip("/") if directory else None
    summary = health_mod.get_summary(root, directory)
    out["health_summary"] = summary
    out["health_score"] = summary.get("health_score")
    red_files: List[str] = []
    yellow_files: List[str] = []
    actionable_yellow_files: List[str] = []
    for path, entry in health_mod.load_health(root).get("entries", {}).items():
        if prefix and not (path == prefix or path.startswith(prefix + "/")):
            continue
        status = str(entry.get("status") or "")
        if "🔴" in status:
            red_files.append(path)
        elif "🟡" in status:
            yellow_files.append(path)
            if not health_mod.summary._is_map_first_stub_entry(entry):
                actionable_yellow_files.append(path)
    out["attention"] = {
        "red": red_files[:max_attention_files],
        "actionable_yellow": actionable_yellow_files[:max_attention_files],
        "yellow_total": len(yellow_files),
        "red_total": len(red_files),
        "stub_yellow": int(summary.get("stub_yellow") or 0),
        "actionable_yellow_count": int(summary.get("actionable_yellow") or 0),
    }
    readiness = health_mod.assess_autonomous_readiness(root, write_metrics=False)
    out["readiness"] = readiness.get("readiness")
    out["scope"] = readiness.get("scope")
    out["blockers"] = readiness.get("blockers") or []

    meta = cs.load_meta(root, keys=("_acs_summary", "_cycles", "_map_coverage"))
    acs = meta.get("_acs_summary") if isinstance(meta.get("_acs_summary"), dict) else {}
    cycles = meta.get("_cycles") if isinstance(meta.get("_cycles"), dict) else {}
    coverage = meta.get("_map_coverage") if isinstance(meta.get("_map_coverage"), dict) else {}
    if coverage:
        out["map_coverage"] = coverage
    out["cache_backend"] = cs.backend_name(root)
    acs_actionable = int(acs.get("actionable_low_conf_edges") or 0)
    out["acs"] = {
        "acs_version": acs.get("acs_version"),
        "actionable_low_conf_edges": acs_actionable,
        "low_conf_edges": acs.get("low_conf_edges"),
        "dynamic_literal_noise_edges": acs.get("dynamic_literal_noise_edges"),
        "avg_confidence": acs.get("avg_confidence"),
        "reason_code_counts": acs.get("reason_code_counts"),
        "agent_signal_counts": acs.get("agent_signal_counts"),
    }
    out["acs_guidance"] = (
        "Work from actionable_low_conf_edges + reason_code_counts "
        "(external_or_bare / dynamic_literal are noise), not raw low_conf_edges."
    )
    out["cycles"] = {
        "cyclic_scc_count": (cycles.get("stats") or {}).get("cyclic_scc_count"),
        "all_cycle_files_sample": (cycles.get("all_cycle_files") or [])[:10],
    }

    from .map_index import bootstrap_map_index

    out["map_index"] = bootstrap_map_index(root, directory=directory, file_budget=map_index_file_budget)

    red_n = int(summary.get("red") or 0)
    action_y = int(summary.get("actionable_yellow") or 0)
    scope_warnings = list((out.get("scope") or {}).get("warnings") or [])
    out["actions"] = build_structured_actions(
        red_files=red_files,
        actionable_yellow_files=actionable_yellow_files,
        stub_yellow=int(summary.get("stub_yellow") or 0),
        actionable_yellow=action_y,
        red=red_n,
        acs_actionable=acs_actionable,
        scope_warnings=scope_warnings,
        blockers=out["blockers"],
        clean=red_n == 0 and int(summary.get("yellow") or 0) == 0,
        map_coverage=coverage,
    )
    out["work_items"] = out["actions"]
    out["selective_work"] = True
    out["map_first"] = True

    remaining = int(coverage.get("files_remaining_dirty") or 0)
    incomplete = remaining > 0 or coverage.get("complete") is False
    state = out["readiness"] or "unknown"
    guidance = {
        "blocked": "fix actions[] / blockers[] first (scope, update_maps, seed_health); the project is not map-ready.",
        "map_ok_scope_risk": "map/health present but scope is risky (often a bare '.' monitor); fix_scope before running the daemon.",
        "ready_for_daemon": "use actions[]; prepare_edit(file) before large edits; record_change after edits.",
    }.get(state, "use actions[]; prepare_edit(file) before large edits; record_change after edits.")
    out["message"] = f"readiness={state} — {guidance}" + (
        f" MAP INCOMPLETE: {remaining} files remaining — re-run update_maps until map_coverage.complete=true."
        if incomplete else ""
    )
    return out
