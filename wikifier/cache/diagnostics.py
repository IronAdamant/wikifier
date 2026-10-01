"""Resolution diagnostics: unresolved / low-confidence edge aggregates and samples."""

from __future__ import annotations

from typing import Any, Dict, List

from ..contracts import NODE_IDENTITY_VERSION_V0
from .cycles import get_cycles_reuse_stats
from .acs import _edge_is_non_actionable_noise


def get_resolution_diagnostics(cache: Dict[str, Any]) -> Dict[str, Any]:
    """Aggregate resolution diagnostics across entire cache (global view for MCP).

    Collects resolved_pairs from all file entries, summarizes via diagnostics layer,
    and injects cycle/graph reuse stats (graph_signature, reused, reuse_reason) for
    observability of delta/incremental Tarjan short-circuits in diagnostics output.
    Called by get_resolution_diagnostics tool; falls back gracefully.
    """
    from .. import diagnostics as _d


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


def get_unresolved_imports(cache: Dict[str, Any], max_results: int = 50) -> List[Dict[str, Any]]:
    """Return bounded list of import edges with resolution_confidence in ('low', 'unresolved')
    or missing resolved_path or carrying a diagnostic (failure mode visible).

    Each item: src (importer relpath), raw, resolved/module, confidence, resolved_path,
    confidence_score, diagnostic (full if present), parser, resolution_strategy, etc.
    (All rich fields preserved from parser outputs via update_file_data.)

    First-class surface per plan. Safe on empty/massive caches.
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
    cache: Dict[str, Any],
    *,
    threshold: float = 0.65,
    max_results: int = 50,
    actionable_only: bool = False,
) -> List[Dict[str, Any]]:
    """Return bounded edges where confidence_score < threshold (or legacy low/unresolved).

    Complements get_unresolved_imports; used for ACS-style hotspots.
    Includes full provenance/diagnostic when present (from python/JS parity).

    actionable_only=True: skip external/bare/stdlib + dynamic-literal noise so
    agents do not treat `import json` or importlib.import_module(\"pkg\") as action items.
    """
    results: List[Dict[str, Any]] = []
    for rel, data in cache.items():
        if isinstance(rel, str) and not rel.startswith("_") and isinstance(data, dict):
            for p in (data.get("resolved_pairs") or []):
                if not isinstance(p, dict):
                    continue
                if actionable_only and _edge_is_non_actionable_noise(p):
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
                    if actionable_only and not p.get("resolved_path") and _edge_is_non_actionable_noise(p):
                        continue
                    entry = dict(p)
                    entry.setdefault("src", rel)
                    results.append(entry)
                    if len(results) >= max_results:
                        return results
    return results
