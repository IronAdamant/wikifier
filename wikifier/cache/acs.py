"""Agent confidence scoring (ACS) summary and map-coverage reporting.

Agents should work from ``actionable_low_conf_edges`` + ``reason_code_counts``;
external/stdlib and literal-dynamic edges are noise, not work items."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .io import save_cache


def _edge_is_external_noise(pair: Dict[str, Any]) -> bool:
    """True for stdlib / third-party / bare-external edges (not project-internal risk).

    these are valid telemetry but must not drive agent "fix the wiki / harden
    imports" actions. Diagnostic category and resolution strategy are authoritative.
    """
    if not isinstance(pair, dict):
        return False
    diag = pair.get("diagnostic") if isinstance(pair.get("diagnostic"), dict) else {}
    cat = str(diag.get("category") or "").lower()
    if cat in ("external_or_bare", "external", "stdlib", "third_party", "builtin"):
        return True
    meta = pair.get("resolution_metadata") if isinstance(pair.get("resolution_metadata"), dict) else {}
    strat = str(meta.get("strategy") or "").lower()
    if "bare-or-external" in strat or strat in ("external", "stdlib", "python-bare-or-external"):
        return True
    reasons = pair.get("confidence_reasons") or []
    for r in reasons:
        if not isinstance(r, str):
            continue
        rl = r.lower()
        if rl in ("external", "stdlib", "third_party") or "external_or_bare" in rl:
            return True
    return False


def _edge_is_dynamic_literal_noise(pair: Dict[str, Any]) -> bool:
    """True for dynamic imports of static string literals (not agent actionable risk).

    ACS v1.2: demote importlib.import_module(\"pkg\"), __import__(\"pkg\"), and other
    is_dynamic + dynamic_type=static string-literal edges. These are intentional runtime
    loads (often optional/try fallbacks), not unresolved project graph holes.

    Keep as telemetry (still in low_conf_edges) but exclude from actionable_low_conf_edges.
    """
    if not isinstance(pair, dict):
        return False
    reasons = pair.get("confidence_reasons") or []
    reason_l = " ".join(str(r).lower() for r in reasons if isinstance(r, str))
    is_dyn = bool(pair.get("is_dynamic")) or ("dynamic" in reason_l)
    if not is_dyn:
        return False

    dtype = str(pair.get("dynamic_type") or "").lower()
    raw = str(pair.get("raw") or pair.get("raw_module") or pair.get("module") or "").strip()
    expl = str(pair.get("confidence_explanation") or "")
    resolved = str(pair.get("resolved") or "").strip()

    # Explicit importlib / __import__ traces → always non-actionable for ACS
    # (includes static string loads and parser traces that mention the call form).
    if "import_module(" in expl or "__import__(" in expl or "importlib.import_module" in expl:
        return True

    # dynamic_type=static means LDSI recovered a concrete string literal
    if dtype in ("static", "string", "literal"):
        # Quoted raw like "\"wikifier.health\"" or '"./x"'
        if (raw.startswith("\"") and raw.endswith("\"")) or (raw.startswith("'") and raw.endswith("'")):
            return True
        # Unquoted but resolved/raw is a dotted package name (no path variables)
        cand = raw or resolved
        if cand and "${" not in cand and "+" not in cand:
            inner = cand.strip().strip("\"'")
            if inner and not any(ch in inner for ch in ("/", "\\", " ", "(", ")")):
                # pure module id literal (e.g. wikifier.health) — not a computed path
                if "." in inner or inner.isidentifier():
                    return True
    return False


def _edge_is_non_actionable_noise(pair: Dict[str, Any]) -> bool:
    """Union of external/stdlib noise + dynamic-literal noise (ACS actionable filter)."""
    return _edge_is_external_noise(pair) or _edge_is_dynamic_literal_noise(pair)


def classify_edge_agent_signal(
    pair: Dict[str, Any],
    low_threshold: float = 0.65,
) -> Dict[str, Any]:
    """Stable agent signal for one edge: skip vs investigate + reason_code.

    ACS v1.3 — agents should trust reason_code rather than free-text alone:
      skip: external_or_bare | dynamic_literal | high_confidence_ok
      investigate: unresolved_project | low_confidence_internal | low_confidence_resolved

    Pure helper; does not mutate *pair*.
    """
    if not isinstance(pair, dict):
        return {
            "agent_signal": "skip",
            "reason_code": "invalid_edge",
            "actionable": False,
        }
    is_ext = _edge_is_external_noise(pair)
    is_dyn = _edge_is_dynamic_literal_noise(pair)
    resolved = str(pair.get("resolved") or "").strip()
    sc = pair.get("confidence_score")
    conf = pair.get("confidence")
    scf: Optional[float] = float(sc) if isinstance(sc, (int, float)) else None
    if scf is None and conf == "low":
        scf = 0.5
    elif scf is None and conf == "high":
        scf = 0.9
    elif scf is None and conf == "medium":
        scf = 0.7

    if is_ext:
        return {
            "agent_signal": "skip",
            "reason_code": "external_or_bare",
            "actionable": False,
            "confidence_score": scf,
        }
    if is_dyn:
        return {
            "agent_signal": "skip",
            "reason_code": "dynamic_literal",
            "actionable": False,
            "confidence_score": scf,
        }
    if not resolved:
        # Project-local unresolved (not classified external) — agent may investigate
        return {
            "agent_signal": "investigate",
            "reason_code": "unresolved_project",
            "actionable": True,
            "confidence_score": scf if scf is not None else 0.4,
        }
    if scf is not None and scf < low_threshold:
        return {
            "agent_signal": "investigate",
            "reason_code": "low_confidence_internal",
            "actionable": True,
            "confidence_score": scf,
        }
    return {
        "agent_signal": "skip",
        "reason_code": "high_confidence_ok",
        "actionable": False,
        "confidence_score": scf,
    }


def compute_acs_summary(
    cache: Dict[str, Any],
    max_samples: int = 5,
    low_threshold: float = 0.65,
) -> Dict[str, Any]:
    """Lightweight ACS aggregate + bounded full-explanation samples.

    Scans resolved_pairs.
    O(E) but practical (E << total files at monorepo scale due to internal-only).
    Used for _acs_summary persistence + surfacing in get_project_status, health MCP,
    library.md "ACS Risk Snapshot", CLI, prompts.

    Returns stable shape with full (not truncated) confidence_explanation samples
    so agents can quote Recommendation: verbatim.

    additive fields (backward compatible):
      - actionable_low_conf_edges: low-conf edges excluding external/bare/stdlib noise
      - external_noise_edges: count of scored edges classified as external noise
      - sample_actionable_low_conf_explanations: samples for agent action only
    Agents should prefer actionable_* for next-steps; low_conf_edges remains full telemetry.

    ACS v1.2: also demotes dynamic string-literal noise (importlib.import_module(\"…\"),
    is_dynamic+dynamic_type=static) from actionable counts. Full low_conf telemetry unchanged.

    ACS v1.3: scores unresolved pairs too; adds reason_code histogram + agent_signal
    counts so agents can skip vs investigate without re-parsing free text. Prefer
    ``actionable_low_conf_edges`` + ``reason_code_counts`` for work selection.
    """
    # compute_acs_summary + get_acs_summary promoted first-class default (O(k) bounded samples via ACS/CIABRE, deque-style in practice) for 20k+ creative; format=summary paths in MCP/CLI/health default to this + barrel summary (per 48/58/50/57, crit2/5 long-term WS A).
    t0 = time.time()
    total = 0
    sum_score = 0.0
    scored_with_numeric = 0
    low_count = 0
    actionable_low = 0
    external_noise = 0
    dynamic_literal_noise = 0
    unresolved_project = 0
    reason_counts: Dict[str, int] = {}
    reason_code_counts: Dict[str, int] = {}
    agent_signal_counts: Dict[str, int] = {"skip": 0, "investigate": 0}
    samples: List[str] = []  # full expls for lowest-risk (prioritized)

    low_items: List[tuple] = []  # (score, expl) all low
    actionable_items: List[tuple] = []  # (score, expl, reason_code) project-internal only

    for rel, data in cache.items():
        if not isinstance(rel, str) or rel.startswith("_") or not isinstance(data, dict):
            continue
        for p in (data.get("resolved_pairs") or []):
            if not isinstance(p, dict):
                continue
            # v1.3: include unresolved edges (still demote external/dynamic noise)
            sig = classify_edge_agent_signal(p, low_threshold=low_threshold)
            reason_code = str(sig.get("reason_code") or "unknown")
            reason_code_counts[reason_code] = reason_code_counts.get(reason_code, 0) + 1
            asig = str(sig.get("agent_signal") or "skip")
            agent_signal_counts[asig] = agent_signal_counts.get(asig, 0) + 1

            is_ext = reason_code == "external_or_bare"
            is_dyn_lit = reason_code == "dynamic_literal"
            if is_ext:
                external_noise += 1
            if is_dyn_lit:
                dynamic_literal_noise += 1
            if reason_code == "unresolved_project":
                unresolved_project += 1

            total += 1
            sc = p.get("confidence_score")
            expl = p.get("confidence_explanation") or ""
            reasons = p.get("confidence_reasons") or []
            # Prefer numeric score; fall back to classifier estimate
            scf = sig.get("confidence_score")
            if isinstance(sc, (int, float)):
                scf = float(sc)
            if isinstance(scf, (int, float)):
                sum_score += float(scf)
                scored_with_numeric += 1
                is_low = float(scf) < low_threshold or reason_code == "unresolved_project"
                if is_low:
                    low_count += 1
                    # Prefer non-noise samples for agent-readable low_conf explanations
                    if expl and not is_ext and not is_dyn_lit:
                        low_items.append((float(scf), expl))
                    if sig.get("actionable"):
                        actionable_low += 1
                        label = expl or f"[{reason_code}] {p.get('raw') or p.get('raw_module') or '?'}"
                        actionable_items.append((float(scf), label, reason_code))
            elif sig.get("actionable"):
                # unresolved without score still counts as low/actionable
                low_count += 1
                actionable_low += 1
                label = expl or f"[{reason_code}] {p.get('raw') or p.get('raw_module') or '?'}"
                actionable_items.append((0.4, label, reason_code))
            # aggregate free-text reasons (filterable by agents)
            for r in reasons:
                if isinstance(r, str) and r:
                    reason_counts[r] = reason_counts.get(r, 0) + 1

    # Select up to max_samples lowest-score (highest risk) full explanations
    low_items.sort(key=lambda x: x[0])  # lowest first
    for scf, expl in low_items[:max_samples]:
        # keep full but defensively cap length for cache bloat (agents still get Recommendation sentence intact)
        safe_expl = expl if len(expl) <= 450 else expl[:447] + "..."
        samples.append(safe_expl)

    actionable_items.sort(key=lambda x: x[0])
    actionable_samples: List[str] = []
    actionable_sample_codes: List[str] = []
    for item in actionable_items[:max_samples]:
        scf, expl = item[0], item[1]
        code = item[2] if len(item) > 2 else ""
        safe_expl = expl if len(expl) <= 450 else expl[:447] + "..."
        actionable_samples.append(safe_expl)
        if code:
            actionable_sample_codes.append(code)

    avg = round(sum_score / scored_with_numeric, 2) if scored_with_numeric > 0 else 0.0
    top_reasons = sorted(reason_counts.items(), key=lambda x: -x[1])[:6]
    # Prefer reason_code histogram for agents (stable tokens)
    top_reason_codes = sorted(reason_code_counts.items(), key=lambda x: -x[1])[:8]

    return {
        "acs_version": "1.3",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_scored_edges": total,
        "avg_confidence": avg,
        "low_conf_edges": low_count,
        "actionable_low_conf_edges": actionable_low,
        "external_noise_edges": external_noise,
        "dynamic_literal_noise_edges": dynamic_literal_noise,
        "unresolved_project_edges": unresolved_project,
        "low_conf_threshold": low_threshold,
        "top_risk_reasons": dict(top_reasons),
        "reason_code_counts": dict(top_reason_codes),
        "agent_signal_counts": agent_signal_counts,
        "sample_low_conf_explanations": samples,  # full Recommendation text for agents
        "sample_actionable_low_conf_explanations": actionable_samples,
        "sample_actionable_reason_codes": actionable_sample_codes,
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
    """On-demand compute + guaranteed persistence for _acs_summary.

    Mirrors the cycles "guaranteed persist" hardening (see get_cycles: did_compute_cycles/analyses + set_* + save_cache).
    Safe for all read/query paths (MCP health(), get_project_status(), CLI `cycles`, sh library.md builders, direct Python):
    - If absent/empty (pre-persist cache, partial update-maps, direct MCP use, packaged paths), compute from
      resolved_pairs, set under RESERVED key,
      and if root provided, best-effort save_cache.
    - Never raises on persist side-effect; always returns usable summary (with full sample Recommendations for quoting).
    - Zero-dep, scalable O(E) scan (E=internal edges << files); enables agents to treat ACS aggregates/samples as
      always-available oracle in primary surfaces without requiring explicit update first.
    """
    acs = get_acs_summary(cache)
    # recompute when missing OR pre-1.3 (reason codes + unresolved)
    needs = (
        not acs
        or acs.get("total_scored_edges", 0) == 0
        or "actionable_low_conf_edges" not in acs
        or str(acs.get("acs_version") or "") < "1.3"
        or "reason_code_counts" not in acs
    )
    if needs:
        acs = compute_acs_summary(cache)
        set_acs_summary(cache, acs)
        if root is not None:
            from .. import cache_store as cs

            if cs.has_sqlite(Path(root)):
                cs.save_meta_key(Path(root), "_acs_summary", acs)
            else:
                save_cache(root, cache)
    return acs


def build_map_coverage(
    *,
    dirty_total: int = 0,
    files_parsed: int = 0,
    files_skipped: int = 0,
    files_to_reparse: int = 0,
    max_files: Optional[int] = None,
    parseable_files: int = 0,
    zero_dirty_fast_path: bool = False,
    acs_version: Optional[str] = None,
    cache_backend: Optional[str] = None,
    directory: Optional[str] = None,
) -> Dict[str, Any]:
    """Structured map completeness for agents (avoid mistaking partial budget for done).

    ``files_remaining_dirty`` is the dirty work not completed in this run
    (typically ``files_skipped`` under max_files, else 0 when fully processed).
    """
    remaining = int(files_skipped or 0)
    if remaining == 0 and files_to_reparse and files_parsed is not None:
        # full process of this batch with no budget skip
        remaining = max(0, int(files_to_reparse) - int(files_parsed or 0))
    complete = (
        bool(zero_dirty_fast_path)
        or (int(dirty_total or 0) == 0 and int(files_skipped or 0) == 0)
        or (int(files_skipped or 0) == 0 and int(files_to_reparse or 0) == int(files_parsed or 0))
    )
    # Budget truncation: not complete
    if int(files_skipped or 0) > 0:
        complete = False
    return {
        "complete": complete,
        "dirty_total": int(dirty_total or 0),
        "files_to_reparse": int(files_to_reparse or 0),
        "files_parsed": int(files_parsed or 0),
        "files_skipped": int(files_skipped or 0),
        "files_remaining_dirty": int(remaining),
        "budget_max_files": max_files,
        "parseable_files": int(parseable_files or 0),
        "scoped_directory": directory,
        "zero_dirty_fast_path": bool(zero_dirty_fast_path),
        "acs_version": acs_version,
        "cache_backend": cache_backend,
        "agent_note": (
            "success≠map-complete when files_remaining_dirty>0 or complete=false; "
            "re-run update_maps (or raise max_files) until complete=true"
        ),
    }
