"""
wikifier/contracts.py

Gap #1 Pre-Wave 0: Shared Cross-Cutting Contracts (FROZEN)

This is the single authoritative, frozen definition of all contracts that the
four Gap #1 phases (Cycles, BREE/Barrels, CDIA, Modern Resolution) and future
work depend on.

It eliminates the highest-risk areas identified across all implementation plans:
- Inconsistent metadata shapes for conditional/dynamic analysis, traces, resolution.
- Fragile wikifier.sh pipeline serialization of rich/nested data.
- Ad-hoc cache key usage and incoherent invalidation.
- Node identity drift between v0 (raw) and v1 (canonical physical).
- Uncontrolled semantic tags and versioning.

Design principles (binding):
- Additive and defensive first. Old data always loads. Never crash on decode.
- Versioned artifacts (field names carry _vN; content carries "version" where needed).
- Dual emission / dual read supported for >=2 minor releases.
- Python dataclasses are the source of truth for internal logic.
- .to_dict() / .from_dict() + JSON forms for pipe, cache, MCP, library.md.
- All helpers are pure, zero-dependency (stdlib only), importable anywhere.
- Shell (wikifier.sh) treats *_vN values as opaque strings; all parsing in Python.

Consumers (import from here):
- wikifier/parsers/javascript.py, python.py (for emission shapes + pack helpers + R2 ACS canonical compute)
- wikifier/import_cache.py (RICH_KEYS, reserved keys, normalize)
- wikifier.sh (via python -c "from wikifier.contracts import ...")
- wikifier/resolution.py, diagnostics.py, parsers/bree.py
- mcp/server.py, future cdia.py, bree extensions, etc.
- Tests and dogfood scripts

R2 ACS (compute_acs_confidence) is the single source for confidence_score/reasons/explanation across the system.

Versioning of this contract module: see __contracts_version__
Any shape change requires new *_vN field name + migration note here + CHANGELOG.

DO NOT implement phase-specific detectors, expanders, or resolvers in this file.
This is purely the shared foundation.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Literal, Optional, Tuple, Union
from datetime import datetime, timezone
import fnmatch
from pathlib import Path

# =============================================================================
# Module Version & Status
# =============================================================================

__contracts_version__ = "1.0.0-prewave0-frozen"
FROZEN_DATE = "2026-05-17"
STATUS = "FROZEN - Pre-Wave 0 complete. All phases must use these definitions."


# =============================================================================
# 1. Core Rich Analysis Dataclasses (Python API + JSON forms)
# =============================================================================

@dataclass(frozen=True)
class AnalysisTraceEntry:
    """
    Single detector firing record for explainability.

    Used inside ConditionalAnalysis.analysis_trace and DynamicAnalysis.analysis_trace.
    Appears in diagnostics, MCP responses, "why low confidence?" explanations,
    ACS confidence_reasons, and library.md.
    """
    detector: str
    fired: bool
    evidence: str
    score_contrib: float
    notes: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AnalysisTraceEntry":
        """Defensive: tolerates missing keys, wrong types, extra keys."""
        if not isinstance(d, dict):
            d = {}
        return cls(
            detector=str(d.get("detector", ""))[:100],
            fired=bool(d.get("fired", False)),
            evidence=str(d.get("evidence", ""))[:500],
            score_contrib=float(d.get("score_contrib", 0.0)),
            notes=[str(x)[:200] for x in (d.get("notes") or [])][:20],
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))


@dataclass
class ConditionalAnalysis:
    """
    Structured output for "this import/edge is conditional".

    Replaces the old flat "is_conditional" + "conditional_context" (which remain
    for transition via legacy synthesis).

    confidence here is *detector agreement* only (0.0-1.0). It does NOT affect
    the edge's primary confidence (which is forced low for any conditional).
    """
    is_conditional: bool = False
    semantic_tags: List[str] = field(default_factory=list)
    predicate_snippet: Optional[str] = None
    detectors_fired: List[str] = field(default_factory=list)
    analysis_trace: List[AnalysisTraceEntry] = field(default_factory=list)
    confidence: float = 0.0
    degraded: bool = False  # True when synthesized from legacy flat fields

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ConditionalAnalysis":
        if not isinstance(d, dict):
            d = {}
        trace_raw = d.get("analysis_trace") or []
        trace = [
            AnalysisTraceEntry.from_dict(t) for t in trace_raw
            if isinstance(t, dict)
        ][:50]
        return cls(
            is_conditional=bool(d.get("is_conditional", False)),
            semantic_tags=[str(x)[:50] for x in (d.get("semantic_tags") or [])][:30],
            predicate_snippet=(str(d.get("predicate_snippet"))[:300] if d.get("predicate_snippet") else None),
            detectors_fired=[str(x)[:50] for x in (d.get("detectors_fired") or [])][:20],
            analysis_trace=trace,
            confidence=float(d.get("confidence", 0.0)),
            degraded=bool(d.get("degraded", False)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_conditional": self.is_conditional,
            "semantic_tags": self.semantic_tags,
            "predicate_snippet": self.predicate_snippet,
            "detectors_fired": self.detectors_fired,
            "analysis_trace": [t.to_dict() for t in self.analysis_trace],
            "confidence": round(self.confidence, 4),
            "degraded": self.degraded,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))


@dataclass
class DynamicAnalysis:
    """
    Structured output for complex dynamic imports (expressions, templates, etc.).

    Replaces / augments the old flat is_dynamic + dynamic_type + expr_raw +
    dynamic_candidates + analysis_* fields during transition.

    Primary edge confidence is forced low for non-static dynamics.
    The analysis object provides the "why" and candidate recovery.
    """
    dynamic_type: str = "static"          # "static" | "template_literal" | "expression" | "unknown"
    complexity: str = "simple"            # "simple" | "moderate" | "high" | "opaque"
    semantic_tags: List[str] = field(default_factory=list)
    expr_raw: Optional[str] = None
    dynamic_candidates: List[Dict[str, Any]] = field(default_factory=list)
    detectors_fired: List[str] = field(default_factory=list)
    analysis_trace: List[AnalysisTraceEntry] = field(default_factory=list)
    source_variable: Optional[str] = None
    dataflow_trace: List[str] = field(default_factory=list)
    confidence: float = 0.0
    degraded: bool = False

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DynamicAnalysis":
        if not isinstance(d, dict):
            d = {}
        trace = [
            AnalysisTraceEntry.from_dict(t) for t in (d.get("analysis_trace") or [])
            if isinstance(t, dict)
        ][:50]
        cands = d.get("dynamic_candidates") or []
        return cls(
            dynamic_type=str(d.get("dynamic_type", "static"))[:30],
            complexity=str(d.get("complexity", d.get("dynamic_complexity", "simple")))[:20],
            semantic_tags=[str(x)[:50] for x in (d.get("semantic_tags") or [])][:30],
            expr_raw=(str(d.get("expr_raw"))[:2000] if d.get("expr_raw") else None),
            dynamic_candidates=[dict(c) for c in cands if isinstance(c, dict)][:100],
            detectors_fired=[str(x)[:50] for x in (d.get("detectors_fired") or [])][:20],
            analysis_trace=trace,
            source_variable=(str(d.get("source_variable"))[:100] if d.get("source_variable") else None),
            dataflow_trace=[str(x)[:300] for x in (d.get("dataflow_trace") or [])][:20],
            confidence=float(d.get("confidence", 0.0)),
            degraded=bool(d.get("degraded", False)),
        )

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Keep both names for transition compatibility with old "dynamic_complexity"
        d.setdefault("dynamic_complexity", d.get("complexity"))
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))


@dataclass(frozen=True)
class ResolutionMetadata:
    """
    Rich strategy + context information attached to a Resolution (Phase 4).

    Stored under resolved_pair["resolution_metadata"] (or "metadata" during early
    transition) and also inside the res_meta_v1 pipe field.

    Extensible: Phase 4 and later may add fields as long as they are JSON-serializable
    primitives / lists / dicts of primitives. Use from_dict defensively.
    """
    strategy: str
    matched_condition: Optional[str] = None
    exports_key: Optional[str] = None
    ts_alias: Optional[str] = None
    symlink_detected: bool = False
    original_logical: Optional[str] = None
    workspace_pkg: Optional[str] = None
    attempted: List[str] = field(default_factory=list)
    # Additive fields for full compatibility with existing resolution.py usage
    # (package_imports_key, extra, etc.). Contracts remains the source of truth.
    package_imports_key: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ResolutionMetadata":
        if not isinstance(d, dict):
            d = {}
        return cls(
            strategy=str(d.get("strategy", "unknown"))[:80],
            matched_condition=(str(d.get("matched_condition"))[:100] if d.get("matched_condition") else None),
            exports_key=(str(d.get("exports_key"))[:200] if d.get("exports_key") else None),
            ts_alias=(str(d.get("ts_alias"))[:100] if d.get("ts_alias") else None),
            symlink_detected=bool(d.get("symlink_detected", False)),
            original_logical=(str(d.get("original_logical"))[:300] if d.get("original_logical") else None),
            workspace_pkg=(str(d.get("workspace_pkg"))[:100] if d.get("workspace_pkg") else None),
            attempted=[str(x)[:80] for x in (d.get("attempted") or [])][:20],
            package_imports_key=(str(d.get("package_imports_key"))[:200] if d.get("package_imports_key") else None),
            extra=dict(d.get("extra") or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))


# =============================================================================
# 2. Pipeline Serialization Strategy v1 (Critical - The Highest Risk Item)
# =============================================================================

# Field names that appear after the legacy 10 positional fields in wikifier.sh lines.
# Format example (one logical line, no spaces around =):
# src|raw|...|b_depth|cdia_v1=eyJjb25k...|barrel_v2=eyJ2aWFf...|res_meta_v1=eyJzdHJhd...
#
# Shell rule (binding): NEVER parse inside the value. Just printf the |key=val suffix.
# Python rule (binding): always use the decode helpers below. On any failure -> None + degraded.

PIPE_FIELD_CDIA_V1 = "cdia_v1"        # carries {"conditional_analysis": {...}, "dynamic_analysis": {...}}
PIPE_FIELD_BARREL_V2 = "barrel_v2"    # carries barrel chain, hops, detector, mtimes_sig, is_partial
PIPE_FIELD_RES_META_V1 = "res_meta_v1"  # carries ResolutionMetadata + strategy details
PIPE_FIELD_CYCLE_V1 = "cycle_v1"      # future (Phase 1)

RICH_PIPE_FIELDS: Tuple[str, ...] = (
    PIPE_FIELD_CDIA_V1,
    PIPE_FIELD_BARREL_V2,
    PIPE_FIELD_RES_META_V1,
    PIPE_FIELD_CYCLE_V1,
)


def encode_v1_payload(data: Dict[str, Any]) -> str:
    """
    Typed versioned base64 payload (the only sanctioned way to carry complex
    nested structures through the wikifier.sh | pipe).

    Rules (strict, never relax):
    - Compact JSON (no whitespace): separators=(",", ":")
    - UTF-8 only inside
    - URL-safe base64, NO PADDING (= stripped)
    - On any error in caller -> treat as absent (graceful fallback)
    """
    if not data or not isinstance(data, dict):
        return ""
    try:
        compact = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        raw = compact.encode("utf-8")
        b64 = base64.urlsafe_b64encode(raw).rstrip(b"=")
        return b64.decode("ascii")
    except Exception:
        return ""


def decode_v1_payload(raw: str) -> Optional[Dict[str, Any]]:
    """
    Extremely defensive decoder. Returns None on ANY failure (bad padding,
    invalid utf8, bad json, non-dict, etc.). Never raises. Caller must fall back.
    """
    if not raw or not isinstance(raw, str):
        return None
    try:
        # Restore padding
        pad_needed = (-len(raw) % 4)
        padded = raw + ("=" * pad_needed)
        decoded_bytes = base64.urlsafe_b64decode(padded)
        obj = json.loads(decoded_bytes.decode("utf-8"))
        if isinstance(obj, dict):
            return obj
        return None
    except Exception:
        return None


def pack_cdia_v1(
    conditional: Optional[ConditionalAnalysis],
    dynamic: Optional[DynamicAnalysis],
) -> str:
    """Produce the value for cdia_v1=... field."""
    payload: Dict[str, Any] = {
        "conditional_analysis": conditional.to_dict() if conditional is not None else None,
        "dynamic_analysis": dynamic.to_dict() if dynamic is not None else None,
    }
    return encode_v1_payload(payload)


def unpack_cdia_v1(raw: str) -> Dict[str, Any]:
    """Decode cdia_v1 payload into dict form (ready for cache / pair)."""
    d = decode_v1_payload(raw) or {}
    ca_d = d.get("conditional_analysis")
    da_d = d.get("dynamic_analysis")
    return {
        "conditional_analysis": ConditionalAnalysis.from_dict(ca_d).to_dict() if isinstance(ca_d, dict) else None,
        "dynamic_analysis": DynamicAnalysis.from_dict(da_d).to_dict() if isinstance(da_d, dict) else None,
    }


def pack_res_meta_v1(meta: Union[Dict[str, Any], ResolutionMetadata]) -> str:
    if isinstance(meta, ResolutionMetadata):
        d = meta.to_dict()
    elif isinstance(meta, dict):
        d = meta
    else:
        d = {}
    return encode_v1_payload({"resolution_metadata": d})


def unpack_res_meta_v1(raw: str) -> Dict[str, Any]:
    d = decode_v1_payload(raw) or {}
    rm_d = d.get("resolution_metadata") or d
    return {
        "resolution_metadata": ResolutionMetadata.from_dict(rm_d).to_dict() if isinstance(rm_d, dict) else None,
    }


# Aliases for names that some modules (javascript.py parser import sites) were
# written against during early Phase 4 planning. They delegate to the canonical
# pack/unpack implementations above. This keeps all call sites working while
# we finish the migration to contracts as the single source.
encode_res_meta_v1 = pack_res_meta_v1
decode_res_meta_v1 = unpack_res_meta_v1


# Barrel v2 packing is intentionally lighter here (bree.py owns the detailed
# ExpandedChainResult / ReexportHop). Use encode_v1_payload on a dict matching
# the shape in the contracts doc for now. Future: central BarrelAnalysis dataclass.


def parse_pipeline_line(line: str) -> Dict[str, Any]:
    """
    Robust parser for extended wikifier.sh resolved-pair lines.

    Supports both pure legacy (10 fields) and the new hybrid form with trailing
    |cdia_v1=...|barrel_v2=... etc.

    Returns:
        {
            "src": "...", "raw": "...", "resolved": "...", "confidence": "...",
            "is_dynamic": "...", ... (legacy strings),
            "rich_payloads": {"cdia_v1": "ey..", "barrel_v2": "...", ...},
            "legacy_rich": {...}   # convenience copy of the 6-10 fields
        }

    Never raises. Always returns a usable dict.
    """
    result: Dict[str, Any] = {
        "raw": "",
        "resolved": "",
        "confidence": "medium",
        "rich_payloads": {},
        "legacy_rich": {},
    }
    if not line or not isinstance(line, str):
        return result

    parts = line.strip().split("|")
    # Positional legacy mapping (first 10)
    pos_keys = [
        "src", "raw", "resolved", "confidence",
        "is_dynamic", "dynamic_type", "is_conditional", "conditional_context",
        "via_barrel", "barrel_depth",
    ]
    for i, key in enumerate(pos_keys):
        if i < len(parts):
            val = parts[i]
            result[key] = val
            if key in ("is_dynamic", "is_conditional", "via_barrel"):
                result["legacy_rich"][key] = (val == "true")
            else:
                result["legacy_rich"][key] = val

    # Trailing key=value rich payloads (opaque to shell)
    for p in parts[10:]:
        if not p:
            continue
        if "=" in p:
            k, v = p.split("=", 1)
            if k and k in RICH_PIPE_FIELDS:
                result["rich_payloads"][k] = v

    # Backfill common aliases for callers that expect the old names at top level
    result.setdefault("module", result.get("resolved", ""))
    return result


# =============================================================================
# 3. Cache Keys, RICH_KEYS & Invalidation Protocol (Single Source of Truth)
# =============================================================================

# Current flat legacy keys that must be preserved through update_file_data.
# New nested keys (from decoded vN payloads) are added here so they also survive.
LEGACY_RICH_KEYS: Tuple[str, ...] = (
    "is_dynamic", "dynamic_type",
    "is_conditional", "conditional_context",
    "via_barrel", "barrel_depth", "barrel_chain",
    "barrel_v2", "barrel_detector",
    "expr_raw", "dynamic_candidates", "dynamic_complexity",
    "analysis_methods", "analysis_notes",
    "confidence_score", "confidence_reasons", "confidence_explanation",
    "diagnostic", "resolved_path",
)

NEW_RICH_STRUCT_KEYS: Tuple[str, ...] = (
    "conditional_analysis",
    "dynamic_analysis",
    "resolution_metadata",
    "barrel_analysis",      # future structured form of barrel_v2
    "cycle_participation",  # future
)

RICH_KEYS: Tuple[str, ...] = LEGACY_RICH_KEYS + NEW_RICH_STRUCT_KEYS


# Reserved top-level keys in the import_cache (never collide with file relpaths).
# All subsystems (including future phases) register here.
RESERVED_TOP_LEVEL_KEYS: Dict[str, str] = {
    "_reverse_dependencies": "Core reverse-dependency map (target -> [sources]). Always authoritative.",
    "_cycles": "Phase 1: Tarjan SCC results, stats, per-cycle metadata. Must record node_identity_version (v0 raw / v1 canonical). Includes graph_signature for reuse. Wave 2: carries 'reused' (bool) + 'reuse_reason'. Wave 3: full delta short-circuit *in main update-maps 3d path* + iterative Tarjan harness-tested + reuse surfaced broadly via get_cycles_reuse_stats (health/diag/MCP/library). Canonical v1 prep: build_dependency_graph + computes support use_canonical + canonical_for_bree remap (Phase 4 flip ready, harnessed). Uses iterative (stack-sim) Tarjan.",
    "_cycle_analyses": "P3 CIABRE v1.2 (R5): per-SCC severity (real-dogfood tuned scoring), blast radius, weakest links (risk-ranked dyn/cond/bar/low-conf), ranked practical recs with rationale/hint/safety from extensible registry. Versioned, persisted on update-maps. See import_cache.py. Wave 2/3: also carries graph_signature + reused/reuse_reason; delta short applies in update path.",
    "_graph_integrity": "Phase 1: warnings, orphan counts, summary for health/MCP.",
    "_graph_signature": "Phase 1 extension (cycles long-term): short stable hash of the full dependency graph adj-list (v0 or v1 canonical nodes). Enables safe skip of Tarjan/CIABRE on match (incremental/delta). Populated + guaranteed. Wave 3+: delta short in main 3d path + compute; canonical v1 graph nodes supported; broad reuse stats (get_cycles_reuse_stats) in health/diag/MCP/library; harnessed.",
    "_barrel_resolutions": "Phase 2: persistent BarrelChainResolution / ExpandedChainResult cache (mtimes_snapshot decoupled).",
    "_barrel_file_index": "Phase 2: barrel -> chain ids + importer reverse index for fast invalidation.",
    "_barrel_invalidation_log": "Wave 4 audit (this continuation): lightweight bounded append-only list of recent BarrelInvalidationReport dicts (with ts) for 'why importer dirtied' traceability across daemon/check-changes/update-maps runs. Appended opportunistically on real barrel-driven invalidations (DEBUG or always in delta paths). Bounded (~100), human/JSON inspectable; never required for correctness. See import_cache.append_barrel_invalidation_log + bree reports.",
    # Wave 2/4 observability (BRC): summary stats + get_barrel_*_reports on-demand + optional persisted _barrel_invalidation_log for audit. Reports carry importer + triggering_barrels + chain_ids + reason + detector + v1 stamp for diagnostics/health/MCP/journal "why re-parsed". Dedicated MCP get_barrel_reports(limit, include_log) now provides full rich surface for agents (complements embedded samples in get_project_status/health). See bree.py:BarrelInvalidationReport + build_* + prune + mcp/server.py:get_barrel_reports.
    "_resolution_context": "Phase 4: ProjectContext snapshot, config mtimes, workspace/TS maps for incremental reuse.",
    "_cdia_summary": "Phase 3: aggregate semantic tag statistics (optional, for health + MCP).",
    "_resolution_diagnostics": "Diagnostics layer aggregate (counts + samples by category). Wave 3: get_resolution_diagnostics + ensure_diagnostics_aggregate implemented in import_cache (delegates summarize + injects cycles_reuse/graph_signature stats for unified observability). Wave 4: optional guaranteed persist now wired into update-maps 3d (both sh) via ensure_ after ACS (so library/MCP always see fresh without extra on-demand compute).",
    "_acs_summary": "Lightweight ACS aggregates (R2 canonical): total_scored_edges, avg_confidence, low_conf_edges<0.65, top_risk_reasons counts, bounded sample_low_conf_explanations (full Recommendation text). Persisted every update-maps via import_cache.compute_acs_summary + set. Enables health/MCP/library surfacing uniformity for agents (biggest trust gap fix).",
    "_acs_summary_version": "Companion for _acs_summary (future).",
}

# Invalidation protocol (high-level, implemented once in import_cache + called by phases)
#
# During perform_first_pass... / update-maps:
#   1. mtime + --full driven dirty set (existing).
#   2. Each subsystem augments:
#        dirty |= barrel_engine.get_files_with_stale_barrel_chains(cache, dirty)
#        dirty |= resolution_engine.get_files_with_stale_contexts(cache, dirty)
#        ...
#   3. Reparse the union.
#   4. Subsystems refresh their _xxx structures from the fresh resolved_pairs.
#
# contracts only supplies the names and the expectation that every subsystem
# exposes a pure "get_dirty_files(cache, known_dirty) -> set" hook.
# A lightweight registry may be added later under get_invalidation_registry().


def is_reserved_top_level_key(key: str) -> bool:
    return bool(key) and (key.startswith("_") or key in RESERVED_TOP_LEVEL_KEYS)


# =============================================================================
# 4. Node Identity Versioning (Canonical Path Contract)
# =============================================================================

NODE_IDENTITY_VERSION_V0 = "v0"   # Raw "resolved" strings as emitted by old resolvers / pre-Phase 4
NODE_IDENTITY_VERSION_V1 = "v1"   # Physical canonical via resolution.to_canonical_rel(..., follow_symlinks=True)
NODE_IDENTITY_VERSION_CURRENT = NODE_IDENTITY_VERSION_V1


def annotate_node_identity(data: Dict[str, Any], version: Optional[str] = None) -> Dict[str, Any]:
    """Return a copy of data with node_identity_version stamped (for cycles, barrel_chains, graphs)."""
    if not isinstance(data, dict):
        data = {}
    out = dict(data)
    out["node_identity_version"] = version or NODE_IDENTITY_VERSION_CURRENT
    return out


def get_node_identity_version(data: Dict[str, Any]) -> str:
    """Safe reader. Defaults to v0 for legacy persisted structures."""
    if not isinstance(data, dict):
        return NODE_IDENTITY_VERSION_V0
    v = data.get("node_identity_version")
    if v in (NODE_IDENTITY_VERSION_V0, NODE_IDENTITY_VERSION_V1):
        return v
    return NODE_IDENTITY_VERSION_V0


# =============================================================================
# 5. Semantic Tag Vocabulary (Append-Only, Versioned)
# =============================================================================

CONDITIONAL_SEMANTIC_TAGS: Tuple[str, ...] = (
    "control_flow", "if_statement", "ternary", "switch_case", "try_catch", "loop",
    "feature_flag", "env_check", "dev_only", "prod_only", "lazy_loading",
    "runtime_optional", "dead_code_guard", "error_boundary", "platform_check",
)

DYNAMIC_SEMANTIC_TAGS: Tuple[str, ...] = (
    "computed_path", "template_substitution", "env_substitution", "map_lookup",
    "call_expression", "alias_dataflow", "var_substitution", "path_api",
    "webpack_magic", "system_import", "require_context", "react_lazy",
    "next_dynamic", "conditional_dynamic",
)

ALL_SEMANTIC_TAGS: Tuple[str, ...] = CONDITIONAL_SEMANTIC_TAGS + DYNAMIC_SEMANTIC_TAGS


def is_valid_semantic_tag(tag: str, category: Literal["conditional", "dynamic", "any"] = "any") -> bool:
    """Check a semantic tag against the known vocabulary (append-only)."""
    if not isinstance(tag, str):
        return False
    if category == "conditional":
        return tag in CONDITIONAL_SEMANTIC_TAGS
    if category == "dynamic":
        return tag in DYNAMIC_SEMANTIC_TAGS
    return tag in ALL_SEMANTIC_TAGS


# =============================================================================
# 6. Legacy Migration Helpers (Transition Support)
# =============================================================================

def synthesize_conditional_from_legacy(
    is_conditional: bool,
    conditional_context: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Produce a ConditionalAnalysis-shaped dict from the old flat fields.
    Always sets degraded=True so consumers know this came from pre-CDIA data.
    """
    if not is_conditional:
        return {"is_conditional": False, "semantic_tags": [], "degraded": False}

    tags: List[str] = []
    ctx = (conditional_context or "").lower()
    if any(k in ctx for k in ("if", "else")):
        tags.append("control_flow")
    if "?" in ctx or "ternary" in ctx:
        tags.append("ternary")
    if not tags:
        tags.append("control_flow")

    ca = ConditionalAnalysis(
        is_conditional=True,
        semantic_tags=tags,
        predicate_snippet=conditional_context,
        detectors_fired=["legacy-heuristic"],
        confidence=0.3,
        degraded=True,
    )
    return ca.to_dict()


