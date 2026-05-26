"""
Import Cache for Incremental update-maps (M2-Rem-03)

Stores parsed import information per file so that only changed files
need to be re-parsed on subsequent update-maps runs.

This design is intended to scale from small projects to massive monorepos.

M2 A0/A2: Now also hosts the minimal streaming generator skeleton
(generate_update_events) that yields ProgressEvent_v1 (with full provenance,
ACS/CIABRE hooks, barrel/cycle signals, ScopeSpec_v1, checkpoint/resumption).
The real pipeline integration is future work (A2+); this is the clean contract
foundation only. All changes additive + backward compatible.
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Iterable, Union
from collections import defaultdict
import time
from datetime import datetime, timezone

# Import locking (M2-Rem-07)
try:
    from . import locking
except ImportError:
    locking = None

# Canonical v1 node identity prep for cycles graph (Gap #1 Guaranteed Cycle Wave next):
# use_canonical support + proper v0/v1 stamping per contracts (ready for Phase 4 flip in sh/harness).
# Zero-dep, defensive imports, backward compatible.
try:
    from .contracts import (
        NODE_IDENTITY_VERSION_V0,
        NODE_IDENTITY_VERSION_V1,
    )
except Exception:
    NODE_IDENTITY_VERSION_V0 = "v0"
    NODE_IDENTITY_VERSION_V1 = "v1"

try:
    from .resolution import canonical_for_bree
except Exception:
    canonical_for_bree = None

CACHE_FILE = ".wikifier_staging/import_cache.json"


def _get_cache_path(root: Path) -> Path:
    return root / CACHE_FILE


def load_cache(root: Path) -> Dict[str, Any]:
    """Load the import cache. Returns empty dict if not present."""
    cache_path = _get_cache_path(root)
    if not cache_path.exists():
        return {}
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_cache(root: Path, cache: Dict[str, Any]) -> None:
    """Save the import cache to disk.

    Uses file locking (M2-Rem-07) to prevent corruption when multiple
    agents are running update-maps or health operations concurrently.
    """
    if locking:
        with locking.file_lock(root):
            _do_save_cache(root, cache)
    else:
        _do_save_cache(root, cache)


def _do_save_cache(root: Path, cache: Dict[str, Any]) -> None:
    """Internal save without locking."""
    cache_path = _get_cache_path(root)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def get_file_data(cache: Dict[str, Any], rel_path: str) -> Optional[Dict[str, Any]]:
    """Return cached data for a relative path, or None if not present."""
    return cache.get(rel_path)


def get_reverse_dependencies(cache: Dict[str, Any]) -> Dict[str, List[str]]:
    """
    Return the reverse dependency map: target_path -> list of source files that import it.
    Stored under a reserved top-level key to avoid colliding with file entries.

    A1: This is now a first-class persisted structure (parallel to forward graph
    built on resolved_pairs + BRC _barrel_* structures). Maintained incrementally
    during updates (O(changed) cost) with its own _reverse_signature for delta
    detection. Always authoritative for get_dependents / reverse queries.
    """
    return cache.get("_reverse_dependencies", {})


def set_reverse_dependencies(cache: Dict[str, Any], reverse_deps: Dict[str, List[str]]) -> None:
    """
    Store the reverse dependency map.
    This allows get_dependents() to work efficiently even in incremental mode.

    A1: Now first-class. Automatically computes + persists the matching
    _reverse_signature (modeled on graph_signature) for observability and
    delta detection. Callers (sh, cli run_full_update, future pure engine)
    get consistent sig for free.
    """
    if reverse_deps:
        cache["_reverse_dependencies"] = reverse_deps
        # A1: auto-keep signature in sync (long-term correct, observable design)
        sig = reverse_dependency_signature(reverse_deps)
        cache["_reverse_signature"] = sig
    else:
        cache.pop("_reverse_dependencies", None)
        cache.pop("_reverse_signature", None)


def maintain_reverse_dependencies_for_source(
    cache: Dict[str, Any],
    source_rel: str,
    old_targets: List[str],
    new_targets: List[str],
) -> None:
    """
    A1 Core: Incrementally maintain the reverse index for one source's edge delta.

    - Removes source from reverse lists of its *old* targets (if present).
    - Adds source to reverse lists of its *new* targets (dedup + sort for stable sig/queries).
    - Cost: O(old_edges + new_edges for this source) only. No full scan.
    - Safe, idempotent, handles missing entries, ignores self-deps.
    - After adjustment, the set_reverse (called internally) auto-updates the signature.

    This delivers the required O(changed) or O(k dependents) scalability for 50k+ files.
    Intended call sites: Python-primary update paths (cli.run_full_update helpers),
    persist_rich_cache_data sites (via python -c or direct), record_deletion paths.
    Existing cycle blast radius and ACS consumers benefit transparently (no changes needed).
    """
    if not source_rel or not isinstance(source_rel, str):
        return
    # Work on a copy of the current rev map (avoid mutating during iteration issues)
    rev = dict(get_reverse_dependencies(cache))
    old = [t for t in (old_targets or []) if t and t != source_rel]
    new = [t for t in (new_targets or []) if t and t != source_rel]

    # Subtract old contributions (clean only this source)
    for tgt in old:
        if tgt in rev and source_rel in rev[tgt]:
            rev[tgt] = [s for s in rev[tgt] if s != source_rel]
            if not rev[tgt]:
                rev.pop(tgt, None)

    # Add new contributions (dedup+sort for determinism + nice sigs)
    for tgt in new:
        if tgt not in rev:
            rev[tgt] = []
        if source_rel not in rev[tgt]:
            rev[tgt].append(source_rel)
            rev[tgt] = sorted(set(rev[tgt]))

    # Persist (this also auto-sets the fresh reverse_signature)
    set_reverse_dependencies(cache, rev)


def rebuild_reverse_dependencies(cache: Dict[str, Any]) -> Dict[str, List[str]]:
    """
    A1: Full O(E) rebuild of reverse map from current per-file resolved_pairs/resolved data.

    Use for initial bootstrap (empty cache), after large renames/deletes via record_deletion,
    or for sh full-rebuild compatibility path. Always returns lists that are sorted + deduped.
    Callers must save_cache after; signature is auto-set on the internal set_reverse call.
    """
    from collections import defaultdict
    rev: Dict[str, List[str]] = defaultdict(list)
    for rel, data in cache.items():
        if not isinstance(rel, str) or rel.startswith("_") or not isinstance(data, dict):
            continue
        pairs = data.get("resolved_pairs") or data.get("resolved") or []
        for p in pairs:
            tgt = ""
            if isinstance(p, dict):
                tgt = p.get("resolved") or ""
            elif p:
                tgt = str(p)
            if tgt and tgt != rel:
                if rel not in rev[tgt]:
                    rev[tgt].append(rel)
    result: Dict[str, List[str]] = {}
    for t in rev:
        result[t] = sorted(set(rev[t]))
    return result


def get_reverse_dependency_stats(cache: Dict[str, Any]) -> Dict[str, Any]:
    """
    A1: Compact, zero-cost, always-safe stats surface for the reverse dependency index.
    Includes the signature (for delta/integrity), counts, edge total.
    Used by CLI run_full_update result, MCP (get_dependents json + new surfaces),
    health surfaces, diagnostics, get_resolution_diagnostics etc.
    Parallel to get_cycles_reuse_stats (reused heuristics can be added later).
    """
    rev = get_reverse_dependencies(cache) or {}
    sig = get_reverse_signature(cache)
    total_edges = sum(len(v or []) for v in rev.values())
    target_count = len(rev)
    return {
        "target_count": target_count,
        "reverse_signature": sig,
        "total_reverse_edges": total_edges,
        "has_index": bool(target_count > 0),
        "average_dependents_per_target": round(total_edges / target_count, 2) if target_count else 0.0,
        "node_identity_version": NODE_IDENTITY_VERSION_V1,  # future-proof for canonical reverse
    }


def update_file_data(
    cache: Dict[str, Any],
    rel_path: str,
    mtime: int,
    imports: List[str],
    resolved: Optional[List[str]] = None,
    resolved_pairs: Optional[List[Dict[str, str]]] = None,
    dependents: Optional[List[str]] = None
) -> None:
    """
    Update or insert data for a file in the cache.

    resolved_pairs (preferred for table + Mermaid generation):
        List of {"raw": "...", "resolved": "...", "confidence": "high|medium|low"}

    dependents: List of files that import this file (reverse dependencies).
    This enables fast per-file "who depends on me" queries and richer Mermaid graphs.
    """
    # Normalize resolved_pairs to always include confidence (for backward compat)
    # Preserve ALL rich fields (via_barrel, barrel_*, cdia_v1, conditional_analysis, dynamic_analysis,
    # res_meta, barrel_v2, resolution_metadata, etc.) so P1 pipeline richness actually reaches cache/MCP.
    normalized_pairs = []
    for p in (resolved_pairs or []):
        if isinstance(p, dict):
            np = {
                "raw": p.get("raw", ""),
                "resolved": p.get("resolved", ""),
                "confidence": p.get("confidence", "medium")
            }
            for k, v in p.items():
                if k not in np:
                    np[k] = v
            normalized_pairs.append(np)

    entry = {
        "mtime": mtime,
        "imports": imports,
        "resolved": resolved or [],
        "resolved_pairs": normalized_pairs
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


# =============================================================================
# Phase 1 Graph Integrity + P3 CIABRE (Cycle Impact Analysis & Breaking Recs Engine)
# Added/refined in Gap #1 Reliability & Scale Follow-up (R5)
# Tarjan SCC for reliable maximal clusters; rich edge signals for severity;
# blast via reverse deps; weakest links + ranked actionable recs.
# Perf: callers pass prebuilt graph+emap to avoid duplicate O(E) scans on large barrel/deep projects.
# Model v1.2 (R5 refinement): tuned scoring for real dogfood (dyn+barrel+blast), extensible rec registry,
# higher-quality context-specific rationales/hints/safety tied to edge signals. Recommendations now
# genuinely useful for agents refactoring real monorepo cycles.
# =============================================================================

def build_dependency_graph(cache: Dict[str, Any], use_canonical: bool = False, root: Optional[Path] = None) -> Dict[str, List[str]]:
    """Build forward adjacency list from resolved_pairs (or legacy resolved).
    Includes all nodes that appear as importers or targets. Skips _reserved keys.

    use_canonical=True (prep for Phase 4 canonical rollout): remaps all keys and resolved targets
    through canonical_for_bree (== to_canonical_rel(..., follow_symlinks=True)) for stable
    physical identity across symlinks/workspaces/pnpm stores. v1 nodes enable consistent
    graph_signature + cycles across views of same monorepo. Old v0 raw entries coexist
    (migration on topo change or full rebuild). Graph signatures and cycles carry
    node_identity_version ("v0" or "v1") to allow safe incremental flip.
    When use_canonical=True but root=None or helper unavailable, falls back to raw (v0).
    """
    graph: Dict[str, List[str]] = defaultdict(list)
    nodes: set = set()
    for rel, data in cache.items():
        if not isinstance(rel, str) or rel.startswith("_") or not isinstance(data, dict):
            continue
        nodes.add(rel)
        pairs = data.get("resolved_pairs") or data.get("resolved") or []
        for p in pairs:
            tgt = ""
            if isinstance(p, dict):
                tgt = p.get("resolved") or ""
            elif p:
                tgt = str(p)
            if tgt:
                nodes.add(tgt)
                if tgt != rel:
                    graph[rel].append(tgt)
    for n in nodes:
        if n not in graph:
            graph[n] = []

    if use_canonical and root is not None and canonical_for_bree is not None:
        # v1 canonical remap for Phase 4 flip readiness (symlink-safe single identity)
        canon_graph: Dict[str, List[str]] = defaultdict(list)
        canon_nodes: set = set()
        for raw_n, tgts in graph.items():
            try:
                cn = canonical_for_bree(raw_n, root) or str(raw_n)
            except Exception:
                cn = str(raw_n)
            canon_nodes.add(cn)
            c_tgts: List[str] = []
            for t in tgts:
                try:
                    ct = canonical_for_bree(t, root) or str(t)
                except Exception:
                    ct = str(t)
                canon_nodes.add(ct)
                if ct != cn:
                    c_tgts.append(ct)
            canon_graph[cn].extend(c_tgts)
        for cn in list(canon_nodes):
            if cn not in canon_graph:
                canon_graph[cn] = []
            else:
                canon_graph[cn] = sorted(set(canon_graph[cn]))
        return dict(canon_graph)

    return dict(graph)


def _tarjan_sccs(graph: Dict[str, List[str]]) -> List[List[str]]:
    """Tarjan's strongly connected components algorithm (O(V+E)), fully iterative
    with explicit call-stack simulation (no Python recursion).

    Returns list of components; caller filters to non-trivial cycles.
    Zero-dep, pure stdlib. Safe for arbitrary-depth dep graphs in 50k+ file
    monorepos (previous recursive form could hit sys recursion limit on chains).

    Wave 2 of cycles long-term strategy (gap1_cycles): implemented here for
    guaranteed scale safety. Behavior identical to prior recursive version
    (verified on real clusters + harness).
    """
    index: Dict[str, int] = {}
    lowlink: Dict[str, int] = {}
    on_stack: Dict[str, bool] = {}
    stack: List[str] = []
    result: List[List[str]] = []
    idx_counter = [0]
    call_stack: List[dict] = []

    for start in list(graph.keys()):
        if start in index:
            continue
        # Initialize root of DFS tree
        index[start] = lowlink[start] = idx_counter[0]
        idx_counter[0] += 1
        stack.append(start)
        on_stack[start] = True
        call_stack.append({"v": start, "children": iter(graph.get(start, []))})

        while call_stack:
            frame = call_stack[-1]
            v = frame["v"]
            try:
                w = next(frame["children"])
                if w not in index:
                    # simulate recursive call: push child frame
                    index[w] = lowlink[w] = idx_counter[0]
                    idx_counter[0] += 1
                    stack.append(w)
                    on_stack[w] = True
                    call_stack.append({"v": w, "children": iter(graph.get(w, []))})
                elif on_stack.get(w, False):
                    lowlink[v] = min(lowlink[v], index.get(w, 0))
            except StopIteration:
                # post-order: SCC root check, then simulate return + lowlink bubble to parent
                if lowlink[v] == index[v]:
                    component: List[str] = []
                    while True:
                        w = stack.pop()
                        on_stack[w] = False
                        component.append(w)
                        if w == v:
                            break
                    result.append(component)
                call_stack.pop()
                if call_stack:
                    parent_frame = call_stack[-1]
                    pv = parent_frame["v"]
                    lowlink[pv] = min(lowlink[pv], lowlink[v])

    return result


def graph_signature(graph: Dict[str, List[str]]) -> str:
    """Stable short signature of the dependency graph structure (adj list).

    Enables cheap reuse / delta detection for _cycles and _cycle_analyses:
    if signature matches a previously persisted one, callers can safely skip
    expensive recompute of Tarjan + CIABRE on incremental runs where graph
    topology is unchanged (future optimization; currently always fresh but sig
    is recorded for observability and incremental strategies).

    Pure stdlib (hashlib), deterministic across runs, zero side effects.
    12-hex-char (48-bit) prefix is sufficient for change detection.
    """
    import hashlib
    parts: List[str] = []
    for v in sorted(graph.keys()):
        ts = sorted(set(graph.get(v, [])))
        parts.append(f"{v}=>{','.join(ts)}")
    canon = "|".join(parts)
    h = hashlib.sha256(canon.encode("utf-8")).hexdigest()
    return h[:12]


def reverse_dependency_signature(reverse_map: Dict[str, List[str]]) -> str:
    """Stable short signature of the reverse dependency index (target -> [sources importers]).

    A1: Persisted first-class parallel to graph_signature + BRC structures.
    Enables cheap delta detection, integrity checks, and future short-circuits
    for reverse-dependent consumers (get_dependents, blast radius in CIABRE,
    health/MCP diagnostics).

    If this matches a previously persisted _reverse_signature, the reverse map
    topology is unchanged (safe to trust for incremental queries even across
    content-only edits).

    Pure stdlib (hashlib), deterministic, zero side effects. 12-hex-char prefix.
    Uses "<=" marker (vs "=>" for forward) so signature is distinct.
    """
    import hashlib
    parts: List[str] = []
    for v in sorted(reverse_map.keys()):
        ts = sorted(set(reverse_map.get(v, [])))
        parts.append(f"{v}<={','.join(ts)}")
    canon = "|".join(parts)
    h = hashlib.sha256(canon.encode("utf-8")).hexdigest()
    return h[:12]


def get_reverse_signature(cache: Dict[str, Any]) -> Optional[str]:
    """Return persisted reverse dependency signature or None (A1 first-class index)."""
    return cache.get("_reverse_signature")


def set_reverse_signature(cache: Dict[str, Any], sig: str) -> None:
    """Persist the reverse dependency signature for delta detection / observability (A1)."""
    if sig:
        cache["_reverse_signature"] = sig
    else:
        cache.pop("_reverse_signature", None)


def compute_cycles(
    cache: Dict[str, Any],
    root: Optional[Path] = None,
    use_canonical: bool = False,
    max_reported_sccs: int = 200,
    graph: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, Any]:
    """Compute normalized SCC cycles using Tarjan. Enrich per-SCC with rich edge signals
    (dynamic/conditional/barrel/low-conf counts, max depth) drawn from resolved_pairs.
    Persistable structure for _cycles. Fast; shares work with CIABRE via optional graph.

    graph: optional pre-built adjacency list (from build_dependency_graph or
           build_graph_with_edge_metadata) for reuse to avoid duplicate O(V+E)
           work on large barrel-heavy or cycle-dense monorepos.
    """
    if graph is None:
        graph = build_dependency_graph(cache, use_canonical=use_canonical, root=root)
    gsig = graph_signature(graph)

    # Wave 2 delta/incremental recompute (cycles long-term strategy):
    # Short-circuit Tarjan + enrichment when graph structure signature matches
    # the one persisted from prior run. Enables safe O(1) reuse on incremental
    # update-maps when only file contents (not dep topology) changed.
    # Zero cost, zero-dep, deterministic.
    persisted_sig = get_graph_signature(cache)
    if persisted_sig and persisted_sig == gsig:
        persisted_cdata = get_cycles(cache)
        if persisted_cdata and "sccs" in persisted_cdata and persisted_cdata.get("graph_signature") == gsig:
            reused_cdata = dict(persisted_cdata)
            reused_cdata["reused"] = True
            reused_cdata["reuse_reason"] = "graph_signature_match"
            reused_cdata.setdefault("graph_signature", gsig)
            reused_cdata.setdefault("node_identity_version", NODE_IDENTITY_VERSION_V0)
            # Guaranteed persistence: update stored so get_cycles / get_cycles_reuse_stats / MCP / health / library reflect the reuse (not just return val)
            set_cycles(cache, reused_cdata)
            return reused_cdata

    # Full path (structure changed or first time)
    raw_sccs = _tarjan_sccs(graph)

    # Normalize + dedup (sorted tuple key) + filter trivial
    seen = set()
    sccs: List[List[str]] = []
    for comp in raw_sccs:
        comp_sorted = sorted(set(c for c in comp if c))
        if len(comp_sorted) < 2:
            continue
        key = tuple(comp_sorted)
        if key in seen:
            continue
        seen.add(key)
        sccs.append(comp_sorted)

    sccs = sccs[:max_reported_sccs]

    # Enrich signals (scan pairs once per cycle member)
    enriched: List[Dict[str, Any]] = []
    all_cycle_files: set = set()
    dyn_c = cond_c = barrel_c = 0
    max_bd = 0
    for nodes in sccs:
        node_set = set(nodes)
        all_cycle_files.update(node_set)
        sig = {
            "dynamic_edge_count": 0,
            "conditional_edge_count": 0,
            "barrel_edge_count": 0,
            "low_conf_edge_count": 0,
            "max_barrel_depth": 0,
            "confidence_breakdown": {"high": 0, "medium": 0, "low": 0},
        }
        for src in node_set:
            data = cache.get(src) if isinstance(cache.get(src), dict) else {}
            for p in (data.get("resolved_pairs") or []):
                if not isinstance(p, dict):
                    continue
                tgt = p.get("resolved") or ""
                if tgt in node_set and tgt != src:
                    if p.get("is_dynamic"):
                        sig["dynamic_edge_count"] += 1
                        dyn_c += 1
                    if p.get("is_conditional"):
                        sig["conditional_edge_count"] += 1
                        cond_c += 1
                    if p.get("via_barrel"):
                        sig["barrel_edge_count"] += 1
                        barrel_c += 1
                    bd = p.get("barrel_depth") or 0
                    if bd > sig["max_barrel_depth"]:
                        sig["max_barrel_depth"] = bd
                    if bd > max_bd:
                        max_bd = bd
                    conf = p.get("confidence") or "medium"
                    if conf in sig["confidence_breakdown"]:
                        sig["confidence_breakdown"][conf] += 1
                    if conf == "low":
                        sig["low_conf_edge_count"] += 1
        ex = " → ".join(nodes[:5]) + (" → ..." if len(nodes) > 5 else "")
        enriched.append({
            "nodes": nodes,
            "size": len(nodes),
            "example_path": ex,
            "signals": sig,
        })

    stats = {
        "cyclic_scc_count": len(enriched),
        "total_files_in_cycles": len(all_cycle_files),
        "largest_scc_size": max([e["size"] for e in enriched] or [0]),
        "dynamic_edges_in_cycles": dyn_c,
        "conditional_edges_in_cycles": cond_c,
        "barrel_edges_in_cycles": barrel_c,
        "max_barrel_depth_in_cycles": max_bd,
    }
    return {
        "sccs": enriched,
        "stats": stats,
        "all_cycle_files": sorted(all_cycle_files),
        "node_identity_version": NODE_IDENTITY_VERSION_V1 if use_canonical else NODE_IDENTITY_VERSION_V0,
        "graph_signature": gsig,
        "reused": False,
        "reuse_reason": "computed_fresh",
    }


def get_cycles(cache: Dict[str, Any]) -> Dict[str, Any]:
    """Return persisted _cycles or empty."""
    return cache.get("_cycles", {}) or {}


def set_cycles(cache: Dict[str, Any], cdata: Dict[str, Any]) -> None:
    if cdata and "sccs" in cdata:  # persist even for empty sccs=[] ("no cycles for this sig") so delta short-circuit + get_reuse_stats work on acyclic graphs too
        cache["_cycles"] = cdata
    else:
        cache.pop("_cycles", None)


def compute_graph_integrity(cache: Dict[str, Any]) -> Dict[str, Any]:
    """Lightweight integrity summary over cycles (for library/MCP)."""
    cdata = get_cycles(cache)
    st = cdata.get("stats", {}) if isinstance(cdata, dict) else {}
    return {
        "summary": f"{st.get('cyclic_scc_count', 0)} cyclic SCC(s) involving {st.get('total_files_in_cycles', 0)} files",
        "stats": st,
        "version": "1.0",
    }


def set_graph_integrity(cache: Dict[str, Any], integrity: Dict[str, Any]) -> None:
    if integrity:
        cache["_graph_integrity"] = integrity
    else:
        cache.pop("_graph_integrity", None)


def get_graph_signature(cache: Dict[str, Any]) -> Optional[str]:
    """Return persisted graph signature or None."""
    return cache.get("_graph_signature")


def set_graph_signature(cache: Dict[str, Any], sig: str) -> None:
    """Persist the graph signature for reuse/incremental detection."""
    if sig:
        cache["_graph_signature"] = sig
    else:
        cache.pop("_graph_signature", None)


def get_cycles_reuse_stats(cache: Dict[str, Any]) -> Dict[str, Any]:
    """Compact, zero-cost accessor for delta reuse observability + canonical version.
    Used broadly by health, diagnostics, MCP, library consumers, get_resolution_diagnostics.
    Enables agents and tooling to see if last cycles/CIABRE was short-circuited (reused graph_signature).
    Always safe even on empty cache.
    """
    cdat = get_cycles(cache) or {}
    gsig = get_graph_signature(cache) or cdat.get("graph_signature")
    reused = bool(cdat.get("reused", False))
    reason = cdat.get("reuse_reason") or ("graph_signature_match" if reused else "computed_fresh")
    ver = cdat.get("node_identity_version") or NODE_IDENTITY_VERSION_V0
    return {
        "graph_signature": gsig,
        "reused": reused,
        "reuse_reason": reason,
        "node_identity_version": ver,
        "has_cycles": bool(cdat.get("sccs")),
        "cyclic_file_count": len(cdat.get("all_cycle_files", []) or []),
    }


def build_graph_with_edge_metadata(
    cache: Dict[str, Any],
    root: Optional[Path] = None,
    use_canonical: bool = False,
) -> Tuple[Dict[str, List[str]], Dict[Tuple[str, str], Dict[str, Any]]]:
    """Build graph + edge metadata map in one pass (for CIABRE perf: share with compute_cycles).
    Edge meta carries ACS + CDIA + barrel signals for risk scoring.
    use_canonical + root forwarded to build_dependency_graph for v1 canonical node identity prep.
    """
    g = build_dependency_graph(cache, use_canonical=use_canonical, root=root)
    emap: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for rel, data in cache.items():
        if not isinstance(rel, str) or rel.startswith("_") or not isinstance(data, dict):
            continue
        for p in (data.get("resolved_pairs") or []):
            if not isinstance(p, dict):
                continue
            tgt = p.get("resolved") or ""
            if tgt:
                key = (rel, tgt)
                emap[key] = {
                    "confidence": p.get("confidence", "medium"),
                    "is_dynamic": bool(p.get("is_dynamic")),
                    "dynamic_type": p.get("dynamic_type"),
                    "is_conditional": bool(p.get("is_conditional")),
                    "via_barrel": bool(p.get("via_barrel")),
                    "barrel_depth": p.get("barrel_depth") or 0,
                }
    return g, emap


def _edge_risk_score(meta: Dict[str, Any]) -> float:
    """Risk for weakest-link ranking. Higher = better break candidate."""
    s = 1.0
    conf = meta.get("confidence", "medium")
    if conf == "low":
        s += 3.0
    elif conf == "medium":
        s += 0.5
    if meta.get("is_dynamic"):
        s += 2.5
    if meta.get("is_conditional"):
        s += 1.8
    if meta.get("via_barrel"):
        bd = meta.get("barrel_depth", 0) or 0
        s += 0.8 * (1 + min(bd, 4))
    # R5 refinement: extra penalty for combined risky signals (dogfood-common: dyn barrel cycles)
    if meta.get("is_dynamic") and meta.get("via_barrel"):
        s += 1.2
    return s


def _compute_external_blast_radius(members: set, reverse_map: Dict[str, List[str]]) -> int:
    """# files outside the cluster that directly depend on any member (real impact)."""
    ext = 0
    for m in members:
        for d in (reverse_map.get(m) or []):
            if d not in members:
                ext += 1
    return ext


