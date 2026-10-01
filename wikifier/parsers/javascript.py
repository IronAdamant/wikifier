"""
JavaScript/TypeScript import parser (agent-first).

AGENT MAP:
  parse_javascript_imports(path) → list of edge dicts (shared contract with python.py)
  Uses resolution.central_resolve, BREE barrels (bree.py), CDIA (cdia.py)
  Self-tests: tests/selftest/run_javascript_selftest.py (+ unittest discover)
Edge fields (summary): module, raw_module, resolved_path, confidence_score/reasons,
  is_dynamic, via_barrel, diagnostic, resolution_metadata, imported_names

Supported:
- ES Modules and CommonJS (static strings)
- Dynamic imports: import("..."), require("..."), require(`...`), require(variable), plus complex/creative expressions (ternaries, calls, concats, aliases) via LDSI progressive analysis
- Template literal imports (including ${} expressions)
- Re-exports (export * from, export { x } from, etc.)
- Barrel expansion for *normal* imports: when `import ... from './barrel'` (or require)
  resolves to a file detected as a barrel (via explicit `export ... from` or via
  name-based heuristic for import+local-export index/barrel files), it is followed
  to ultimate sources (with via_barrel, barrel_depth, barrel_chain, barrel_v2 rich struct,
  resolution_metadata for res_meta_v1, confidence degradation + numeric score + reasons per ACS).
  Same logic applies to explicit re-exports. max_depth=_BARREL_MAX_DEPTH (currently 3) + visited
  cycle guard. All barrel paths now guaranteed rich emission.
- TypeScript type-only imports/exports
- import.meta.resolve(...)
- package.json "exports" maps for modern bare (e.g. "pkg": {".": {"import": "./dist/index.js"}})
  and local-package relative imports. Used in normal resolution (populates resolved_path)
  and barrel following (_follow_reexports). Pragmatic zero-dependency implementation
  covers the most common shapes (string, conditional objects, subpaths, arrays, main fallback).
  (Addresses for barrel and general resolution. Exotic/wildcard cases now
  handled by the long-term BREE subsystem in bree.py with full registry extensibility.)

Dynamic imports are now classified with `is_dynamic`, `dynamic_type`, `dynamic_complexity`,
`expr_raw`, `dynamic_candidates` (enriched), `analysis_methods`, `analysis_notes`, plus
Layer 3 hooks (`indirect_via`, `source_variable`). Full LDSI progressive analysis:
- Layer 0: _extract_balanced_argument (no more truncation on nested calls/ternaries)
- Layer 1: _extract_candidate_literals (recovers possibles from ?:, ||, +, templates, calls)
- Layer 2: _analyze_dynamic_specifier (complexity scoring + notes)
- Layer 3 + 3.5: _resolve_simple_var_dataflow (alias tracking + deeper alias chains / simple alias CFG)
- Layer 4: DYNAMIC_SPECIFIER_REGISTRY + _apply_dynamic_registry (creative handlers)
All rich fields (dynamic + barrel + conditional) flow end-to-end through cache/sh/MCP/Mermaid/library.md
(Phase A pipeline hardening ensures expr_raw + candidates survive the main update_maps path).
Conditional flags detected at import/re-export sites or inside barrel re-exports
are OR-combined during expansion so conditional barrels downgrade confidence and
are marked appropriately.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union

# BREE — Barrel & Re-export Analysis Engine
# Pluggable registry + multi-strategy detectors/extractors/chain expander.
# Imported here for delegation of barrel logic while preserving all contracts.
from .bree import (
    get_bree_engine,
    BREERegistry,
    ExpansionPolicy,
    LightweightRegexReexportExtractor,  # for pattern injection
)

# CDIA — Conditional & Dynamic Import Analysis
# Pluggable registry-driven engine following the exact BREE pattern.
# Produces rich ConditionalAnalysis + DynamicAnalysis (cdia_v1 shape) and
# replaces the legacy 800-char heuristic with explainable, brace-aware detectors.
from .cdia import (
    get_cdia_engine,
    CDIARegistry,
    ConditionalAnalysis,
    DynamicAnalysis,
    AnalysisTraceEntry,
)

from .. import diagnostics
from ..resolution import (
    Resolution,
    ResolutionMetadata,
    decode_res_meta_v1,
    encode_res_meta_v1,
    resolve as central_resolve,
    to_canonical_rel,
    _pick_target_from_conditions as _central_pick_target_from_conditions,
    _read_package_json as _central_read_package_json,
    _resolve_target_path as _central_resolve_target_path,
    resolve_exports_map as _central_resolve_exports_map,
)


# improved root fallbacks for all parser paths
# (supports direct python -m invocation + cwd in subdir / via-symlink / pnpm-store of
# pip-installed external monorepo). Central discover now handles logical PWD walk-up.
# Memo for _get_project_root_fallback: it is called per resolution site —
# during barrel-leaf name routing that means per LEAF per statement — and each
# call used to re-run marker-walk discovery plus Path.resolve(). On a deep
# real tree (Babylon.js) that alone burned 75 minutes on a scoped re-run.
# Keyed by (anchor, env root, cwd) so env/cwd changes can never serve a stale
# root; cleared alongside the other parser caches.
_root_fallback_cache: dict = {}


def _get_project_root_fallback(default: Optional[Union[str, Path]] = None) -> Path:
    """Robust project root fallback used throughout JS parser + resolution sites.

    Primary: discover_project_root() (hardened for symlinks/pnpm stores).
    Secondary: WIKIFIER_* env. Tertiary: default/cwd. Memoized (see above).

    Containment rule: when `default` names the concrete file/dir being
    resolved, the returned root must CONTAIN it — a root that does not contain
    the importer cannot resolve its imports. That situation arises whenever a
    file outside the configured project is parsed (temp fixtures, sibling
    checkouts, ad-hoc single-file runs). In that case the discovered/env root
    is rejected and we walk up from the anchor to the nearest directory with a
    project marker, falling back to the anchor's own directory.

    A literal "." default carries no anchor meaning (callers use it for
    cache-root lookup) and keeps the historical discovery-first behavior.
    """
    memo_key = (
        str(default) if default is not None else None,
        os.environ.get("WIKIFIER_PROJECT_ROOT") or os.environ.get("WIKIFIER_ROOT"),
        os.getcwd(),
    )
    cached = _root_fallback_cache.get(memo_key)
    if cached is not None:
        return cached

    anchor: Optional[Path] = None
    if default is not None and str(default) != ".":
        resolved_default = Path(default).resolve()
        anchor = resolved_default if resolved_default.is_dir() else resolved_default.parent

    def _contains(root: Path) -> bool:
        if anchor is None:
            return True
        try:
            anchor.relative_to(root)
            return True
        except ValueError:
            return False

    def _finish(result: Path) -> Path:
        _root_fallback_cache[memo_key] = result
        return result

    from ..project_root import discover_project_root

    discovered = Path(discover_project_root()).resolve()
    if _contains(discovered):
        return _finish(discovered)
    if anchor is not None:
        markers = ("package.json", ".git", "pyproject.toml", "monitored_paths.txt", ".wikifier", "node_modules")
        for cand in (anchor, *anchor.parents):
            if any((cand / m).exists() for m in markers):
                return _finish(cand)
        return _finish(anchor)
    return _finish(Path.cwd().resolve())


def _make_diag_for_js(
    confidence: str,
    is_dynamic: bool,
    dynamic_type: str,
    is_conditional: bool,
    resolved_path: Optional[str],
    via_barrel: bool,
    barrel_depth: Optional[int],
    raw_module: str,
    barrel_conf: Optional[str] = None,
    *,
    # optional creative CDIA signals for wiring into rich diagnostics (additive, default preserves old calls)
    dynamic_analysis: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Centralized diagnostic factory for all JS downgrade sites (keeps reasons consistent)."""
    c = (confidence or "").lower()
    if c not in ("low", "unresolved"):
        return None

    da = dynamic_analysis or {}
    tags = da.get("semantic_tags", []) or []
    dets = da.get("detectors_fired", []) or []
    creative_tags = [t for t in tags if t in ("tagged_template", "registry_map", "multi_condition_feature_wrapper", "call_produced_path")]
    is_creative = bool(creative_tags) or any(d in ("TaggedTemplateDetector", "RegistryMapDetector", "MultiConditionFeatureWrapperDetector", "CallProducedPathDetector") for d in dets)

    if is_creative:
        # Wire creative signals (prefer new dedicated factory from diagnostics)
        expr = da.get("expr_raw") or raw_module or ""
        return diagnostics.make_creative_dynamic_diagnostic(
            expr=expr,
            creative_tags=creative_tags or tags,
            detectors_fired=dets,
        )

    if is_dynamic and dynamic_type and dynamic_type != "static":
        return diagnostics.make_diagnostic(
            "dynamic",
            f"Dynamic import (type={dynamic_type}) uses runtime expression; static analysis cannot resolve target.",
            severity="warn",
            suggestion_for_agent="Rewrite as static literal import or supply explicit static mapping for complete dependency graph.",
            details={"dynamic_type": dynamic_type, "raw": raw_module},
        )

    if is_conditional:
        return diagnostics.make_diagnostic(
            "conditional",
            "Import/require is inside a conditional context (if/for/try/ternary) or inherited from conditional barrel hop.",
            severity="info",
            suggestion_for_agent="Likely runtime-optional import. Safe for many analyses; map manually if critical path.",
            details={"raw": raw_module},
        )

    if via_barrel and (barrel_depth or 0) >= 3:
        return diagnostics.make_diagnostic(
            "barrel_depth_exceeded",
            f"Re-export barrel chain depth {barrel_depth} reached or exceeded _BARREL_MAX_DEPTH.",
            severity="warn",
            suggestion_for_agent="Inspect the barrel_chain for the terminal file; consider refactoring deep barrels or raising depth limit cautiously.",
            details={"barrel_depth": barrel_depth},
        )

    if not resolved_path:
        cat = "no_fs_match"
        reason = f"No on-disk file found for specifier '{raw_module}' after relative walk + package.json exports probing."
        if "exports" in (raw_module or ""):
            cat = "exports_unmatched"
        return diagnostics.make_diagnostic(
            cat,
            reason,
            severity="warn",
            suggestion_for_agent="External package, missing file, or unsupported exports map shape. Verify the path or treat as third-party.",
            alternatives=[],
            details={"raw": raw_module},
        )

    return diagnostics.make_diagnostic(
        "other",
        f"Resolution succeeded but downgraded to {c} (see rich flags for context).",
        severity="info",
        details={"raw": raw_module},
    )


