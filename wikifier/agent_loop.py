"""
Agent-first ideal loop helpers (bootstrap, preflight, journal, dispatchable actions).

AGENT MAP:
  session_bootstrap(root)     — one-shot session start snapshot
  prepare_edit(file, root)    — wiki + status + deps + dependents preflight
  search_journal(...)         — free-text / file-filtered journal search
  why_file(file, root)        — recent semantic reasons for a path
  build_structured_actions()  — dispatchable work items for suggest

Zero new deps. Prefer these over multi-tool protocol scrambles.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import importlib

from .project_root import discover_project_root

# Core daily agent surface (4.6+) — prefer these every session.
CORE_DAILY_TOOLS: List[Dict[str, str]] = [
    {"name": "session_bootstrap", "role": "one-shot root + health + attention + actions[]"},
    {"name": "check_changes", "role": "content-honest dirty / ghosts"},
    {"name": "prepare_edit", "role": "single-file preflight wiki/status/deps/dependents"},
    {"name": "suggest_next_actions", "role": "selective work + dispatchable actions[]"},
    {"name": "record_change", "role": "semantic why after edits"},
    {"name": "mark_green", "role": "trust + source content-hash baseline"},
]
CORE_DAILY_NAMES: List[str] = [t["name"] for t in CORE_DAILY_TOOLS]
ADVANCED_INTEL_TOOLS: List[str] = [
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
]


def list_core_tools() -> Dict[str, Any]:
    """Return Core daily vs advanced intel tool metadata (agents prefer Core)."""
    return {
        "success": True,
        "core_daily": list(CORE_DAILY_TOOLS),
        "core_names": list(CORE_DAILY_NAMES),
        "advanced_intel": list(ADVANCED_INTEL_TOOLS),
        "core_count": len(CORE_DAILY_NAMES),
        "note": "Use Core every session; advanced remains available but non-core.",
    }


def _health_module():
    """Real health submodule (not the shadowed package attribute function)."""
    return importlib.import_module("wikifier.health")


def resolve_dependents_from_cache(cache: Dict[str, Any], rel: str) -> List[str]:
    """Extract reverse dependents for *rel* from multiple reverse-index shapes.

    Supported:
      - flat: ``_reverse_dependencies[rel] -> [importers]``
      - nested index: ``_reverse_dependencies["index"][rel]``
      - dependents key: ``_reverse_dependencies["dependents"][rel]``
      - map value dict: ``{rel: {"importers": [...]}}`` or ``{"sources": [...]}``
      - import_cache.get_reverse_dependencies when available
    Fallback: scan resolved_pairs for edges pointing at rel.
    """
    if not rel or not isinstance(cache, dict):
        return []

    def _as_list(val: Any) -> List[str]:
        if val is None:
            return []
        if isinstance(val, list):
            return [str(x) for x in val if x]
        if isinstance(val, dict):
            for k in ("importers", "sources", "dependents", "files", "from"):
                if isinstance(val.get(k), list):
                    return [str(x) for x in val[k] if x]
            # keys-as-importers
            return [str(k) for k in val.keys() if k and not str(k).startswith("_")]
        if isinstance(val, str) and val:
            return [val]
        return []

    # Prefer library helper when present (canonical flat map)
    try:
        from . import import_cache as ic
        rev_map = ic.get_reverse_dependencies(cache) or {}
        if isinstance(rev_map, dict) and rel in rev_map:
            got = _as_list(rev_map.get(rel))
            if got:
                return got[:80]
    except Exception:
        pass

    rev = cache.get("_reverse_dependencies") or {}
    if not isinstance(rev, dict):
        return []

    # Direct flat
    if rel in rev:
        got = _as_list(rev.get(rel))
        if got:
            return got[:80]

    # Nested common containers
    for nest_key in ("index", "dependents", "map", "by_target", "targets"):
        nested = rev.get(nest_key)
        if isinstance(nested, dict) and rel in nested:
            got = _as_list(nested.get(rel))
            if got:
                return got[:80]

    # Fallback: O(E) scan of resolved_pairs
    found: List[str] = []
    for src, data in cache.items():
        if not isinstance(src, str) or src.startswith("_") or not isinstance(data, dict):
            continue
        for p in data.get("resolved_pairs") or []:
            if not isinstance(p, dict):
                continue
            tgt = p.get("resolved_path") or p.get("resolved") or ""
            if tgt == rel or str(tgt).endswith("/" + rel) or str(tgt).endswith(rel):
                if src not in found:
                    found.append(src)
    return found[:80]


def _root(project_root: Optional[Union[str, Path]] = None) -> Path:
    if project_root:
        try:
            p = Path(project_root).expanduser().resolve()
            if p.exists():
                return p
        except Exception:
            pass
    try:
        return Path(discover_project_root()).resolve()
    except Exception:
        return Path.cwd().resolve()


def _rel_file(root: Path, file: str) -> str:
    try:
        pp = Path(file)
        if pp.is_absolute():
            return str(pp.resolve().relative_to(root.resolve()))
    except Exception:
        pass
    return file.replace("\\", "/").lstrip("./")


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
    """Build dispatchable action objects for agents (not prose-only).

    Each item: action, file?, priority (1=highest), reason, optional preflight.
    Priority ≤2 is reserved for readiness blockers (scope + missing map/health).
    """
    actions: List[Dict[str, Any]] = []
    prio = 3  # file work starts after readiness fix actions (priority 1–2)
    cov = map_coverage if isinstance(map_coverage, dict) else {}
    remaining = int(cov.get("files_remaining_dirty") or 0)
    complete = cov.get("complete")
    blocker_list = [str(b) for b in (blockers or []) if b]
    # G6: missing map / file_health always get priority ≤2
    for b in blocker_list:
        bl = b.lower()
        # Prefer seed_health before generic update-maps (blocker text often mentions both)
        if "file_health" in bl or "seed-health" in bl or "seed_health" in bl:
            actions.append({
                "action": "seed_health",
                "file": None,
                "priority": 1,
                "reason": b,
                "preflight": ["seed_health", "update_maps"],
            })
        elif "import map" in bl or "update-maps" in bl or "update_maps" in bl:
            actions.append({
                "action": "update_maps",
                "file": None,
                "priority": 1,
                "reason": b,
                "preflight": ["update_maps"],
            })
        else:
            actions.append({
                "action": "fix_blocker",
                "file": None,
                "priority": 2,
                "reason": b,
                "preflight": [],
            })
    for w in (scope_warnings or [])[:3]:
        actions.append({
            "action": "fix_scope",
            "file": None,
            "priority": 2,
            "reason": str(w),
            "preflight": [],
        })
    # Incomplete map under budget — agents must not treat success alone as done (G5)
    if complete is False or remaining > 0:
        actions.append({
            "action": "update_maps_until_complete",
            "file": None,
            "priority": 2,
            "reason": (
                f"Map incomplete: files_remaining_dirty={remaining}, complete={complete}. "
                "Re-run update_maps (same directory/max_files) until map_coverage.complete=true; "
                "success alone does not mean the map is done."
            ),
            "preflight": ["update_maps"],
            "map_coverage": {
                "complete": complete,
                "files_remaining_dirty": remaining,
                "files_skipped": cov.get("files_skipped"),
                "budget_max_files": cov.get("budget_max_files"),
            },
        })
    for f in (red_files or [])[:max_file_actions]:
        actions.append({
            "action": "investigate_red",
            "file": f,
            "priority": prio,
            "reason": "Red health entry — restore, record-deletion, or fix missing path",
            "preflight": ["prepare_edit"],
        })
        prio = min(prio + 1, 9)
    for f in (actionable_yellow_files or [])[:max_file_actions]:
        actions.append({
            "action": "wiki_refresh",
            "file": f,
            "priority": prio,
            "reason": "Actionable yellow — record-change already done or content dirty; refresh wiki then mark-green",
            "preflight": ["prepare_edit", "why_file"],
        })
        prio = min(prio + 1, 9)
    if red == 0 and actionable_yellow == 0 and clean and remaining == 0 and not blocker_list:
        actions.append({
            "action": "lookup_only",
            "file": None,
            "priority": 5,
            "reason": "Health clean — do not re-summarize tree; use prepare_edit/get_file_wiki for lookup",
            "preflight": [],
        })
    # G10: stub-only yellows are map coverage — never bulk wiki_refresh
    if stub_yellow > 0 and actionable_yellow == 0 and red == 0:
        actions.append({
            "action": "map_first_ok",
            "file": None,
            "priority": 6,
            "reason": (
                f"{stub_yellow} Initial stubs are map coverage only — not bulk wiki work. "
                "Wiki a file only when you edit it, then mark-green."
            ),
            "preflight": [],
        })
    if acs_actionable > 0:
        actions.append({
            "action": "review_acs",
            "file": None,
            "priority": 4,
            "reason": (
                f"{acs_actionable} actionable low-confidence project edges "
                "(prefer actionable_low_conf_edges + reason_code_counts; not raw low_conf_edges)"
            ),
            "preflight": ["get_dependencies"],
        })
    if not any(
        a["action"] in (
            "update_maps",
            "update_maps_until_complete",
            "update_maps_if_structure",
        )
        for a in actions
    ):
        actions.append({
            "action": "update_maps_if_structure",
            "file": None,
            "priority": 8,
            "reason": "Run update_maps only if imports/structure changed (not wiki-only edits)",
            "preflight": [],
        })
    actions.sort(key=lambda a: int(a.get("priority") or 9))
    return actions


# ---------------------------------------------------------------------------
# Journal search
# ---------------------------------------------------------------------------

_ENTRY_SPLIT = re.compile(r"(?=^## \[)", re.M)


def search_journal(
    project_root: Optional[Union[str, Path]] = None,
    query: Optional[str] = None,
    file: Optional[str] = None,
    max_results: int = 20,
) -> Dict[str, Any]:
    """Search journal markdown under journal/YYYY/MM/*.md.

    Filters: substring query (case-insensitive) and/or file path fragment.
    Returns matching entry blocks newest-first (by file mtime then order).
    """
    root = _root(project_root)
    jroot = root / "journal"
    result: Dict[str, Any] = {
        "success": True,
        "project_root": str(root),
        "query": query,
        "file": file,
        "matches": [],
        "scanned_files": 0,
    }
    if not jroot.is_dir():
        result["message"] = "no journal directory"
        return result

    rel_filter = _rel_file(root, file) if file else None
    q = (query or "").strip().lower() or None
    day_files: List[Path] = sorted(jroot.rglob("*.md"), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    matches: List[Dict[str, Any]] = []

    for jf in day_files:
        try:
            text = jf.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        result["scanned_files"] += 1
        try:
            rel_j = str(jf.relative_to(root))
        except Exception:
            rel_j = str(jf)
        chunks = _ENTRY_SPLIT.split(text) if text.strip() else []
        if not chunks and text.strip():
            chunks = [text]
        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk.startswith("## ["):
                continue
            low = chunk.lower()
            if rel_filter and rel_filter.lower() not in low and Path(rel_filter).name.lower() not in low:
                continue
            if q and q not in low:
                continue
            # parse light fields
            file_m = re.search(r"\*\*File:\*\*\s*(.+)", chunk)
            reason_m = re.search(r"\*\*Reason:\*\*\s*(.+)", chunk)
            action_m = re.search(r"^## \[[^\]]+\]\s*(\S+)", chunk, re.M)
            matches.append({
                "journal_file": rel_j,
                "action": (action_m.group(1) if action_m else "").strip(),
                "file": (file_m.group(1).strip() if file_m else ""),
                "reason": (reason_m.group(1).strip() if reason_m else ""),
                "snippet": chunk[:500],
            })
            if len(matches) >= max_results:
                result["matches"] = matches
                return result

    result["matches"] = matches
    return result


def why_file(
    file: str,
    project_root: Optional[Union[str, Path]] = None,
    max_results: int = 10,
) -> Dict[str, Any]:
    """Recent semantic reasons for a file from journal + current health reason."""
    root = _root(project_root)
    rel = _rel_file(root, file)
    out: Dict[str, Any] = {
        "success": True,
        "project_root": str(root),
        "file": rel,
        "health_reason": None,
        "health_status": None,
        "journal_matches": [],
    }
    try:
        health_mod = _health_module()
        data = health_mod.load_health(root)
        ent = (data.get("entries") or {}).get(rel) or {}
        out["health_status"] = ent.get("status")
        out["health_reason"] = ent.get("reason")
        out["source_content_hash"] = ent.get("source_content_hash")
    except Exception as e:
        out["health_error"] = str(e)
    j = search_journal(project_root=root, file=rel, max_results=max_results)
    out["journal_matches"] = j.get("matches") or []
    return out


# ---------------------------------------------------------------------------
# Preflight / prepare_edit
# ---------------------------------------------------------------------------

def prepare_edit(
    file: str,
    project_root: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Single-file preflight: status, wiki, deps, dependents, cycle/ACS flags."""
    root = _root(project_root)
    rel = _rel_file(root, file)
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
    # Missing path: structured failure (agents must not treat empty preflight as OK)
    src_path = root / rel
    if not src_path.is_file() and not Path(file).is_file():
        out["success"] = False
        out["error"] = f"file not found: {rel}"
        out["next_step"] = "Pass an existing project-relative source path"
        # Still attach health/cache if present (ghost / deleted) for impact analysis
        try:
            health_mod = _health_module()
            data = health_mod.load_health(root)
            ent = (data.get("entries") or {}).get(rel) or {}
            if ent:
                out["status"] = ent.get("status")
                out["reason"] = ent.get("reason")
                out["ghost"] = True
        except Exception:
            pass
        return out
    try:
        health_mod = _health_module()
        data = health_mod.load_health(root)
        ent = (data.get("entries") or {}).get(rel) or {}
        out["status"] = ent.get("status")
        out["reason"] = ent.get("reason")
        out["source_content_hash"] = ent.get("source_content_hash")
        # wiki body (best-effort)
        wiki_path = None
        for cand in (
            root / f"{rel}.wiki.md",
            root / rel.replace(".py", ".py.wiki.md"),
            (root / Path(rel).name).with_suffix(Path(rel).suffix + ".wiki.md") if Path(rel).suffix else None,
        ):
            if cand and cand.is_file():
                wiki_path = cand
                break
        # also search common patterns under package
        if wiki_path is None:
            try:
                p = root / rel
                sibling = p.with_name(p.name + ".wiki.md")
                if sibling.is_file():
                    wiki_path = sibling
            except Exception:
                pass
        if wiki_path and wiki_path.is_file():
            try:
                body = wiki_path.read_text(encoding="utf-8", errors="replace")
                out["wiki"] = body[:4000]
                out["wiki_path"] = str(wiki_path.relative_to(root))
            except Exception:
                pass
    except Exception as e:
        out["health_error"] = str(e)

    try:
        from . import import_cache as ic
        cache = ic.load_cache(root) or {}
        entry = cache.get(rel) or {}
        pairs = entry.get("resolved_pairs") or []
        deps = []
        low = 0
        for p in pairs:
            if not isinstance(p, dict):
                continue
            sc = p.get("confidence_score")
            try:
                if sc is not None and float(sc) < 0.65:
                    if not ic._edge_is_non_actionable_noise(p):
                        low += 1
            except Exception:
                pass
            deps.append({
                "raw": p.get("raw") or p.get("module") or p.get("raw_module"),
                "resolved_path": p.get("resolved_path"),
                "confidence_score": p.get("confidence_score"),
            })
        out["dependencies"] = deps[:80]
        out["low_conf_edges"] = low
        out["dependents"] = resolve_dependents_from_cache(cache, rel)
        cycles = cache.get("_cycles") or {}
        all_cyc = set(cycles.get("all_cycle_files") or [])
        out["in_cycle"] = rel in all_cyc
    except Exception as e:
        out["cache_error"] = str(e)

    why = why_file(rel, project_root=root, max_results=5)
    out["recent_why"] = why.get("journal_matches") or []
    return out


# ---------------------------------------------------------------------------
# Session bootstrap
# ---------------------------------------------------------------------------

def session_bootstrap(
    project_root: Optional[Union[str, Path]] = None,
    directory: Optional[str] = None,
    max_attention_files: int = 15,
) -> Dict[str, Any]:
    """One-shot agent session start snapshot (Core daily surface)."""
    root = _root(project_root)
    out: Dict[str, Any] = {
        "success": True,
        "project_root": str(root),
        "core_surface": list(CORE_DAILY_NAMES),
        "core_daily": list(CORE_DAILY_TOOLS),
        "core_count": len(CORE_DAILY_NAMES),
        "advanced_intel": list(ADVANCED_INTEL_TOOLS),
    }
    health_sum: Dict[str, Any] = {}
    red_files: List[str] = []
    yellow_files: List[str] = []
    actionable_yellow_files: List[str] = []

    try:
        health_mod = _health_module()
        health_sum = health_mod.get_summary(root, directory) or {}
        out["health_summary"] = health_sum
        out["health_score"] = health_sum.get("health_score")
        data = health_mod.load_health(root)
        entries = data.get("entries") or {}
        for f, e in entries.items():
            if directory and not str(f).startswith(directory.rstrip("/") + "/") and str(f) != directory.rstrip("/"):
                continue
            st = str((e or {}).get("status") or "")
            reason = str((e or {}).get("reason") or "")
            if "Red" in st or "🔴" in st:
                red_files.append(f)
            elif "Yellow" in st or "🟡" in st:
                yellow_files.append(f)
                if "Initial stub" not in reason and "stub" not in reason.lower()[:20]:
                    # heuristic: non-stub yellows are actionable
                    if "Initial stub" not in reason:
                        actionable_yellow_files.append(f)
                if "Initial stub" not in reason:
                    if f not in actionable_yellow_files:
                        # already handled
                        pass
        # Prefer health module classifier if available
        if hasattr(health_mod, "get_files_needing_attention"):
            try:
                # may not exist — use manual lists
                pass
            except Exception:
                pass
        # Re-classify actionable: not Initial stub
        actionable_yellow_files = [
            f for f in yellow_files
            if "Initial stub" not in str((entries.get(f) or {}).get("reason") or "")
        ]
        out["attention"] = {
            "red": red_files[:max_attention_files],
            "actionable_yellow": actionable_yellow_files[:max_attention_files],
            "yellow_total": len(yellow_files),
            "red_total": len(red_files),
            "stub_yellow": int(health_sum.get("stub_yellow") or 0),
            "actionable_yellow_count": int(health_sum.get("actionable_yellow") or len(actionable_yellow_files)),
        }
        if hasattr(health_mod, "assess_autonomous_readiness"):
            ready = health_mod.assess_autonomous_readiness(root, write_metrics=False)
            out["readiness"] = ready.get("readiness")
            out["scope"] = ready.get("scope")
            out["blockers"] = ready.get("blockers") or []
        elif hasattr(health_mod, "detect_scope_risks"):
            out["scope"] = health_mod.detect_scope_risks(root)
    except Exception as e:
        out["health_error"] = str(e)

    acs_actionable = 0
    try:
        from . import import_cache as ic
        try:
            from . import cache_store as cs
        except Exception:
            cs = None  # type: ignore
        # Prefer light meta read (SQLite) over full multi-MB pair deserialize
        acs: Dict[str, Any] = {}
        cyc: Dict[str, Any] = {}
        if cs is not None:
            meta = cs.load_meta(root, keys=("_acs_summary", "_cycles", "_map_coverage"))
            acs = meta.get("_acs_summary") if isinstance(meta.get("_acs_summary"), dict) else {}
            cyc = meta.get("_cycles") if isinstance(meta.get("_cycles"), dict) else {}
            cov = meta.get("_map_coverage") if isinstance(meta.get("_map_coverage"), dict) else {}
            if cov:
                out["map_coverage"] = cov
            out["cache_backend"] = cs.backend_name(root)
        needs_full = (
            not acs
            or str(acs.get("acs_version") or "") < "1.3"
            or "reason_code_counts" not in acs
            or "actionable_low_conf_edges" not in acs
        )
        if needs_full:
            cache = ic.load_cache(root) or {}
            acs = ic.ensure_acs_summary_persisted(cache, root) or {}
            cyc = cache.get("_cycles") or {}
            if cs is not None and not out.get("cache_backend"):
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
        # Agents must not thrash on raw low_conf_edges (ACS v1.3 scores more edges)
        out["acs_guidance"] = (
            "Prefer actionable_low_conf_edges + reason_code_counts "
            "(skip external_or_bare/dynamic_literal); do not use low_conf_edges alone as a work queue."
        )
        out["cycles"] = {
            "cyclic_scc_count": (cyc.get("stats") or {}).get("cyclic_scc_count"),
            "all_cycle_files_sample": (cyc.get("all_cycle_files") or [])[:10],
        }
        if "map_coverage" not in out and cs is not None:
            snap = cs.get_map_coverage_from_meta(root)
            if snap.get("map_coverage"):
                out["map_coverage"] = snap["map_coverage"]
    except Exception as e:
        out["acs_error"] = str(e)

    red_n = int(health_sum.get("red") or len(red_files) or 0)
    action_y = int(health_sum.get("actionable_yellow") or len(actionable_yellow_files) or 0)
    stub_y = int(health_sum.get("stub_yellow") or 0)
    clean = red_n == 0 and int(health_sum.get("yellow") or 0) == 0
    scope_warnings = []
    if isinstance(out.get("scope"), dict):
        scope_warnings = list(out["scope"].get("warnings") or [])

    map_cov = out.get("map_coverage") if isinstance(out.get("map_coverage"), dict) else {}
    blockers = list(out.get("blockers") or [])
    out["actions"] = build_structured_actions(
        red_files=red_files,
        actionable_yellow_files=actionable_yellow_files,
        stub_yellow=stub_y,
        actionable_yellow=action_y,
        red=red_n,
        acs_actionable=acs_actionable,
        scope_warnings=scope_warnings,
        blockers=blockers,
        clean=clean,
        map_coverage=map_cov,
    )
    out["work_items"] = out["actions"]  # alias
    out["selective_work"] = True
    out["map_first"] = True
    rem = int(map_cov.get("files_remaining_dirty") or 0) if map_cov else 0
    readiness = out.get("readiness") or "unknown"
    map_incomplete = rem > 0 or map_cov.get("complete") is False
    # G2: never claim "ready" when readiness is blocked
    if readiness == "blocked":
        out["message"] = (
            f"session_bootstrap readiness=blocked — fix actions[] / blockers[] first "
            f"(typically fix_scope + update_maps / seed_health); do not treat project as map-ready."
            + (
                f" MAP INCOMPLETE: files_remaining_dirty={rem}."
                if map_incomplete
                else ""
            )
        )
    elif readiness == "map_ok_scope_risk":
        out["message"] = (
            f"session_bootstrap readiness=map_ok_scope_risk — map/health present but scope risk "
            f"(often bare '.' monitor); fix_scope before unattended daemon. "
            f"Use actions[] / attention; prepare_edit(file) before large edits; record_change after."
            + (
                f" MAP INCOMPLETE: files_remaining_dirty={rem} — re-run update_maps until "
                f"map_coverage.complete=true."
                if map_incomplete
                else ""
            )
        )
    elif readiness == "ready_for_daemon":
        out["message"] = (
            "session_bootstrap readiness=ready_for_daemon — use actions[] / attention; "
            "prepare_edit(file) before large edits; record_change after edits."
            + (
                f" MAP INCOMPLETE: files_remaining_dirty={rem} — re-run update_maps until "
                f"map_coverage.complete=true (success alone is not map-ready)."
                if map_incomplete
                else ""
            )
        )
    else:
        out["message"] = (
            f"session_bootstrap readiness={readiness} — use actions[] / attention; "
            "prepare_edit(file) before large edits; record_change after edits. "
            "Unattended ops require readiness=ready_for_daemon (not Map Ready alone)."
            + (
                f" MAP INCOMPLETE: files_remaining_dirty={rem} — re-run update_maps until complete."
                if map_incomplete
                else ""
            )
        )
    return out