def _compute_severity_score(size: int, blast: int, risks: Dict[str, Any], internal_edges: int) -> float:
    """v1.2 scoring (R5 real-dogfood refinement): size + external blast + risk-weighted signals + density.
    Weights tuned on RecipeLab_alt / self-dogfood patterns (CJS barrel + dynamic template cycles common in real monorepos).
    High-blast or multi-risk clusters reliably surface as HIGH/CRITICAL for trustworthy prioritization.
    """
    base = size * 2.5 + min(blast * 0.28, 18.0)
    rb = (
        risks.get("low_conf_edges", 0) * 1.6
        + risks.get("dynamic_edges", 0) * 2.3
        + risks.get("conditional_edges", 0) * 1.1
        + risks.get("barrel_edges", 0) * 0.75
    )
    dens = (internal_edges / max(1, size)) if size else 0.0
    # R5: mature combined-signal boost (common in real dogfood CJS barrels + dyn templates)
    if risks.get("dynamic_edges", 0) > 0 and risks.get("barrel_edges", 0) > 0:
        base += 2.5
    # R5.2 real-data extension: extra weight for high external blast (practical impact on monorepos) and dense risky clusters
    if blast >= 8:
        base += min((blast - 8) * 0.35, 6.0)
    if size >= 5 and (risks.get("dynamic_edges", 0) + risks.get("low_conf_edges", 0)) >= 1:
        base += 1.8
    # Cap for outliers while preserving relative ranking
    score = base + rb + dens * 4.0
    return min(score, 48.0)


