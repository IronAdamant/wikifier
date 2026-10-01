"""Cycle detection (Tarjan SCCs) and cycle impact analysis with breaking recommendations.

Persisted under ``_cycles`` / ``_cycle_analyses``. The graph signature lets an
incremental run reuse the previous result when topology is unchanged."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..contracts import NODE_IDENTITY_VERSION_V0, NODE_IDENTITY_VERSION_V1
from .graph import _tarjan_sccs, build_dependency_graph, build_graph_with_edge_metadata, get_graph_signature, get_reverse_dependencies, graph_signature, set_graph_signature


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

    # delta/incremental recompute (cycles long-term strategy):
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
            set_graph_signature(cache, gsig)
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
    payload = {
        "sccs": enriched,
        "stats": stats,
        "all_cycle_files": sorted(all_cycle_files),
        "node_identity_version": NODE_IDENTITY_VERSION_V1 if use_canonical else NODE_IDENTITY_VERSION_V0,
        "graph_signature": gsig,
        "reused": False,
        "reuse_reason": "computed_fresh",
    }
    set_cycles(cache, payload)
    set_graph_signature(cache, gsig)
    return payload


def get_cycles(cache: Dict[str, Any]) -> Dict[str, Any]:
    """Return persisted _cycles or empty."""
    return cache.get("_cycles", {}) or {}


def set_cycles(cache: Dict[str, Any], cdata: Dict[str, Any]) -> None:
    if cdata and "sccs" in cdata:  # persist even for empty sccs=[] ("no cycles for this sig") so delta short-circuit + get_reuse_stats work on acyclic graphs too
        cache["_cycles"] = cdata
    else:
        cache.pop("_cycles", None)


def compute_graph_integrity(cache: Dict[str, Any]) -> Dict[str, Any]:
    """One-line cycle summary, always derived from the current ``_cycles``."""
    stats = get_cycles(cache).get("stats", {}) or {}
    return {
        "summary": (
            f"{stats.get('cyclic_scc_count', 0)} cyclic SCC(s) involving "
            f"{stats.get('total_files_in_cycles', 0)} files"
        ),
        "stats": stats,
        "version": "1.0",
    }


def set_graph_integrity(cache: Dict[str, Any], integrity: Optional[Dict[str, Any]] = None) -> None:
    """Deprecated: integrity is derived on read. Drops any stale persisted copy."""
    cache.pop("_graph_integrity", None)


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
    # extra penalty for combined risky signals (dogfood-common: dyn barrel cycles)
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
    """v1.2 scoring: size + external blast + risk-weighted signals + density.
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
    # mature combined-signal boost (common in real dogfood CJS barrels + dyn templates)
    if risks.get("dynamic_edges", 0) > 0 and risks.get("barrel_edges", 0) > 0:
        base += 2.5
    # extra weight for high external blast (practical impact on monorepos) and dense risky clusters
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
    """CIABRE v1.3 entrypoint. If graph+edge_meta supplied (from sh first-pass), reuse to avoid 2x scan.
    Returns versioned payload with per-SCC analyses (severity, blast, weakest, recs with hardened rationales) + summary.
    Registry extended (conditional + new high-dynamic rule). Used by get_cycles(analysis=True), library.md, CLI, agent prompts.
    use_canonical + root: forwarded for v1 canonical graph identity; stamps node_identity_version.
    passthrough + sig reuse (graph_signature) delivers 0.037-0.7ms reuse / <1ms full on 50-node synth (subagent-64 2026-05-27 measurement on clean main; path to full <120ms GREEN confirmed for harness + sh first-pass integration).
    """
    t0 = time.time()
    if graph is None or edge_meta is None:
        graph, edge_meta = build_graph_with_edge_metadata(cache, root=root, use_canonical=use_canonical)
    gsig = graph_signature(graph)

    # delta/incremental for CIABRE analyses (reuses same sig check as cycles)
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
