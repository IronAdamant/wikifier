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

# =============================================================================
# Module Version & Status
# =============================================================================

<<<<<<< HEAD
=======
# Workstream E (v0.4 Protocol + Library): Library high-level returns are plain dicts
# with "success": bool, "project_root": str, optional "error", plus domain fields
# (e.g. "changes_detected", health "entries", acs in "dependency_intel").
# These are not frozen dataclasses (for max zero-dep agent ergonomics + json direct).
# New shapes should be additive; see m2-full-closure plan + skills/run.md for I/O contracts.
# Conformance harness validates shapes + error taxonomy against this + the public API.


>>>>>>> agent-6-library-final
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
    """Future-proof validator. Currently permissive (append-only policy)."""
    if not isinstance(tag, str):
        return False
    if category == "conditional":
        return tag in CONDITIONAL_SEMANTIC_TAGS
    if category == "dynamic":
        return tag in DYNAMIC_SEMANTIC_TAGS
    return tag in ALL_SEMANTIC_TAGS or True  # allow future additions without breaking


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
<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
    """For health, MCP diagnostics, and agent introspection."""
    return {
=======
    """For health, MCP diagnostics, and agent introspection. Extended additively for journal_event_v1 (M2 Workstream C)."""
    base = {
>>>>>>> agent-4-journal
=======
    """For health, MCP diagnostics, and agent introspection."""
    return {
>>>>>>> agent-7-harness-final
=======
    """For health, MCP diagnostics, and agent introspection."""
    return {
>>>>>>> agent-6-library-final
        "contracts_version": __contracts_version__,
        "frozen_date": FROZEN_DATE,
        "status": STATUS,
        "rich_pipe_fields": list(RICH_PIPE_FIELDS),
        "reserved_top_level_keys": list(RESERVED_TOP_LEVEL_KEYS.keys()),
        "node_identity_versions": [NODE_IDENTITY_VERSION_V0, NODE_IDENTITY_VERSION_V1],
        "num_conditional_tags": len(CONDITIONAL_SEMANTIC_TAGS),
        "num_dynamic_tags": len(DYNAMIC_SEMANTIC_TAGS),
    }
<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
=======
    base["journal"] = get_journal_event_info()
    return base
>>>>>>> agent-4-journal
=======
>>>>>>> agent-7-harness-final
=======
>>>>>>> agent-6-library-final


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
<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
=======
# 9. Structured Journal & Durable Intent Log (Workstream C - M2 Full Closure start)
# =============================================================================
#
# journal_event_v1 (and evolution path) per M2 long-term scalable plan.
# Typed events for semantic intent recording: record-change, record-deletion,
# auto-detected changes, future rationale attachments, etc.
#
# Core requirements (long-term durability for years on large repos):
# - Actor (type + identifier for agents/humans/daemons/swarms) + session_id
#   for correlating activity across concurrent or long-running agent sessions.
# - Full provenance (source, wikifier ver, host/pid, git context) for audit.
# - Explicit links to ACS (confidence snapshots, explanations, low-conf edges
#   involved in the change) + rationale wiki/library.md anchors + related events.
# - Semantic action types (extensible append-only vocabulary).
# - Significance scoring (0-1) + semantic tags for time+impact based compaction.
# - Bounded, self-describing, JSONL friendly. Defensive from_dict everywhere.
# - Event IDs stable for cross-refs and compaction manifests.
#
# Storage (implemented in health.py + wikifier.sh dual-write):
#   Primary (durable): $ROOT/.wikifier_staging/journal/v1/events.jsonl  (append-only)
#   Projection (human): $ROOT/journal/YYYY/MM/DD.md  (existing format, untouched)
#
# Evolution rules (binding, like other contracts):
# - v1 is frozen after this slice. Additive fields only (new optional keys OK).
# - v2 will introduce JournalEventV2 + migrate_v1_to_v2 helper + dual read.
# - from_dict always tolerates missing/extra keys, future versions, corrupt data.
# - Consumers check .get("version") or "schema_version".
# - Dual emission/compat for >=2 releases.
# - All new shapes registered here; update get_contracts_info + smoke.
#
# This survives: 100k+ events/year, monorepo refactors, agent swarm activity,
# project moves, without O(n) scans or unbounded MD bloat. Queries later use
# streaming + same graph techniques as BRC/cycles.
#
# Zero new deps. Pure stdlib + existing patterns.

JOURNAL_SCHEMA_VERSION = "v1"

JOURNAL_SEMANTIC_ACTIONS: Tuple[str, ...] = (
    "record-change",
    "record-deletion",
    "auto-detected",
    # Future (append-only): "mark-green", "heal-stub", "rationale-attach",
    # "intent-update", "compaction-summary", "session-start", ...
)

@dataclass(frozen=True)
class ActorV1:
    """
    Who originated the intent record.
    Supports human edits, single agents, daemons, and multi-agent swarms.
    Identifier examples: "claude-3-5-sonnet-1234", "human:aron", "daemon:monitor",
    "swarm:gap1-wave@host-42".
    """
    type: Literal["human", "agent", "system", "daemon", "swarm"] = "agent"
    identifier: str = "unknown"
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ActorV1":
        if not isinstance(d, dict):
            d = {}
        return cls(
            type=str(d.get("type", "agent"))[:30],
            identifier=str(d.get("identifier", "unknown"))[:200],
            metadata=dict(d.get("metadata") or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProvenanceV1:
    """
    Complete machine + process + version provenance for the emission.
    Enables years-later debugging of "why did this event appear" under
    concurrent agents, daemon runs, or packaged installs.
    """
    source: str = "unknown"  # e.g. "mcp:record_change", "sh:cmd_record_change", "python:health.emit_journal_event"
    wikifier_version: str = ""
    timestamp_local: str = ""
    host: Optional[str] = None
    pid: Optional[int] = None
    git_commit: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ProvenanceV1":
        if not isinstance(d, dict):
            d = {}
        pid = d.get("pid")
        return cls(
            source=str(d.get("source", "unknown"))[:100],
            wikifier_version=str(d.get("wikifier_version", ""))[:50],
            timestamp_local=str(d.get("timestamp_local", ""))[:40],
            host=(str(d.get("host"))[:100] if d.get("host") else None),
            pid=int(pid) if isinstance(pid, (int, float, str)) and str(pid).isdigit() else None,
            git_commit=(str(d.get("git_commit"))[:40] if d.get("git_commit") else None),
            extra=dict(d.get("extra") or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class JournalEventV1:
    """
    Canonical v1 typed journal event.

    Primary on-disk form (JSONL line): compact, one event per line.
    Every field clamped + defensive for 10-year log hygiene on busy repos.

    Links:
    - acs_links: list of dicts capturing ACS snapshot at time of change
      (e.g. [{"target": "foo.js:bar", "confidence": 0.72, "explanation": "...", "rationale_ref": "library.md#sec-3"}])
    - rationale_links: wiki summaries, library sections, prior event_ids that
      provide the "why" for this change.
    - session_id: correlates all events from one logical agent session / task.

    significance: drives safe compaction (high = keep longer or forever).
    """
    version: str = JOURNAL_SCHEMA_VERSION
    event_id: str = ""
    ts: str = ""  # ISO-8601 UTC preferred
    event_type: str = "unknown"
    actor: Dict[str, Any] = field(default_factory=dict)
    session_id: Optional[str] = None
    file: str = ""
    reason: str = ""
    provenance: Dict[str, Any] = field(default_factory=dict)
    acs_links: List[Dict[str, Any]] = field(default_factory=list)
    rationale_links: List[str] = field(default_factory=list)
    semantic_tags: List[str] = field(default_factory=list)
    significance: float = 0.5
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "JournalEventV1":
        """Extremely defensive loader. Tolerates v0 (pre), v1, future v2+ fields, garbage."""
        if not isinstance(d, dict):
            d = {}
        actor_d = d.get("actor") or {}
        prov_d = d.get("provenance") or {}
        # support legacy "action" key from early sh
        et = d.get("event_type") or d.get("action") or "unknown"
        return cls(
            version=str(d.get("version", d.get("schema_version", "v1")))[:10],
            event_id=str(d.get("event_id", ""))[:128],
            ts=str(d.get("ts", d.get("timestamp", "")))[:40],
            event_type=str(et)[:50],
            actor=ActorV1.from_dict(actor_d).to_dict(),
            session_id=(str(d.get("session_id"))[:100] if d.get("session_id") else None),
            file=str(d.get("file", ""))[:500],
            reason=str(d.get("reason", ""))[:2048],
            provenance=ProvenanceV1.from_dict(prov_d).to_dict(),
            acs_links=[dict(x) for x in (d.get("acs_links") or []) if isinstance(x, dict)][:20],
            rationale_links=[str(x)[:400] for x in (d.get("rationale_links") or []) if x][:30],
            semantic_tags=[str(x)[:40] for x in (d.get("semantic_tags") or []) if x][:20],
            significance=max(0.0, min(1.0, float(d.get("significance", 0.5) or 0.5))),
            extra=dict(d.get("extra") or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # ensure sub-structures are normalized dicts
        if isinstance(self.actor, ActorV1):
            d["actor"] = self.actor.to_dict()
        if isinstance(self.provenance, ProvenanceV1):
            d["provenance"] = self.provenance.to_dict()
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))

    def to_jsonl_line(self) -> str:
        """One-line compact form for append-only JSONL log."""
        return self.to_json()


def make_journal_event(
    *,
    event_type: str,
    file: str,
    reason: str,
    actor: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
    provenance: Optional[Dict[str, Any]] = None,
    acs_links: Optional[List[Dict[str, Any]]] = None,
    rationale_links: Optional[List[str]] = None,
    semantic_tags: Optional[List[str]] = None,
    significance: Optional[float] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> JournalEventV1:
    """
    Ergonomic factory for emitting v1 events. Auto-generates stable event_id,
    ISO ts, sensible defaults + best-effort provenance capture (git, host, pid).
    Boosts significance for high-impact actions (deletions, breaking changes).
    Never raises; always returns a valid event (degraded fields on capture fail).
    """
    import uuid
    import datetime
    import socket
    import os

    ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    eid = str(uuid.uuid4())

    if actor is None:
        actor = {
            "type": "agent",
            "identifier": os.environ.get("WIKIFIER_ACTOR", os.environ.get("USER", "unknown-agent")),
            "metadata": {"via": "make_journal_event"},
        }

    if provenance is None:
        prov: Dict[str, Any] = {
            "source": "python:make_journal_event",
            "wikifier_version": __contracts_version__,
            "timestamp_local": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z"),
            "host": socket.gethostname() if "socket" in dir() else None,
            "pid": os.getpid(),
        }
        # best-effort git (no hard dep, silent fail)
        try:
            import subprocess
            root = os.environ.get("WIKIFIER_PROJECT_ROOT", ".")
            res = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=1,
            )
            if res.returncode == 0:
                prov["git_commit"] = res.stdout.strip()[:12]
        except Exception:
            pass
        provenance = prov

    # significance policy (skeleton; health compaction will use + allow override)
    sig = significance if significance is not None else 0.5
    et_lower = event_type.lower()
    if et_lower == "record-deletion":
        sig = max(sig, 0.85)
    if any(kw in reason.lower() for kw in ("breaking", "contract", "security", "api change", "core delete", "refactor critical")):
        sig = max(sig, 0.9)
    if et_lower in ("record-change", "auto-detected") and any(kw in reason.lower() for kw in ("add", "new feature", "introduce")):
        sig = max(sig, 0.65)

    ev = JournalEventV1(
        event_id=eid,
        ts=ts,
        event_type=event_type,
        actor=actor,
        session_id=session_id,
        file=file,
        reason=reason,
        provenance=provenance or {},
        acs_links=acs_links or [],
        rationale_links=rationale_links or [],
        semantic_tags=semantic_tags or [],
        significance=round(sig, 3),
        extra=extra or {},
    )
    return ev


def get_journal_event_info() -> Dict[str, Any]:
    """For health/MCP diagnostics and contracts introspection."""
    return {
        "journal_schema_version": JOURNAL_SCHEMA_VERSION,
        "semantic_actions": list(JOURNAL_SEMANTIC_ACTIONS),
        "event_class": "JournalEventV1",
        "primary_storage": ".wikifier_staging/journal/v1/events.jsonl (JSONL)",
        "projection": "journal/YYYY/MM/DD.md (human MD, dual-written)",
        "compaction": "time + significance (skeleton in health.py)",
    }


# =============================================================================
>>>>>>> agent-4-journal
=======
>>>>>>> agent-7-harness-final
=======
>>>>>>> agent-6-library-final
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

<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
=======
    # === JournalEventV1 (M2 Workstream C) smoke ===
    ev1 = make_journal_event(
        event_type="record-change",
        file="src/foo.py",
        reason="Refactor for M2 durable journal foundation. Links to ACS and prior rationale.",
        session_id="sess-smoke-42",
        semantic_tags=["refactor", "foundation"],
        significance=0.75,
    )
    assert ev1.version == "v1"
    assert ev1.event_type == "record-change"
    assert ev1.file == "src/foo.py"
    assert 0.7 <= ev1.significance <= 0.8
    assert ev1.session_id == "sess-smoke-42"
    assert "python:make_journal_event" in str(ev1.provenance)
    assert ev1.event_id and len(ev1.event_id) > 10

    d = ev1.to_dict()
    assert d["version"] == "v1"
    loaded = JournalEventV1.from_dict(d)
    assert loaded.event_id == ev1.event_id
    assert loaded.significance == ev1.significance

    # from_dict tolerance (legacy / future fields)
    legacyish = {"action": "auto-detected", "file": "bar.js", "reason": "mtime", "extra_future": {"x":1}}
    loaded2 = JournalEventV1.from_dict(legacyish)
    assert loaded2.event_type == "auto-detected"
    assert loaded2.file == "bar.js"

    # deletion boosts significance
    ev_del = make_journal_event(event_type="record-deletion", file="core/api.py", reason="Remove deprecated")
    assert ev_del.significance >= 0.85

    info = get_journal_event_info()
    assert info["journal_schema_version"] == "v1"
    assert "record-deletion" in info["semantic_actions"]
    assert "JSONL" in info["primary_storage"]

>>>>>>> agent-4-journal
=======
>>>>>>> agent-7-harness-final
=======
>>>>>>> agent-6-library-final
    print("All smoke tests passed. Contracts are stable and defensive.")
    print(json.dumps(get_contracts_info(), indent=2))
    sys.exit(0)