def _looks_like_barrel_file(filepath: str, parsed_items: List[Dict[str, Any]]) -> bool:
    """Conservative heuristic for: detect barrel files that act as
    aggregators/facades even without any `export ... from` statements.

    Covers the common "import-then-local-export" pattern in index files:
        import { foo } from './foo';
        import { bar } from './bar';
        export { foo, bar };

    Gated behind "barrel-like filename" (index.*, barrel*, entry, api, etc.)
    + presence of >=1 static *relative* import/require. This prevents false
    positives on ordinary source files that use relative imports internally.

    Only used as fallback when no explicit export_* reexports are present.
    """
    if not parsed_items:
        return False

    p = Path(filepath)
    stem = p.stem.lower()
    name = p.name.lower()

    barrel_stems = {"index", "barrel", "entry", "entrypoint", "api", "exports", "public"}
    is_barrel_named = (
        stem in barrel_stems
        or stem.startswith("index")
        or "barrel" in stem
        or "barrel" in name
    )
    if not is_barrel_named:
        return False

    # Static relative imports/requires are the likely sources being re-exported
    relative_aggregates = [
        item for item in parsed_items
        if item.get("is_relative")
        and item.get("dynamic_type") == "static"
        and item.get("statement_type") in ("es_import", "require", "import_equals")
    ]
    return len(relative_aggregates) >= 1


# Barrel following depth limit.
# Raised from hardcoded 2 to 3 to support common real-world barrel chains
# such as "index barrel" -> "feature barrel" -> "leaf module" (3 hops).
# The change is isolated here; recursion is still strictly bounded by
# (1) the visited set on resolved filesystem paths (cycle guard) and
# (2) max_depth <= 0 early return. No other logic or heuristics modified.
_BARREL_MAX_DEPTH = 3


from ._ldsi import (
    _classify_dynamic_import,
    _analyze_dynamic_specifier,
    _extract_balanced_argument,
    _extract_candidate_literals,
    _apply_dynamic_registry,
    DYNAMIC_SPECIFIER_REGISTRY,
)