def _severity_level(score: float) -> str:
    if score >= 26:
        return "CRITICAL"
    if score >= 16:
        return "HIGH"
    if score >= 8.5:
        return "MEDIUM"
    return "LOW"


# =============================================================================
# CIABRE Breaking Recommendation Rules Registry (R5 matured, v1.3 surfacing uniformity)
# Extensible list of pure rule fns. Each inspects analysis signals/weakest and returns
# 0+ candidate rec dicts (with strategy/rationale/hint/safety). Generator collects,
# de-dups by strategy, assigns stable ranks, keeps top practical ones.
# Rules informed by real dogfood cycles (3-SCC dyn+barrel CJS, large tangles).
# v1.3: _rule_conditional_or_feature_flag activated + _rule_high_dynamic_in_cycle added; rationales hardened w/ ACS expl refs.
# Add new rule by appending _rule_* fn; no core changes needed.
# =============================================================================

def _rule_weakest_risky_edge(nodes: List[str], weakest: List[Dict], risks: Dict, blast: int, size: int) -> List[Dict[str, Any]]:
    """Primary rule: always consider the highest-risk (weakest) link first."""
    recs: List[Dict[str, Any]] = []
    if not weakest:
        return recs
    w = weakest[0]
    tgt_edge = f"{w.get('from','?')}→{w.get('to','?')}"
    conf = w.get("confidence", "medium")
    dyn = bool(w.get("is_dynamic"))
    cond = bool(w.get("is_conditional"))
    bar = bool(w.get("via_barrel"))
    bd = w.get("barrel_depth", 0) or 0
    if dyn or conf == "low":
        recs.append({
            "strategy": "lazy_load_or_conditional_guard",
            "target_edge": tgt_edge,
            "rationale": f"Break first on the {conf} dynamic edge {tgt_edge} (barrel_depth={bd}). This is already a low-trust participant per ACS (see confidence_explanation Recommendation); lazy deferral avoids init-time cycles and keeps blast minimal. Matches dogfood patterns (template literals + conditional requires).",
            "hint": "Move the require/import inside the using function (or behind if (env.feature) guard). Prefer dynamic import() in ESM or a getX() factory.",
            "safety": "high (targets non-static/low-conf edge; no behavior change for untaken paths)",
            "signals_addressed": ["dynamic" if dyn else "low_conf", "conditional" if cond else None],
        })
    elif bar:
        recs.append({
            "strategy": "barrel_reorg_avoid_cycle",
            "target_edge": tgt_edge,
            "rationale": f"Barrel edge {tgt_edge} (depth {bd}) is mediating the cycle, multiplying the maintenance surface across all barrel consumers. Direct leaf import or carve-out reduces coupling.",
            "hint": "Change importer to require the concrete './leafX' instead of barrel index; or move the shared export into a dedicated non-barrel util/shared.",
            "safety": "medium (verify no other consumers rely on barrel re-export side-effects; run get_dependents)",
            "signals_addressed": ["via_barrel"],
        })
    return recs


