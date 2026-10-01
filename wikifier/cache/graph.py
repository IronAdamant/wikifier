"""Dependency graph primitives: forward adjacency, reverse index, Tarjan SCC, signatures."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..contracts import NODE_IDENTITY_VERSION_V1
from ..resolution import canonical_for_bree


def get_reverse_dependencies(cache: Dict[str, Any]) -> Dict[str, List[str]]:
    """
    Return the reverse dependency map: target_path -> list of source files that import it.
    Stored under a reserved top-level key to avoid colliding with file entries.

    This is now a first-class persisted structure (parallel to forward graph
    built on resolved_pairs + BRC _barrel_* structures). Maintained incrementally
    during updates (O(changed) cost) with its own _reverse_signature for delta
    detection. Always authoritative for get_dependents / reverse queries.
    """
    return cache.get("_reverse_dependencies", {})


def set_reverse_dependencies(cache: Dict[str, Any], reverse_deps: Dict[str, List[str]]) -> None:
    """
    Store the reverse dependency map.
    This allows get_dependents() to work efficiently even in incremental mode.

    Now first-class. Automatically computes + persists the matching
    _reverse_signature (modeled on graph_signature) for observability and
    delta detection. Callers (sh, cli run_full_update, future pure engine)
    get consistent sig for free.
    """
    if reverse_deps:
        cache["_reverse_dependencies"] = reverse_deps
        # auto-keep signature in sync (long-term correct, observable design)
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
    Incrementally maintain the reverse index for one source's edge delta.

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


def remove_file_from_graph(cache: Dict[str, Any], rel: str) -> Dict[str, Any]:
    """Drop ``rel``'s entry and every reverse-index reference to it (deletions).

    Importers of ``rel`` keep their (now dangling) pairs until they are re-parsed;
    the reverse index stops listing ``rel`` as an importer immediately.
    """
    entry = cache.pop(rel, None)
    old_targets = []
    for pair in (entry or {}).get("resolved_pairs") or []:
        if isinstance(pair, dict) and pair.get("resolved"):
            old_targets.append(pair["resolved"])
    if old_targets:
        maintain_reverse_dependencies_for_source(cache, rel, old_targets, [])
    return {"removed_entry": entry is not None, "targets_cleaned": len(set(old_targets))}


def rebuild_reverse_dependencies(cache: Dict[str, Any]) -> Dict[str, List[str]]:
    """
    Full O(E) rebuild of reverse map from current per-file resolved_pairs/resolved data.

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
    Compact, zero-cost, always-safe stats surface for the reverse dependency index.
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


def build_dependency_graph(cache: Dict[str, Any], use_canonical: bool = False, root: Optional[Path] = None) -> Dict[str, List[str]]:
    """Build forward adjacency list from resolved_pairs (or legacy resolved).
    Includes all nodes that appear as importers or targets. Skips _reserved keys.

    use_canonical=True: remaps all keys and resolved targets
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
        # v1 canonical remap for flip readiness (symlink-safe single identity)
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

    implemented here for
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

    Persisted first-class parallel to graph_signature + BRC structures.
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
    """Return persisted reverse dependency signature or None."""
    return cache.get("_reverse_signature")


def set_reverse_signature(cache: Dict[str, Any], sig: str) -> None:
    """Persist the reverse dependency signature for delta detection / observability."""
    if sig:
        cache["_reverse_signature"] = sig
    else:
        cache.pop("_reverse_signature", None)


def get_graph_signature(cache: Dict[str, Any]) -> Optional[str]:
    """Return persisted graph signature or None."""
    return cache.get("_graph_signature")


def set_graph_signature(cache: Dict[str, Any], sig: str) -> None:
    """Persist the graph signature for reuse/incremental detection."""
    if sig:
        cache["_graph_signature"] = sig
    else:
        cache.pop("_graph_signature", None)


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