def _enrich_and_resolve_candidates(src_path: Path, cands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    LDSI Phase: Post-process harvested dynamic_candidates by attempting resolution
    against the current source file using the existing relative + bare resolvers.

    Attaches "resolved_path" and "resolution_confidence": "low" (speculative) when
    successful. Primary dynamic entry keeps its (low) confidence; candidates give
    agents concrete possible targets without overclaiming.

    Safe, best-effort; failures silently drop the resolved fields for that cand.
    """
    if not cands:
        return cands
    enriched: list[dict[str, Any]] = []
    for c in cands:
        raw = c.get("raw", "") or ""
        if not raw:
            enriched.append(dict(c))
            continue
        ec = dict(c)
        try:
            if raw.startswith("."):
                resolved = _try_resolve_relative_path(src_path, raw)
                if resolved:
                    ec["resolved_path"] = str(resolved)
                    ec["resolution_confidence"] = "low"
            else:
                _mod, pth, _c = _try_resolve_bare_internal_import(src_path, raw)
                if pth:
                    ec["resolved_path"] = str(pth)
                    ec["resolution_confidence"] = "low"
        except Exception:
            # never fail the parse for enrichment
            pass
        enriched.append(ec)
    return enriched


def _resolve_simple_var_dataflow(content: str, var_name: str, before_pos: int, max_chars: int = 2500) -> list[dict[str, Any]]:
    """
    LDSI Layer 3 + 3.5: cheap intra-file backward scan to recover the value(s)
    of a simple identifier used as dynamic import argument (e.g. require(mod) where
    const mod = "./foo" or const mod = cond ? "a" : "b" appears earlier).

    Returns harvested candidates from the RHS of the last assignment before the site.
    Very conservative (last textual match in window); over-approx is safe due to low conf.

    Layer 3.5 (deeper aliases / simple alias CFG): builds a lightweight assignment map
    over the window (var_name -> last RHS), then transitively follows simple identifier
    aliases (a = b; b = "./lit" or b = call(); ... ) up to depth 4. Unions literal
    candidates + registry hits from the full alias chain. This is a minimal "CFG for
    aliases" (textual dataflow graph of assignments, last-wins per var, no full control
    flow predicates). Still strictly intra-file, zero-dep, scalable, additive.
    """
    if not var_name or not re.match(r"^[a-zA-Z_$][\w$]*$", var_name):
        return []
    start = max(0, before_pos - max_chars)
    window = content[start:before_pos]
    # Last assignment (textual, supports const/let/var, simple = RHS until ; or end)
    # Handles multi-line RHS crudely by non-greedy but last match wins.
    # allow longer creative RHS (calls, maps, tpls) and parens-balanced feel via limit
    pat = re.compile(
        r"(?:^|[\s;])(?:const|let|var)\s+" + re.escape(var_name) + r"\s*=\s*([^;]{0,400}?)(?:;|$|\n)",
        re.MULTILINE
    )
    ms = list(pat.finditer(window))
    if not ms:
        return []
    rhs = ms[-1].group(1).strip()
    cands = _extract_candidate_literals(rhs)
    # strengthen LDSI dataflow with Layer 4 registry (creative map/call/tagged cases in RHS)
    try:
        reg = _apply_dynamic_registry(rhs, {"context": "dataflow_rhs", "var": var_name})
        for ec in (reg.get("extra_candidates") or []):
            cands.append(ec)
    except Exception:
        pass

    # === Layer 3.5: deeper aliases + simple alias CFG (transitive resolution) ===
    # Scan window once for all simple assignments to build alias map (last textual wins).
    # Follow chain if RHS of a var is itself a bare identifier; harvest cands + registry
    # from every step in the chain. Enables cases like: const p = getPath(x); const m = p; import(m)
    # or const a = "./foo"; const b = a; const c = b; require(c)
    try:
        assign_pat = re.compile(
            r"(?:^|[\s;])(?:const|let|var)?\s*([a-zA-Z_$][\w$]*)\s*=\s*([^;]{0,200}?)(?:;|$|\n)",
            re.MULTILINE
        )
        alias_map: dict[str, str] = {}
        for m in assign_pat.finditer(window):
            v = m.group(1)
            r = (m.group(2) or "").strip()
            if v and r:
                alias_map[v] = r  # last wins (textual order in window)
        # transitive follow for the target var (and any it aliases to)
        def _follow_chain(v: str, seen: set[str], depth: int = 0) -> list[str]:
            if depth > 4 or v in seen:
                return []
            seen.add(v)
            rhs0 = alias_map.get(v)
            if not rhs0:
                return []
            if re.match(r"^[a-zA-Z_$][\w$]*$", rhs0):
                return [rhs0] + _follow_chain(rhs0, seen, depth + 1)
            return [rhs0]
        chain = _follow_chain(var_name, set())
        for item in chain:
            if not item:
                continue
            # harvest literals from this item's text (covers creative RHS in chain)
            for mc in _extract_candidate_literals(item):
                cands.append(mc)
            # registry activation on chain steps (richer creative like call/registry/tagged)
            try:
                reg2 = _apply_dynamic_registry(item, {"context": "alias_chain_3.5", "var": var_name, "depth": len(chain)})
                for ec in (reg2.get("extra_candidates") or []):
                    cands.append(ec)
            except Exception:
                pass
        if len(chain) > 1:
            # mark for upstream (caller appends to notes if cands grew)
            # we leave a sentinel that can be observed in cands context if needed
            pass
        # Light cross-file guard (per creative_dynamic next slice): do not chase RHS that look like
        # module specifiers or paths from other files (keeps O(window) intra-file only; zero-dep, safe).
        # Real cross-file dataflow would require full symbol table / import graph (future, expensive).
        for c in list(cands):
            cr = (c.get("raw") if isinstance(c, dict) else c) or ""
            if "/" in cr or cr.startswith(".") or "require" in cr or "import" in cr:
                # ignore as not local alias value
                try:
                    cands.remove(c) if c in cands else None
                except Exception:
                    pass
    except Exception:
        pass
    # Note: caller will enrich with paths using the real src_path
    return cands


def _detect_conditional_context(content: str, match_start: int) -> str | None:
    """
    CDIA-powered replacement for the legacy 800-char heuristic.

    Delegates to the pluggable CDIA engine which uses ScopeBuilder +
    5+ registered conditional detectors for accurate, explainable results.
    The legacy flat lookback is now only a fallback for extreme edge cases.

    Returns one of:
        "if", "ternary", "switch", "unknown", or None (if it looks top-level)
    """
    return get_cdia_engine().legacy_detect_conditional_context(content, match_start)


def _follow_reexports(
    current_file: Path,
    target_module: str,
    max_depth: int = _BARREL_MAX_DEPTH,
    visited: set | None = None
) -> list[dict]:
    """
    Attempt to follow re-export chains (export * from / export { x } from, or
    import-then-export in barrel-named index files per _looks_like_barrel_file heuristic).

    BREE INTEGRATION: This is now a thin, backward-compatible
    facade over the BarrelReexportAnalysisEngine.expand_chain(). All strategy
    selection, multi-detector scoring, policy-driven expansion, and future
    pluggable extractors (lightweight vs AST) are handled by BREE.

    Resolution, cycle guards, conditional propagation, and exact output shape
    are preserved exactly so that every consumer (parse_javascript_imports,
    shell pipeline, cache, MCP, Mermaid, library.md) sees identical (or richer)
    data. New additive fields such as "barrel_detector" appear automatically.
    """
    if visited is None:
        visited = set()

    if max_depth <= 0:
        return []

    resolved_path = None
    resolved = target_module  # default
    if target_module.startswith('.'):
        level = len(re.match(r'\.+', target_module).group())
        resolved = _resolve_relative_import(current_file, target_module, level)
        # Prefer central_resolve directly; avoid the deprecated shim on the
        # hot path so tests/production do not emit DeprecationWarning.
        resolved_path = _try_resolve_relative_path(current_file, target_module)
        if not resolved_path:
            return [{
                "module": resolved,
                "resolved_path": None,
                "via_barrel": True,
                "barrel_chain": [target_module],
                "barrel_depth": 1,
                "is_conditional": False,
                "conditional_context": None,
                # synthesize minimal barrel_v2 even on early failure
                "barrel_v2": {
                    "via_barrel": True,
                    "barrel_depth": 1,
                    "barrel_chain": [target_module],
                    "barrel_detector": "resolution_failed",
                    "is_partial": True,
                    "partial_reason": "no_resolved_path",
                    "hops": [],
                    "mtimes_signature": "",
                }
            }]
    else:
        resolved, resolved_path, _ = _try_resolve_bare_internal_import(current_file, target_module)
        if not resolved_path:
            return [{
                "module": resolved,
                "resolved_path": None,
                "via_barrel": True,
                "barrel_chain": [target_module],
                "barrel_depth": 1,
                "is_conditional": False,
                "conditional_context": None,
                # synthesize minimal barrel_v2 even on early failure
                "barrel_v2": {
                    "via_barrel": True,
                    "barrel_depth": 1,
                    "barrel_chain": [target_module],
                    "barrel_detector": "resolution_failed",
                    "is_partial": True,
                    "partial_reason": "no_resolved_path",
                    "hops": [],
                    "mtimes_signature": "",
                }
            }]

    # Do not pre-populate visited with this hop.
    # BREE engine owns cycle detection starting from its first resolution
    # (pre-add caused immediate false cycle on every top-level follow call,
    # returning empty results and breaking barrel expansion + via_barrel tagging).

    # === BREE-DRIVEN EXPANSION ===
    # Build a resolver closure that the engine can call for each hop.
    # It re-uses the exact same relative/bare logic we just executed.
    def _resolver_for_engine(curr_file: Path, spec: str) -> Tuple[str, Optional[str], Optional[dict]]:
        """Resolve one hop via the central resolver; returns (display, file, metadata)."""
        r = _central(curr_file, spec)
        meta = r.metadata.to_dict() if isinstance(r.metadata, ResolutionMetadata) else dict(r.metadata or {})
        meta.setdefault("strategy", r.strategy or "central")
        return r.display_module or spec, r.resolved_file, meta

    engine = get_bree_engine()
    # Honor the caller's max_depth by constructing a one-off policy
    # (does not mutate the shared engine policy for other callers).
    call_policy = ExpansionPolicy(
        max_depth=max_depth,
        max_fanout_per_hop=128,
        prefer_precomputed=False,
    )
    # We temporarily create a dedicated engine instance for this call so policy is respected.
    # (Long-term the engine could accept per-call policy override; this is safe & simple.)
    call_engine = type(engine)(policy=call_policy)  # fresh with same registry wiring

    # === prod wiring ===
    # Auto-load persistent BarrelResolutionCache when running under a real project
    # (WIKIFIER_PROJECT_ROOT or CWD with .wikifier_staging/import_cache.json).
    # This makes the normal `python -m wikifier.parsers.javascript <file>` path (used by
    # update-maps first-pass) participate in mtime-validated barrel cache hits + rich
    # barrel_v2 (hops/chain/detector/mtimes) emission for *all* barrel relationships.
    from . import bree as _bree_mod

    proj_root = _get_project_root_fallback(".")
    barrel_ctx = {
        "barrel_cache": _bree_mod.get_session_barrel_cache(proj_root),
        "cache_root": proj_root,
        "importer_rel": to_canonical_rel(current_file, proj_root, follow_symlinks=True) if current_file else None,
    }

    chain_result = call_engine.expand_chain(
        current_file,
        target_module,
        _resolver_for_engine,
        max_depth=max_depth,
        visited=visited,
        **barrel_ctx,  # persistent mtime-aware lookup + store of full barrel_v2
    )

    # Map BREE structured result back to the exact legacy list-of-dicts shape.
    # All legacy fields + new BREE enrichment ("barrel_detector") are present.
    legacy_results = []
    for r in chain_result.results:
        # Ensure all mandatory legacy keys exist (defensive)
        r.setdefault("via_barrel", True)
        r.setdefault("barrel_chain", [target_module])
        r.setdefault("barrel_depth", 1)
        r.setdefault("is_conditional", False)
        r.setdefault("conditional_context", None)
        # emit barrel_v2 rich field (per shared contracts)
        r["barrel_v2"] = {
            "via_barrel": True,
            "barrel_depth": r.get("barrel_depth", 1),
            "barrel_chain": r.get("barrel_chain", [target_module]),
            "barrel_detector": r.get("barrel_detector", getattr(chain_result, "detector_used", "bree")),
            "is_partial": bool(getattr(chain_result, "is_partial", False)),
            "partial_reason": getattr(chain_result, "partial_reason", None),
            "hops": [h.__dict__ if hasattr(h, "__dict__") else h for h in (getattr(chain_result, "hops", []) or [])],
            "mtimes_signature": "",  # populated via persistent cache entry when hit/stored
        }
        # BREE leaves (and early-fail synths) now carry
        # "resolution_metadata" + "strategy" from the final-hop central_resolve (via the 3-tuple
        # returned by _resolver_for_engine and injected at BREE leaf construction sites).
        # We defensively ensure here; the sh normalizer (parse_parser_json_output) will then
        # see the key on *every* barrel-tagged record and emit res_meta_v1 (no contract/sh changes
        # needed). Fallback to site's meta happens at the append site below for ACS + emission.
        r.setdefault("resolution_metadata", r.get("resolution_metadata", {}))
        r.setdefault("strategy", r.get("strategy", "bree"))
        legacy_results.append(r)

    return legacy_results


# Memo for _abs_resolved_target: name routing calls it once per barrel leaf
# per statement (hundreds of thousands of times on barrel-heavy repos); the
# (importer dir, resolved path) -> absolute mapping is stable within a run.
# Cleared alongside the other parser caches.
_abs_target_cache: dict = {}


def _abs_resolved_target(importer_path: Path, resolved_path) -> Optional[Path]:
    """Best-effort absolutization of a resolver-produced path.

    central_resolve returns project-relative paths ("barrel/index.js"); legacy
    fallbacks may return absolute ones. Try project-root-, cwd- and
    importer-relative anchoring; return None when the file cannot be located.
    Memoized per (importer dir, resolved path).
    """
    if not resolved_path:
        return None
    memo_key = (str(importer_path.parent), str(resolved_path))
    if memo_key in _abs_target_cache:
        return _abs_target_cache[memo_key]
    result: Optional[Path] = None
    try:
        p = Path(resolved_path)
        if p.is_absolute():
            result = p.resolve() if p.exists() else p
        else:
            proj_root = _get_project_root_fallback(importer_path.parent)
            cand = proj_root / p
            if cand.exists():
                result = cand.resolve()
            elif p.exists():
                result = p.resolve()
            else:
                cand2 = importer_path.parent / p
                if cand2.exists():
                    result = cand2.resolve()
    except Exception:
        result = None
    _abs_target_cache[memo_key] = result
    return result


# Detector labels that do NOT constitute positive barrel evidence:
# "none" = BREE looked and found no barrel; "unresolved"/"resolution_failed" =
# nothing was followed; "cycle" = expansion aborted; "cached" = replay default
# that carries no signal of its own (real cached barrels keep their original
# detector name). Empty/None = field absent.
_NON_BARREL_DETECTORS = {None, "", "none", "unresolved", "resolution_failed", "cycle", "cached"}


def _probe_shows_real_barrel(probe: List[Dict[str, Any]], direct_resolved_path, importer_path: Path) -> bool:
    """fix (via_barrel pollution): decide whether a _follow_reexports
    probe constitutes GENUINE barrel evidence for a normal (non export_*) import.

    _follow_reexports/BREE unconditionally tag every result with
    via_barrel=True / barrel_depth>=1 — even a plain `import {x} from './a.js'`
    whose "chain" is just the directly-resolved file itself (depth 1, detector
    "none", no hops). Emitting those as barrel edges polluted every clean
    static import. Follow the probe only when the chain actually traversed
    >=1 re-export hop, a detector positively identified the target as a
    barrel, or the expansion produced leaves different from the direct
    resolution. Depth-1 aggregator barrels stay covered by the direct
    structural re-export check on the resolved target itself.

    Unresolved imports (no direct resolution) keep the legacy partial-tagged
    synthetic emission — barrelness cannot be disproved without a resolution,
    and the synth is explicitly marked is_partial/no_resolved_path.
    """
    if not probe:
        return False
    if not direct_resolved_path:
        return True  # legacy behavior for unresolved imports (partial synth)

    direct_abs = _abs_resolved_target(importer_path, direct_resolved_path)
    for r in probe:
        if not isinstance(r, dict):
            continue
        # 1) Chain actually traversed a re-export hop (depth 1 = the file itself).
        if (r.get("barrel_depth") or 0) >= 2:
            return True
        if len(r.get("barrel_chain") or []) >= 2:
            return True
        # 2) A BREE detector positively identified the resolved target as a barrel.
        det = r.get("barrel_detector") or (r.get("barrel_v2") or {}).get("barrel_detector")
        if det not in _NON_BARREL_DETECTORS:
            return True
        # 3) Expansion landed on a different file than the direct resolution.
        rp = r.get("resolved_path")
        if rp and direct_abs is not None:
            r_abs = _abs_resolved_target(importer_path, rp)
            if r_abs is not None and r_abs != direct_abs:
                return True

    # 4) Structural check on the directly-resolved target itself: covers
    # depth-1 aggregator barrels and environments where BREE produced no hops
    # (e.g. a cleared/unwired registry after reset_bree_engine, or unreadable
    # project-relative paths — its extractor then silently returns []).
    try:
        direct_abs = direct_abs or _abs_resolved_target(importer_path, direct_resolved_path)
        if direct_abs is not None and _file_has_reexports(direct_abs):
            return True
    except Exception:
        pass
    return False


def _file_has_reexports(abs_path: Path) -> bool:
    """True if the file contains at least one re-export statement.

    First asks the BREE-backed memoized extractor; on an empty answer falls
    back to a direct scan with the authoritative hoisted EXPORT_PATTERNS,
    because the engine path returns [] (without raising) whenever the BREE
    registry is empty/unwired. Memoized per absolute path via _reexport_cache's
    sibling dict and cleared together with it.
    """
    key = str(abs_path)
    if key in _reexport_probe_cache:
        return _reexport_probe_cache[key]
    result = False
    try:
        if _extract_barrel_reexports(key):
            result = True
        else:
            content = abs_path.read_text(encoding="utf-8", errors="ignore")
            # Same cheap early-out as _extract_barrel_reexports
            if "export" in content and "from" in content:
                result = any(
                    pattern.search(content) for pattern, _ptype in EXPORT_PATTERNS
                )
    except Exception:
        result = False
    _reexport_probe_cache[key] = result
    return result


# ---------------------------------------------------------------------
# Actionable Confidence System (ACS) —
# Numeric score (0.0-1.0) + reasons list derived from existing signals.
# Pure helper; called at emission sites. Backward compat: string "resolution_confidence"
# remains authoritative for legacy consumers; new fields are additive.
# ---------------------------------------------------------------------

def _compute_confidence_score_and_reasons(
    base_conf: str,
    *,
    is_dynamic: bool = False,
    dynamic_type: str = "static",
    is_conditional: bool = False,
    barrel_depth: int | None = None,
    via_barrel: bool = False,
    resolved_path: str | None = None,
    # rich signals from CDIA, Resolution,
    # cycles. All default for full backward compat with old call sites.
    conditional_analysis: dict | None = None,
    dynamic_analysis: dict | None = None,
    resolution_metadata: dict | None = None,
    strategy: str | None = None,
    in_cycle: bool = False,
) -> tuple[float, list[str], str]:
    """
    Thin wrapper delegating to the canonical single-source implementation in
    wikifier.contracts.compute_acs_confidence.

    This guarantees 100% consistency of scores, reasons tokens, and
    high-quality decision-oriented explanations between the JS and Python
    parsers — critical for reliability at monorepo scale.

    See contracts.py:compute_acs_confidence for full authoritative docs,
    penalty tables, explanation builder, and _action_recommendation logic.
    All prior call sites and output shapes are preserved exactly.
    """
    from wikifier.contracts import compute_acs_confidence as _canonical_acs

    return _canonical_acs(
        base_conf,
        is_dynamic=is_dynamic,
        dynamic_type=dynamic_type,
        is_conditional=is_conditional,
        barrel_depth=barrel_depth,
        via_barrel=via_barrel,
        resolved_path=resolved_path,
        conditional_analysis=conditional_analysis,
        dynamic_analysis=dynamic_analysis,
        resolution_metadata=resolution_metadata,
        strategy=strategy,
        in_cycle=in_cycle,
    )


# ---------------------------------------------------------------------
# Resolution helpers (all resolution goes through wikifier.resolution)
# ---------------------------------------------------------------------

_read_package_json = _central_read_package_json
_resolve_target_path = _central_resolve_target_path
_pick_target_from_conditions = _central_pick_target_from_conditions


def _resolve_from_exports(pkg_dir: Path, subpath: str = ".") -> Path | None:
    """Resolve a package subpath via package.json "exports" (central resolver, then BREE
    wildcard handling), falling back to "module"/"main" for packages without exports."""
    via = _central_resolve_exports_map(pkg_dir, subpath) or get_bree_engine().resolve_via_exports(pkg_dir, subpath)
    if via:
        return via
    pkg = _read_package_json(pkg_dir)
    if pkg and pkg.get("exports") is None:
        for key in ("module", "main", "jsnext:main"):
            value = pkg.get(key)
            if isinstance(value, str):
                target = _resolve_target_path(pkg_dir, value)
                if target:
                    return target
    return None


def _central(current_file: Path, raw_module: str):
    return central_resolve(raw_module, str(current_file), _get_project_root_fallback(current_file.parent))


def _try_resolve_relative_path(current_file: Path, raw_module: str) -> str | None:
    """Resolved target file for a specifier (or None)."""
    return _central(current_file, raw_module).resolved_file


def _try_resolve_bare_internal_import(current_file: Path, raw_module: str) -> tuple[str, str | None, str]:
    """``(display_module, resolved_file_or_None, confidence)`` for a specifier."""
    res = _central(current_file, raw_module)
    return res.display_module or raw_module, res.resolved_file, res.confidence or "medium"


def _resolve_relative_import(current_file: Path, raw_module: str, level: int) -> str:
    """Dotted display name for a relative specifier (directory names up to the project root)."""
    if level == 0 or not raw_module.startswith("."):
        return raw_module
    root = _get_project_root_fallback(current_file.parent)
    try:
        parts = list(current_file.parent.relative_to(root).parts)
    except ValueError:
        parts = [current_file.parent.name]
    for _ in range(level - 1):
        if parts:
            parts.pop()
    cleaned = raw_module.lstrip(".").replace("/", ".").replace("\\", ".").strip(".")
    return ".".join(p for p in (*parts, cleaned) if p) or cleaned or raw_module


# =============================================================================
# Hoisted module-level regex patterns (compiled once per process), EXPORT subset,
# memo caches, and _extract_barrel_reexports — optimizations for.
# (The original local compiles inside parse() will be removed in follow-up edit.)
# =============================================================================

# ES Module imports (including bare side-effect imports like: import "module")
es_import_pattern = re.compile(
    r'import\s+(?:(?:\*\s+as\s+\w+|[\w\s{},*]+)\s+from\s+)?[\'"]([^\'"]+)[\'"]',
    re.MULTILINE
)

# CommonJS: require("..."), require(`...`), require(someVar)
require_pattern = re.compile(
    r'require\s*\(\s*'
    r'(?:'
        r'[\'"](?P<static>[^\'"]+)[\'"]'
        r'|`(?P<template>[^`]+)`'
        r'|(?P<expression>[^)]+?)'
    r')\s*\)',
    re.MULTILINE
)

# import ... = require("...")
# [^=\n;]+ (was [^=]+) — the unbounded class crossed statement
# boundaries (newlines/semicolons), so `import {x} from './a';\nconst y = require('./b');`
# matched as a single bogus import-equals and emitted a DUPLICATE edge for './b'
# (already captured by require_pattern). TS `import x = require("y")` is a
# single-line statement, so excluding \n and ; is safe.
import_equals_pattern = re.compile(
    r'import\s+[^=\n;]+=\s*require\s*\(\s*[\'"]([^\'"]+)[\'"]',
    re.MULTILINE
)

# Dynamic import() — supports static strings, template literals, and expressions/variables
dynamic_import_pattern = re.compile(
    r'import\s*\(\s*'
    r'(?:'
        r'[\'"](?P<static>[^\'"]+)[\'"]'
        r'|`(?P<template>[^`]+)`'
        r'|(?P<expression>[^)]+?)'
    r')\s*\)',
    re.MULTILINE
)

# import.meta (import.meta.url, import.meta.resolve, import.meta.env, etc.)
# import.meta.resolve is a Stage 3 proposal and may not be widely supported yet.
import_meta_pattern = re.compile(
    r'import\.meta(?:\.[a-zA-Z0-9_]+)?',
    re.MULTILINE
)

# Re-exports: export ... from "...", export * from "...", export {x} from "..."
export_from_pattern = re.compile(
    r'export\s+(?:\*\s+from|[\w\s{},*]+\s+from)\s+[\'"]([^\'"]+)[\'"]',
    re.MULTILINE
)

# TypeScript: import type { ... } from "...", import type * as X from "..."
import_type_pattern = re.compile(
    r'import\s+type\s+(?:[^\'"]+from\s+)?[\'"]([^\'"]+)[\'"]',
    re.MULTILINE
)

# Bare side-effect imports: import "module" or import 'module'
side_effect_pattern = re.compile(
    r'^\s*import\s+[\'"]([^\'"]+)[\'"]\s*;?\s*$',
    re.MULTILINE
)

# export * as name from "..."
export_as_pattern = re.compile(
    r'export\s+\*\s+as\s+[a-zA-Z0-9_]+\s+from\s+[\'"]([^\'"]+)[\'"]',
    re.MULTILINE
)

# export * from "..." (bare re-export)
export_star_pattern = re.compile(
    r'export\s+\*\s+from\s+[\'"]([^\'"]+)[\'"]',
    re.MULTILINE
)

# TypeScript: export type { ... } from "..."
export_type_pattern = re.compile(
    r'export\s+type\s+(?:[^\'"]+from\s+)?[\'"]([^\'"]+)[\'"]',
    re.MULTILINE
)

# TypeScript: import type * as X from "..."
import_type_as_pattern = re.compile(
    r'import\s+type\s+\*\s+as\s+\w+\s+from\s+[\'"]([^\'"]+)[\'"]',
    re.MULTILINE
)

# TypeScript: export type * from "..."
export_type_star_pattern = re.compile(
    r'export\s+type\s+\*\s+from\s+[\'"]([^\'"]+)[\'"]',
    re.MULTILINE
)

# TypeScript: export type * as ns from "..."
export_type_as_star_pattern = re.compile(
    r'export\s+type\s+\*\s+as\s+\w+\s+from\s+[\'"]([^\'"]+)[\'"]',
    re.MULTILINE
)

# TypeScript: export { type Foo } from "..."
export_type_only_pattern = re.compile(
    r'export\s*\{\s*type\s+[^}]+\}\s+from\s+[\'"]([^\'"]+)[\'"]',
    re.MULTILINE
)

# TypeScript: export { type Foo as Bar } from "..."
export_type_alias_pattern = re.compile(
    r'export\s*\{\s*type\s+\w+\s+as\s+\w+[^}]*\}\s+from\s+[\'"]([^\'"]+)[\'"]',
    re.MULTILINE
)

# TypeScript: export type { Foo as Bar } from "..."
export_type_only_alias_pattern = re.compile(
    r'export\s+type\s*\{\s*\w+\s+as\s+\w+[^}]*\}\s+from\s+[\'"]([^\'"]+)[\'"]',
    re.MULTILINE
)

# TypeScript: export { type Foo as Bar } from "..." (with possible other items)
export_type_alias_full_pattern = re.compile(
    r'export\s*\{[^}]*type\s+\w+\s+as\s+\w+[^}]*\}\s+from\s+[\'"]([^\'"]+)[\'"]',
    re.MULTILINE
)

# TypeScript: export { type Foo, Bar } from "..." (mixed type and value)
export_mixed_type_pattern = re.compile(
    r'export\s*\{[^}]*type\s+\w+[^}]*\}\s+from\s+[\'"]([^\'"]+)[\'"]',
    re.MULTILINE
)

# Modern: import.meta.resolve("...") — now supports static + template + expression via named groups
# so it participates in full LDSI pipeline (Layer 0 balanced capture for nested, Layer 1 harvesting,
# classification, expr_raw, dynamic_candidates, confidence downgrade). Matches require/dynamic_import_pattern shape.
import_meta_resolve_pattern = re.compile(
    r'import\.meta\.resolve\s*\(\s*'
    r'(?:'
        r'[\'"](?P<static>[^\'"]+)[\'"]'
        r'|`(?P<template>[^`]+)`'
        r'|(?P<expression>[^)]+?)'
    r')\s*\)',
    re.MULTILINE
)


# Subset for lightweight extractor (only re-export patterns)
EXPORT_PATTERNS = [
    (export_from_pattern, "export_from"),
    (export_as_pattern, "export_as"),
    (export_star_pattern, "export_star"),
    (export_type_pattern, "export_type"),
    (export_type_star_pattern, "export_type_star"),
    (export_type_as_star_pattern, "export_type_as_star"),
    (export_type_only_pattern, "export_type_only"),
    (export_type_alias_pattern, "export_type_alias"),
    (export_type_alias_full_pattern, "export_type_alias_full"),
    (export_type_only_alias_pattern, "export_type_only_alias"),
    (export_mixed_type_pattern, "export_mixed_type"),
]

# Wire the authoritative hoisted patterns + conditional detector into BREE's
# default lightweight extractor so that bree.py and javascript.py stay in sync
# and exotic re-export syntax (export * as, type variants, etc.) is fully covered.
_bree_light = BREERegistry.get_extractor("lightweight-regex")
if _bree_light and isinstance(_bree_light, LightweightRegexReexportExtractor):
    _bree_light._patterns = EXPORT_PATTERNS  # type: ignore[attr-defined]
    # Provide the real conditional heuristic (used during extract)
    # The extractor will receive it via **context in calls below.

# Memoization for full parses and (especially) barrel reexport extractions.
# Safe within-process cache for the duration of one parser invocation in update-maps.
_parse_cache: dict[str, List[Dict[str, Any]]] = {}
_reexport_cache: dict[str, list[dict]] = {}
# boolean "does this file contain any re-export?" probe results
# (see _file_has_reexports); cleared together with _reexport_cache.
_reexport_probe_cache: dict[str, bool] = {}
# Leaf-explosion policy: per-file "names this module exports" harvest results
# (see _harvest_export_names); cleared together with _reexport_cache.
_export_names_cache: dict[str, frozenset] = {}


def _clear_parse_cache() -> None:
    _parse_cache.clear()


def _clear_reexport_cache() -> None:
    _reexport_cache.clear()
    _reexport_probe_cache.clear()
    _export_names_cache.clear()
    _root_fallback_cache.clear()
    _abs_target_cache.clear()


# =============================================================================
# Barrel-leaf explosion policy
#
# A single `import { X } from "big-barrel"` against an `export *` barrel used
# to emit one edge per reachable leaf — 778 edges for a 2-symbol import on
# Babylon.js's @dev/core, ~107 edges/file repo-wide. The entry-barrel edge is
# always the true filesystem dependency; the leaves are a refinement, so they
# are (1) routed by the names the statement actually imports when possible,
# else (2) capped, with the selection reported on the first emitted edge —
# truncation is never silent.
# =============================================================================

_EXPORT_DECL_RE = re.compile(
    r'export\s+(?:declare\s+)?(?:abstract\s+)?(?:async\s+)?'
    r'(?:const|let|var|function\*?|class|enum|interface|type|namespace)\s+([A-Za-z_$][\w$]*)'
)
_EXPORT_BRACE_RE = re.compile(r'export\s*(?:type\s*)?\{([^}]*)\}')
_EXPORT_DEFAULT_RE = re.compile(r'export\s+default\b')


def _barrel_leaf_cap() -> int:
    """Max leaves emitted per barrel import site when name routing fails.

    Tunable via WIKIFIER_BARREL_LEAF_CAP (0 = unlimited / legacy behavior).
    Read dynamically so tests and agents can adjust without re-import.
    """
    try:
        return max(0, int(os.environ.get("WIKIFIER_BARREL_LEAF_CAP", "24")))
    except ValueError:
        return 24


def _harvest_export_names(file_path: str) -> frozenset:
    """Best-effort set of names a module exports (regex-based, memoized).

    Covers declarations (const/class/function/enum/interface/type/...),
    brace exports including re-exports (`export { a, b as c } from ...` —
    the public name is the alias side), and `export default`. `export *`
    contributes nothing (the names are unknowable without recursion); a
    leaf reached only through `export *` chains simply won't match and the
    caller falls back to the cap.
    """
    cached = _export_names_cache.get(file_path)
    if cached is not None:
        return cached
    names: set = set()
    try:
        text = Path(file_path).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        text = ""
    if text:
        for m in _EXPORT_DECL_RE.finditer(text):
            names.add(m.group(1))
        for m in _EXPORT_BRACE_RE.finditer(text):
            for part in m.group(1).split(","):
                part = re.sub(r'^\s*type\s+', '', part.strip())
                if " as " in part:
                    part = part.split(" as ")[-1].strip()
                if part and part != "default":
                    names.add(part)
        if _EXPORT_DEFAULT_RE.search(text):
            names.add("default")
    result = frozenset(names)
    _export_names_cache[file_path] = result
    return result


def _extract_imported_names(stmt: str) -> Optional[list]:
    """Names a statement imports, as exported by the target module.

    `import { a, b as c, type d } from "x"` -> ["a", "b", "d"] (left side of
    `as` — that's the name the barrel exports). Default imports contribute
    "default"; destructured require contributes the left side of `:`.
    Returns None when routing is impossible: namespace (`import * as ns`),
    side-effect, and dynamic imports may use anything from the module.
    """
    s = stmt or ""
    if re.search(r'import\s*\(', s) or re.match(r'\s*import\s+[\'"]', s):
        return None
    if re.search(r'import\s+\*\s+as\s+', s):
        return None
    names: list = []
    m = re.search(r'(?:import|export)\s*(?:type\s*)?\{([^}]*)\}', s)
    if m:
        for part in m.group(1).split(","):
            part = re.sub(r'^\s*type\s+', '', part.strip())
            left = part.split(" as ")[0].strip() if " as " in part else part
            if left:
                names.append(left)
    if re.match(r'\s*import\s+(?:type\s+)?([A-Za-z_$][\w$]*)\s*(?:,|\s+from)', s):
        names.append("default")
    rm = re.search(r'(?:const|let|var)\s*\{([^}]*)\}\s*=\s*require', s)
    if rm:
        for part in rm.group(1).split(","):
            left = part.split(":")[0].strip()
            if left:
                names.append(left)
    return names or None


def _select_barrel_leaves(
    followed: List[Dict[str, Any]],
    imported_names: Optional[list],
    entry_prepended: bool,
    entry_resolved_path: Optional[str] = None,
    importer_path: Optional[Path] = None,
) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Apply the leaf-explosion policy to a barrel expansion result.

    The entry edge is always kept — whether it was prepended by the caller
    (index 0) or arrived inside the expansion itself (matched against
    entry_resolved_path; a pure `export *` barrel exports no harvestable
    names, so name routing must never be allowed to drop it). Leaves are
    deduped by resolved_path (BREE can reach the same leaf via multiple hop
    paths), then name-routed when the statement names symbols and >=1 leaf's
    harvested exports intersect them, then capped at _barrel_leaf_cap().
    Returns (selected, selection_meta); selection_meta is None when nothing
    was dropped.
    """
    entry_abs = None
    if entry_resolved_path and importer_path is not None:
        try:
            entry_abs = _abs_resolved_target(importer_path, entry_resolved_path)
        except Exception:
            entry_abs = None

    entry = None
    leaves: List[Dict[str, Any]] = []
    seen_rp: set = set()
    for idx, rec in enumerate(followed):
        rp = rec.get("resolved_path") if isinstance(rec, dict) else None
        is_entry = entry_prepended and idx == 0
        if not is_entry and rp and entry_resolved_path:
            is_entry = rp == entry_resolved_path or (
                entry_abs is not None
                and importer_path is not None
                and _abs_resolved_target(importer_path, rp) == entry_abs
            )
        if is_entry:
            if entry is None:
                entry = rec
            continue  # entry duplicates add nothing
        if rp:
            if rp in seen_rp:
                continue
            seen_rp.add(rp)
        leaves.append(rec)

    total = len(leaves)
    if total == 0:
        return ([entry] if entry is not None else list(followed)), None

    mode = None
    if imported_names:
        wanted = set(imported_names)
        matched = []
        for leaf in leaves:
            rp = leaf.get("resolved_path") if isinstance(leaf, dict) else None
            if not rp:
                continue
            # resolved_path is usually project-relative; absolutize so the
            # export-name harvest reads the real file regardless of cwd.
            rp_abs = None
            if importer_path is not None:
                try:
                    rp_abs = _abs_resolved_target(importer_path, rp)
                except Exception:
                    rp_abs = None
            if _harvest_export_names(str(rp_abs or rp)) & wanted:
                matched.append(leaf)
        if matched:
            leaves = matched
            mode = "name-match"

    truncated = False
    cap = _barrel_leaf_cap()
    if cap and len(leaves) > cap:
        leaves = leaves[:cap]
        truncated = True
        mode = f"{mode}+capped" if mode else "capped"

    selection = None
    if len(leaves) < total:
        selection = {
            "mode": mode or "name-match",
            "leaves_total": total,
            "leaves_emitted": len(leaves),
            "truncated": truncated,
        }
    out = ([entry] + leaves) if entry is not None else leaves
    return out, selection


def _extract_barrel_reexports(filepath: str) -> list[dict]:
    """
    Lightweight re-export only extractor for barrel probe path in _follow_reexports.
    Now delegates to BREE (Barrel & Re-export Analysis Engine) for pluggable
    extraction while preserving the exact legacy cache, early-out heuristics,
    and dict shape for 100% backward compatibility.
    """
    path = Path(filepath).resolve()
    key = str(path)
    if key in _reexport_cache:
        return _reexport_cache[key]
    if not path.exists():
        res: list[dict] = []
        _reexport_cache[key] = res
        return res
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        res = []
        _reexport_cache[key] = res
        return res

    content, _barrel_string_spans = _lex_mask(content)
    # Early exit heuristic (cheap str check) — only regex if possibly relevant.
    if "export" not in content or "from" not in content:
        res = []
        _reexport_cache[key] = res
        return res

    # === BREE INTEGRATION ===
    # Delegate the actual extraction to the registered lightweight extractor
    # (which now has the full EXPORT_PATTERNS and conditional helper wired).
    # This enables future swap to AST extractor or additional registered strategies
    # without touching this call site.
    results = get_bree_engine().extract_reexports(
        filepath,
        extractor_name="lightweight-regex",
        content=content,
        _detect_conditional=_detect_conditional_context,
    ) or []
    unique: list[dict] = []
    seen_hops: set = set()
    for item in results:
        sig = (item.get("raw_module"), bool(item.get("is_conditional")))
        if sig not in seen_hops:
            seen_hops.add(sig)
            unique.append(item)
    _reexport_cache[key] = unique
    return unique



# =============================================================================
# Lexical masking: blank comments, record string-literal spans
# =============================================================================

_REGEX_PRECEDERS = set("(,=:[!&|?{};+-*%<>~^")


def _lex_mask(content: str):
    """Return ``(masked, string_spans)``.

    ``masked`` is ``content`` with every ``//`` and ``/* */`` comment replaced
    by spaces (newlines kept, so offsets and line numbers are unchanged).
    ``string_spans`` lists ``(start, end)`` offsets of quote/template string
    literals — code inside template ``${...}`` is *not* part of a span. Regex
    literals are skipped heuristically (``/`` after an operator or line start).
    """
    out = list(content)
    spans = []
    n = len(content)
    i = 0
    last_sig = ""          # last significant (non-space) code char
    template_depth = []    # brace depth stack for nested ${ } inside templates

    def blank(a: int, b: int) -> None:
        for k in range(a, b):
            if out[k] != "\n":
                out[k] = " "

    while i < n:
        c = content[i]
        nxt = content[i + 1] if i + 1 < n else ""
        if c == "/" and nxt == "/":
            end = content.find("\n", i)
            end = n if end == -1 else end
            blank(i, end)
            i = end
            continue
        if c == "/" and nxt == "*":
            end = content.find("*/", i + 2)
            end = n if end == -1 else end + 2
            blank(i, end)
            i = end
            continue
        if c in ("'", '"') or (c == "`"):
            quote = c
            start = i
            i += 1
            while i < n:
                ch = content[i]
                if ch == "\\":
                    i += 2
                    continue
                if quote == "`" and ch == "$" and i + 1 < n and content[i + 1] == "{":
                    spans.append((start, i))
                    template_depth.append(0)
                    i += 2
                    start = None
                    break
                if ch == quote or (quote != "`" and ch == "\n"):
                    i += 1
                    break
                i += 1
            if start is not None:
                spans.append((start, i))
            last_sig = quote
            continue
        if template_depth:
            if c == "{":
                template_depth[-1] += 1
            elif c == "}":
                if template_depth[-1] == 0:
                    template_depth.pop()
                    # resume the enclosing template literal
                    start = i
                    i += 1
                    while i < n:
                        ch = content[i]
                        if ch == "\\":
                            i += 2
                            continue
                        if ch == "$" and i + 1 < n and content[i + 1] == "{":
                            spans.append((start, i))
                            template_depth.append(0)
                            i += 2
                            start = None
                            break
                        if ch == "`":
                            i += 1
                            break
                        i += 1
                    if start is not None:
                        spans.append((start, i))
                    continue
                template_depth[-1] -= 1
        if c == "/" and (not last_sig or last_sig in _REGEX_PRECEDERS):
            j = i + 1
            in_class = False
            while j < n and content[j] != "\n":
                ch = content[j]
                if ch == "\\":
                    j += 2
                    continue
                if ch == "[":
                    in_class = True
                elif ch == "]":
                    in_class = False
                elif ch == "/" and not in_class:
                    break
                j += 1
            if j < n and content[j] == "/":
                spans.append((i, j + 1))
                i = j + 1
                last_sig = "/"
                continue
        if not c.isspace():
            last_sig = c
        i += 1
    return "".join(out), spans


def _in_spans(spans, pos: int) -> bool:
    """Binary search: is ``pos`` inside any (start, end) span?"""
    import bisect

    idx = bisect.bisect_right(spans, (pos, float("inf"))) - 1
    return idx >= 0 and spans[idx][0] <= pos < spans[idx][1]


def parse_javascript_imports(filepath: str) -> List[Dict[str, Any]]:
    """
    Parse a JavaScript or TypeScript file and return structured import information.
    """
    path = Path(filepath).resolve()
    key = str(path)
    if key in _parse_cache:
        return _parse_cache[key]

    if not path.exists():
        res = []
        _parse_cache[key] = res
        return res

    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        res = []
        _parse_cache[key] = res
        return res

    # Comments are blanked (offsets kept); matches whose keyword sits inside a
    # string literal are ignored, so commented-out or quoted imports are not edges.
    content, string_spans = _lex_mask(content)
    claimed_specifiers: set = set()
    imports: List[Dict[str, Any]] = []

    # (Local pattern compiles removed — all regexes are hoisted at module level for
    # single compile per process for top-level parses too,
    # in addition to the probe-path wins from _extract + heuristic + caches.)

    # (remaining local pattern compiles removed in second pass — all now hoisted)

    # Most specific patterns first: each string specifier is claimed by the
    # first pattern that matches it, so overlapping patterns (export_from vs
    # export_star, es_import vs import_type, ...) cannot emit duplicate edges.
    all_patterns = [
        (import_type_as_pattern, "import_type_as"),
        (import_type_pattern, "import_type"),
        (export_type_as_star_pattern, "export_type_as_star"),
        (export_type_star_pattern, "export_type_star"),
        (export_type_only_alias_pattern, "export_type_only_alias"),
        (export_type_alias_full_pattern, "export_type_alias_full"),
        (export_type_alias_pattern, "export_type_alias"),
        (export_type_only_pattern, "export_type_only"),
        (export_mixed_type_pattern, "export_mixed_type"),
        (export_type_pattern, "export_type"),
        (export_as_pattern, "export_as"),
        (export_star_pattern, "export_star"),
        (export_from_pattern, "export_from"),
        (side_effect_pattern, "side_effect_import"),
        (import_equals_pattern, "import_equals"),
        (es_import_pattern, "es_import"),
        (require_pattern, "require"),
        (dynamic_import_pattern, "dynamic_import"),
        (import_meta_resolve_pattern, "import_meta_resolve"),
        (import_meta_pattern, "import_meta"),
    ]

    for pattern, ptype in all_patterns:
        for match in pattern.finditer(content):
            keyword_pos = match.start() + (len(match.group(0)) - len(match.group(0).lstrip()))
            if _in_spans(string_spans, keyword_pos):
                continue
            spec_positions = [match.start(g) for g in range(1, (match.lastindex or 0) + 1) if match.group(g)]
            spec_pos = spec_positions[0] if spec_positions else match.start()
            if spec_pos in claimed_specifiers:
                continue
            claimed_specifiers.add(spec_pos)
            groups = match.groupdict()

            # Prefer named groups (new dynamic/require patterns)
            if groups:
                if groups.get("static"):
                    raw_module = groups["static"]
                    # import('./x') is a runtime (lazy) load even with a literal path.
                    dynamic_type = "literal" if ptype in ("dynamic_import", "import_meta_resolve") else "static"
                    dynamic_complexity = "simple"
                    expr_raw = None
                    dynamic_candidates = []
                    analysis_notes = []
                elif groups.get("template"):
                    raw_module = groups["template"]
                    dynamic_type = "template_literal"
                    expr_raw = f"`{raw_module}`"
                    dynamic_candidates = _extract_candidate_literals(expr_raw)
                    dynamic_candidates = _enrich_and_resolve_candidates(path, dynamic_candidates)
                    analysis = _analyze_dynamic_specifier(expr_raw)
                    dynamic_complexity = analysis.get("dynamic_complexity", "moderate")
                    analysis_notes = analysis.get("analysis_notes", [])
                elif groups.get("expression"):
                    # === Layer 0: Robust balanced capture (fixes nested parens in creative exprs) ===
                    balanced = _extract_balanced_argument(content, match.start())
                    expr_text = balanced if balanced is not None else groups["expression"].strip()
                    # === Layer 2: Rich analysis (complexity + notes) ===
                    analysis = _analyze_dynamic_specifier(expr_text)
                    dynamic_type = analysis["dynamic_type"]
                    raw_module = analysis["cleaned"]
                    dynamic_complexity = analysis["dynamic_complexity"]
                    analysis_notes = analysis["analysis_notes"]
                    # === Layer 1: Harvest embedded literals for candidate recovery ===
                    expr_raw = expr_text
                    dynamic_candidates = _extract_candidate_literals(expr_text)
                    dynamic_candidates = _enrich_and_resolve_candidates(path, dynamic_candidates)
                    # === Layer 3 (initial): if the expr reduced to a simple var ident, pull its definition ===
                    if re.match(r"^[a-zA-Z_$][\w$]*$", raw_module):
                        var_cands = _resolve_simple_var_dataflow(content, raw_module, match.start())
                        if var_cands:
                            # merge (dedup later or by enrich consumer); tag
                            for vc in var_cands:
                                vc.setdefault("context", "dataflow_var_rhs")
                            dynamic_candidates = (dynamic_candidates or []) + var_cands
                            analysis_notes = (analysis_notes or []) + ["dataflow_var_substitution"]
                            dynamic_candidates = _enrich_and_resolve_candidates(path, dynamic_candidates)

                    # ===: invoke dynamic registry in expression paths (LDSI Layer 4 activation for creative) ===
                    # Covers TaggedTemplate, RegistryMap, MultiCond, CallProduced etc. without core loop changes.
                    try:
                        reg_hit = _apply_dynamic_registry(expr_text, {"path": str(path), "raw": raw_module, "context": "expression_path"})
                        extras = reg_hit.get("extra_candidates") or []
                        if extras:
                            dynamic_candidates = (dynamic_candidates or []) + extras
                            dynamic_candidates = _enrich_and_resolve_candidates(path, dynamic_candidates)
                        for note in (reg_hit.get("notes") or []):
                            if note and note not in (analysis_notes or []):
                                analysis_notes = (analysis_notes or []) + [f"registry:{note}"]
                        for tag in (reg_hit.get("tags") or []):
                            if tag and f"tag:{tag}" not in (analysis_notes or []):
                                analysis_notes = (analysis_notes or []) + [f"tag:{tag}"]
                    except Exception:
                        pass  # never break parse
                else:
                    continue
            else:
                # Fallback for patterns without named groups (es_import, import_equals,
                # export_*, import_type*, side_effect_import, ...). Every one of these
                # patterns captures its specifier from INSIDE a quoted string literal,
                # so the edge is static by construction.
                #
                # fix (is_dynamic bleed): this branch used to run the captured
                # literal through _analyze_dynamic_specifier, which classified plain
                # relative specifiers like './a.js' as dynamic_type="expression"
                # (no surrounding quotes survive the regex capture), polluting every
                # static ES import with is_dynamic=True + "low" confidence. The
                # genuinely dynamic-capable patterns (require, dynamic_import,
                # import.meta.resolve) all use named groups and are fully handled in
                # the `if groups:` branch above — they never reach here.
                raw_module = ""
                for g in match.groups():
                    if g:
                        raw_module = g.strip()
                        break
                dynamic_type = "static"
                dynamic_complexity = "simple"
                analysis_notes = []
                expr_raw = None
                dynamic_candidates = []

            if not raw_module:
                continue

            original = match.group(0).strip()
            # Include `const {a, b} = require(...)` so imported_names can route BREE.
            if ptype == "require":
                line_start = content.rfind("\n", 0, match.start()) + 1
                prefix = content[line_start:match.start()]
                original = (prefix + match.group(0)).strip()

            is_relative = raw_module.startswith('.')
            level = len(re.match(r'\.+', raw_module).group()) if is_relative else 0

            resolved_path = None
            confidence = "unresolved"
            strategy_name = "legacy-fallback"
            res_meta: Dict[str, Any] = {}

            try:
                res: Resolution = _central(path, raw_module)
            except (OSError, ValueError) as resolve_error:
                # Unreadable configs / odd specifiers: keep the edge, mark it unresolved.
                resolved_path = None
                resolved_module = raw_module
                confidence = "unresolved"
                strategy_name = "resolver-error"
                res_meta = {"strategy": strategy_name, "error": f"{type(resolve_error).__name__}: {resolve_error}"}
            else:
                resolved_path = res.resolved_file
                resolved_module = res.display_module or raw_module
                confidence = res.confidence
                strategy_name = res.strategy
                if isinstance(res.metadata, ResolutionMetadata):
                    res_meta = res.metadata.to_dict()
                else:
                    res_meta = dict(res.metadata or {})
                res_meta["strategy"] = strategy_name

            # Downgrade confidence for genuinely dynamic cases
            if dynamic_type == "template_literal":
                confidence = "low" if confidence == "medium" else confidence
            elif dynamic_type == "expression":
                confidence = "low"
            elif dynamic_type == "unknown":
                confidence = "unresolved"

            is_dynamic = dynamic_type != "static"

            # === CDIA Integration (additive, non-breaking) ===
            # Call the pluggable CDIA engine (registry + ScopeBuilder + 8 detectors).
            # This replaces the old crude heuristic while producing the exact
            # ConditionalAnalysis + DynamicAnalysis shapes for cdia_v1.
            # Legacy fields (is_conditional, conditional_context) are derived from
            # the rich result so all existing consumers, ACS, Mermaid, cache, etc.
            # continue to work unchanged. The full cdia dict is attached for
            # future pipeline emission of the versioned base64 cdia_v1 field.
            cdia_payload: Dict[str, Any] = {}
            try:
                cdia_engine = get_cdia_engine()
                cdia_payload = cdia_engine.analyze_import_site(
                    content,
                    match.start(),
                    raw_module,
                    expr_raw=expr_raw,
                    dynamic_type_hint=dynamic_type if is_dynamic else "static",
                    statement_type=ptype,
                    # Pass through any existing dynamic_candidates for enrichment
                    dynamic_candidates=dynamic_candidates if is_dynamic else [],
                )
                ca = cdia_payload.get("conditional_analysis", {})
                da = cdia_payload.get("dynamic_analysis", {})
                is_conditional = bool(ca.get("is_conditional", False))
                # Derive legacy conditional_context string from CDIA for compat
                cond_tags = ca.get("semantic_tags", [])
                predicate = ca.get("predicate_snippet") or ""
                if "ternary" in cond_tags or "ternary" in predicate.lower():
                    conditional_context = "ternary"
                elif any(t in ("if_statement", "control_flow") for t in cond_tags) or "if" in predicate.lower():
                    conditional_context = "if"
                elif "switch" in predicate.lower():
                    conditional_context = "switch"
                else:
                    conditional_context = "unknown" if is_conditional else None
            except Exception:
                # Absolute safety net — fall back to (now CDIA-powered) legacy path
                conditional_context = _detect_conditional_context(content, match.start())
                is_conditional = conditional_context is not None
                cdia_payload = {
                    "conditional_analysis": {"is_conditional": is_conditional, "semantic_tags": [], "detectors_fired": [], "analysis_trace": [], "confidence": 0.0, "degraded": True},
                    "dynamic_analysis": {"dynamic_type": dynamic_type, "complexity": "simple", "semantic_tags": [], "detectors_fired": [], "analysis_trace": [], "confidence": 0.0, "degraded": True},
                }
                ca = cdia_payload.get("conditional_analysis", {})
                da = cdia_payload.get("dynamic_analysis", {})

            # Downgrade confidence for conditional imports (unchanged behavior)
            if is_conditional:
                confidence = "low"

            # ===: Barrel Re-export Following ===
            # Explicit re-exports (export_* ptypes) always attempt to follow the chain

            # For normal imports (es_import, require, dynamic, etc.), we only expand when
            # the import resolves directly to a barrel file. Barrel detection (see
            # _looks_like_barrel_file + export_* filter in _follow_reexports) now covers
            # both explicit `export ... from` and common import-then-local-export patterns
            # in barrel-named files (index.*, barrel*, etc). We detect by probing with
            # _follow_reexports and checking for recursion evidence (depth>=2 or chain>1
            # entry after prepend/bump). Non-barrel targets produce a synthetic depth-1
            # entry which we discard to avoid spuriously tagging plain files with via_barrel.
            # This enables get_dependencies/get_dependents/Mermaid/library.md to show
            # *ultimate* sources for imports like `import {x} from './barrels/index'`.
            # Rich metadata (via_barrel, barrel_depth, barrel_chain, barrel_v2, resolution_metadata,
            # confidence penalty) is propagated identically for *all* barrel emission paths.
            # max_depth/cycle guard (visited) unchanged (only the configured limit was raised from 2 to 3).

            followed = None
            if ptype.startswith("export_"):
                followed = _follow_reexports(path, raw_module, max_depth=_BARREL_MAX_DEPTH)
            else:
                probe = _follow_reexports(path, raw_module, max_depth=_BARREL_MAX_DEPTH)
                # only adopt the probe when it shows GENUINE barrel
                # evidence (traversed >=1 re-export hop, positive detector,
                # leaves differing from the direct resolution, or the resolved
                # target structurally contains re-exports — the latter keeps the
                # depth-1 CJS aggregator barrels flagged). The previous
                # `d >= 1 or len(ch) >= 1` accepted every probe result (BREE
                # tags depth>=1 unconditionally), so EVERY resolvable relative
                # import was spuriously emitted as via_barrel=True/barrel_depth=1.
                # Unresolved package (bare) specifiers are external modules, never barrels.
                if probe and (resolved_path or is_relative) and _probe_shows_real_barrel(probe, resolved_path, path):
                    followed = probe
            if followed:
                # for normal imports that hit a
                # real barrel, emit the DIRECT entry-barrel edge first (the file the
                # import statement actually lands on — the true filesystem
                # dependency), then the BREE-expanded ultimate leaves. Previously
                # only leaves were emitted, hiding the consumer -> entry-barrel
                # dependency whenever expansion succeeded. Skipped when expansion
                # already terminated on the entry file itself (no duplicate).
                _entry_prepended = False
                if not ptype.startswith("export_") and resolved_path:
                    _root_abs = _abs_resolved_target(path, resolved_path)
                    _root_already_present = False
                    for f in followed:
                        f_rp = f.get("resolved_path") if isinstance(f, dict) else None
                        if f_rp and (
                            f_rp == resolved_path
                            or (_root_abs is not None and _abs_resolved_target(path, f_rp) == _root_abs)
                        ):
                            _root_already_present = True
                            break
                    if not _root_already_present:
                        followed = [{
                            "module": resolved_module,
                            "resolved_path": resolved_path,
                            "via_barrel": True,
                            "barrel_chain": [raw_module],
                            "barrel_depth": 1,
                            "is_conditional": False,
                            "conditional_context": None,
                            "barrel_detector": (followed[0].get("barrel_detector") if isinstance(followed[0], dict) else None) or "bree",
                        }] + list(followed)
                        _entry_prepended = True

                # Leaf-explosion policy: route the expanded leaves by the names
                # this statement actually imports (precise), else cap. The
                # selection metadata lands on the first emitted edge below so
                # truncation is observable, never silent.
                _stmt_names = _extract_imported_names(original)
                followed, _leaf_selection = _select_barrel_leaves(
                    followed,
                    _stmt_names,
                    entry_prepended=_entry_prepended,
                    entry_resolved_path=resolved_path,
                    importer_path=path,
                )

                for _leaf_idx, f in enumerate(followed):
                    depth = f.get("barrel_depth", 1)

                    # Confidence propagation through barrels
                    if depth >= 3:
                        barrel_conf = "low"
                    elif depth == 2:
                        barrel_conf = "low" if confidence == "medium" else confidence
                    else:
                        barrel_conf = confidence

                    # Combine outer (import/re-export site) conditional with any conditional
                    # detected inside the barrel chain (from re-export statements in followed barrels).
                    # This ensures we do not over-follow conditional barrels.
                    f_is_cond = bool(f.get("is_conditional"))
                    f_cond_ctx = f.get("conditional_context")
                    effective_is_conditional = bool(is_conditional or f_is_cond)
                    effective_cond_ctx = conditional_context or f_cond_ctx
                    if effective_is_conditional:
                        barrel_conf = "low"

                    # ACS: compute numeric + reasons + actionable explanation
                    conf_score, conf_reasons, conf_explanation = _compute_confidence_score_and_reasons(
                        barrel_conf,
                        is_dynamic=is_dynamic,
                        dynamic_type=dynamic_type if is_dynamic else "static",
                        is_conditional=effective_is_conditional,
                        barrel_depth=depth,
                        via_barrel=True,
                        resolved_path=f.get("resolved_path"),
                        # Rich signals (site-level CDIA for the original import; resolution of the barrel root)
                        conditional_analysis=cdia_payload.get("conditional_analysis") if isinstance(cdia_payload, dict) else None,
                        dynamic_analysis=cdia_payload.get("dynamic_analysis") if isinstance(cdia_payload, dict) else None,
                        resolution_metadata=res_meta,
                        strategy=strategy_name,
                        in_cycle=False,
                    )

                    imports.append({
                        "module": f.get("module", resolved_module),
                        "raw_module": raw_module,
                        "is_relative": is_relative,
                        "level": level if is_relative else 0,
                        "alias": None,
                        "imported_names": list(_stmt_names or []),
                        **({"barrel_leaf_selection": _leaf_selection} if (_leaf_selection and _leaf_idx == 0) else {}),
                        "original_statement": original,
                        "statement_type": ptype,
                        "resolved_path": f.get("resolved_path"),
                        "resolution_confidence": barrel_conf,
                        "confidence_score": conf_score,
                        "confidence_reasons": conf_reasons,
                        "confidence_explanation": conf_explanation,
                        "is_dynamic": is_dynamic,
                        "dynamic_type": dynamic_type if is_dynamic else "static",
                        "is_conditional": effective_is_conditional,
                        "conditional_context": effective_cond_ctx,
                        "via_barrel": True,
                        "barrel_depth": depth,
                        "barrel_chain": f.get("barrel_chain", [raw_module]),
                        # (broader barrel emission audit): forward barrel_v2 from the
                        # _follow_reexports/BREE result (which always carries it post BREE + early synths)
                        # so that parse_parser_json_output sees "barrel_v2" and emits |barrel_v2=... suffix.
                        # Strategy + resolution_metadata now prefer the *final hop* (BREE leaf's resolver
                        # central_resolve result) for accurate per-leaf res_meta_v1; falls back to barrel-root
                        # site values for early-synth failure leaves. Flow: closure->BREE leaf ctor->f dict->here.
                        "barrel_v2": f.get("barrel_v2") or {
                            "via_barrel": True,
                            "barrel_depth": depth,
                            "barrel_chain": f.get("barrel_chain", [raw_module]),
                            "barrel_detector": "bree",
                            "is_partial": False,
                            "partial_reason": None,
                            "hops": [],
                            "mtimes_signature": "",
                        },
                        "strategy": f.get("strategy") or strategy_name,
                        "resolution_metadata": f.get("resolution_metadata") or res_meta,
                        # New in progressive analysis (LDSI Layers 0+1 + Layer 2)
                        "expr_raw": expr_raw,
                        "dynamic_candidates": dynamic_candidates if is_dynamic else [],
                        "dynamic_complexity": dynamic_complexity if is_dynamic else "simple",
                        "analysis_methods": ["balanced_capture", "literal_harvest"] + (["complexity_analysis"] if analysis_notes else []),
                        "analysis_notes": analysis_notes if is_dynamic else [],
                        "diagnostic": _make_diag_for_js(
                            barrel_conf, is_dynamic, dynamic_type, effective_is_conditional,
                            f.get("resolved_path"), True, depth, raw_module, barrel_conf,
                            dynamic_analysis=(cdia_payload.get("dynamic_analysis") if isinstance(cdia_payload, dict) else None),
                        ),
                        # CDIA rich analysis (cdia_v1 source). Site-level analysis
                        # is attached even for barrel-expanded leaves so agents see the
                        # original import site's conditional/dynamic explanation.
                        "cdia": cdia_payload,
                    })
                continue  # We emitted the ultimate sources instead of the barrel itself

            # Normal import / re-export that we couldn't or didn't follow
            # ACS: compute numeric + reasons + actionable explanation
            conf_score, conf_reasons, conf_explanation = _compute_confidence_score_and_reasons(
                confidence,
                is_dynamic=is_dynamic,
                dynamic_type=dynamic_type if is_dynamic else "static",
                is_conditional=is_conditional,
                barrel_depth=None,
                via_barrel=False,
                resolved_path=resolved_path,
                # Rich signals from this import site
                conditional_analysis=ca if isinstance(ca, dict) else (cdia_payload.get("conditional_analysis") if isinstance(cdia_payload, dict) else None),
                dynamic_analysis=da if isinstance(da, dict) else (cdia_payload.get("dynamic_analysis") if isinstance(cdia_payload, dict) else None),
                resolution_metadata=res_meta,
                strategy=strategy_name,
                in_cycle=False,
            )

            imports.append({
                "module": resolved_module,
                "raw_module": raw_module,
                "is_relative": is_relative,
                "level": level if is_relative else 0,
                "alias": None,
                "imported_names": list(_extract_imported_names(original) or []),
                "original_statement": original,
                "statement_type": ptype,
                "resolved_path": resolved_path,
                "resolution_confidence": confidence,
                "confidence_score": conf_score,
                "confidence_reasons": conf_reasons,
                "confidence_explanation": conf_explanation,
                "is_dynamic": is_dynamic,
                "dynamic_type": dynamic_type if is_dynamic else "static",
                "is_conditional": is_conditional,
                "conditional_context": conditional_context,
                # a direct (non-barrel) edge
                # explicitly states via_barrel=False / barrel_depth=0 instead of
                # omitting the keys (additive; consumers tolerate extra fields).
                "via_barrel": False,
                "barrel_depth": 0,
                # rich Resolution metadata for res_meta_v1 emission
                "strategy": strategy_name,
                "resolution_metadata": res_meta,
                # New in progressive analysis (LDSI Layers 0+1 + Layer 2)
                "expr_raw": expr_raw,
                "dynamic_candidates": dynamic_candidates if is_dynamic else [],
                "dynamic_complexity": dynamic_complexity if is_dynamic else "simple",
                "analysis_methods": ["balanced_capture", "literal_harvest"] + (["complexity_analysis"] if analysis_notes else []),
                "analysis_notes": analysis_notes if is_dynamic else [],
                "diagnostic": _make_diag_for_js(
                    confidence, is_dynamic, dynamic_type, is_conditional,
                    resolved_path, False, None, raw_module,
                    dynamic_analysis=(cdia_payload.get("dynamic_analysis") if isinstance(cdia_payload, dict) else None),
                ),
                # CDIA (additive) — full ConditionalAnalysis + DynamicAnalysis
                # ready for cdia_v1 base64 serialization in the pipeline (see contracts).
                "cdia": cdia_payload,
            })

    # Note: import.meta is captured but has no "module" in the traditional sense.
    # We keep it for completeness (agents may want to know about its usage).
    # import.meta.resolve is a Stage 3 proposal and may not be widely supported yet.

    # Note: Dynamic imports (variables, template literals, expressions, import.meta.resolve)
    # are classified with is_dynamic/dynamic_type/dynamic_complexity + full LDSI support.
    # Layers 0-2 implemented: balanced capture, literal harvest (with resolution enrichment),
    # complexity analysis. expr_raw + dynamic_candidates + analysis_* flow to cache/MCP.
    # Layer 3 (dataflow/aliases) and Layer 4 (registry) next per plan in m2-gap-closure doc.
    # Primary dynamic entries stay low/unresolved conf; candidates provide speculative signals.

    # collapse fully-identical edges (same raw specifier, resolution,
    # statement type, original statement and barrel/dynamic shape). Sources of
    # duplicates: overlapping regex patterns matching the same statement, and
    # BREE chains reaching the same leaf via equivalent re-export statements
    # (e.g. export_from + export_star both matching `export * from './leaf'`).
    # First occurrence wins (preserves emission order: entry barrel before leaves).
    _seen_edge_sigs = set()
    _deduped: List[Dict[str, Any]] = []
    for _e in imports:
        _sig = (
            _e.get("raw_module"),
            _e.get("resolved_path"),
            _e.get("statement_type"),
            _e.get("original_statement"),
            bool(_e.get("via_barrel")),
            _e.get("barrel_depth"),
            bool(_e.get("is_dynamic")),
        )
        if _sig in _seen_edge_sigs:
            continue
        _seen_edge_sigs.add(_sig)
        _deduped.append(_e)
    imports = _deduped

    _parse_cache[key] = imports

    # Persist any barrel-chain resolutions accumulated during this parse.
    # One flush per file (pipe/standalone mode); batched runs (run_full_update)
    # bracket the whole loop with bree.begin_batch()/end_batch() and flush once.
    from . import bree as _bree_mod

    _bree_mod.flush_barrel_cache_if_not_batched()

    return imports