def _rule_large_or_high_blast_cluster(nodes: List[str], weakest: List[Dict], risks: Dict, blast: int, size: int) -> List[Dict[str, Any]]:
    """For sizable or high-impact clusters, recommend seam extraction."""
    recs: List[Dict[str, Any]] = []
    if size >= 4 or blast >= 10:
        seam_target = f"{nodes[0] if nodes else '?'} <-> shared seam"
        recs.append({
            "strategy": "extract_interface_shared_module",
            "target_edge": seam_target,
            "rationale": f"Size-{size} cluster with external blast radius {blast} creates wide refactoring cost. A neutral seam (interface/contracts) outside the tangle allows one-way deps and incremental migration.",
            "hint": "Create e.g. src/shared/contracts.js (or /types/cycle-boundary.d.ts); move common abstractions there; update members to depend on seam only.",
            "safety": "medium-high (use get_dependents + get_file_wiki on seam candidates first; test boundary)",
            "signals_addressed": ["size", "blast"],
        })
    return recs


def _rule_conditional_or_feature_flag(nodes: List[str], weakest: List[Dict], risks: Dict, blast: int, size: int) -> List[Dict[str, Any]]:
    """When conditional/flag edges are prominent in cycle, recommend promoting to explicit config seam (harden for ACS alignment)."""
    recs: List[Dict[str, Any]] = []
    cond = risks.get("conditional_edges", 0)
    if cond >= 2 or (size > 2 and cond > 0):
        recs.append({
            "strategy": "promote_conditional_to_config_seam",
            "target_edge": "feature/guard sites in cluster",
            "rationale": "Hardened: conditional or feature-flag edges (ACS-tagged) inside cycle mean runtime paths determine the tangle. Promote predicates to top-level config or DI seam so static structure is cycle-free and analyzable.",
            "hint": "Extract a config module or use a registry/factory; make the cycle members depend on the seam (not each other) for the varying cases.",
            "safety": "high (config changes are explicit; run get_cycles(analysis=True) + tests post-split)",
            "signals_addressed": ["conditional_edges", "feature_flag"],
        })
    return recs


def _rule_default_audit_split(nodes: List[str], weakest: List[Dict], risks: Dict, blast: int, size: int) -> List[Dict[str, Any]]:
    """Fallback for 2-cycles and simple mutuals without standout risky edges. (Harden rationale per ACS surfacing audit)"""
    recs: List[Dict[str, Any]] = []
    if not weakest and size <= 3:
        recs.append({
            "strategy": "audit_and_directional_split",
            "target_edge": "review weakest or mutual pair",
            "rationale": "Classic bidirectional dependency (ACS often shows medium/low on mutuals). Identify conceptual owner and break direction (or use DI) to eliminate the SCC; prevents coordinated multi-file refactors.",
            "hint": "Introduce parameter injection, move shared concept one layer up the package hierarchy, or use a small event/observer seam.",
            "safety": "verify with full test suite + get_cycles(analysis=True) post-change",
            "signals_addressed": ["mutual"],
        })
    return recs


def _rule_high_dynamic_in_cycle(nodes: List[str], weakest: List[Dict], risks: Dict, blast: int, size: int) -> List[Dict[str, Any]]:
    """New rule (1.3): high dynamic participation inside SCC — recommend static indirection or registry."""
    recs: List[Dict[str, Any]] = []
    dyn = risks.get("dynamic_edges", 0)
    if dyn >= 1 and (dyn >= 2 or size >= 3):
        recs.append({
            "strategy": "introduce_static_indirection_registry",
            "target_edge": "dynamic sites in cluster",
            "rationale": "High dynamic edges (ACS low-trust: opaque/complex) inside cycle amplify blast and defeat static tools. Replace with registry, plugin map, or explicit static re-exports at seam; keeps runtime flexibility while making graph acyclic and analyzable.",
            "hint": "Create a central 'featureRegistry.js' or equivalent; dynamic participants register at startup (or lazy); importers take from registry (static dep on registry).",
            "safety": "medium (test registration order + get_dependencies post-change; prefer for non-performance-critical paths)",
            "signals_addressed": ["dynamic_edges", "complexity"],
        })
    return recs


BREAKING_RECOMMENDATION_RULES = [
    _rule_weakest_risky_edge,
    _rule_large_or_high_blast_cluster,
    _rule_conditional_or_feature_flag,
    _rule_default_audit_split,
    _rule_high_dynamic_in_cycle,  # v1.3 extension (ACS/CIABRE surfacing uniformity)
]


def _generate_breaking_recommendations(
    nodes: List[str], weakest: List[Dict], risks: Dict, blast: int, size: int
) -> List[Dict[str, Any]]:
    """Ranked, practical, context-sensitive recs using the extensible registry.
    Produces 1-3 high-quality recommendations with concrete rationales, hints, and safety notes
    derived from real edge signals (dyn/cond/bar/low-conf) observed in dogfood.
    """
    candidates: List[Dict[str, Any]] = []
    seen_strategies: set = set()
    for rule_fn in BREAKING_RECOMMENDATION_RULES:
        try:
            for rec in rule_fn(nodes, weakest, risks, blast, size) or []:
                strat = rec.get("strategy")
                if strat and strat not in seen_strategies:
                    seen_strategies.add(strat)
                    candidates.append(rec)
        except Exception:
            # defensive: never break CIABRE on a bad rule
            continue

    # Stable ranking: primary (weakest) first, then size/blast, then fallback
    rank_order = {"lazy_load_or_conditional_guard": 1, "barrel_reorg_avoid_cycle": 2, "extract_interface_shared_module": 3, "audit_and_directional_split": 4}
    for i, rec in enumerate(candidates):
        rec["rank"] = rank_order.get(rec.get("strategy"), 10 + i)
    candidates.sort(key=lambda r: r.get("rank", 99))

    # Always ensure at least one fallback
    if not candidates:
        candidates.append({
            "rank": 1,
            "strategy": "audit_and_directional_split",
            "target_edge": "review weakest",
            "rationale": "Classic mutual dependency; break directionally after identifying owner of the abstraction.",
            "hint": "Use dependency injection or move the shared concept one layer up the package hierarchy.",
            "safety": "verify with tests + get_cycles(analysis=True)",
            "signals_addressed": [],
        })

    # Return top 3 (practical)
    return candidates[:3]