def synthesize_dynamic_from_legacy(
    is_dynamic: bool,
    dynamic_type: str = "static",
    expr_raw: Optional[str] = None,
    dynamic_candidates: Optional[List[Dict[str, Any]]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Analogous legacy -> DynamicAnalysis dict (degraded)."""
    if not is_dynamic and dynamic_type == "static":
        return {"dynamic_type": "static", "complexity": "simple", "degraded": False}

    da = DynamicAnalysis(
        dynamic_type=dynamic_type or "expression",
        complexity=kwargs.get("dynamic_complexity", "moderate"),
        expr_raw=expr_raw,
        dynamic_candidates=dynamic_candidates or [],
        detectors_fired=["legacy-ldsi"],
        confidence=0.4,
        degraded=True,
    )
    return da.to_dict()


# =============================================================================
# 7. Convenience & Diagnostics
# =============================================================================

def get_contracts_info() -> Dict[str, Any]:
    """For health, MCP diagnostics, and agent introspection."""
    base = {
        "contracts_version": __contracts_version__,
        "frozen_date": FROZEN_DATE,
        "status": STATUS,
        "rich_pipe_fields": list(RICH_PIPE_FIELDS),
        "reserved_top_level_keys": list(RESERVED_TOP_LEVEL_KEYS.keys()),
        "node_identity_versions": [NODE_IDENTITY_VERSION_V0, NODE_IDENTITY_VERSION_V1],
        "num_conditional_tags": len(CONDITIONAL_SEMANTIC_TAGS),
        "num_dynamic_tags": len(DYNAMIC_SEMANTIC_TAGS),
    }
    # M2 A0+ additive extension (safe; evaluated at call time after full module load)
    try:
        base["m2_contracts_version"] = M2_CONTRACTS_VERSION
        base["m2_shapes"] = [
            "ScopeSpec_v1", "ProgressEvent_v1", "UpdateRun_v1",
            "PartialResult_v1", "ReverseDependencyIndex_v1",
            "ScopeSpecV1", "ProgressEventV1", "UpdateRunV1",
            "PartialResultV1", "ReverseDependencyIndexV1",
        ]
        base["m2_reserved_keys"] = [
            k for k in RESERVED_TOP_LEVEL_KEYS if k.startswith("_reverse_dependency") or k.startswith("_update") or k.startswith("_partial")
        ]
    except Exception:
        pass  # defensive: if M2 section not yet loaded (impossible post-import) or during smoke
    return base


def enrich_diagnostic_with_analysis(
    diagnostic: Dict[str, Any],
    *,
    conditional: Optional[ConditionalAnalysis] = None,
    dynamic: Optional[DynamicAnalysis] = None,
    resolution_meta: Optional[ResolutionMetadata] = None,
) -> Dict[str, Any]:
    """Non-destructive enrichment of a Diagnostic dict (used by diagnostics.py + phases)."""
    d = dict(diagnostic) if isinstance(diagnostic, dict) else {}
    details = d.setdefault("details", {})
    if conditional and conditional.is_conditional:
        details.setdefault("conditional_analysis", conditional.to_dict())
    if dynamic and dynamic.dynamic_type != "static":
        details.setdefault("dynamic_analysis", dynamic.to_dict())
    if resolution_meta:
        details.setdefault("resolution_metadata", resolution_meta.to_dict())
    return d


# =============================================================================
# 8. Actionable Confidence System (ACS) Helpers — R2 Reliability & Scale Follow-up
# Single source of truth for numeric score + canonical reasons + high-quality
# decision-oriented confidence_explanation strings.
#
# Guarantees identical behavior and output quality between javascript.py and
# python.py parsers (no drift at monorepo scale). Explanations are concise,
# evidence-backed, and prescriptive so agents can make reliable calls from
# the string alone (e.g. "safe to auto-refactor?", "high blast-radius risk").
#
# Additive R2 extension (non-breaking to frozen data contracts / dataclasses).
# Placed in contracts per design (parsers, MCP, diagnostics all import here).
# =============================================================================

def compute_acs_confidence(
    base_conf: str,
    *,
    is_dynamic: bool = False,
    dynamic_type: str = "static",
    is_conditional: bool = False,
    barrel_depth: int | None = None,
    via_barrel: bool = False,
    resolved_path: str | None = None,
    # Rich signals (CDIA Phase 3, Resolution Phase 4, Cycles Phase 1)
    conditional_analysis: dict | None = None,
    dynamic_analysis: dict | None = None,
    resolution_metadata: dict | None = None,
    strategy: str | None = None,
    in_cycle: bool = False,
) -> tuple[float, list[str], str]:
    """
    Canonical ACS implementation (P2 base + F2 explanations + R2 hardening).

    - Preserves exact prior penalty math and reason tokens for backward compat
      with caches, tests, harness, library.md, and existing agent prompts.
    - Produces noticeably higher-quality, consistent, actionable
      `confidence_explanation` strings optimized for agent decision-making.
    - Works identically from 10-file projects to 20k+ file monorepos (pure,
      bounded work per edge; generation cost <<1us).
    - Reasons use stable "base:*", "tag:*", "detector:*", "strategy:*", etc.
      vocabulary (filterable, aggregatable).
    - Explanations are self-contained narratives + specific recommendations.

    Used by: parsers (via thin _compute wrapper for compat), MCP get_*, prompts,
    gap1_validation_harness, future cdia/bree consumers.
    """
    base_map = {
        "high": 0.90,
        "medium": 0.60,
        "low": 0.30,
        "unresolved": 0.10,
    }
    score = base_map.get(base_conf, 0.50)
    reasons: list[str] = [f"base:{base_conf}"]

    # Legacy + rich factor penalties (order-stable; exact prior values)
    if is_conditional:
        score -= 0.22
        reasons.append("conditional_context")

    if is_dynamic:
        if dynamic_type == "expression":
            score -= 0.35
            reasons.append("dynamic_expression")
        elif dynamic_type == "template_literal":
            score -= 0.18
            reasons.append("dynamic_template")
        else:
            score -= 0.12
            reasons.append("dynamic")

    if barrel_depth is not None and barrel_depth > 1:
        if barrel_depth >= 3:
            score -= 0.28
            reasons.append(f"barrel_depth={barrel_depth}")
        else:
            score -= 0.14
            reasons.append(f"barrel_depth={barrel_depth}")

    if via_barrel:
        reasons.append("via_barrel")

    if not resolved_path:
        if base_conf not in ("low", "unresolved"):
            score -= 0.12
            reasons.append("no_resolved_path")

    # Rich CDIA / Resolution / Cycle extensions (identical to prior F2)
    ca = conditional_analysis or {}
    da = dynamic_analysis or {}
    rm = resolution_metadata or {}
    strat = strategy or (rm.get("strategy") if isinstance(rm, dict) else None) or ""

    if ca.get("is_conditional") or is_conditional:
        tags = ca.get("semantic_tags") or []
        if not tags and is_conditional:
            tags = ["control_flow"]
        for tag in tags:
            pen = 0.0
            rsn = f"tag:{tag}"
            if tag in ("dev_only", "dead_code_guard"):
                pen = 0.20
            elif tag in ("runtime_optional", "lazy_loading"):
                pen = 0.15
            elif tag in ("feature_flag", "env_check", "prod_only", "platform_check"):
                pen = 0.07
            elif tag in ("try_catch", "error_boundary"):
                pen = 0.09
            else:
                pen = 0.12
            score -= pen
            if rsn not in reasons:
                reasons.append(rsn)
        for det in (ca.get("detectors_fired") or []):
            rsn = f"detector:{det}"
            if rsn not in reasons:
                reasons.append(rsn)
        det_conf = float(ca.get("confidence", 1.0) or 1.0)
        if det_conf < 0.5:
            score -= 0.05
            if "low_detector_agreement" not in reasons:
                reasons.append("low_detector_agreement")

    dyn_type_eff = (da.get("dynamic_type") or ("expression" if is_dynamic else "static"))
    if dyn_type_eff != "static" or is_dynamic:
        tags = da.get("semantic_tags") or []
        comp = da.get("complexity", "simple")
        if not tags and is_dynamic:
            tags = ["computed_path"] if dynamic_type != "static" else []
        for tag in tags:
            pen = 0.0
            rsn = f"tag:{tag}"
            if tag in ("webpack_magic", "system_import", "require_context"):
                pen = 0.30
            elif tag in ("react_lazy", "next_dynamic", "conditional_dynamic"):
                pen = 0.22
            elif tag in ("call_expression", "alias_dataflow", "path_api"):
                pen = 0.18
            elif tag in ("tagged_template", "registry_map", "multi_condition_feature_wrapper", "call_produced_path"):
                # Phase 1 creative signals: higher penalty for extremely creative patterns (opaque to static analysis)
                pen = 0.25 if comp in ("high", "opaque") else 0.17
            else:
                pen = 0.12 if comp in ("high", "opaque") else 0.08
            score -= pen
            if rsn not in reasons:
                reasons.append(rsn)
        for det in (da.get("detectors_fired") or []):
            rsn = f"detector:{det}"
            if rsn not in reasons:
                reasons.append(rsn)
        if comp in ("high", "opaque"):
            score -= 0.08
            ctag = f"complexity:{comp}"
            if ctag not in reasons:
                reasons.append(ctag)

    if strat:
        rsn = f"strategy:{strat}"
        if rsn not in reasons:
            reasons.append(rsn)
        strat_l = str(strat).lower()
        if any(k in strat_l for k in ("unresolved", "fallback", "guessed", "bare-heuristic", "legacy", "unknown")):
            score -= 0.18
            if "weak_resolution_strategy" not in reasons:
                reasons.append("weak_resolution_strategy")
        elif any(k in strat_l for k in ("exports", "ts-paths", "workspace", "package-exports", "relative-fs")):
            score += 0.04
            if "strong_resolution_strategy" not in reasons:
                reasons.append("strong_resolution_strategy")

    if in_cycle:
        score -= 0.10
        if "cycle_participant" not in reasons:
            reasons.append("cycle_participant")

    final = max(0.05, min(1.0, score))
    final = round(final, 2)

    # -----------------------------------------------------------------
    # R2: Significantly improved explanation builder
    # - Prioritized risk ordering (most severe first for quick scanning)
    # - Consistent, professional phrasing
    # - Evidence traces + resolution context embedded
    # - Prescriptive, decision-oriented recommendation (agents act on it)
    # -----------------------------------------------------------------
    SEVERITY = {
        "tag:dev_only": 100, "tag:dead_code_guard": 100,
        "dynamic_expression": 95, "complexity:opaque": 90, "complexity:high": 85,
        "cycle_participant": 92, "weak_resolution_strategy": 80,
        "no_resolved_path": 75, "low_detector_agreement": 70,
        "tag:webpack_magic": 65, "tag:react_lazy": 60, "tag:conditional_dynamic": 60,
        "conditional_context": 50, "via_barrel": 45, "barrel_depth": 40,
        "tag:feature_flag": 35, "tag:env_check": 35,
        # Phase 1 creative dynamic signals wired into ACS
        "tag:tagged_template": 55, "tag:registry_map": 52, "tag:multi_condition_feature_wrapper": 48, "tag:call_produced_path": 45,
    }

    def _sev(r: str) -> int:
        for k, v in SEVERITY.items():
            if r == k or r.startswith(k):
                return v
        if r.startswith("tag:"):
            return 30
        if r.startswith("detector:") or r.startswith("strategy:"):
            return 25
        return 10

    risk_reasons = []
    positive_reasons = []
    for r in reasons[1:]:
        if any(x in r for x in ("dev_only", "dead_code", "dynamic_expression", "cycle_participant", "weak_resolution", "complexity:opaque", "complexity:high", "no_resolved", "low_detector")):
            risk_reasons.append(r)
        elif "strong_resolution" in r:
            positive_reasons.append(r)
        elif r.startswith(("tag:", "detector:", "barrel_depth", "conditional_context", "via_barrel", "dynamic", "strategy:")):
            if r.startswith("strategy:") and "strong_resolution_strategy" in reasons:
                # strong strategies are positive signals, not risks; positive handler surfaces them cleanly
                pass
            else:
                risk_reasons.append(r)

    risk_reasons.sort(key=_sev, reverse=True)
    risk_reasons = list(dict.fromkeys(risk_reasons))  # stable dedup preserve order

    expl_parts: list[str] = [f"Base {base_conf} ({final:.2f})"]

    for r in risk_reasons[:4]:  # top 4 most severe + dedicated evidence slots for scale (large monorepos)
        if r.startswith("tag:"):
            tag = r[4:]
            if tag in ("dev_only", "dead_code_guard"):
                expl_parts.append(f"high-risk {tag} (prod/shipping danger)")
            elif tag in ("feature_flag", "env_check"):
                expl_parts.append(f"runtime-variable {tag}")
            elif tag in ("webpack_magic", "system_import", "require_context"):
                expl_parts.append(f"opaque {tag} dynamic")
            elif tag in ("tagged_template", "registry_map", "multi_condition_feature_wrapper", "call_produced_path"):
                # Phase 1: wire creative signals into explanations
                expl_parts.append(f"creative {tag} (LDSI/CDIA)")
            else:
                expl_parts.append(f"{tag} semantics")
        elif r.startswith("detector:"):
            det = r[9:]
            expl_parts.append(f"detector:{det}")
        elif r.startswith("strategy:"):
            # only raw for non-strong (weak/unknown handled as risk earlier)
            expl_parts.append(f"via strategy '{r[9:]}'")
        elif r == "cycle_participant":
            expl_parts.append("cycle participant (refactor hazard)")
        elif r.startswith("barrel_depth"):
            depth = r.split("=", 1)[-1]
            expl_parts.append(f"deep barrel (depth={depth})")
        elif r == "conditional_context":
            expl_parts.append("conditional context")
        elif r == "dynamic_expression":
            expl_parts.append("opaque dynamic expression")
        elif r == "weak_resolution_strategy":
            expl_parts.append("weak/fragile resolution")
        elif r in ("complexity:opaque", "complexity:high"):
            expl_parts.append("high complexity")
        elif r == "low_detector_agreement":
            expl_parts.append("low detector consensus")
        elif r == "no_resolved_path":
            expl_parts.append("unresolved target")
        elif r == "via_barrel":
            expl_parts.append("via barrel re-export")
        else:
            expl_parts.append(r.replace("_", " "))
    for r in positive_reasons[:1]:
        if r == "strong_resolution_strategy":
            # surface the concrete strategy name for decision context (monorepo scale: which resolver succeeded)
            strat_name = next((r2[9:] for r2 in reasons if r2.startswith("strategy:")), "")
            if strat_name:
                expl_parts.append(f"strong strategy '{strat_name}'")
            else:
                expl_parts.append("strong resolution fidelity")

    # Embed short trace evidence (prioritized for agent trust; always try top 1-2 even at scale)
    trace_ev = []
    for tr in (ca.get("analysis_trace") or da.get("analysis_trace") or [])[:2]:
        if isinstance(tr, dict) and tr.get("fired"):
            det = str(tr.get("detector", "det"))[:28]
            ev = str(tr.get("evidence", ""))[:45]
            if ev:
                trace_ev.append(f"{det}={ev}")
    if trace_ev:
        expl_parts.append("trace: " + "; ".join(trace_ev))

    # Resolution metadata highlights (workspace/monorepo context)
    if isinstance(rm, dict):
        if rm.get("workspace_pkg"):
            expl_parts.append(f"workspace:{rm.get('workspace_pkg')}")
        if rm.get("matched_condition"):
            expl_parts.append(f"matched:{rm.get('matched_condition')}")

    if len(expl_parts) <= 1:
        explanation = f"Standard {base_conf} confidence ({final:.2f}) with no special risk factors."
    else:
        # R2: cleaner separator for readability on large result sets; factors before evidence
        cleaned = [p.rstrip(". ") for p in expl_parts[:7]]
        explanation = cleaned[0] + (". " + "; ".join(cleaned[1:]) if len(cleaned) > 1 else "") + "."

    # R2 prescriptive, decision-oriented recommendation (core deliverable) — now with barrel nuance
    rec = _action_recommendation(reasons, final, strat, rm)
    explanation = (explanation.rstrip(".") + ". Recommendation: " + rec).strip()

    return final, reasons, explanation


def _action_recommendation(reasons: list[str], final: float, strat: str = "", rm: dict | None = None) -> str:
    """R2: Return a specific, agent-actionable recommendation string based on dominant signals.
    Prioritized for decision readiness on both tiny projects and 10k+ file monorepos.
    Agents should quote the full sentence after 'Recommendation:' for impact reports.
    """
    rset = set(reasons)
    rm = rm or {}
    has_dev = any(x in rset for x in ("tag:dev_only", "tag:dead_code_guard"))
    has_cycle = "cycle_participant" in rset
    has_opaque_dyn = any(x in rset for x in ("dynamic_expression", "complexity:opaque", "complexity:high"))
    has_creative = any(x in rset for x in ("tag:tagged_template", "tag:registry_map", "tag:multi_condition_feature_wrapper", "tag:call_produced_path"))
    has_weak = "weak_resolution_strategy" in rset
    has_strong = "strong_resolution_strategy" in rset
    has_cond = "conditional_context" in rset or any("tag:feature_flag" in r or "tag:env_check" in r for r in rset)
    has_deep_barrel = any(r.startswith("barrel_depth=") and int((r.split("=", 1)[1] or "0").split()[0]) >= 3 for r in rset)
    has_via_barrel = "via_barrel" in rset

    if has_dev:
        return "CRITICAL: dev-only or dead-code path — eliminate guard or make unconditional before using in production paths or automated refactors."
    if has_cycle:
        return "Cycle participant (high refactor risk) — use get_cycles(analysis=True) to retrieve severity, blast radius and weakest-link recommendations; change requires coordinated edit across the SCC."
    if has_opaque_dyn:
        return "Opaque or high-complexity dynamic resolution — refactor to static import or introduce explicit runtime guard; current edge is unsuitable for static analysis tooling."
    if has_creative:
        # Phase 1 creative signals wired: specific rec for new CDIA-covered extremely creative patterns
        return "Extremely creative dynamic (tagged template / registry map / multi-cond feature / call-produced path) — CDIA detectors fired; supply static mappings or treat as runtime-only for dependency graphs."
    if has_weak:
        return "Weak/fragile resolution strategy — target may shift with package.json or build changes. Pin to a stronger strategy or verify stability."
    if has_deep_barrel:
        return "Deep barrel expansion (depth>=3) — root resolution strong but verify leaf re-exports and build contracts; safe for read queries, exercise caution on wide automated refactors."
    if has_strong and final >= 0.75 and not (has_cond or has_via_barrel or has_deep_barrel):
        return "High-fidelity static resolution via strong strategy. Safe for automated impact analysis, dependency queries, and the majority of refactors."
    if has_cond or has_via_barrel:
        return "Runtime conditional, feature-controlled or barrel-mediated — behavior or target may vary by deployment/build; inspect predicate + usage site before relying on the edge for changes."
    if final >= 0.68:
        return "Moderate-to-high confidence edge. Suitable for most analysis and targeted refactors; still verify at the call site for mission-critical or high-blast-radius changes."
    return "Low-confidence or fragile edge — review the concrete usage site and consider hardening the import (or pin resolution) before trusting the dependency for automation."


# =============================================================================
# 9. M2 Full Closure — Workstream A0 + early A2: Scalable Update Contracts
# (Additive, non-breaking foundation. Long-term scalable design per plan.)
# =============================================================================
#
# Guiding principles (binding for this slice + future waves):
# - Event-sourced friendly: every ProgressEvent_v1 is a first-class record with
#   full provenance (actor, session, intent_ref, parent), ACS/CIABRE hooks,
#   barrel + cycle signals, scope projection info, and checkpoint/resumption hints.
# - Proportional cost + resumable: ScopeSpec_v1 enables subtree/focus scoping at
#   engine level (not post-filter). Checkpoint tokens allow pause/resume on
#   50k-file creative monorepos without losing partial work.
# - Dual persisted structures: forward (existing) + ReverseDependencyIndex_v1
#   (incremental, graph_signature delta, node_identity_v1 ready).
# - Zero new dependencies. Pure stdlib + dataclasses + existing patterns
#   (defensive from_dict, RESERVED keys, ACS compute, version stamps).
# - Versioning: All shapes carry explicit "version". New major via new _vN names
#   + migration note + CHANGELOG. Dual emission supported.
# - Observability: Events feed health, MCP streaming responses, journal (C),
#   diagnostics, library.md summaries (A3). ACS/CIABRE always first-class citizens.
#
# RESERVED keys extended below for persisted M2 structures.
# These shapes are the contract for the minimal streaming generator skeleton
# (in import_cache.py) and all later A1-A4 / cross workstreams.
#
# DO NOT put engine logic or full UX here. Pure shapes + helpers only.
# =============================================================================

M2_CONTRACTS_VERSION = "1.0.0-wave3-a0-finalized"

# --- ScopeSpec_v1 (first-class scope for scoped/resumable updates) ---
@dataclass(frozen=True)
class ScopeSpec_v1:
    """
    Declarative scope for update-maps / streaming runs (A0 foundation, A2 delivery).

    Applied early (dirty detection, graph build, reverse index projection) for
    true O(changed + scope) cost even on 50k+ file monorepos.

    Supports:
    - directory subtree (with max_depth)
    - include/exclude globs (portable, no fnmatch dep beyond stdlib)
    - focus_files: seed set + optional transitive closure (for "impact of X")
    - follow_symlinks + node_identity_version awareness

    Long-term: Scope projector lives in update engine; produces checkpointable
    partial scopes for resumption. Resource_hints (time_budget_ms, token_budget,
    max_files) influence early termination + best-effort partials.

    Serialized in ProgressEvent_v1, UpdateRun_v1, PartialResult_v1, and MCP/CLI.
    """
    directory: Optional[str] = None
    include_globs: List[str] = field(default_factory=list)
    exclude_globs: List[str] = field(default_factory=list)
    focus_files: List[str] = field(default_factory=list)
    max_depth: Optional[int] = None
    transitive_closure: bool = True
    follow_symlinks: bool = False
    seed_reason: Optional[str] = None  # e.g. "cli:--dir src/" or "agent:focus:core.ts+dependents"
    resource_hints: Dict[str, Any] = field(default_factory=dict)
    version: str = "1.0"

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ScopeSpec_v1":
        """Defensive loader. Tolerates legacy/partial/malformed input."""
        if not isinstance(d, dict):
            d = {}
        return cls(
            directory=(str(d.get("directory"))[:500] if d.get("directory") else None),
            include_globs=[str(x)[:200] for x in (d.get("include_globs") or [])][:100],
            exclude_globs=[str(x)[:200] for x in (d.get("exclude_globs") or [])][:100],
            focus_files=[str(x)[:500] for x in (d.get("focus_files") or [])][:500],
            max_depth=(int(d.get("max_depth")) if isinstance(d.get("max_depth"), (int, float)) else None),
            transitive_closure=bool(d.get("transitive_closure", True)),
            follow_symlinks=bool(d.get("follow_symlinks", False)),
            seed_reason=(str(d.get("seed_reason"))[:300] if d.get("seed_reason") else None),
            resource_hints=dict(d.get("resource_hints") or {}),
            version=str(d.get("version", "1.0"))[:10],
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))


# --- ProgressEvent_v1 (the heartbeat of the streaming / resumable pipeline) ---
@dataclass(frozen=True)
class ProgressEvent_v1:
    """
    Canonical event shape yielded by the M2 streaming generator foundation.
    (Wave 3 A0: finalized with full defensive shapes + ACS/CIABRE hooks.)

    EVERY milestone (parse, resolve, barrel expand, cycle, ACS, CIABRE, reverse update)
    emits one. Consumers can:
    - Stream live (CLI progress, MCP SSE-like)
    - Checkpoint (save token + last event for --resume)
    - Filter (e.g. only barrel/cycle events for diagnostics)
    - Early terminate on budget

    Required fields for long-term trust:
    - Provenance: who/why/when/session/intent link (journal correlation ready)
    - ACS/CIABRE hooks: partial aggregates or refs (never lose "why low conf?")
      acs_hook carries {confidence_score, reasons[], explanation, ...} from compute_acs_confidence
      cycle_signals + barrel_signals carry CIABRE blast/severity + barrel depth/chain info
    - Barrel/cycle signals: first-class (no grepping logs)
    - Scope + checkpoint: enables subtree + resumption at 50k scale

    Event types are append-only vocabulary (document new ones here).
    """
    event_type: str
    timestamp: str
    run_id: str
    scope: Dict[str, Any]  # ScopeSpec_v1 shape (defensive)
    payload: Dict[str, Any] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)
    acs_hook: Optional[Dict[str, Any]] = None
    barrel_signals: Dict[str, Any] = field(default_factory=dict)
    cycle_signals: Dict[str, Any] = field(default_factory=dict)
    checkpoint_token: Optional[str] = None
    resumable: bool = True
    diagnostics: Dict[str, Any] = field(default_factory=dict)
    version: str = "1.0"

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ProgressEvent_v1":
        if not isinstance(d, dict):
            d = {}
        sc = ScopeSpec_v1.from_dict(d.get("scope") or {})
        return cls(
            event_type=str(d.get("event_type", "unknown"))[:60],
            timestamp=str(d.get("timestamp") or datetime.now(timezone.utc).isoformat())[:50],
            run_id=str(d.get("run_id", "run-unknown"))[:120],
            scope=sc.to_dict(),
            payload=dict(d.get("payload") or {}),
            provenance=dict(d.get("provenance") or {}),
            acs_hook=(dict(d.get("acs_hook")) if isinstance(d.get("acs_hook"), dict) else None),
            barrel_signals=dict(d.get("barrel_signals") or {}),
            cycle_signals=dict(d.get("cycle_signals") or {}),
            checkpoint_token=(str(d.get("checkpoint_token"))[:300] if d.get("checkpoint_token") else None),
            resumable=bool(d.get("resumable", True)),
            diagnostics=dict(d.get("diagnostics") or {}),
            version=str(d.get("version", "1.0"))[:10],
        )

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Normalize scope
        if "scope" in d and isinstance(d["scope"], ScopeSpec_v1):
            d["scope"] = d["scope"].to_dict()
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))


# --- UpdateRun_v1 (lifecycle descriptor for long-running / resumable updates) ---
@dataclass
class UpdateRun_v1:
    """
    Descriptor for an entire update-maps execution (CLI, MCP, daemon, library).

    Created at start of streaming run. Updated on checkpoints / completion.
    Enables:
    - Tracking concurrent runs under locking
    - --resume from last checkpoint_token
    - Query "what is the status of the long update I started?"
    - Correlating journal events (Workstream C) to runs

    Persisted (bounded) under _update_runs reserved key in future waves.
    """
    run_id: str
    started_at: str
    scope: Dict[str, Any]
    status: str = "running"  # pending|running|paused|completed|failed|cancelled
    completed_at: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    partial_result: Optional[Dict[str, Any]] = None
    checkpoint_token: Optional[str] = None
    provenance: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    version: str = "1.0"

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "UpdateRun_v1":
        if not isinstance(d, dict):
            d = {}
        return cls(
            run_id=str(d.get("run_id", ""))[:120],
            started_at=str(d.get("started_at", ""))[:50],
            scope=ScopeSpec_v1.from_dict(d.get("scope") or {}).to_dict(),
            status=str(d.get("status", "running"))[:30],
            completed_at=(str(d.get("completed_at"))[:50] if d.get("completed_at") else None),
            metrics=dict(d.get("metrics") or {}),
            partial_result=(dict(d.get("partial_result")) if isinstance(d.get("partial_result"), dict) else None),
            checkpoint_token=(str(d.get("checkpoint_token"))[:300] if d.get("checkpoint_token") else None),
            provenance=dict(d.get("provenance") or {}),
            error=(str(d.get("error"))[:2000] if d.get("error") else None),
            version=str(d.get("version", "1.0"))[:10],
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))


# --- PartialResult_v1 (safe early output for agents on budgets) ---
@dataclass(frozen=True)
class PartialResult_v1:
    """
    Bounded, actionable snapshot from a (still-running or paused) scoped update.

    The primary deliverable for "I only have 30s / 4k tokens" agent workflows.
    Always safe to act on (consistency within the applied scope + last checkpoint).

    Contains:
    - Counts + bounded samples (resolved_pairs, cycles)
    - ACS + CIABRE partials (hooks, never lose diagnostics)
    - Reverse index delta (A1 tie-in)
    - next_checkpoint_hint for clean resumption
    - Full diagnostics bag

    Returned by streaming generator on "partial_ready" events or explicit --partial calls.
    """
    run_id: str
    yielded_at: str
    scope_applied: Dict[str, Any]
    files_processed: int = 0
    edges_resolved: int = 0
    cycles_found: int = 0
    low_conf_edges: int = 0
    barrel_chains_expanded: int = 0
    resolved_pairs_sample: List[Dict[str, Any]] = field(default_factory=list)
    cycles_sample: List[Dict[str, Any]] = field(default_factory=list)
    acs_partial: Optional[Dict[str, Any]] = None
    cycle_analyses_partial: Optional[Dict[str, Any]] = None
    reverse_index_delta: Optional[Dict[str, Any]] = None
    next_checkpoint_hint: Optional[str] = None
    diagnostics: Dict[str, Any] = field(default_factory=dict)
    version: str = "1.0"

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PartialResult_v1":
        if not isinstance(d, dict):
            d = {}
        return cls(
            run_id=str(d.get("run_id", ""))[:120],
            yielded_at=str(d.get("yielded_at", ""))[:50],
            scope_applied=ScopeSpec_v1.from_dict(d.get("scope_applied") or {}).to_dict(),
            files_processed=int(d.get("files_processed") or 0),
            edges_resolved=int(d.get("edges_resolved") or 0),
            cycles_found=int(d.get("cycles_found") or 0),
            low_conf_edges=int(d.get("low_conf_edges") or 0),
            barrel_chains_expanded=int(d.get("barrel_chains_expanded") or 0),
            resolved_pairs_sample=[dict(x) for x in (d.get("resolved_pairs_sample") or []) if isinstance(x, dict)][:30],
            cycles_sample=[dict(x) for x in (d.get("cycles_sample") or []) if isinstance(x, dict)][:15],
            acs_partial=(dict(d.get("acs_partial")) if isinstance(d.get("acs_partial"), dict) else None),
            cycle_analyses_partial=(dict(d.get("cycle_analyses_partial")) if isinstance(d.get("cycle_analyses_partial"), dict) else None),
            reverse_index_delta=(dict(d.get("reverse_index_delta")) if isinstance(d.get("reverse_index_delta"), dict) else None),
            next_checkpoint_hint=(str(d.get("next_checkpoint_hint"))[:300] if d.get("next_checkpoint_hint") else None),
            diagnostics=dict(d.get("diagnostics") or {}),
            version=str(d.get("version", "1.0"))[:10],
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))


# --- ReverseDependencyIndex_v1 (A0 contract, A1 implementation target) ---
@dataclass
class ReverseDependencyIndex_v1:
    """
    Authoritative, incrementally-updatable reverse dependency index.

    Shape: target_relpath -> sorted list of direct importer relpaths.

    Key properties (long-term):
    - graph_signature + node_identity_version for safe delta/reuse (like cycles/BRC)
    - Provenance (build_mode, reused, source_run, merge details)
    - ACS tie-in: low-conf reverse edges annotated for risk
    - CIABRE blast hints: high-impact dependents surfaced for cycle recs
    - Checkpointable for partial rebuilds on massive repos

    Persisted under _reverse_dependency_index_v1 (see RESERVED_TOP_LEVEL_KEYS).
    Current flat _reverse_dependencies coexists for transition (import_cache helpers
    will dual-write in A1).

    Query surfaces (get_dependents, get_impact, MCP) will use this directly for
    O(k) instead of O(E) reconstruction.
    """
    version: str = "1.0"
    generated_at: str = ""
    index: Dict[str, List[str]] = field(default_factory=dict)
    graph_signature: Optional[str] = None
    node_identity_version: str = NODE_IDENTITY_VERSION_V1
    stats: Dict[str, Any] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)
    acs_tied: bool = False
    ciabre_blast_hints: Dict[str, Any] = field(default_factory=dict)
    checkpoint_ref: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ReverseDependencyIndex_v1":
        if not isinstance(d, dict):
            d = {}
        raw_idx = d.get("index") or {}
        if isinstance(raw_idx, dict):
            clean_idx: Dict[str, List[str]] = {}
            for k, v in raw_idx.items():
                if isinstance(k, str) and k:
                    importers = [str(x)[:500] for x in (v or []) if x][:2000]
                    clean_idx[str(k)[:500]] = sorted(set(importers))  # stable
        else:
            clean_idx = {}
        return cls(
            version=str(d.get("version", "1.0"))[:10],
            generated_at=str(d.get("generated_at", ""))[:50],
            index=clean_idx,
            graph_signature=(str(d.get("graph_signature"))[:64] if d.get("graph_signature") else None),
            node_identity_version=str(d.get("node_identity_version", NODE_IDENTITY_VERSION_V1))[:10],
            stats=dict(d.get("stats") or {}),
            provenance=dict(d.get("provenance") or {}),
            acs_tied=bool(d.get("acs_tied", False)),
            ciabre_blast_hints=dict(d.get("ciabre_blast_hints") or {}),
            checkpoint_ref=(str(d.get("checkpoint_ref"))[:300] if d.get("checkpoint_ref") else None),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))


# =============================================================================
# V1 Aliases (for plan/docs naming parity + consumer convenience; same classes)
# =============================================================================
# Plan refers to ScopeSpecV1 / ProgressEventV1 etc.; implementation uses _v1
# suffix for pythonic versioned names. Aliases provide both.
ScopeSpecV1 = ScopeSpec_v1
ProgressEventV1 = ProgressEvent_v1
UpdateRunV1 = UpdateRun_v1
PartialResultV1 = PartialResult_v1
ReverseDependencyIndexV1 = ReverseDependencyIndex_v1


# Extend RESERVED_TOP_LEVEL_KEYS (additive, documented for M2)
RESERVED_TOP_LEVEL_KEYS["_reverse_dependency_index_v1"] = (
    "M2 A0/A1: Structured ReverseDependencyIndex_v1 (target -> importers list). "
    "Incrementally maintained with graph_signature delta detection + node_identity_version. "
    "Provenance, stats, ACS low-conf ties, CIABRE blast hints, checkpoint support. "
    "Enables O(k) dependents + impact analysis at massive scale. Coexists with legacy "
    "_reverse_dependencies during A1 transition. Authoritative for get_dependents etc."
)
RESERVED_TOP_LEVEL_KEYS["_update_runs"] = (
    "M2 A0/A2: Bounded registry of UpdateRun_v1 descriptors (lifecycle + checkpoints). "
    "Supports resumable streaming UX, concurrent agent visibility, MCP status queries. "
    "Not a full semantic journal (see Workstream C). Retention policy + compaction future."
)
RESERVED_TOP_LEVEL_KEYS["_partial_results"] = (
    "M2 A0/A2: Named or latest PartialResult_v1 snapshots from long/scoped/streaming updates. "
    "Agents consume early results + continuation tokens safely. Bounded; ties to run_id + scope."
)


def create_progress_event(
    event_type: str,
    run_id: str,
    scope: Union[ScopeSpec_v1, Dict[str, Any], None] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Factory for well-formed ProgressEvent_v1 dicts (use in generator skeleton + engine).
    Ensures provenance/acs/barrel/cycle scaffolding is present.
    Extra kwargs go into payload (or override known fields if exact match).
    """
    if isinstance(scope, ScopeSpec_v1):
        sc_d = scope.to_dict()
    elif isinstance(scope, dict):
        sc_d = ScopeSpec_v1.from_dict(scope).to_dict()
    else:
        sc_d = ScopeSpec_v1().to_dict()

    base_payload = kwargs.pop("payload", {})
    prov = kwargs.pop("provenance", {})
    acs = kwargs.pop("acs_hook", None)
    barrel = kwargs.pop("barrel_signals", {})
    cycle = kwargs.pop("cycle_signals", {})
    chk = kwargs.pop("checkpoint_token", None)
    res = kwargs.pop("resumable", True)
    diag = kwargs.pop("diagnostics", {})

    # Remaining kwargs -> payload
    extra_payload = {**base_payload, **kwargs}

    ev = ProgressEvent_v1(
        event_type=event_type,
        timestamp=datetime.now(timezone.utc).isoformat(),
        run_id=run_id,
        scope=sc_d,
        payload=extra_payload,
        provenance=prov,
        acs_hook=acs if isinstance(acs, dict) else None,
        barrel_signals=dict(barrel),
        cycle_signals=dict(cycle),
        checkpoint_token=chk,
        resumable=bool(res),
        diagnostics=dict(diag),
        version="1.0",
    )
    return ev.to_dict()


# =============================================================================
# 10. M2 Scope Projector (A0 finalized in Wave 3, A2 full engine wiring)
# (Pure, zero-dep, long-term scalable. Lives with ScopeSpec_v1 / ScopeSpecV1 contract.)
# =============================================================================
#
# Why here (contracts): ScopeSpec_v1 is the frozen declarative contract.
# The projector is the canonical, testable implementation of "apply this spec".
# All consumers (generator, run_update_stream, dirty detectors, MCP/CLI scoping,
# future daemon) use this single source — guarantees consistent semantics from
# tiny scripts to 50k-file creative monorepos.
#
# Design (non-negotiable per M2 plan):
# - Proportional: directory subtree + globs prune candidates early (O(candidates in scope)).
# - Focus + transitive_closure: for "impact of X" uses reverse edges (dependents closure);
#   seeds + their transitive importers. Requires reverse_index (A1); graceful degrade if absent.
# - max_depth: relative to scope.directory (or root). Prevents explosion in deep trees.
# - Globs: stdlib fnmatch only (portable, no third-party). Normalized to / .
# - Deterministic + defensive: never crashes on bad input; logs diagnostics in return.
# - Checkpoint friendly: projector can return "projected_scope" + "next_seed" hints for partials.
# - Symlinks: follow_symlinks advisory passed through; actual FS walk (cli/import_cache)
#   decides os.walk(followlinks=...) or Path.resolve handling.
#
# Eventual: full Scope_v1 dataclass will hold spec + applied_file_set + stats +
# partial_projection_token for resumable scoped runs.
# =============================================================================


def _normalize_rel(p: Union[str, Path]) -> str:
    """Internal: POSIX-style relative path, no leading ./ , no trailing / (except root), safe for matching."""
    s = str(p).replace("\\", "/").strip()
    if s.startswith("./"):
        s = s[2:]
    if s.startswith("/"):
        # absolute -> best effort basename tail for safety; real roots use rel from root
        s = s.lstrip("/")
    s = s.rstrip("/")  # critical for dir specs like 'src/' to become 'src'
    return s or "."


def _compute_depth(rel: str, base_dir: Optional[str]) -> int:
    """Depth in directory tree relative to base or implicit root (count of / segments)."""
    r = rel.strip("/")
    if not r:
        return 0
    if base_dir:
        b = base_dir.strip("/")
        if r.startswith(b + "/") or r == b:
            r = r[len(b):].lstrip("/")
        elif r == b:
            return 0
    return 0 if not r else r.count("/") + 1


def _matches_globs(rel: str, include_globs: List[str], exclude_globs: List[str]) -> bool:
    """Portable glob match using fnmatch (stdlib). include: any-of (or all if empty). exclude: none-of."""
    if any(fnmatch.fnmatch(rel, g) or fnmatch.fnmatch("/" + rel, g) for g in (exclude_globs or [])):
        return False
    if not include_globs:
        return True
    return any(fnmatch.fnmatch(rel, g) or fnmatch.fnmatch("/" + rel, g) for g in include_globs)


def matches_scope(
    spec: Union[ScopeSpec_v1, Dict[str, Any], None],
    file_path: Union[str, Path],
    *,
    root: Optional[Path] = None,
) -> bool:
    """
    Pure predicate: does this file (rel or abs) satisfy the ScopeSpec_v1?

    Directory + max_depth + globs only (FS-level filter). Does not handle
    focus_files transitive (see project_scope for that).
    Used for early pruning in candidate collection and dirty walks.
    """
    if spec is None:
        return True
    if isinstance(spec, dict):
        spec = ScopeSpec_v1.from_dict(spec)
    elif not isinstance(spec, ScopeSpec_v1):
        return True

    rel = _normalize_rel(file_path)

    # Directory subtree filter
    if spec.directory:
        d = _normalize_rel(spec.directory)
        d_prefix = d + "/" if d else ""
        if not (rel == d or (d_prefix and rel.startswith(d_prefix))):
            return False

    # Depth (relative to directory or root)
    depth = _compute_depth(rel, spec.directory)
    if spec.max_depth is not None and depth > int(spec.max_depth):
        return False

    # Globs (include any, exclude none)
    if not _matches_globs(rel, spec.include_globs, spec.exclude_globs):
        return False

    return True


def compute_focus_closure(
    focus_files: List[str],
    reverse_index: Optional[Dict[str, List[str]]] = None,
    *,
    max_depth: Optional[int] = None,
    follow_forward: bool = False,  # False = dependents (impact); True = deps (forward)
) -> Dict[str, Any]:
    """
    Compute transitive closure for focus set.

    - If reverse_index present: for dependents mode, BFS following importers (who depends on me).
    - Seeds always included.
    - Bounded by max_depth (edge hops) if given.
    - Returns dict with 'closure', 'seeds', 'stats' for diagnostics / PartialResult.
    - Graceful: if no index, returns just the seeds (no transitive).
    - Zero side effects, pure, O(closure size) which is proportional by design.
    """
    seeds = [ _normalize_rel(f) for f in (focus_files or []) if f ]
    if not seeds:
        return {"closure": [], "seeds": [], "stats": {"hops": 0, "degraded": True}}

    if not reverse_index or not isinstance(reverse_index, dict):
        # No index: best-effort seeds only (transitive deferred or handled upstream)
        return {
            "closure": sorted(set(seeds)),
            "seeds": sorted(set(seeds)),
            "stats": {"hops": 0, "degraded": True, "reason": "no_reverse_index"},
        }

    # Build reverse or forward adj for BFS
    # reverse_index: target -> [importers]  => for dependents, from seed follow the importers list
    adj: Dict[str, List[str]] = {}
    if follow_forward:
        # Would need forward graph; not primary for "dependents" use case. Degrade.
        return {
            "closure": sorted(set(seeds)),
            "seeds": sorted(set(seeds)),
            "stats": {"hops": 0, "degraded": True, "reason": "forward_not_supported_yet"},
        }

    # Dependents mode: from each node, the "dependents" are the keys that list it as importer? Wait:
    # reverse_index[target] = list of direct importers of target.
    # So to find who depends on seed (transitive), we need the inverse of reverse_index:
    # importer -> [targets it imports] would be forward.
    # To walk dependents: start from seed, find all X such that seed in reverse_index.get(X, []) ? No.
    # reverse_index["foo.js"] = ["bar.js", "baz.js"] means bar and baz import foo.
    # So dependents of foo = ["bar","baz"] (direct).
    # To find dependents of bar: look for entries where bar appears in their importer list.
    # I.e. we need the "who imports bar" -> invert the index.

    # Build inverted: importer -> list of things_it_imports ? No, wait for walk:
    # To traverse "dependents graph": from a target, its direct dependents are the values in reverse_index[target].
    # Yes: dependents_graph[ target ] = reverse_index[target]  (the importers)
    # Then from seed, collect all reachable in dependents_graph.

    dependents_graph: Dict[str, List[str]] = {
        _normalize_rel(k): [_normalize_rel(v) for v in (vs or [])] for k, vs in reverse_index.items()
    }

    from collections import deque  # stdlib, local import ok inside func for zero top-level cost
    visited: set = set()
    q = deque()
    for s in seeds:
        q.append((s, 0))
        visited.add(s)

    closure: List[str] = []
    hops = 0
    maxd = max_depth if max_depth is not None else 999999

    while q:
        cur, d = q.popleft()
        closure.append(cur)
        hops = max(hops, d)
        if d >= maxd:
            continue
        for dep in dependents_graph.get(cur, []):
            if dep not in visited:
                visited.add(dep)
                q.append((dep, d + 1))

    return {
        "closure": sorted(set(closure)),
        "seeds": sorted(set(seeds)),
        "stats": {
            "hops": hops,
            "size": len(closure),
            "degraded": False,
            "used_reverse_index": True,
        },
    }


def project_scope(
    spec: Union[ScopeSpec_v1, Dict[str, Any], None],
    candidate_files: Iterable[Union[str, Path]],
    *,
    root: Optional[Path] = None,
    reverse_index: Optional[Dict[str, List[str]]] = None,
    include_focus_closure: bool = True,
) -> Dict[str, Any]:
    """
    Full Scope projector (the engine-level applicator). Wave 3 A0 finalized.

    Pure, stdlib-only, proportional (never O(repo) for large creative monorepos).
    Supports directory subtree, portable globs (fnmatch), max_depth, focus_files +
    transitive_closure (dependents via reverse index for impact cones).

    Returns:
        {
            "matched_files": List[str] (relpaths satisfying spec; intersect dir+globs+focus_closure),
            "focus_closure": (if focus + index) the transitive dependents or seeds,
            "stats": {num_candidates, num_matched, focus_size, degraded, ...},
            "applied_spec": spec.to_dict() if applicable,
            "next_checkpoint_hint": optional for large projections,
        }

    Usage in streaming pipeline:
        candidates = collect_dirty_candidates(root)
        proj = project_scope(scope, candidates, reverse_index=rev_index)
        for f in proj["matched_files"]:
            ... parse only these ...
        # Then for graph build, further project edges using same.

    This is what makes subtree / focus / partials O(scope) not O(repo) at 50k scale.
    Full ACS/CIABRE provenance flows through events using the matched set.
    """
    if spec is None:
        spec = ScopeSpec_v1()
    elif isinstance(spec, dict):
        spec = ScopeSpec_v1.from_dict(spec)
    elif not isinstance(spec, ScopeSpec_v1):
        spec = ScopeSpec_v1()

    candidates = [_normalize_rel(f) for f in candidate_files]

    # 1. FS-level filter (dir + globs + depth)
    fs_matched = [f for f in candidates if matches_scope(spec, f, root=root)]

    # 2. Focus + transitive (dependents by default for impact/partial UX)
    # Semantics (Wave 3 A0 finalized, long-term scalable):
    # - First apply directory + globs + max_depth FS filter (proportional prune).
    # - If focus_files + transitive_closure: compute dependents closure via reverse index (BFS, O(closure)).
    # - Then intersect: effective matched = (dir/glob/depth filtered) ∩ focus_closure (incl seeds).
    #   This gives "the impact cone of focus inside the scoped dir" — proportional, not whole-repo.
    # - Seeds (focus_files) always in closure even on degraded (no index).
    # - If no dir specified but focus given: matched reduces to the closure (seeds + dependents).
    # - max_depth on focus hops is honored in compute_focus_closure.
    # - Always deterministic, sorted, defensive (no crashes on bad globs/paths).
    focus_info: Dict[str, Any] = {"closure": [], "seeds": [], "stats": {"degraded": True}}
    if spec.focus_files and include_focus_closure:
        focus_info = compute_focus_closure(
            spec.focus_files,
            reverse_index=reverse_index,
            max_depth=spec.max_depth,
            follow_forward=False,
        )
        if focus_info.get("closure"):
            focus_set = set(focus_info["closure"])
            # Clean intersect (bugfix from skeleton): previous "or" was no-op and confusing.
            # Intersection ensures proportional scoped update (focus impact within dir/glob constraints).
            fs_matched = [f for f in fs_matched if f in focus_set]

    stats = {
        "num_candidates": len(candidates),
        "num_matched": len(fs_matched),
        "focus_seeds": len(spec.focus_files or []),
        "focus_closure_size": len(focus_info.get("closure", [])),
        "degraded_focus": focus_info.get("stats", {}).get("degraded", False),
        "directory": spec.directory,
        "max_depth": spec.max_depth,
    }

    return {
        "matched_files": sorted(set(fs_matched)),
        "focus_closure": focus_info,
        "stats": stats,
        "applied_spec": spec.to_dict(),
        "next_checkpoint_hint": f"scope-proj:{spec.directory or 'root'}:{len(fs_matched)}" if fs_matched else None,
        "version": "1.0",
    }


# =============================================================================
# Self-test / smoke (run as python -m wikifier.contracts)
# =============================================================================

if __name__ == "__main__":
    import sys

    print(f"Wikifier Contracts {__contracts_version__} - {STATUS}")
    print("Smoke test starting...")

    # Dataclass roundtrip
    trace = AnalysisTraceEntry("TestDetector", True, "foo.bar", 0.87, ["note1"])
    ca = ConditionalAnalysis(True, ["feature_flag"], "if (featureFlags?.x)", ["FeatDetector"], [trace], 0.91, False)
    da = DynamicAnalysis("expression", "high", ["computed_path"], "cond ? a : b", [], [], [], "m", ["def m=..."], 0.65, False)
    rm = ResolutionMetadata("package-exports:./dist", "import", "./*", None, False, None, "@pkg/core", ["ts-paths", "exports"])

    assert ca.is_conditional
    assert "feature_flag" in ca.to_dict()["semantic_tags"]

    # Serialization
    packed = pack_cdia_v1(ca, da)
    assert len(packed) > 10 and "=" not in packed
    unpacked = unpack_cdia_v1(packed)
    assert unpacked["conditional_analysis"]["is_conditional"] is True
    assert unpacked["dynamic_analysis"]["dynamic_type"] == "expression"

    # Legacy synthesis
    leg = synthesize_conditional_from_legacy(True, "if (x)")
    assert leg["degraded"] is True and "control_flow" in leg["semantic_tags"]

    # Pipeline line parser
    sample = "src/app.js|./utils|dist/utils.js|high|false|static|false||false||cdia_v1=eyJjb25kaXRpb25hbF9hbmFseXNpcyI6eyJpc19jb25kaXRpb25hbCI6ZmFsc2V9fQ==|res_meta_v1=eyJzdHJhdGVneSI6InRlc3QifQ=="
    parsed = parse_pipeline_line(sample)
    assert parsed["rich_payloads"]["cdia_v1"]
    assert "res_meta_v1" in parsed["rich_payloads"]

    # Decode failure tolerance
    assert decode_v1_payload("!!!notbase64!!!") is None
    assert decode_v1_payload("") is None

    # Node identity
    stamped = annotate_node_identity({"foo": 1})
    assert get_node_identity_version(stamped) == NODE_IDENTITY_VERSION_V1
    assert get_node_identity_version({}) == NODE_IDENTITY_VERSION_V0

    # R2 ACS helper smoke (score parity + explanation quality + rich signals)
    score, rs, expl = compute_acs_confidence(
        "high",
        is_conditional=True,
        conditional_analysis={"is_conditional": True, "semantic_tags": ["feature_flag"], "detectors_fired": ["FeatureFlagDetector"], "analysis_trace": [{"fired": True, "detector": "FeatureFlagDetector", "evidence": "featureFlags?.newUI"}]},
        resolution_metadata={"strategy": "package-exports:./dist"},
        strategy="package-exports:./dist",
    )
    assert 0.5 <= score <= 0.9
    assert "base:high" in rs and any("tag:feature_flag" in r for r in rs)
    assert "Base high" in expl and "feature_flag" in expl.lower() and "Recommendation:" in expl
    assert "trace:" in expl or "detector" in expl.lower()  # evidence surfaced
    # R2 maturity: no ugly duplication, strong strategy name surfaced, rec decision-ready
    assert "barrel barrel" not in expl and "missing resolved" not in expl.lower()
    assert "strong strategy" in expl or "strong resolution" in expl.lower()

    score2, rs2, expl2 = compute_acs_confidence("low", in_cycle=True)
    assert "cycle_participant" in rs2
    assert "Cycle participant" in expl2 and "get_cycles" in expl2

    # R2 deep barrel + via + clean high-fidelity cases (scale + monorepo realism)
    s3, r3, e3 = compute_acs_confidence("medium", barrel_depth=4, via_barrel=True, resolved_path="x.js")
    assert "deep barrel (depth=4)" in e3 and "via barrel re-export" in e3
    assert "Recommendation:" in e3 and ("Deep barrel" in e3 or "barrel" in e3.split("Recommendation:")[-1])
    assert "barrel barrel" not in e3  # regression guard

    s4, r4, e4 = compute_acs_confidence("high", strategy="ts-paths:src", resolution_metadata={"strategy": "ts-paths:src"}, resolved_path="core.js")
    assert "strong strategy 'ts-paths:src'" in e4 or "strong resolution" in e4.lower()
    assert "High-fidelity" in e4 or "Safe for automated" in e4  # decision language

    # ========== NEW M2 A0 shapes smoke (defensive roundtrips + factory + RESERVED) - Wave 3 finalized ==========
    print("M2 A0 contracts smoke...")

    scope = ScopeSpec_v1(directory="src/", focus_files=["core.ts"], transitive_closure=True, seed_reason="test-focus", resource_hints={"max_files": 500})
    scope_d = scope.to_dict()
    scope2 = ScopeSpec_v1.from_dict(scope_d)
    assert scope2.directory == "src/"
    assert "core.ts" in scope2.focus_files
    assert scope2.version == "1.0"

    run_id = "run-20260526-abc123"
    ev = create_progress_event(
        "file_parsed",
        run_id,
        scope=scope,
        file="src/core.ts",
        progress_pct=12.5,
        provenance={"actor": "cli", "session_id": "sess-xyz"},
        acs_hook={"low_conf_delta": 1},
        barrel_signals={"depth": 2, "via_barrel": True},
        cycle_signals={"in_cycle": True, "scc_size": 4},
        checkpoint_token="after:src/core.ts:17",
    )
    assert ev["event_type"] == "file_parsed"
    assert ev["run_id"] == run_id
    assert ev["scope"]["directory"] == "src/"
    assert ev["provenance"]["actor"] == "cli"
    assert ev["barrel_signals"]["depth"] == 2
    assert ev["cycle_signals"]["in_cycle"]
    assert ev["checkpoint_token"] and ev["resumable"]
    assert "acs_hook" in ev

    ev2 = ProgressEvent_v1.from_dict(ev)
    assert ev2.event_type == "file_parsed"
    assert ev2.checkpoint_token == "after:src/core.ts:17"

    run = UpdateRun_v1(run_id=run_id, started_at="2026-...", scope=scope_d, status="running", provenance={"actor": "mcp"})
    run_d = run.to_dict()
    run2 = UpdateRun_v1.from_dict(run_d)
    assert run2.status == "running"

    partial = PartialResult_v1(
        run_id=run_id,
        yielded_at="2026-...",
        scope_applied=scope_d,
        files_processed=42,
        acs_partial={"avg": 0.71},
        cycle_analyses_partial={"version": "1.3"},
        next_checkpoint_hint="after:src/core.ts:17",
    )
    p_d = partial.to_dict()
    p2 = PartialResult_v1.from_dict(p_d)
    assert p2.files_processed == 42 and p2.acs_partial and p2.next_checkpoint_hint

    rev = ReverseDependencyIndex_v1(
        index={"dist/utils.js": ["src/core.ts", "src/app.ts"]},
        graph_signature="a1b2c3d4e5f6",
        provenance={"build_mode": "incremental", "reused": False},
        acs_tied=True,
        ciabre_blast_hints={"high_blast": ["dist/utils.js"]},
    )
    rev_d = rev.to_dict()
    rev2 = ReverseDependencyIndex_v1.from_dict(rev_d)
    assert "dist/utils.js" in rev2.index
    assert rev2.acs_tied and rev2.graph_signature
    assert rev2.node_identity_version == NODE_IDENTITY_VERSION_V1

    # ========== NEW M2 A0 Scope Projector smoke (matches, closure, project_scope) - Wave 3 finalized ==========
    print("M2 Scope projector smoke...")

    # FS level matches + globs + depth
    spec = ScopeSpec_v1(directory="src/", include_globs=["*.ts"], exclude_globs=["*.d.ts"], max_depth=3)
    assert matches_scope(spec, "src/core.ts")
    assert matches_scope(spec, "src/deep/nested/foo.ts")
    assert not matches_scope(spec, "src/deep/nested/foo.js")  # glob
    assert not matches_scope(spec, "src/deep/nested/foo.d.ts")  # exclude
    assert not matches_scope(spec, "tests/bar.ts")  # wrong dir
    # depth calc: src/a/b/c/d.ts under src/ -> after prefix 'a/b/c/d' -> count(/)=3 +1 =4 > max=3 => False
    assert not matches_scope(spec, "src/a/b/c/d.ts")
    spec2 = ScopeSpec_v1(directory="src/", max_depth=4)
    assert matches_scope(spec2, "src/a/b/c/d.ts")

    # Globs empty = match all under dir
    spec3 = ScopeSpec_v1(directory="lib/")
    assert matches_scope(spec3, "lib/foo/bar.py")

    # Focus closure using synthetic reverse index (dependents)
    rev_idx = {
        "src/core.ts": ["src/app.ts", "src/pages/home.ts"],
        "src/utils.ts": ["src/core.ts", "src/app.ts"],
        "src/app.ts": ["tests/test_app.ts"],
    }
    clos = compute_focus_closure(["src/core.ts"], reverse_index=rev_idx)
    assert "src/core.ts" in clos["closure"]
    assert "src/app.ts" in clos["closure"]
    assert "tests/test_app.ts" in clos["closure"]  # transitive
    assert clos["stats"]["size"] >= 3 and not clos["stats"].get("degraded")

    # Full project_scope integration (FS + focus)
    candidates = ["src/core.ts", "src/utils.ts", "src/app.ts", "tests/test_app.ts", "lib/other.js"]
    proj = project_scope(
        ScopeSpec_v1(directory="src/", focus_files=["src/core.ts"], transitive_closure=True),
        candidates,
        reverse_index=rev_idx,
    )
    assert "matched_files" in proj and "focus_closure" in proj and "stats" in proj
    assert "src/core.ts" in proj["matched_files"]
    assert "src/app.ts" in proj["matched_files"]
    assert proj["stats"]["num_matched"] >= 2
    assert proj["next_checkpoint_hint"] and "scope-proj" in proj["next_checkpoint_hint"]
    assert proj["version"] == "1.0"

    # Degrade gracefully with no index
    proj2 = project_scope(ScopeSpec_v1(focus_files=["src/core.ts"]), candidates, reverse_index=None)
    assert proj2["stats"]["degraded_focus"] is True
    assert "src/core.ts" in proj2["matched_files"]  # seeds still

    # V1 alias smoke (plan naming + dual access)
    assert ScopeSpecV1 is ScopeSpec_v1
    s_v1 = ScopeSpecV1(directory="src")
    assert s_v1.directory == "src"
    ev_v1 = ProgressEventV1.from_dict({"event_type": "test", "run_id": "r1", "scope": {}})
    assert ev_v1.version == "1.0"

    # Cleaned projector intersect regression (focus limits matched proportionally)
    proj3 = project_scope(
        ScopeSpec_v1(focus_files=["src/core.ts"]),
        candidates + ["other/out.ts"],
        reverse_index=rev_idx,
    )
    assert "src/core.ts" in proj3["matched_files"]
    assert "src/app.ts" in proj3["matched_files"]
    assert "other/out.ts" not in proj3["matched_files"]  # outside focus closure
    assert not any("lib/" in m for m in proj3["matched_files"])

    print("M2 Scope projector smoke: PASS")

    # RESERVED keys present and documented
    assert "_reverse_dependency_index_v1" in RESERVED_TOP_LEVEL_KEYS
    assert "M2 A0/A1" in RESERVED_TOP_LEVEL_KEYS["_reverse_dependency_index_v1"]
    assert "_update_runs" in RESERVED_TOP_LEVEL_KEYS
    assert "_partial_results" in RESERVED_TOP_LEVEL_KEYS

    # contracts_info now surfaces M2
    info = get_contracts_info()
    assert "m2_contracts_version" in info
    assert "ScopeSpec_v1" in info.get("m2_shapes", [])
    assert "ScopeSpecV1" in info.get("m2_shapes", [])
    assert any(k.startswith("_reverse_dependency") for k in info.get("m2_reserved_keys", []))

    print("M2 A0 shape roundtrips + factory + RESERVED + info extension: PASS")

    print("All smoke tests passed. Contracts are stable and defensive.")
    print(json.dumps(get_contracts_info(), indent=2))
    sys.exit(0)