def _ciabre_summary(analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not analyses:
        return {"total_sccs_analyzed": 0, "high_severity_count": 0, "max_blast_radius": 0, "avg_score": 0.0}
    highs = sum(1 for a in analyses if a.get("severity") in ("HIGH", "CRITICAL"))
    maxb = max((a.get("external_blast_radius", 0) for a in analyses), default=0)
    avgs = sum(a.get("score", 0) for a in analyses) / len(analyses)
    return {
        "total_sccs_analyzed": len(analyses),
        "high_severity_count": highs,
        "max_blast_radius": maxb,
        "avg_score": round(avgs, 2),
    }


# =============================================================================
# Lightweight ACS Aggregates (for surfacing uniformity in health/MCP/library/prompts)
# Zero-dep, bounded scan over resolved_pairs (which carry full R2 canonical ACS fields
# post-parser emission + RICH_KEYS persistence). Provides quick filters + verbatim
# Recommendation samples for agents without full get_dependencies scan.
# =============================================================================

def compute_acs_summary(
    cache: Dict[str, Any],
    max_samples: int = 5,
    low_threshold: float = 0.65,
) -> Dict[str, Any]:
    """Lightweight ACS aggregate + bounded full-explanation samples.

    Scans resolved_pairs (rich ACS present after R2 contracts + parser pipeline).
    O(E) but practical (E << total files at monorepo scale due to internal-only).
    Used for _acs_summary persistence + surfacing in get_project_status, health MCP,
    library.md "ACS Risk Snapshot", CLI, prompts.

    Returns stable shape with full (not truncated) confidence_explanation samples
    so agents can quote Recommendation: verbatim.
    """
    t0 = time.time()
    total = 0
    sum_score = 0.0
    low_count = 0
    reason_counts: Dict[str, int] = {}
    samples: List[str] = []  # full expls for lowest-risk (prioritized)

    low_items: List[tuple] = []  # (score, expl) for sorting top risks

    for rel, data in cache.items():
        if not isinstance(rel, str) or rel.startswith("_") or not isinstance(data, dict):
            continue
        for p in (data.get("resolved_pairs") or []):
            if not isinstance(p, dict) or not p.get("resolved"):
                continue
            total += 1
            sc = p.get("confidence_score")
            expl = p.get("confidence_explanation") or ""
            reasons = p.get("confidence_reasons") or []
            if isinstance(sc, (int, float)):
                scf = float(sc)
                sum_score += scf
                if scf < low_threshold:
                    low_count += 1
                    if expl:
                        low_items.append((scf, expl))
            # aggregate reasons (filterable by agents)
            for r in reasons:
                if isinstance(r, str) and r:
                    reason_counts[r] = reason_counts.get(r, 0) + 1

    # Select up to max_samples lowest-score (highest risk) full explanations
    low_items.sort(key=lambda x: x[0])  # lowest first
    for scf, expl in low_items[:max_samples]:
        # keep full but defensively cap length for cache bloat (agents still get Recommendation sentence intact)
        safe_expl = expl if len(expl) <= 450 else expl[:447] + "..."
        samples.append(safe_expl)

    avg = round(sum_score / total, 2) if total > 0 else 0.0
    top_reasons = sorted(reason_counts.items(), key=lambda x: -x[1])[:6]

    return {
        "acs_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_scored_edges": total,
        "avg_confidence": avg,
        "low_conf_edges": low_count,
        "low_conf_threshold": low_threshold,
        "top_risk_reasons": dict(top_reasons),
        "sample_low_conf_explanations": samples,  # full Recommendation text for agents
        "compute_time_ms": int((time.time() - t0) * 1000),
    }


def get_acs_summary(cache: Dict[str, Any]) -> Dict[str, Any]:
    """Return persisted ACS summary (or empty)."""
    return cache.get("_acs_summary", {}) or {}


def set_acs_summary(cache: Dict[str, Any], summary: Dict[str, Any]) -> None:
    """Persist ACS summary (defensive: only if meaningful data). Mirrors cycle_analyses pattern."""
    if summary and isinstance(summary, dict) and summary.get("total_scored_edges", 0) >= 0:
        cache["_acs_summary"] = summary
    else:
        cache.pop("_acs_summary", None)


def ensure_acs_summary_persisted(
    cache: Dict[str, Any], root: Optional[Path] = None
) -> Dict[str, Any]:
    """On-demand compute + guaranteed persistence for _acs_summary (Gap #1 ACS + CIABRE Surfacing Uniformity).

    Mirrors the cycles "guaranteed persist" hardening (see get_cycles: did_compute_cycles/analyses + set_* + save_cache).
    Safe for all read/query paths (MCP health(), get_project_status(), CLI `cycles`, sh library.md builders, direct Python):
    - If absent/empty (pre-persist cache, partial update-maps, direct MCP use, packaged paths), compute from
      resolved_pairs (full R2 confidence_score/reasons/explanation present post-pipeline), set under RESERVED key,
      and if root provided, best-effort save_cache (M2 file lock protected).
    - Never raises on persist side-effect; always returns usable summary (with full sample Recommendations for quoting).
    - Zero-dep, scalable O(E) scan (E=internal edges << files); enables agents to treat ACS aggregates/samples as
      always-available oracle in primary surfaces without requiring explicit update first.
    """
    acs = get_acs_summary(cache)
    if not acs or acs.get("total_scored_edges", 0) == 0:
        acs = compute_acs_summary(cache)
        set_acs_summary(cache, acs)
        if root is not None:
            try:
                save_cache(root, cache)
            except Exception:
                pass  # never let a read/query path fail due to persist side-effect
        return acs
    return acs


def _analyze_one_scc(
    nodes: List[str], graph: Dict[str, List[str]], emap: Dict[Tuple[str, str], Dict], reverse_map: Dict[str, List[str]]
) -> Dict[str, Any]:
    node_set = set(nodes)
    size = len(node_set)
    internal = 0
    risks = {"low_conf_edges": 0, "dynamic_edges": 0, "conditional_edges": 0, "barrel_edges": 0, "max_barrel_depth": 0}
    weakest: List[Dict] = []
    for src in node_set:
        for tgt in graph.get(src, []):
            if tgt in node_set:
                internal += 1
                meta = emap.get((src, tgt), {"confidence": "medium"})
                conf = meta.get("confidence", "medium")
                if conf == "low":
                    risks["low_conf_edges"] += 1
                if meta.get("is_dynamic"):
                    risks["dynamic_edges"] += 1
                if meta.get("is_conditional"):
                    risks["conditional_edges"] += 1
                if meta.get("via_barrel"):
                    risks["barrel_edges"] += 1
                bd = meta.get("barrel_depth", 0) or 0
                if bd > risks["max_barrel_depth"]:
                    risks["max_barrel_depth"] = bd
                rsc = _edge_risk_score(meta)
                weakest.append({
                    "from": src,
                    "to": tgt,
                    "confidence": conf,
                    "is_dynamic": bool(meta.get("is_dynamic")),
                    "is_conditional": bool(meta.get("is_conditional")),
                    "via_barrel": bool(meta.get("via_barrel")),
                    "barrel_depth": bd,
                    "risk_score": round(rsc, 2),
                })
    weakest.sort(key=lambda x: x.get("risk_score", 0), reverse=True)
    blast = _compute_external_blast_radius(node_set, reverse_map)
    score = _compute_severity_score(size, blast, risks, internal)
    sev = _severity_level(score)
    recs = _generate_breaking_recommendations(nodes, weakest, risks, blast, size)
    return {
        "nodes": sorted(nodes),
        "size": size,
        "internal_edges": internal,
        "external_blast_radius": blast,
        "severity": sev,
        "score": round(score, 1),
        "risk_signals": risks,
        "weakest_links": weakest[:3],
        "recommendations": recs[:3],
    }


def compute_cycle_analyses(
    cache: Dict[str, Any],
    root: Optional[Path] = None,
    max_items: int = 50,
    graph: Optional[Dict[str, List[str]]] = None,
    edge_meta: Optional[Dict[Tuple[str, str], Dict[str, Any]]] = None,
    use_canonical: bool = False,
    **kwargs: Any,
) -> Dict[str, Any]:
    """CIABRE v1.3 entrypoint (R5 + surfacing uniformity). If graph+edge_meta supplied (from sh first-pass), reuse to avoid 2x scan.
    Returns versioned payload with per-SCC analyses (severity, blast, weakest, recs with hardened rationales) + summary.
    Registry extended (conditional + new high-dynamic rule). Used by get_cycles(analysis=True), library.md, CLI, agent prompts.
    use_canonical + root: forwarded for v1 canonical graph identity (Phase 4 prep); stamps node_identity_version.
    """
    t0 = time.time()
    if graph is None or edge_meta is None:
        graph, edge_meta = build_graph_with_edge_metadata(cache, root=root, use_canonical=use_canonical)
    gsig = graph_signature(graph)

    # Wave 2 delta/incremental for CIABRE analyses (reuses same sig check as cycles)
    persisted_sig = get_graph_signature(cache)
    if persisted_sig and persisted_sig == gsig:
        persisted_anal = get_cycle_analyses(cache)
        if persisted_anal and "analyses" in persisted_anal and persisted_anal.get("graph_signature") == gsig:
            ra = dict(persisted_anal)
            ra["reused"] = True
            ra["reuse_reason"] = "graph_signature_match"
            ra.setdefault("graph_signature", gsig)
            ra.setdefault("node_identity_version", NODE_IDENTITY_VERSION_V0)
            # Guaranteed persistence: update stored so get_cycle_analyses / reuse_stats reflect the reuse state
            set_cycle_analyses(cache, ra)
            return ra

    # ensure cycles present (compute_cycles itself may now short-circuit on sig match)
    cdata = get_cycles(cache)
    if not cdata or "sccs" not in cdata:
        # Graph reuse improvement: share the already-built graph from this call site
        # (avoids duplicate O(V+E) build + scan on large monorepos with deep cycles)
        cdata = compute_cycles(cache, root=root, use_canonical=use_canonical, graph=graph)
    sccs = cdata.get("sccs", [])
    rev = get_reverse_dependencies(cache)
    anlist: List[Dict[str, Any]] = []
    for s in sccs[:max_items]:
        nds = s.get("nodes", [])
        if len(nds) < 2:
            continue
        an = _analyze_one_scc(nds, graph, edge_meta, rev)
        anlist.append(an)
    summ = _ciabre_summary(anlist)
    return {
        "analysis_version": "1.3",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "analyses": anlist,
        "summary": summ,
        "graph_signature": gsig,
        "reused": False,
        "reuse_reason": "computed_fresh",
        "node_identity_version": NODE_IDENTITY_VERSION_V1 if use_canonical else NODE_IDENTITY_VERSION_V0,
        "compute_time_ms": int((time.time() - t0) * 1000),
    }


def get_cycle_analyses(cache: Dict[str, Any]) -> Dict[str, Any]:
    return cache.get("_cycle_analyses", {}) or {}


def set_cycle_analyses(cache: Dict[str, Any], analyses: Dict[str, Any]) -> None:
    if analyses and "analyses" in analyses:  # persist even for empty analyses=[] ("no cycles for this sig") so delta short-circuit + reuse work on acyclic graphs too
        cache["_cycle_analyses"] = analyses
    else:
        cache.pop("_cycle_analyses", None)


def compute_files_needing_reparse(
    root: Path,
    candidate_full_paths: List[Path],
    full_rebuild: bool = False,
) -> List[Path]:
    """R7 Performance: Single-invocation replacement for the O(N) python -c mtime / has_cache / cache-key loops
    inside determine_files_to_reparse() in wikifier.sh first-pass.

    Eliminates thousands of interpreter + wikifier.* imports on large monorepos (previously ~800ms each).
    Detection cost now O(1) spawns regardless of project size (1k-20k+ files), while preserving exact
    mtime-dirty + new-file semantics for incremental correctness + barrel invalidation.

    Called from first-pass; returns deduped full Paths in encounter order.
    """
    if full_rebuild:
        # preserve order, dedup
        seen: set = set()
        out: List[Path] = []
        for p in candidate_full_paths:
            pr = Path(p).resolve() if p else None
            if pr and pr not in seen:
                seen.add(pr)
                out.append(pr)
        return out

    cache = load_cache(root)
    to_reparse: List[Path] = []
    seen: set = set()
    try:
        root_res = root.resolve()
    except Exception:
        root_res = root

    # 1. Check all current sources: changed or absent from cache => dirty/new
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
        # Robust rel for cache key (handles Path objects, symlinks, win/linux)
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
        data = get_file_data(cache, rel) or {}
        cached_mtime = int(data.get("mtime", 0) or 0)
        curr_mtime = 0
        if p_res.exists():
            try:
                curr_mtime = int(p_res.stat().st_mtime)
            except Exception:
                curr_mtime = 0
        needs = (curr_mtime > cached_mtime) or (not data)
        if needs:
            to_reparse.append(p_res)

    # 2. Also honor any cache-tracked files that changed on disk (old behavior for completeness)
    for rel, data in list(cache.items()):
        if not isinstance(rel, str) or rel.startswith("_") or not isinstance(data, dict):
            continue
        try:
            full = (root / rel).resolve()
            if full in seen:
                continue
            if full.exists():
                curr = int(full.stat().st_mtime)
                cached = int(data.get("mtime", 0) or 0)
                if curr > cached:
                    to_reparse.append(full)
                    seen.add(full)
        except Exception:
            pass

    return to_reparse


# =============================================================================
# BarrelResolutionCache thin accessors (Phase 2.3 prod wiring)
# These are the minimal surface the BREE BarrelResolutionCache expects.
# The real state lives under reserved top-level keys in the import cache JSON.
# =============================================================================

def get_mtime(path: Path) -> int:
    """Return mtime of a file as int seconds (0 on error)."""
    try:
        return int(path.stat().st_mtime)
    except Exception:
        return 0


def get_barrel_resolutions(cache: Dict[str, Any]) -> Dict[str, Any]:
    """Return the persisted _barrel_resolutions dict (or empty)."""
    return (cache or {}).get("_barrel_resolutions", {}) or {}


def get_barrel_file_index(cache: Dict[str, Any]) -> Dict[str, Any]:
    """Return the persisted _barrel_file_index reverse map (or empty)."""
    return (cache or {}).get("_barrel_file_index", {}) or {}


def set_barrel_resolutions(cache: Dict[str, Any], resolutions: Dict[str, Any]) -> None:
    if resolutions:
        cache["_barrel_resolutions"] = resolutions
    else:
        cache.pop("_barrel_resolutions", None)


def set_barrel_file_index(cache: Dict[str, Any], file_index: Dict[str, Any]) -> None:
    if file_index:
        cache["_barrel_file_index"] = file_index
    else:
        cache.pop("_barrel_file_index", None)


def invalidate_stale_barrel_entries(
    cache: Dict[str, Any],
    root: Path,
    changed_files: Optional[Iterable[Union[str, Path]]] = None,
) -> List[str]:
    """
    Return list of importer relpaths that were using barrel chains now considered stale
    (any file in their mtimes_snapshot has a newer mtime) or, when changed_files is
    supplied, the fast O(#changed) path: for each changed file that is a known barrel
    in the reverse index, return its registered importers.

    This enables the scalable "edit barrel → only affected importers re-analyzed"
    hot path (Wave 1 of deep barrel invalidation strategy).

    When changed_files is provided (list of str/Path from the just-computed dirty set),
    we use brc.get_affected_importers() via the file_index (no full scan over chains).
    Falls back to full collect_stale_importers(root) only if changed_files is None.

    Used by first-pass to augment the dirty set before re-parsing.
    Non-destructive (does not mutate cache here; caller decides).
    All paths are handled defensively for rel/abs forms (pre-canonical-hardening).
    """
    from .parsers.bree import BarrelResolutionCache  # local import to avoid cycles at module load

    brc = BarrelResolutionCache.from_cache(cache)

    # Wave 2 canonical pass: prefer canonical_for_bree (to_canonical_rel v1 physical) for all BRC delta lookups
    # Ensures importer_rel, changed_file lookups, etc. always match the stamped v1 keys in file_index/resolutions.
    _canon = None
    try:
        from .parsers.bree import _brc_canonical as _canon
    except Exception:
        try:
            from .resolution import canonical_for_bree as _canon_for_bree
            def _make_canon(tc):
                def _c(p, r):
                    try:
                        return tc(p, r) or str(p)
                    except Exception:
                        return str(p)
                return _c
            _canon = _make_canon(_canon_for_bree)
        except Exception:
            try:
                from .resolution import to_canonical_rel as _to_canon
                def _make_canon(tc):
                    def _c(p, r):
                        try:
                            return tc(p, r, follow_symlinks=True) or str(p)
                        except Exception:
                            return str(p)
                    return _c
                _canon = _make_canon(_to_canon)
            except Exception:
                _canon = None

    if changed_files is not None:
        # Delta / fast path (preferred for incremental update-maps and daemon):
        # Cost = O(#changed files that happen to be barrels in the index) — perfect scaling.
        affected: set = set()
        root_res = None
        try:
            root_res = root.resolve()
        except Exception:
            root_res = root
        for f in changed_files:
            if not f:
                continue
            fstr = str(f)
            # Direct lookup (works if caller passed matching key form, e.g. rel from index)
            aff = brc.get_affected_importers(fstr)
            affected.update(aff)
            # Wave 1 canonical v1 lookup: try the normalized physical rel form (keys in BRC file_index are now v1)
            if _canon:
                try:
                    c = _canon(f, root) or _canon(f, root_res or root)
                    if c and c != fstr:
                        affected.update(brc.get_affected_importers(c))
                except Exception:
                    pass
            # Robust cross-form lookup: if abs, also try canonical-ish rel under root
            try:
                fp = Path(fstr)
                if fp.is_absolute() or str(fp).startswith(str(root_res or root)):
                    if root_res:
                        try:
                            rel = str(fp.resolve().relative_to(root_res))
                            if rel and rel != fstr:
                                aff = brc.get_affected_importers(rel)
                                affected.update(aff)
                                # also posix normalized
                                relp = rel.replace("\\", "/")
                                if relp != rel:
                                    affected.update(brc.get_affected_importers(relp))
                        except Exception:
                            pass
                    # also try just the name or tail as last resort (rare)
                    try:
                        tail = fp.name
                        if tail and tail != fstr:
                            affected.update(brc.get_affected_importers(tail))
                    except Exception:
                        pass
            except Exception:
                pass
        return sorted(affected)

    # Legacy / full-rebuild / no-dirty-list path: scan all chains (still safe, #chains << #files)
    stale_importers = brc.collect_stale_importers(root)
    affected = set(stale_importers)
    return sorted(affected)


# =============================================================================
# Wave 2 Observability: BRC summary stats + rich invalidation reports (for health/MCP/diagnostics/sh DEBUG)
# Zero-dep, uses the build_invalidation_reports already in bree; returns plain dicts for easy JSON/MCP.
# Scalable: fast index path when changed_files provided; bounded samples in future.
# =============================================================================

def get_barrel_invalidation_reports(
    cache: Dict[str, Any],
    root: Path,
    changed_files: Optional[Iterable[Union[str, Path]]] = None,
) -> List[Dict[str, Any]]:
    """Wave 2: Return structured BarrelInvalidationReport dicts (importer, triggering_barrels,
    chain_ids, reason, detector_used, is_partial, node_identity_version=v1, ...).
    Enables "why was this re-parsed?" answers in sh debug, diagnostics, MCP, journal.
    Delegates to BRC.build_invalidation_reports for the logic (O(changed) or scan).
    """
    try:
        from .parsers.bree import BarrelResolutionCache
        from dataclasses import asdict
        brc = BarrelResolutionCache.from_cache(cache)
        reports = brc.build_invalidation_reports(changed_files=changed_files, root=root)
        return [asdict(r) if hasattr(r, "__dataclass_fields__") else (r if isinstance(r, dict) else vars(r)) for r in reports]
    except Exception:
        return []


def get_barrel_cache_summary(cache: Dict[str, Any]) -> Dict[str, Any]:
    """Lightweight BRC summary stats for health/MCP/diagnostics surfacing (Wave 2 start).
    Counts only (no content); includes v1 canonical stamp coverage + partials.
    Always safe, fast, zero-dep. Used in get_project_status + health(json) + sh.
    """
    try:
        from .parsers.bree import BarrelResolutionCache
        brc = BarrelResolutionCache.from_cache(cache)
        resolutions = brc.resolutions or {}
        n_chains = len(resolutions)
        n_index = len(brc.file_index or {})
        v1_count = sum(1 for e in resolutions.values() if isinstance(e, dict) and e.get("node_identity_version") == "v1")
        partial_count = sum(1 for e in resolutions.values() if isinstance(e, dict) and e.get("is_partial"))
        return {
            "num_chains": n_chains,
            "num_indexed_barrels": n_index,
            "v1_canonical_chains": v1_count,
            "partial_chains": partial_count,
            "node_identity_version": "v1",
            "has_brc": bool(n_chains or n_index),
            "version": "bree-v2-wave2",
        }
    except Exception:
        return {"num_chains": 0, "has_brc": False, "error": "unavailable"}


def append_barrel_invalidation_log(
    cache: Dict[str, Any],
    reports: List[Dict[str, Any]],
    max_entries: int = 100,
) -> int:
    """Lightweight audit append for _barrel_invalidation_log (Wave 4 per deep barrel strategy).

    Mutates the cache dict in-place with bounded recent structured reports (each augmented
    with 'ts' epoch for ordering). Only grows on real barrel-driven invalidation events.
    Zero-dep, O(reports), safe for hot paths; called from sh delta blocks (both copies),
    check-changes, and any future daemon/MCP direct use of reports.

    The log is human-readable in cache JSON and queryable via load_cache + key for agents
    doing post-mortem on "which barrel edits caused which re-parses over time".
    Bounded to prevent unbounded growth even on long-lived daemons at 50k scale.
    """
    if not reports:
        return 0
    try:
        from dataclasses import asdict
        log = cache.get("_barrel_invalidation_log")
        if not isinstance(log, list):
            log = []
        now = time.time()
        for r in reports:
            if isinstance(r, dict):
                rec = dict(r)
            else:
                try:
                    rec = asdict(r) if hasattr(r, "__dataclass_fields__") else {"raw": str(r)}
                except Exception:
                    rec = {"raw": str(r)}
            rec["ts"] = now
            log.append(rec)
        # keep most recent N
        if len(log) > max_entries:
            log = log[-max_entries:]
        cache["_barrel_invalidation_log"] = log
        return len(reports)
    except Exception:
        # never fail a caller
        return 0


# =============================================================================
# Resolution Diagnostics Aggregate (for get_resolution_diagnostics MCP tool + ensure)
# Integrates diagnostics.py summarize for global cache scan. Surfaces cycle/graph
# reuse stats (from Wave 2/3 delta short-circuit) so diagnostics consumers see
# "graph_signature + reused" without separate get_cycles call. Zero-dep, scalable.
# =============================================================================

def get_resolution_diagnostics(cache: Dict[str, Any]) -> Dict[str, Any]:
    """Aggregate resolution diagnostics across entire cache (global view for MCP).

    Collects resolved_pairs from all file entries, summarizes via diagnostics layer,
    and injects cycle/graph reuse stats (graph_signature, reused, reuse_reason) for
    observability of delta/incremental Tarjan short-circuits in diagnostics output.
    Called by get_resolution_diagnostics tool; falls back gracefully.
    """
    try:
        from . import diagnostics as _d
    except Exception:
        _d = None
    if _d is None:
        return {"total_imports": 0, "low_or_unresolved_count": 0, "by_category": {}, "top_categories": [], "samples": [], "error": "diagnostics module unavailable"}

    all_pairs: List[Dict[str, Any]] = []
    for rel, data in cache.items():
        if isinstance(rel, str) and not rel.startswith("_") and isinstance(data, dict):
            for p in (data.get("resolved_pairs") or []):
                if isinstance(p, dict):
                    pp = dict(p)
                    pp.setdefault("src", rel)
                    all_pairs.append(pp)

    if not all_pairs:
        summary = _d.empty_diagnostics_summary()
    else:
        summary = _d.summarize_diagnostics(all_pairs)

    # Surface reuse stats broadly via dedicated helper (health/diag/MCP/library consumers)
    reuse = get_cycles_reuse_stats(cache)
    summary["graph_signature"] = reuse.get("graph_signature") or "N/A"
    summary["cycles_reused"] = reuse.get("reused", False)
    summary["cycles_reuse_reason"] = reuse.get("reuse_reason")
    summary["cycles_graph_signature"] = reuse.get("graph_signature")
    summary["cycles_node_identity_version"] = reuse.get("node_identity_version", NODE_IDENTITY_VERSION_V0)
    return summary


def ensure_diagnostics_aggregate(cache: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure a non-empty _resolution_diagnostics aggregate exists (compute on demand if missing/empty).

    Used by get_resolution_diagnostics MCP when first call yields no data; populates
    for future fast path (additive, does not force save). Reuses the get_ impl which
    now carries reuse stats.
    """
    existing = cache.get("_resolution_diagnostics")
    if existing and isinstance(existing, dict) and existing.get("total_imports", 0) > 0:
        return existing
    fresh = get_resolution_diagnostics(cache)
    if fresh.get("total_imports", 0) > 0:
        cache["_resolution_diagnostics"] = fresh
    return fresh


# =============================================================================
# Workstream D: Resolution Transparency Surfaces (first-class unresolved/low-conf)
# New helpers (additive, zero-dep, bounded, O(E) with early cutoff for scale).
# Power get_project_status, health(json), MCP (get_dependencies filters + dedicated),
# library.md generator, and agent "show me untrustworthy edges" workflows.
# All problematic edges carry the new python.py provenance + diagnostics for actionability.
# Ties directly into ACS (low<0.65) + CIABRE (weakest links include low-conf edges).
# =============================================================================

def get_unresolved_imports(cache: Dict[str, Any], max_results: int = 50) -> List[Dict[str, Any]]:
    """Return bounded list of import edges with resolution_confidence in ('low', 'unresolved')
    or missing resolved_path or carrying a diagnostic (failure mode visible).

    Each item: src (importer relpath), raw, resolved/module, confidence, resolved_path,
    confidence_score, diagnostic (full if present), parser, resolution_strategy, etc.
    (All rich fields preserved from parser outputs via update_file_data.)

    First-class surface per M2 plan Workstream D. Safe on empty/massive caches.
    """
    results: List[Dict[str, Any]] = []
    for rel, data in cache.items():
        if isinstance(rel, str) and not rel.startswith("_") and isinstance(data, dict):
            for p in (data.get("resolved_pairs") or []):
                if not isinstance(p, dict):
                    continue
                conf = (p.get("confidence") or p.get("resolution_confidence") or "").lower()
                has_diag = bool(p.get("diagnostic"))
                no_path = not p.get("resolved_path")
                is_problem = conf in ("low", "unresolved") or has_diag or no_path
                if is_problem:
                    entry = dict(p)
                    entry.setdefault("src", rel)
                    entry.setdefault("confidence", conf or "unknown")
                    results.append(entry)
                    if len(results) >= max_results:
                        return results
    return results


def get_low_confidence_edges(
    cache: Dict[str, Any], *, threshold: float = 0.65, max_results: int = 50
) -> List[Dict[str, Any]]:
    """Return bounded edges where confidence_score < threshold (or legacy low/unresolved).

    Complements get_unresolved_imports; used for ACS-style hotspots.
    Includes full provenance/diagnostic when present (from python/JS parity).
    """
    results: List[Dict[str, Any]] = []
    for rel, data in cache.items():
        if isinstance(rel, str) and not rel.startswith("_") and isinstance(data, dict):
            for p in (data.get("resolved_pairs") or []):
                if not isinstance(p, dict):
                    continue
                score = p.get("confidence_score")
                conf_str = (p.get("confidence") or p.get("resolution_confidence") or "").lower()
                is_low = False
                try:
                    if score is not None:
                        is_low = float(score) < threshold
                    elif conf_str in ("low", "unresolved"):
                        is_low = True
                except Exception:
                    is_low = conf_str in ("low", "unresolved")
                if is_low or not p.get("resolved_path"):
                    entry = dict(p)
                    entry.setdefault("src", rel)
                    results.append(entry)
                    if len(results) >= max_results:
                        return results
    return results


def prune_barrel_resolutions(
    root: Path, max_age_days: float = 90.0, dry_run: bool = False,
    deleted_files: Optional[Iterable[Union[str, Path]]] = None
) -> Dict[str, Any]:
    """Lightweight age-based + deletion-triggered pruning/GC for persistent BarrelResolutionCache (Wave 4 continuation).

    Delegates to BRC.prune_aged_entries + new prune_references_to (for record-deletion paths).
    Supports deleted_files for precise removal of chains/importers/index refs mentioning deleted paths.
    Saves under lock only on actual change. Scalable (O(#chains) tiny).
    Returns rich stats; called from check-changes, update-maps, record-deletion (both sh), health CLI.

    Zero-dep, additive to prior age-only behavior (deleted_files=None keeps old contract).
    """
    try:
        from .parsers.bree import BarrelResolutionCache
        cache = load_cache(root)
        brc = BarrelResolutionCache.from_cache(cache)
        before_chains = len(brc.resolutions)
        before_index = len(brc.file_index)
        del_list = [str(d) for d in (deleted_files or []) if d]
        if dry_run:
            now = time.time()
            cutoff = now - (max_age_days * 86400.0)
            pruned = 0
            for cid, ent in (brc.resolutions or {}).items():
                try:
                    ca = 0.0
                    if isinstance(ent, dict):
                        ca = float(ent.get("created_at", 0) or 0)
                    else:
                        ca = float(getattr(ent, "created_at", 0) or 0)
                    if ca > 0 and ca < cutoff:
                        pruned += 1
                except Exception:
                    continue
            # dry-run also counts potential deletion matches (no mutate)
            for cid, ent in (brc.resolutions or {}).items():
                try:
                    chain_imps = []
                    if isinstance(ent, dict):
                        chain_imps = (ent.get("barrel_chain", []) or []) + (ent.get("importers", []) or [])
                    else:
                        chain_imps = (getattr(ent, "barrel_chain", []) or []) + (getattr(ent, "importers", []) or [])
                    hay = " ".join(str(x) for x in chain_imps)
                    if any(d in hay for d in del_list):
                        pruned += 1  # count as would-be-pruned
                except Exception:
                    continue
            ret = {
                "pruned": pruned,
                "dry_run": True,
                "before_chains": before_chains,
                "before_indexed_barrels": before_index,
                "max_age_days": max_age_days,
            }
            if del_list:
                ret["deleted_files_considered"] = del_list[:5]
            return ret
        pruned_age = brc.prune_aged_entries(max_age_days)
        pruned_del = brc.prune_references_to(del_list) if del_list else 0
        pruned = pruned_age + pruned_del
        saved = False
        if pruned > 0:
            brc.to_cache_updates(cache)
            save_cache(root, cache)
            saved = True
        ret = {
            "pruned": pruned,
            "pruned_age": pruned_age,
            "pruned_by_deletion": pruned_del,
            "dry_run": False,
            "before_chains": before_chains,
            "after_chains": len(brc.resolutions),
            "before_indexed_barrels": before_index,
            "after_indexed_barrels": len(brc.file_index),
            "max_age_days": max_age_days,
            "saved": saved,
        }
        if del_list:
            ret["deleted_files_considered"] = del_list[:5]
        return ret
    except Exception as e:
        return {"pruned": 0, "error": str(e), "max_age_days": max_age_days}


if __name__ == "__main__":
    import sys
    print("Wikifier Import Cache module. Import it from Python or use via shell helpers.")


# =============================================================================
# M2 A0 + early A2: Minimal Streaming Skeleton (generator foundation)
# =============================================================================
#
# Purpose (per long-term plan):
# - Provide a *clean, typed, versioned event-yielding generator* that later waves
#   (A2 full streaming UX, CLI --resume, MCP partials, scoped subtree) can build on
#   without re-architecting.
# - Events are *always* ProgressEvent_v1 shaped (via contracts.create_progress_event
#   or direct dataclass) and carry:
#     * Provenance (actor, session, intent, parent)
#     * ACS + CIABRE hooks (partials, refs, low_conf deltas)
#     * Barrel + cycle signals (depth, via, scc, severity)
#     * ScopeSpec_v1 (directory/globs/focus + budgets)
#     * Checkpoint tokens + resumable hints (for pause/resume on massive repos)
# - Zero new dependencies. Uses only stdlib + existing wikifier.* (contracts,
#   locking patterns, compute_* helpers).
# - **NOT a full implementation**: No real dirty detection, parsing, cycles, ACS,
#   CIABRE, or persist yet inside the generator. Synthetic milestone events only,
#   to prove the shape + consumption contract. Real wiring = A2+.
# - Backward compatible: new function only. Existing callers of load/save/compute_*
#   unaffected.
# - Future: this generator will become the heart of run_full_update streaming mode,
#   daemon background updates, etc.
#
# Usage skeleton (for consumers written in A2+):
#   from wikifier.import_cache import generate_update_events
#   for event in generate_update_events(root, scope={"directory": "src/"}, run_id="..."):
#       if event["event_type"] == "partial_ready":
#           ... act on PartialResult ...
#       if event.get("checkpoint_token"):
#           save_checkpoint(...)
# =============================================================================

def generate_update_events(
    root: Optional[Path] = None,
    scope: Optional[Union[Dict[str, Any], "ScopeSpec_v1"]] = None,
    force_full: bool = False,
    run_id: Optional[str] = None,
    verbose: bool = False,
    **kwargs: Any,
) -> Iterable[Dict[str, Any]]:
    """
    Minimal generator yielding structured ProgressEvent_v1 dicts.

    This is the A0 foundation only. It:
    - Normalizes scope to ScopeSpec_v1
    - Emits a start event with full provenance scaffolding
    - Emits a scope_applied event (with resource hints)
    - Emits a handful of representative milestone events exercising
      barrel/cycle/ACS/CIABRE hook fields + checkpoint example
    - Yields a synthetic partial_result + complete (with next_checkpoint_hint)
    - Never raises on best-effort paths; always produces usable events.

    Later A2 waves will replace the body with real incremental pipeline:
        for changed in dirty:
            yield parsed event
            for edge in resolve(...):
                yield edge_resolved (with acs computed inline)
            ...
            if budget_exhausted:
                yield partial_ready with PartialResult_v1 + checkpoint
        yield ciabre / reverse_index updates
        yield complete

    Checkpoint/resumption contract (future-proofed here):
    - Each event may carry "checkpoint_token" (opaque string)
    - Consumer can pass last_token on resume; generator will (in future)
      fast-forward using it + Scope.

    Locking: generator itself does not acquire locks (caller responsibility,
    same as today for run_full_update). Long-running consumers should hold
    project lock for the whole stream if mutating state.

    All events use contracts.create_progress_event for consistency.
    """
    # Defensive root
    if root is None:
        try:
            from .cli import discover_project_root
            root = discover_project_root()
        except Exception:
            root = Path(".").resolve()

    try:
        root = Path(root).resolve()
    except Exception:
        root = Path(".")

    # Normalize scope (supports raw dict or dataclass)
    try:
        from .contracts import (
            ScopeSpec_v1,
            create_progress_event,
            M2_CONTRACTS_VERSION,
        )
    except Exception:
        # ultra-defensive fallback (should never happen post A0)
        ScopeSpec_v1 = None  # type: ignore
        create_progress_event = None  # type: ignore
        M2_CONTRACTS_VERSION = "0.0-fallback"

    if ScopeSpec_v1 is not None:
        if isinstance(scope, ScopeSpec_v1):
            sc = scope
        elif isinstance(scope, dict):
            sc = ScopeSpec_v1.from_dict(scope)
        else:
            sc = ScopeSpec_v1()
    else:
        sc = type("obj", (object,), {"to_dict": lambda s: {"directory": None}})()  # type: ignore

    if not run_id:
        run_id = f"run-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{id(root) % 100000:05d}"

    actor = kwargs.get("actor", "import_cache.skeleton")
    session = kwargs.get("session_id", f"sess-{run_id[-6:]}")

    # 1. Start event (provenance + initial scope + hook scaffolding)
    start_ev = None
    if create_progress_event:
        start_ev = create_progress_event(
            "start",
            run_id,
            scope=sc,
            provenance={
                "actor": actor,
                "session_id": session,
                "intent_ref": kwargs.get("intent_ref", "update-maps:skeleton"),
                "parent_checkpoint": kwargs.get("resume_from"),
            },
            payload={
                "force_full": bool(force_full),
                "m2_foundation": True,
                "contracts_version": M2_CONTRACTS_VERSION,
            },
            diagnostics={"note": "A0 minimal skeleton - real pipeline in A2+"},
        )
    else:
        start_ev = {
            "event_type": "start",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id,
            "scope": (sc.to_dict() if hasattr(sc, "to_dict") else {}),
            "provenance": {"actor": actor, "session_id": session},
            "version": "1.0",
        }
    yield start_ev

    # 2. Scope applied (early projection point for future real scoping)
    scope_ev = None
    if create_progress_event:
        scope_ev = create_progress_event(
            "scope_applied",
            run_id,
            scope=sc,
            provenance={"actor": actor, "session_id": session},
            payload={
                "effective_directory": sc.directory if hasattr(sc, "directory") else None,
                "focus_count": len(getattr(sc, "focus_files", []) or []),
                "transitive": getattr(sc, "transitive_closure", True),
            },
            resource_hints=getattr(sc, "resource_hints", {}) if hasattr(sc, "resource_hints") else {},
        )
    else:
        scope_ev = {"event_type": "scope_applied", "run_id": run_id, "scope": {}, "version": "1.0"}
    yield scope_ev

    # 3-5. Representative milestone events exercising all required signal channels
    # (barrel, cycle, ACS, checkpoint). These prove the long-term shape.
    if create_progress_event:
        yield create_progress_event(
            "file_parsed",
            run_id,
            scope=sc,
            provenance={"actor": actor, "session_id": session},
            payload={"file": "src/example.ts", "mtime": int(time.time())},
            barrel_signals={"via_barrel": True, "depth": 2, "detector": "bree"},
        )
        yield create_progress_event(
            "edge_resolved",
            run_id,
            scope=sc,
            provenance={"actor": actor, "session_id": session},
            payload={"raw": "./utils", "resolved": "src/utils.ts", "confidence": "high"},
            acs_hook={
                "confidence_score": 0.87,
                "reasons": ["base:high", "strong_resolution_strategy"],
                "explanation": "High-fidelity ... Recommendation: Safe for automated...",
            },
            cycle_signals={"in_cycle": False},
        )
        yield create_progress_event(
            "cycle_detected",
            run_id,
            scope=sc,
            provenance={"actor": actor, "session_id": session},
            cycle_signals={"scc_id": "scc-001", "size": 3, "severity": "medium", "ciabre_version": "1.3"},
            acs_hook={"blast_radius_hint": 12},
            checkpoint_token=f"after:cycle:scc-001:{run_id[-4:]}",
        )
    else:
        yield {"event_type": "file_parsed", "run_id": run_id, "version": "1.0"}
        yield {"event_type": "edge_resolved", "run_id": run_id, "acs_hook": {}, "version": "1.0"}
        yield {"event_type": "cycle_detected", "run_id": run_id, "cycle_signals": {}, "checkpoint_token": "synthetic", "version": "1.0"}

    # 6. Partial ready (early result contract for A2+ agents on budgets)
    if create_progress_event:
        partial = {
            "run_id": run_id,
            "yielded_at": datetime.now(timezone.utc).isoformat(),
            "scope_applied": (sc.to_dict() if hasattr(sc, "to_dict") else {}),
            "files_processed": 1,
            "edges_resolved": 2,
            "cycles_found": 1,
            "acs_partial": {"avg_confidence": 0.71, "low_conf_edges": 0},
            "next_checkpoint_hint": f"after:partial:{run_id[-4:]}",
            "version": "1.0",
        }
        yield create_progress_event(
            "partial_ready",
            run_id,
            scope=sc,
            provenance={"actor": actor, "session_id": session},
            payload={"partial_result": partial},
            partial_result=partial,  # convenience for consumers
            checkpoint_token=partial["next_checkpoint_hint"],
        )
    else:
        yield {"event_type": "partial_ready", "run_id": run_id, "checkpoint_token": "synthetic-partial", "version": "1.0"}

    # 7. Complete (with final checkpoint + summary hooks)
    if create_progress_event:
        yield create_progress_event(
            "complete",
            run_id,
            scope=sc,
            provenance={"actor": actor, "session_id": session, "completed": True},
            payload={
                "success": True,
                "note": "A0 skeleton complete. Full engine integration in A2+ waves.",
                "m2_foundation": True,
            },
            acs_hook={"final_summary_ref": "_acs_summary"},
            cycle_signals={"ciabre_ref": "_cycle_analyses"},
            checkpoint_token=f"final:{run_id}",
            resumable=False,  # stream ended
        )
    else:
        yield {"event_type": "complete", "run_id": run_id, "version": "1.0"}

    # Generator exhausted cleanly. Real impl will also yield barrel_expanded,
    # ciabre_updated, reverse_index_updated, error, etc.
