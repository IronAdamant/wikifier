"""
BREE — barrel / re-export expansion for JS/TS (agent-first).

AGENT MAP:
  get_bree_engine() / BarrelReexportAnalysisEngine.expand_chain — follow export *
  BarrelResolutionCache — mtime cache + reverse index for invalidation
  Used by javascript.py parse path; surfaces via_barrel on edges
  Stale importers → check_changes / BRC auto-yellow (not automatic wiki rewrite)
Agents: use get_barrel_reports / get_dependents; open this only for barrel bugs.
Zero-dep, bounded depth, cycle-safe.

PHASE 1 — ABSTRACTIONS & REGISTRY (this file, core of deliverable)
- Core data models: ReexportHop, BarrelInfo, ExpansionPolicy, ExpandedChainResult.
- Protocols (structural, no hard abc dep): BarrelDetector, ReexportExtractor,
  ExportsMapHandler, SpecifierResolver (thin for now; defers to future robust resolution #3).
- Multi-strategy BarrelDetector with scoring/priority (name-heuristic, export-from presence,
  package-exports presence, future pluggable).
- ReexportExtractor split: LightweightRegexExtractor (current fast path, hoisted patterns)
  + ASTReexportExtractor (skeleton + registration hook; zero-dep by default, opt-in via
  factory or 3rd-party that populates via register).
- ExportsMapHandler with full condition priority + NEW wildcard ("*") support using
  safe regex substitution (addresses documented LIMITATION in old resolver).
- Policy-driven ChainExpander: ExpansionPolicy(max_depth, max_fanout, cost_budget,
  stop_on_low_confidence, prefer_precomputed, allow_exotic). Default policy replicates
  the v0.3.2 _BARREL_MAX_DEPTH=3 + visited behavior exactly.
- Central BREERegistry + BarrelReexportAnalysisEngine (the "BREE" singleton/engine).
  - register_detector(detector, priority=0)
  - register_extractor(name, extractor)
  - register_exports_handler(handler)
  - get_engine() -> engine
  Future patterns register at import time or via public API (no plugin system yet;
  keeps zero-dep; docstring shows example for "nextjs-barrel-detector").

PHASE 2 — CORE IMPLEMENTATION & WILDCARD (this file)
- Default strategies implemented and registered at module load so get_engine() works
  immediately and replicates 100% of prior behavior + enhancements.
- ExportsMapHandler._resolve_with_wildcards: handles "./utils/*" -> "./dist/utils/*",
  conditional dicts under wildcard keys, arrays, etc. Integrated into resolution path.
- ChainExpander implements bounded recursion (or iterative) with visited (by resolved_path),
  per-hop metadata aggregation (conditional OR), barrel_chain building, depth tracking.
- Precomputation skeleton: build_barrel_index(files) -> BarrelIndex (file->direct hops)
  usable by ChainExpander when policy.prefer_precomputed=True. Cheap extractor used.
  (Full persistence + incremental update in later phase or with #5 diagnostics.)

PHASE 3 — INTEGRATION (javascript.py edits)
- Import BREE in javascript.py.
- Refactor (non-breaking):
    _extract_barrel_reexports -> delegates to engine.extract_reexports (lightweight default)
    _looks_like_barrel_file  -> delegates to engine.is_barrel(...) using detectors
    _follow_reexports        -> thin wrapper around engine.expand_chain(...) that maps
                                 result back to exact old dict shape + metadata.
    _resolve_from_exports    -> delegates to engine.resolve_via_exports(...)
  All existing caches (_reexport_cache, _parse_cache, _package_marker_cache) remain;
  BREE may layer its own short-term memo for the engine lifetime.
- New rich fields (additive, optional, backward compatible):
    "barrel_detector": "name-heuristic|export-from|exports-map|..."
    "expansion_policy": {...}
    "reexport_hops": list of hop details (future for diagnostics #5)
- No behavior change on legacy projects; exotic now supported (e.g. wildcard exports
  barrels will resolve and chain-expand correctly).

PHASE 4 — PERFORMANCE, BOUNDS & MONOREPO (this + follow-up)
- Pre-filters preserved/enhanced ( "export" and "from" in content, barrel name stems ).
- BREE engine honors existing memo; adds optional BarrelIndex for O(1) hop lookup on
  hot paths in huge monorepos (10k+ files).
- Policy allows early termination, fan-out caps, and "cheap-only" mode.
- Bounded work guarantee: total hops <= max_depth * max_fanout; visited set global
  per top-level expand call.

PHASE 5 — EXTENSIBILITY, TESTS, VALIDATION
- Example registration shown for future exotic (e.g. a detector that reads
  "barrel.config.json" or analyzes "export * as everything from './src'").
- Self-tests extended (in javascript.py __main__) with wildcard exports cases,
  export-* -as chains, mixed type/non-type barrels, deep conditional chains.
- Full roundtrip validation: python -m wikifier.parsers.javascript (self-tests pass),
  synthetic monorepo, update-maps --full on test-js-flat + self, metadata in
  library.md / get_dependencies() / Mermaid unchanged for old cases + richer for new.
- Deprecations: none (old _ functions remain as stable shims for any external callers).
- Documentation: this docstring + inline; later sync to CHANGELOG / v0.4 plan.

FUTURE (post this subagent, coordinated with other Limitations):
- Phase 4 complete: SpecifierResolver / barrel hops now receive rich Resolution objects (strategy, metadata) via central engine delegation in JS parser. Full direct use of ResolutionStrategy possible in future.
- AST extractor via optional "tree-sitter" or subprocess to tsc/acorn (behind flag).
- Persisted _bree_barrel_index.json for cross-run monorepo speed (with mtime).
- Diagnostics attachment per hop (for #5 Failure Transparency).
- Integration into cycle impact (#6) so barrel chains participate in blast radius.
- Config-driven policy per-project (e.g. via .wikifierrc).

Design invariants (never violated):
1. Zero new runtime dependencies.
2. Exact preservation of public parse dict contract and all  barrel_*/conditional fields.
3. Default behavior = previous behavior (bit-for-bit on synthetic + dogfood).
4. Registration is additive; core never hardcodes the list of strategies.
5. Performance: cheap path (lightweight) is default and fast; heavy paths opt-in.
6. Monorepo friendly: precomp + bounds prevent quadratic explosion.

This BREE is the long-term home for all future barrel/re-export intelligence.
================================================================================
"""

from __future__ import annotations

import json
import re
import warnings
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple, Union

# =============================================================================
# Wave 2 External / Packaged helpers: improved fallbacks (used by norm/expand/store paths)
# =============================================================================

def _get_project_root_fallback(default: Optional[Union[str, Path]] = None) -> Path:
    """Robust project root for BREE/parser internals (Wave 3).

    Tries canonical discover_project_root() first — now hardened (Wave 3) for symlinks,
    pnpm/yarn store layouts via logical $PWD parent-walk (see cli.py). Supports pip-installed
    wikifier + external monorepo + cwd-in-subdir or cwd-via-symlink/store. Then env, default/cwd.
    Prevents state/cache pollution or wrong root when parsers/BREE run directly or
    from subdirs of user monorepos. Safe, zero-dep, never raises.
    """
    try:
        # Load-safe: project_root (not cli) — avoids bree→cli→import_cache→bree cycle
        from ..project_root import discover_project_root
        root = discover_project_root()
        if root:
            return Path(root).resolve()
    except Exception:
        pass
    env = os.environ.get("WIKIFIER_PROJECT_ROOT") or os.environ.get("WIKIFIER_ROOT")
    if env:
        try:
            return Path(env).expanduser().resolve()
        except Exception:
            pass
    if default is not None:
        try:
            return Path(default).resolve()
        except Exception:
            pass
    return Path.cwd().resolve()


# =============================================================================
# Data Models (rich, forward-compatible, used by registry + engine + diagnostics)
# =============================================================================

@dataclass(frozen=True)
class ReexportHop:
    """A single re-export hop discovered inside a barrel file."""
    raw_specifier: str
    statement_type: str  # "export_star", "export_from", "export_as", "export_type_*", ...
    is_conditional: bool = False
    conditional_context: Optional[str] = None
    # Future: imported_names: List[str] | None = None   # for named {a,b} from
    # Future: source_range: Tuple[int,int] | None = None


@dataclass
class BarrelInfo:
    """Result of a BarrelDetector strategy."""
    is_barrel: bool
    confidence: float  # 0.0–1.0 (1.0 = explicit export-from evidence)
    detector_name: str
    reasons: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExpansionPolicy:
    """Policy object driving ChainExpander behavior (extensible)."""
    max_depth: int = 3
    max_fanout_per_hop: int = 128          # safety against pathological barrels
    cost_budget: int = 10_000              # abstract "work units" for monorepos
    stop_on_low_confidence: bool = False
    prefer_precomputed: bool = False
    allow_exotic: bool = True
    # Future: stop_conditions: List[Callable[[...], bool]] = ...


@dataclass
class ExpandedChainResult:
    """Structured return from chain expansion (maps to legacy dicts + richer data)."""
    results: List[Dict[str, Any]]          # list of ultimate leaf dicts (compat shape)
    barrel_chain: List[str]
    max_depth_reached: int
    detector_used: str
    policy: ExpansionPolicy
    hops: List[ReexportHop] = field(default_factory=list)  # full trace for #5 diagnostics
    precomputed: bool = False
    # Phase 2 additions for persistent cache + graceful degradation
    is_partial: bool = False
    partial_reason: Optional[str] = None
    # E1 fix (additive): canonical rel paths of EVERY file traversed in this expansion
    # (entry barrel + intermediate barrel hops + leaves). Lets the top-level store build
    # a complete mtimes_snapshot / file_index covering mid-chain barrels, which the
    # results list alone cannot provide (it only carries final leaves).
    chain_files: List[str] = field(default_factory=list)


# =============================================================================
# Phase 2: Persistent BarrelResolutionCache & BarrelChainResolution (Gap #1 Finisher)
# =============================================================================

# Additional imports for cache layer (placed here for locality with the feature)
import hashlib
import os
import time

# Canonical normalization (Wave 1 of deep barrel invalidation long-term strategy)
# Single source of truth from resolution.py; follow_symlinks=True for physical inode identity
# under symlinked monorepos/workspaces. Graceful fallback if import fails (direct tests).
try:
    from ..resolution import to_canonical_rel as _to_canonical_rel, canonical_for_bree as _canonical_for_bree
except ImportError:
    try:
        from wikifier.resolution import to_canonical_rel as _to_canonical_rel, canonical_for_bree as _canonical_for_bree
    except Exception:
        _to_canonical_rel = None
        _canonical_for_bree = None


def _brc_canonical(p: Any, root: Path) -> str:
    """Return canonical POSIX relpath string for BRC keys (barrel_chain, mtimes keys, importer_rel, index).
    Wave 2: delegates to canonical_for_bree (which uses to_canonical_rel v1 physical) on all BRC paths.
    Ensures every store/ctx/hit/lookup/index uses the v1 stamped canonical form. Fallback safe.
    """
    if p is None:
        return ""
    try:
        if _canonical_for_bree is not None:
            c = _canonical_for_bree(p, root)
            if c:
                return c
        if _to_canonical_rel is not None:
            c = _to_canonical_rel(p, root, follow_symlinks=True)
            if c:
                return c
    except Exception:
        pass
    # Fallback (never introduces deps; matches old .resolve().relative_to behavior for compat)
    try:
        pp = Path(p)
        if not pp.is_absolute():
            pp = (root / pp).resolve(strict=False)
        rroot = root.resolve(strict=False)
        try:
            rel = pp.resolve(strict=False).relative_to(rroot)
        except ValueError:
            rel = pp.resolve(strict=False)
        canon = str(rel).replace("\\", "/").lstrip("./")
        return canon or str(p)
    except Exception:
        return str(p) if p else ""


@dataclass
class BarrelChainResolution:
    """
    Persistent, mtime-aware record of one barrel re-export chain expansion.
    Stored in import_cache under "_barrel_resolutions[chain_id]".
    The mtimes_snapshot (not the importer's mtime) is the source of truth for freshness.
    Reverse indexes allow precise "only affected importers" invalidation.
    """
    chain_id: str
    importers: List[str] = field(default_factory=list)  # relpaths of files whose imports expanded via this chain
    barrel_chain: List[str] = field(default_factory=list)  # ordered canonical/resolved paths of barrels in chain
    hops: List[Dict[str, Any]] = field(default_factory=list)  # ReexportHop dicts + resolved info for replay
    results: List[Dict[str, Any]] = field(default_factory=list)  # the legacy-shaped leaf results for cache hit replay
    start_specifier: str = ""
    detector_used: str = "unknown"
    is_partial: bool = False
    partial_reason: Optional[str] = None
    mtimes_snapshot: Dict[str, int] = field(default_factory=dict)  # path -> mtime at expansion time
    mtimes_signature: str = ""  # for fast equality / debug
    node_identity_version: str = "v1"  # Wave 1: canonical normalization pass uses v1 (to_canonical_rel + physical identity)
    created_at: float = field(default_factory=lambda: time.time())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "BarrelChainResolution":
        if not d:
            return cls(chain_id="empty")
        clean = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**clean)


@dataclass
class BarrelInvalidationReport:
    """
    Structured observability record (Wave 1/2 of deep barrel invalidation strategy).
    Returned by future rich invalidation APIs (or enhanced invalidate(..., rich=True)).

    Answers "why was this importer re-parsed?": exactly which barrel change(s) + which
    chains + detector + partial status + human reason. Zero-dep, serializable via asdict.
    Enables diagnostics, journal, MCP, health "stale via barrel X", and agent explanations.
    """
    importer: str
    triggering_barrels: List[str] = field(default_factory=list)
    chain_ids: List[str] = field(default_factory=list)
    is_partial: bool = False
    reason: str = ""
    detector_used: str = ""
    node_identity_version: str = "v1"
    mtime_delta: Optional[Dict[str, Any]] = None  # e.g. {"barrel": "x", "old": 123, "new": 456, "deleted": False}


@dataclass
class BarrelResolutionCache:
    """
    In-memory manager over the two reserved cache keys.
    Provides lookup, mtime validation, store+index maintenance, and invalidation queries.
    Used by expand_chain (for hits) and by first-pass (for dirty augmentation).
    Thread-unsafe is acceptable (CLI/MCP single-threaded usage).
    """
    resolutions: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    file_index: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.resolutions = dict(self.resolutions or {})
        self.file_index = dict(self.file_index or {})
        # Transient set views over persisted membership lists (never serialized;
        # see _membership). Without these, store() membership tests were linear
        # scans that went quadratic across a run on barrels with many importers.
        self._fast_sets: Dict[str, set] = {}

    @classmethod
    def from_cache(cls, cache: Dict[str, Any]) -> "BarrelResolutionCache":
        res = get_barrel_resolutions(cache) if "get_barrel_resolutions" in globals() else cache.get("_barrel_resolutions", {}) or {}
        idx = get_barrel_file_index(cache) if "get_barrel_file_index" in globals() else cache.get("_barrel_file_index", {}) or {}
        return cls(resolutions=dict(res), file_index=dict(idx))

    def to_cache_updates(self, cache: Dict[str, Any]) -> None:
        """Push mutations back into the main cache dict (caller decides save).

        E1 fix: always materialize both reserved keys (even when empty) instead of
        popping them. save_cache() preserves on-disk barrel state only when the
        keys are *absent* from the dict being saved (caller never touched barrel
        state); an explicit empty dict therefore remains the way to express
        intentional clearing (prune-to-zero, clear()).
        """
        # Stable output: importer/chain lists are append-ordered in memory for
        # speed; sort once here so the persisted form is deterministic.
        for entry in self.resolutions.values():
            if isinstance(entry.get("importers"), list):
                entry["importers"] = sorted(set(entry["importers"]))
        for idxe in self.file_index.values():
            if isinstance(idxe.get("importers"), list):
                idxe["importers"] = sorted(set(idxe["importers"]))
            if isinstance(idxe.get("chain_ids"), list):
                idxe["chain_ids"] = sorted(set(idxe["chain_ids"]))
        cache["_barrel_resolutions"] = self.resolutions or {}
        cache["_barrel_file_index"] = self.file_index or {}

    def _make_chain_id(self, barrel_chain: List[str], start_spec: str = "") -> str:
        key_mat = "|".join(barrel_chain or []) + "::" + (start_spec or "")
        return hashlib.sha256(key_mat.encode("utf-8")).hexdigest()[:16]

    def _compute_mtime_signature(self, snap: Dict[str, int]) -> str:
        items = sorted((str(k), int(v)) for k, v in (snap or {}).items())
        return hashlib.sha256(json.dumps(items).encode("utf-8")).hexdigest()[:12]

    def get(self, chain_id: str) -> Optional[Dict[str, Any]]:
        return self.resolutions.get(chain_id)

    @staticmethod
    def _lean_results(results: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """Compress chain results for persistence.

        Stored results exist so a cache hit can replay the expansion (and so
        name routing on hits still sees the full leaf set) — they do NOT need
        the heavy per-leaf payloads (resolution_metadata, barrel_v2 hop blobs,
        analysis fields), which the emission layer rebuilds or defaults.
        Those payloads were the dominant weight of barrel-heavy caches
        (274MB import_cache.json on Babylon.js). Leaves are also deduped by
        resolved_path (BREE can reach the same leaf via multiple hop paths).
        """
        lean: List[Dict[str, Any]] = []
        seen: set = set()
        for r in results or []:
            if not isinstance(r, dict):
                continue
            rp = r.get("resolved_path")
            if rp:
                if rp in seen:
                    continue
                seen.add(rp)
            slim = {}
            for k in (
                "module", "resolved_path", "via_barrel", "barrel_chain",
                "barrel_depth", "is_conditional", "conditional_context",
                "barrel_detector",
            ):
                v = r.get(k)
                if v is not None:
                    slim[k] = v
            lean.append(slim)
        return lean

    @staticmethod
    def _lean_hops(hops: Optional[List[Any]]) -> List[Dict[str, Any]]:
        """Keep only primitive hop fields (drop per-hop metadata dicts)."""
        out: List[Dict[str, Any]] = []
        for h in hops or []:
            if isinstance(h, dict):
                out.append({k: v for k, v in h.items() if not isinstance(v, (dict, list))})
        return out

    def _membership(self, key: str, current: List[str]) -> set:
        """Transient set view over a persisted list (membership tests during
        store() were linear scans — quadratic across a run on popular barrels)."""
        s = self._fast_sets.get(key)
        if s is None:
            s = set(current)
            self._fast_sets[key] = s
        return s

    def store(
        self,
        *,
        chain_id: Optional[str] = None,
        importers: Optional[List[str]] = None,
        barrel_chain: Optional[List[str]] = None,
        hops: Optional[List[Dict[str, Any]]] = None,
        results: Optional[List[Dict[str, Any]]] = None,
        start_specifier: str = "",
        detector_used: str = "unknown",
        is_partial: bool = False,
        partial_reason: Optional[str] = None,
        mtimes_snapshot: Optional[Dict[str, int]] = None,
        node_identity_version: str = "v1",  # canonical v1 for Wave 1
        ctx: Optional[Dict[str, Any]] = None,  # additive for defensive importer_rel recording from top consumer ctx (final squeeze)
    ) -> str:
        """Store (or merge) a resolution, update reverse indexes, return the chain_id used.
        Wave 1: all incoming paths (importers, barrel_chain, mtimes keys) are forced through
        canonical v1 normalizer (physical rel) before indexing or id computation. Ensures
        symlink/workspace safety and single identity for overlapping chains.
        """
        # Canonical normalization pass (importer_rel, barrel_chain, mtimes_snapshot keys, file_index)
        # We defensively normalize here. E1 fix: prefer the caller's project root (ctx["cache_root"],
        # set by expand_chain) over CWD/env inference — when CWD != project root the fallback
        # produced wrong canonical keys for relative paths, silently corrupting the snapshot/index.
        root_for_norm = None
        if ctx:
            try:
                cr = ctx.get("cache_root")
                if cr:
                    root_for_norm = Path(cr)
            except Exception:
                root_for_norm = None
        if root_for_norm is None:
            root_for_norm = _get_project_root_fallback(".")
        bc = [_brc_canonical(p, root_for_norm) for p in (barrel_chain or []) if p]
        imps = [_brc_canonical(p, root_for_norm) for p in (importers or []) if p]
        # Final squeeze (Agent B, BRC side): small defensive recording of importer when ctx has "importer_rel".
        # This guarantees that for a top-level consumer import of a barrel chain (e.g. "../barrels" resolving
        # via dir->index to reexporting index -> `export * from "./leaf"`), the recursive leaf (and intermediate)
        # hops' stores always populate reverse file_index + resolution importers with the original consumer's
        # importer_rel (propagated in ctx). Works for synth proof layout + canon symlink + deletion cases.
        # Zero-dep, additive, prod call sites unchanged (they pass importers= explicitly).
        if not imps and ctx:
            imp = ctx.get("importer_rel")
            if imp:
                cim = _brc_canonical(imp, root_for_norm)
                if cim:
                    imps = [cim]
        snap = {}
        for k, v in (mtimes_snapshot or {}).items():
            if k:
                ck = _brc_canonical(k, root_for_norm)
                # E1: keep sub-second precision (float). Whole-second ints made a
                # snapshot-then-edit within the same second invisible to is_stale.
                try:
                    snap[ck or str(k)] = float(v)
                except Exception:
                    snap[ck or str(k)] = 0.0
        cid = chain_id or self._make_chain_id(bc, start_specifier)
        entry = self.resolutions.get(cid, {})
        # merge importers (set-backed membership; lists stay the persisted form)
        imp_list = entry.get("importers", [])
        imp_set = self._membership(f"res:{cid}", imp_list)
        for imp in imps:
            if imp and imp not in imp_set:
                imp_set.add(imp)
                imp_list.append(imp)
        entry.update({
            "chain_id": cid,
            "importers": imp_list,
            "barrel_chain": bc or entry.get("barrel_chain", []),
            "hops": self._lean_hops(hops) if hops else entry.get("hops", []),
            "results": self._lean_results(results) if results else entry.get("results", []),
            "start_specifier": start_specifier or entry.get("start_specifier", ""),
            "detector_used": detector_used or entry.get("detector_used", "unknown"),
            "is_partial": is_partial or entry.get("is_partial", False),
            "partial_reason": partial_reason or entry.get("partial_reason"),
            "mtimes_snapshot": snap or entry.get("mtimes_snapshot", {}),
            "mtimes_signature": self._compute_mtime_signature(snap) if snap else entry.get("mtimes_signature", ""),
            "node_identity_version": node_identity_version,
            "created_at": entry.get("created_at", time.time()),
        })
        self.resolutions[cid] = entry

        # Maintain reverse index: barrel_path -> {chain_ids, importers}
        for f in bc:
            if not f:
                continue
            fkey = str(f)
            if fkey not in self.file_index:
                self.file_index[fkey] = {"chain_ids": [], "importers": []}
            idxe = self.file_index[fkey]
            cid_set = self._membership(f"idx_c:{fkey}", idxe["chain_ids"])
            if cid not in cid_set:
                cid_set.add(cid)
                idxe["chain_ids"].append(cid)
            imp_idx_set = self._membership(f"idx_i:{fkey}", idxe["importers"])
            for imp in imps:
                if imp and imp not in imp_idx_set:
                    imp_idx_set.add(imp)
                    idxe["importers"].append(imp)

        return cid

    def is_stale(self, entry: Dict[str, Any], root: Path) -> bool:
        """
        True iff any file in the snapshot has been modified since the snapshot was taken,
        *or* no longer exists on disk (broken chain / deletion case → importers must re-analyze).

        This closes the deletion staleness gap (Wave 1 correctness hardening).
        """
        snap = entry.get("mtimes_snapshot", {}) or {}
        if not snap:
            return True
        for f, old in snap.items():
            try:
                fp = root / str(f) if not Path(str(f)).is_absolute() else Path(str(f))
                if not fp.exists():
                    # Deleted barrel in chain → treat as stale so consumers get refreshed
                    # (they will naturally observe the missing import on re-expand).
                    return True
                # E1: compare with sub-second precision (snapshots now store float
                # mtimes); whole-second int comparison missed same-second edits.
                try:
                    cur = float(fp.stat().st_mtime)
                except Exception:
                    cur = float(ic_get_mtime(fp)) if callable(ic_get_mtime) else 0.0
                if cur > float(old or 0):
                    return True
            except Exception:
                return True
        return False

    def get_affected_importers(self, changed_file: str) -> List[str]:
        """Fast path using the reverse index (no full scan).
        Additive tolerance for abs/rel/tail key forms (harness synth + real monorepo path variants + canon v1);
        still O(1) hot for common case, falls back to cheap tail scan over tiny #barrels.
        """
        affected: set[str] = set()
        cf = str(changed_file)
        # direct (common after canon)
        e = self.file_index.get(cf, {})
        for imp in (e.get("importers", []) or []):
            affected.add(imp)
        for cid in (e.get("chain_ids", []) or []):
            res = self.resolutions.get(cid, {})
            for imp in (res.get("importers", []) or []):
                affected.add(imp)
        # tolerant tail/name/contains match (fixes harness abs vs rel, symlink edge, deletion renorm)
        try:
            tail = Path(cf).name if cf else ""
            if tail and tail != cf:
                for k, ee in list(self.file_index.items()):
                    kstr = str(k)
                    if kstr == tail or kstr.endswith("/" + tail) or tail in kstr.split("/")[-1] or tail in kstr:
                        for imp in (ee.get("importers", []) or []):
                            affected.add(imp)
                        for cid in (ee.get("chain_ids", []) or []):
                            res = self.resolutions.get(cid, {})
                            for imp in (res.get("importers", []) or []):
                                affected.add(imp)
        except Exception:
            pass
        return sorted(affected)

    def collect_stale_importers(self, root: Path) -> List[str]:
        """Full scan used at first-pass start (acceptable; #barrel_chains << #files)."""
        dirty: set[str] = set()
        for cid, entry in list(self.resolutions.items()):
            if self.is_stale(entry, root):
                for imp in (entry.get("importers", []) or []):
                    dirty.add(imp)
        return sorted(dirty)

    def build_invalidation_reports(
        self,
        changed_files: Optional[Iterable[str]] = None,
        root: Optional[Path] = None,
    ) -> List[BarrelInvalidationReport]:
        """Wave 1/2: produce structured BarrelInvalidationReport list for observability.
        When changed_files given, uses fast index path + enriches with per-chain details
        (triggering barrels, chain_ids, partial flag, reason). Falls back to full scan.
        Zero-dep, ready for sh debug prints, diagnostics, journal, MCP get_files_needing...
        """
        reports: List[BarrelInvalidationReport] = []
        root = root or _get_project_root_fallback(".")
        affected_imps: Dict[str, set] = {}  # imp -> set of (chain_id, barrels, detector, partial, reason)

        if changed_files is not None:
            cset = {str(c) for c in changed_files if c}
            for cf in cset:
                # direct + tolerant key match (abs/rel/tail) so leaf edits find their index entries even under variant canon forms
                matched = []
                if cf in self.file_index:
                    matched.append(cf)
                try:
                    t = Path(cf).name if cf else ""
                    if t:
                        for k in list(self.file_index.keys()):
                            ks = str(k)
                            if ks == cf or ks == t or ks.endswith("/" + t) or t in ks:
                                if k not in matched:
                                    matched.append(k)
                except Exception:
                    pass
                for mk in matched:
                    for cid in (self.file_index.get(mk, {}) or {}).get("chain_ids", []):
                        ent = self.resolutions.get(cid, {})
                        for imp in ent.get("importers", []) or []:
                            if imp not in affected_imps:
                                affected_imps[imp] = set()
                            trig = [cf] + (ent.get("barrel_chain", []) or [])
                            det = ent.get("detector_used", "bree")
                            part = bool(ent.get("is_partial"))
                            rsn = "mtime changed" if not self.is_stale(ent, root) else "stale (mtime or deletion)"
                            affected_imps[imp].add( (cid, tuple(sorted(set(trig))), det, part, rsn) )
        else:
            for cid, ent in list(self.resolutions.items()):
                if self.is_stale(ent, root):
                    for imp in ent.get("importers", []) or []:
                        if imp not in affected_imps:
                            affected_imps[imp] = set()
                        trig = ent.get("barrel_chain", []) or []
                        det = ent.get("detector_used", "bree")
                        part = bool(ent.get("is_partial"))
                        rsn = "stale via mtime snapshot or deleted barrel"
                        affected_imps[imp].add( (cid, tuple(sorted(set(trig))), det, part, rsn) )

        for imp, infos in affected_imps.items():
            trig_b = []
            cids = []
            dets = set()
            parts = False
            reasons = []
            for cid, trig_t, det, part, rsn in infos:
                cids.append(cid)
                trig_b.extend(trig_t)
                dets.add(det)
                parts = parts or part
                reasons.append(rsn)
            report = BarrelInvalidationReport(
                importer=imp,
                triggering_barrels=sorted(set(trig_b)),
                chain_ids=sorted(set(cids)),
                is_partial=parts,
                reason="; ".join(sorted(set(reasons))) or "barrel staleness",
                detector_used=",".join(sorted(dets)),
                node_identity_version="v1",
            )
            reports.append(report)
        return reports

    def prune_aged_entries(self, max_age_days: float = 90.0, now: Optional[float] = None) -> int:
        """Lightweight age-based cleanup / GC for BRC entries at massive scale (Wave 4 starter).

        Removes any BarrelChainResolution entries whose `created_at` exceeds the age cutoff.
        Cleans dangling chain_id references from the reverse `file_index` (importer lists left
        for natural repopulation on next store of active chains). Zero new deps, O(#chains) which
        is tiny in practice (#barrel_chains << #files), safe to call often or on every --full / daemon cycle.

        Returns the number of chains actually pruned (0 for common no-op case).
        """
        if now is None:
            now = time.time()
        cutoff = now - (max_age_days * 86400.0)
        to_prune: List[str] = []
        for cid, ent in list(self.resolutions.items()):
            try:
                ca = 0.0
                if isinstance(ent, dict):
                    ca = float(ent.get("created_at", 0) or 0)
                else:
                    ca = float(getattr(ent, "created_at", 0) or 0)
                if ca > 0 and ca < cutoff:
                    to_prune.append(cid)
            except Exception:
                # never let a bad entry prevent pruning of others
                continue
        for cid in to_prune:
            self.resolutions.pop(cid, None)
        # Lightweight index hygiene: drop pruned cids from any barrel's chain list
        for bpath, e in list(self.file_index.items()):
            if not isinstance(e, dict):
                continue
            old_cids = e.get("chain_ids", []) or []
            if not old_cids:
                continue
            new_cids = [c for c in old_cids if c not in to_prune]
            if len(new_cids) != len(old_cids):
                e["chain_ids"] = new_cids
        return len(to_prune)

    def prune_references_to(self, deleted_paths: List[str]) -> int:
        """Wave 4 continuation for Deep Barrel GC (per long-term strategy): on record-deletion etc.

        Remove any BarrelChainResolution entries whose barrel_chain list or importers list
        (or whose keys appear in file_index) reference any of the deleted canonical paths.
        Also prunes dangling refs from file_index entries.
        Uses defensive norm (str contains or exact match after canon where possible).
        Returns count of chains pruned (safe no-op on empty).
        Complements age prune; called opportunistically from record-deletion for correctness on deletes.
        """
        if not deleted_paths:
            return 0
        # Normalize deleted for contains checks (physical-ish)
        dels = [str(d).replace("\\", "/") for d in (deleted_paths or []) if d]
        if not dels:
            return 0
        to_prune: List[str] = []
        for cid, ent in list(self.resolutions.items()):
            try:
                chain = []
                imps = []
                if isinstance(ent, dict):
                    chain = ent.get("barrel_chain", []) or []
                    imps = ent.get("importers", []) or []
                else:
                    chain = getattr(ent, "barrel_chain", []) or []
                    imps = getattr(ent, "importers", []) or []
                hay = " ".join(str(x) for x in (chain + imps))
                for d in dels:
                    if d in hay or any(d in str(x) for x in chain + imps):
                        to_prune.append(cid)
                        break
            except Exception:
                continue
        for cid in to_prune:
            self.resolutions.pop(cid, None)
        # Clean file_index too: drop cids and possibly empty barrel entries referencing dels
        for bpath, e in list(self.file_index.items()):
            if not isinstance(e, dict):
                continue
            old_cids = e.get("chain_ids", []) or []
            if any(any(d in str(bpath) or d in str(c) for d in dels) for c in old_cids):  # rough but safe
                # drop any cids that came from pruned, but since we don't have map, drop matching bpath entirely if del
                if any(d in str(bpath) for d in dels):
                    self.file_index.pop(bpath, None)
                    continue
            new_cids = [c for c in old_cids if c not in to_prune]
            if len(new_cids) != len(old_cids):
                e["chain_ids"] = new_cids
                if not new_cids:
                    self.file_index.pop(bpath, None)
        return len(to_prune)

    def clear(self) -> None:
        self.resolutions.clear()
        self.file_index.clear()


# Thin import guard so bree.py can be imported early; real load in helpers
def _ensure_import_cache_helpers():
    global get_barrel_resolutions, get_barrel_file_index, ic_get_mtime
    try:
        if "get_barrel_resolutions" not in globals() or get_barrel_resolutions is None:
            from .. import import_cache as _ic
            get_barrel_resolutions = _ic.get_barrel_resolutions
            get_barrel_file_index = _ic.get_barrel_file_index
            ic_get_mtime = _ic.get_mtime
    except Exception:
        # Fallback no-op for standalone bree usage / tests (e.g. direct import or synthetic tests)
        def _fb_get_barrel_resolutions(c): return (c or {}).get("_barrel_resolutions", {}) or {}
        def _fb_get_barrel_file_index(c): return (c or {}).get("_barrel_file_index", {}) or {}
        def _fb_ic_get_mtime(p):
            try:
                return int(Path(p).stat().st_mtime) if Path(p).exists() else 0
            except Exception:
                return 0
        get_barrel_resolutions = _fb_get_barrel_resolutions
        get_barrel_file_index = _fb_get_barrel_file_index
        ic_get_mtime = _fb_ic_get_mtime


get_barrel_resolutions = None
get_barrel_file_index = None
ic_get_mtime = None
_ensure_import_cache_helpers()


# =============================================================================
# Process-level barrel-cache session (performance-critical)
#
# expand_chain used to load AND save the entire import_cache.json once per
# barrel chain expansion (multiple times per parsed file). On real projects
# that serialization dominated parse time (~93% of wall time on Babylon.js).
# Instead we keep one BarrelResolutionCache per process/root, mark it dirty on
# store, and flush once: per parsed file in standalone/pipe mode, or once per
# run when the caller brackets the run with begin_batch()/end_batch().
# =============================================================================

_BRC_SESSION: Dict[str, Any] = {"root": None, "brc": None, "dirty": False, "batch": False}


def get_session_barrel_cache(cache_root: Path) -> Optional["BarrelResolutionCache"]:
    """Return the per-process BarrelResolutionCache for cache_root (loaded once).

    Switching roots flushes any pending state for the previous root first.
    Returns None when the import cache cannot be loaded (standalone usage).
    """
    try:
        root_key = str(Path(cache_root).resolve())
    except Exception:
        root_key = str(cache_root)
    if _BRC_SESSION["brc"] is not None and _BRC_SESSION["root"] == root_key:
        return _BRC_SESSION["brc"]
    if _BRC_SESSION["dirty"]:
        flush_barrel_cache()
    try:
        _ensure_import_cache_helpers()
        from .. import import_cache as _ic
        cdict = _ic.load_cache(Path(cache_root))
        brc = BarrelResolutionCache.from_cache(cdict)
    except Exception:
        return None
    _BRC_SESSION.update({"root": root_key, "brc": brc, "dirty": False})
    return brc


def mark_session_dirty(brc: Optional["BarrelResolutionCache"]) -> None:
    """Mark the session cache as needing a flush (no-op for foreign caches)."""
    if brc is not None and brc is _BRC_SESSION["brc"]:
        _BRC_SESSION["dirty"] = True


def begin_batch() -> None:
    """Suppress per-file flushes; caller promises to call end_batch()."""
    _BRC_SESSION["batch"] = True


def end_batch() -> None:
    """End a batched run and persist any pending barrel resolutions."""
    _BRC_SESSION["batch"] = False
    flush_barrel_cache()


def flush_barrel_cache(force: bool = False) -> bool:
    """Persist the session barrel cache into import_cache.json if dirty.

    Returns True when a save happened. Lock-protected via import_cache.save_cache.
    """
    if _BRC_SESSION["brc"] is None or _BRC_SESSION["root"] is None:
        return False
    if not (_BRC_SESSION["dirty"] or force):
        return False
    try:
        from .. import import_cache as _ic
        root = Path(_BRC_SESSION["root"])
        cdict = _ic.load_cache(root)
        _BRC_SESSION["brc"].to_cache_updates(cdict)
        _ic.save_cache(root, cdict)
        _BRC_SESSION["dirty"] = False
        return True
    except Exception:
        return False


def flush_barrel_cache_if_not_batched() -> bool:
    """Flush unless inside a begin_batch()/end_batch() bracket."""
    if _BRC_SESSION["batch"]:
        return False
    return flush_barrel_cache()


# =============================================================================
# Protocols / Extension Points (the "pluggable" heart of BREE)
# =============================================================================

class BarrelDetector(Protocol):
    """Multi-strategy detector. Implementations register with the registry."""
    name: str

    def detect(
        self,
        filepath: str,
        content: Optional[str] = None,
        lightweight_reexports: Optional[List[Dict[str, Any]]] = None,
        **context: Any,
    ) -> BarrelInfo:
        ...


class ReexportExtractor(Protocol):
    """Extracts only the re-export statements (for barrel following)."""
    name: str

    def extract(
        self,
        filepath: str,
        content: Optional[str] = None,
        **context: Any,
    ) -> List[Dict[str, Any]]:  # same shape as legacy _extract output
        ...


class ExportsMapHandler(Protocol):
    """Handles package.json "exports" (including exotic wildcard/conditional)."""
    name: str

    def resolve(
        self,
        pkg_dir: Path,
        subpath: str = ".",
    ) -> Optional[Path]:
        ...


class SpecifierResolver(Protocol):
    """Unified specifier (bare/relative) → filesystem resolution.
    Thin wrapper today; Phase 4 Resolution Core (resolution.py) is now the
    authoritative engine. Future: delegate to wikifier.resolution.resolve or
    the strategy objects for canonical + metadata-rich results.
    """
    name: str

    def resolve(
        self,
        current_file: Path,
        raw_module: str,
        **context: Any,
    ) -> Tuple[str, Optional[str]]:  # (display_module, resolved_path or None)
        ...


# =============================================================================
# Default Strategy Implementations (replicate + enhance current behavior)
# =============================================================================

class ExportFromPresenceDetector:
    """Highest confidence: file contains at least one export ... from statement."""
    name = "export-from-presence"

    def detect(self, filepath: str, content: Optional[str] = None,
               lightweight_reexports: Optional[List[Dict[str, Any]]] = None,
               **context: Any) -> BarrelInfo:
        if lightweight_reexports and len(lightweight_reexports) > 0:
            return BarrelInfo(
                is_barrel=True,
                confidence=0.95,
                detector_name=self.name,
                reasons=["explicit-export-from-statements"],
            )
        if content and ("export" in content and " from " in content):
            # Cheap signal; real confirmation happens via extractor
            return BarrelInfo(True, 0.7, self.name, ["contains-export-from-text"])
        return BarrelInfo(False, 0.0, self.name, ["no-export-from-evidence"])


class NameAndHeuristicBarrelDetector:
    """Conservative name-based + relative import heuristic (the _looks_like_barrel_file logic)."""
    name = "name-heuristic"

    BARREL_STEMS = {"index", "barrel", "entry", "entrypoint", "api", "exports", "public"}

    def detect(self, filepath: str, content: Optional[str] = None,
               lightweight_reexports: Optional[List[Dict[str, Any]]] = None,
               parsed_items: Optional[List[Dict[str, Any]]] = None,
               **context: Any) -> BarrelInfo:
        p = Path(filepath)
        stem = p.stem.lower()
        name = p.name.lower()

        is_barrel_named = (
            stem in self.BARREL_STEMS
            or stem.startswith("index")
            or "barrel" in stem
            or "barrel" in name
        )
        if not is_barrel_named:
            return BarrelInfo(False, 0.0, self.name, ["not-barrel-named"])

        # Prefer caller-supplied parsed_items (from full parse) or lightweight
        items = parsed_items or lightweight_reexports or []
        relative_aggregates = [
            it for it in items
            if it.get("is_relative")
            and it.get("dynamic_type", "static") == "static"
            and it.get("statement_type") in ("es_import", "require", "import_equals")
        ]
        if len(relative_aggregates) >= 1:
            return BarrelInfo(
                True, 0.65, self.name,
                reasons=["barrel-named", "has-relative-static-imports"],
            )
        return BarrelInfo(True, 0.4, self.name, ["barrel-named-but-weak-import-evidence"])


class PackageExportsDetector:
    """Detects modern packages whose entry is declared only via "exports" (no index)."""
    name = "package-exports"

    def detect(self, filepath: str, content: Optional[str] = None,
               lightweight_reexports: Optional[List[Dict[str, Any]]] = None,
               pkg_has_exports: Optional[bool] = None,
               **context: Any) -> BarrelInfo:
        if pkg_has_exports:
            return BarrelInfo(True, 0.6, self.name, ["package-exports-map-present"])
        # Caller (engine) can pre-compute via cheap package.json probe
        return BarrelInfo(False, 0.0, self.name, ["no-exports-signal"])


# Lightweight (current production default — fast, regex, no full AST)
class LightweightRegexReexportExtractor:
    """Fast, regex-based extractor using the same hoisted EXPORT_PATTERNS as before."""
    name = "lightweight-regex"

    # NOTE: The actual patterns live in javascript.py for now (shared).
    # We accept an injected pattern list or fall back to a minimal self-contained set
    # so bree.py is independently importable/testable. In integration we pass the real ones.

    def __init__(self, export_patterns: Optional[List[Tuple[re.Pattern, str]]] = None):
        self._patterns = export_patterns  # populated at integration time

    def extract(
        self,
        filepath: str,
        content: Optional[str] = None,
        **context: Any,
    ) -> List[Dict[str, Any]]:
        path = Path(filepath).resolve()
        if not path.exists():
            return []
        if content is None:
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                return []

        # Early-out (perf critical)
        if "export" not in content or " from " not in content:
            return []

        results: List[Dict[str, Any]] = []
        patterns = self._patterns or []
        # Fallback minimal patterns if not injected (keeps bree usable standalone)
        if not patterns:
            patterns = [
                (re.compile(r'export\s+\*\s+from\s+[\'"]([^\'"]+)[\'"]', re.M), "export_star"),
                (re.compile(r'export\s+(?:\*\s+as\s+\w+|[\w\s{},*]+)\s+from\s+[\'"]([^\'"]+)[\'"]', re.M), "export_from"),
            ]

        for pattern, ptype in patterns:
            for match in pattern.finditer(content):
                raw = ""
                for g in match.groups():
                    if g:
                        raw = g.strip()
                        break
                if raw:
                    # Conditional detection delegated to context helper or simple heuristic
                    cond_ctx = context.get("_detect_conditional", lambda c, s: None)(content, match.start())
                    results.append({
                        "raw_module": raw,
                        "statement_type": ptype,
                        "is_conditional": cond_ctx is not None,
                        "conditional_context": cond_ctx,
                    })
        return results


# Skeleton for future full-AST extractor (registered but not default)
class ASTReexportExtractor:
    """Placeholder for a heavier but more accurate extractor (tree-sitter / acorn / etc.).
    Never active unless explicitly registered and selected via policy or factory.
    """
    name = "ast-full"

    def extract(self, filepath: str, content: Optional[str] = None, **context: Any) -> List[Dict[str, Any]]:
        # Future: if context.get("use_ast"):
        #     return real_ast_extraction(...)
        return []  # safe no-op today


# Enhanced ExportsMapHandler with wildcard support
class DefaultExportsMapHandler:
    """Production handler with wildcard ("*") pattern support + full condition logic.

    DEPRECATION NOTE (P4 + R4 Legacy Deprecation Execution): Wildcard + exports resolution provided by
    central wikifier.resolution (resolve_exports_map + PackageExportsStrategy). BREE registry allows
    pluggable barrel handlers (local fallback only, now ultra-slim: main + wildcards only; standard
    matching deduped via delegation to central _read/_target/_pick + resolve_exports_map).
    ALWAYS prefers central first; warn only on fallback. JS shims match (R4 thinned). Central is the
    UNAMBIGUOUS DEFAULT. Removal of remaining dupe: v0.5. See resolution.py.
    """
    name = "default-exports-map"

    def __init__(self):
        self._pkg_cache: Dict[str, Optional[dict]] = {}

    def _read_pkg(self, pkg_dir: Path) -> Optional[dict]:
        """R4: thin caching wrapper around central _read_package_json (deduped impl)."""
        key = str(pkg_dir)
        if key in self._pkg_cache:
            return self._pkg_cache[key]
        try:
            from ..resolution import _read_package_json as _central_read
            data = _central_read(pkg_dir)
            self._pkg_cache[key] = data
            return data
        except Exception:
            pass
        # Rare fallback (central unavailable) — minimal to avoid reintroducing dupe
        pj = pkg_dir / "package.json"
        if not pj.exists():
            self._pkg_cache[key] = None
            return None
        try:
            with pj.open(encoding="utf-8") as f:
                data = json.load(f)
            self._pkg_cache[key] = data if isinstance(data, dict) else None
        except Exception:
            self._pkg_cache[key] = None
        return self._pkg_cache[key]

    def _resolve_target(self, pkg_dir: Path, target: str) -> Optional[Path]:
        """R4 Legacy Deprecation: delegates to central _resolve_target_path (single source, no dupe)."""
        try:
            from ..resolution import _resolve_target_path as _central_target
            return _central_target(pkg_dir, target)
        except Exception:
            pass
        # Minimal fallback only if central missing (should not happen post-R4)
        if not target or not isinstance(target, str):
            return None
        t = target.strip()
        if t.startswith("file:"):
            t = t[5:]
        p = pkg_dir / t.lstrip("/").lstrip("./")
        try:
            if p.exists():
                if p.is_file():
                    return p
                if p.is_dir():
                    for idx in ("index.js", "index.ts", "index.jsx", "index.tsx", "index.mjs", "index.cjs"):
                        cand = p / idx
                        if cand.exists():
                            return cand
            if not p.suffix:
                for ext in (".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"):
                    cand = p.with_suffix(ext)
                    if cand.exists() and cand.is_file():
                        return cand
                if p.exists() and p.is_dir():
                    for idx in ("index.js", "index.ts", "index.mjs", "index.cjs"):
                        cand = p / idx
                        if cand.exists():
                            return cand
        except Exception:
            pass
        return None

    def _pick_from_conditions(self, spec: Any, pkg_dir: Path) -> Optional[Path]:
        """R4: delegates to central _pick_target_from_conditions (deduped priority/condition logic)."""
        try:
            from ..resolution import _pick_target_from_conditions as _central_pick
            return _central_pick(spec, pkg_dir)
        except Exception:
            pass
        # Fallback minimal (rare)
        if isinstance(spec, str):
            return self._resolve_target(pkg_dir, spec)
        if isinstance(spec, list):
            for item in spec:
                res = self._pick_from_conditions(item, pkg_dir)
                if res:
                    return res
            return None
        if not isinstance(spec, dict):
            return None

        priority = [
            "import", "module", "esm", "es2020", "es2015", "es6",
            "default", "node", "node-addons", "require", "types", "typings", "browser"
        ]
        for cond in priority:
            if cond in spec:
                res = self._pick_from_conditions(spec[cond], pkg_dir)
                if res:
                    return res
        for v in spec.values():
            res = self._pick_from_conditions(v, pkg_dir)
            if res:
                return res
        return None

    def _apply_wildcard(self, key: str, subpath: str, target_template: Any) -> Optional[str]:
        """Return substituted target string if key is a wildcard pattern matching subpath."""
        if "*" not in key:
            return None
        # Build regex: "./foo/*" -> r"^\./foo/(.*)$"
        escaped = re.escape(key)
        regex_str = "^" + escaped.replace(r"\*", "(.*)") + "$"
        m = re.match(regex_str, subpath)
        if not m:
            return None
        replacement = m.group(1)
        if isinstance(target_template, str):
            return target_template.replace("*", replacement)
        # If target_template is dict (conditions), we will resolve later; return a marker
        return target_template  # caller will handle dict form

    def resolve(self, pkg_dir: Path, subpath: str = ".") -> Optional[Path]:
        pkg = self._read_pkg(pkg_dir)
        if not pkg:
            return None

        # P4/F4 deprecation path: ALWAYS prefer central resolution.py first (no warning).
        # This eliminates duplication and gains monorepo-hardened logic (complex conditionals,
        # ts refs, pnpm stores, rich metadata). Local BREE impl kept only as fallback for
        # registry pluggability + transition compat. Warn ONLY when legacy path is actually taken.
        # Full removal of duplicate after v0.5.
        try:
            from ..resolution import resolve_exports_map as _central_exp
            via = _central_exp(pkg_dir, subpath)
            if via:
                return via
        except Exception:
            pass  # fallthrough to local BREE logic (kept for compat + registry) --> warn below

        # Reached legacy duplicate path: emit deprecation warning (R4 strengthened: only on fallback)
        try:
            warnings.warn(
                "DefaultExportsMapHandler.resolve (bree.py) legacy path deprecated (R4). "
                "BREE delegates to central wikifier.resolution (JS side now also thin shims; low-levels deduped). "
                "Full removal of duplicate after v0.5. Central is the unambiguous default. "
                "See resolution.py + contracts for migration.",
                DeprecationWarning,
                stacklevel=2,
            )
        except Exception:
            pass

        # R4 final slim: only no-exports main + BREE's wildcard block (its pluggable value-add).
        # All standard export key/exact/subpath/condition/string-shorthand matching removed from
        # here (now exclusively in central resolve_exports_map). Reduces dupe surface in BREE.
        exports = pkg.get("exports")
        if exports is None:
            # legacy main/module fallback only
            for k in ("module", "main", "jsnext:main"):
                v = pkg.get(k)
                if isinstance(v, str):
                    res = self._resolve_target(pkg_dir, v)
                    if res:
                        return res
            return None

        # BREE wildcard support (kept as registry enhancement for barrel-specific cases)
        if self._is_wildcard_enabled():
            for key, val in (exports.items() if isinstance(exports, dict) else []):
                if not isinstance(key, str) or "*" not in key:
                    continue
                substituted = self._apply_wildcard(key, subpath, val)
                if substituted is not None:
                    if isinstance(substituted, dict):
                        return self._pick_from_conditions(substituted, pkg_dir)
                    if isinstance(substituted, str):
                        return self._resolve_target(pkg_dir, substituted)

        # Non-wildcard exports cases: central already tried; no dupe exact-match here.
        return None

    def _is_wildcard_enabled(self) -> bool:
        # Hook for future policy gating; always True for now (exotic support on by default)
        return True


# =============================================================================
# Registry (the extension point for future patterns)
# =============================================================================

class BREERegistry:
    """Central registry. All strategies are discovered/registered here.
    Default strategies are auto-registered on import of bree.
    """

    _detectors: List[Tuple[int, BarrelDetector]] = []
    _extractors: Dict[str, ReexportExtractor] = {}
    _exports_handlers: Dict[str, ExportsMapHandler] = {}
    _specifier_resolvers: Dict[str, SpecifierResolver] = {}

    @classmethod
    def register_detector(cls, detector: BarrelDetector, priority: int = 0) -> None:
        cls._detectors.append((priority, detector))
        # Highest priority first
        cls._detectors.sort(key=lambda t: -t[0])

    @classmethod
    def register_extractor(cls, name: str, extractor: ReexportExtractor) -> None:
        cls._extractors[name] = extractor

    @classmethod
    def register_exports_handler(cls, name: str, handler: ExportsMapHandler) -> None:
        cls._exports_handlers[name] = handler

    @classmethod
    def get_detectors(cls) -> List[BarrelDetector]:
        return [d for _, d in cls._detectors]

    @classmethod
    def get_extractor(cls, name: str = "lightweight-regex") -> Optional[ReexportExtractor]:
        return cls._extractors.get(name)

    @classmethod
    def get_exports_handler(cls, name: str = "default-exports-map") -> Optional[ExportsMapHandler]:
        return cls._exports_handlers.get(name)

    @classmethod
    def clear(cls) -> None:
        """Primarily for tests."""
        cls._detectors.clear()
        cls._extractors.clear()
        cls._exports_handlers.clear()
        cls._specifier_resolvers.clear()


# Auto-register defaults (executed exactly once at import)
_default_detector1 = ExportFromPresenceDetector()
_default_detector2 = NameAndHeuristicBarrelDetector()
_default_detector3 = PackageExportsDetector()

BREERegistry.register_detector(_default_detector1, priority=100)
BREERegistry.register_detector(_default_detector2, priority=50)
BREERegistry.register_detector(_default_detector3, priority=30)

_default_light_extractor = LightweightRegexReexportExtractor()
BREERegistry.register_extractor("lightweight-regex", _default_light_extractor)
BREERegistry.register_extractor("ast-full", ASTReexportExtractor())

_default_exports = DefaultExportsMapHandler()
BREERegistry.register_exports_handler("default-exports-map", _default_exports)

# Phase 2 / Agent 2 integration: SpecifierResolver adapter (defined early for load; registered at end of module)
class DefaultSpecifierResolver:
    """Delegates to wikifier.resolution.resolve for canonical + rich strategy output (from Agent 2)."""
    name = "resolution-layer-v1"

    def resolve(self, current_file: Path, raw_module: str, **context: Any) -> Tuple[str, Optional[str]]:
        try:
            from ..resolution import resolve
            root = context.get("root") or _get_project_root_fallback(".")
            res = resolve(raw_module, str(current_file), root, follow_symlinks=True)
            disp = res.display_module or raw_module
            rp = str(res.resolved_file) if res.resolved_file else None
            return disp, rp
        except Exception:
            return raw_module, None


# =============================================================================
# Core Engine (the BREE)
# =============================================================================

class BarrelReexportAnalysisEngine:
    """
    The central BREE engine. Obtain via get_bree_engine().

    All high-level operations (is_barrel, extract, expand_chain, resolve_via_exports)
    go through here so that policy, registry, precomputation and diagnostics are
    applied uniformly.
    """

    def __init__(
        self,
        policy: Optional[ExpansionPolicy] = None,
        registry: Optional[BREERegistry] = None,
    ):
        self.policy = policy or ExpansionPolicy()
        self.registry = registry or BREERegistry
        self._barrel_index: Dict[str, List[ReexportHop]] = {}  # precomputed (optional)
        self._memo: Dict[str, Any] = {}  # short-lived per-run memo

    # --- Public high-level API (what javascript.py and future consumers use) ---

    def is_barrel(self, filepath: str, **context: Any) -> BarrelInfo:
        """Run all registered detectors; return the best (highest confidence) result."""
        best: Optional[BarrelInfo] = None
        for det in self.registry.get_detectors():
            try:
                info = det.detect(filepath, **context)
                if info.is_barrel and (best is None or info.confidence > best.confidence):
                    best = info
            except Exception:
                continue  # never let one bad detector kill the engine
        if best is None:
            return BarrelInfo(False, 0.0, "none", ["no-detector-claimed"])
        return best

    def extract_reexports(
        self,
        filepath: str,
        extractor_name: str = "lightweight-regex",
        **context: Any,
    ) -> List[Dict[str, Any]]:
        """Use the named (or default) extractor. Results are cached lightly."""
        key = f"reexp::{filepath}::{extractor_name}"
        if key in self._memo:
            return self._memo[key]
        extractor = self.registry.get_extractor(extractor_name)
        if not extractor:
            extractor = self.registry.get_extractor("lightweight-regex")
        if not extractor:
            res: List[Dict[str, Any]] = []
        else:
            try:
                res = extractor.extract(filepath, **context) or []
            except Exception:
                res = []
        self._memo[key] = res
        return res

    def resolve_via_exports(self, pkg_dir: Path, subpath: str = ".") -> Optional[Path]:
        handler = self.registry.get_exports_handler("default-exports-map")
        if handler:
            try:
                return handler.resolve(pkg_dir, subpath)
            except Exception:
                return None
        return None

    def expand_chain(
        self,
        start_file: Path,
        start_specifier: str,
        resolver_func: Callable[[Path, str], Tuple[str, Optional[str]]],  # (display, resolved_path)
        max_depth: Optional[int] = None,
        visited: Optional[set] = None,
        **context: Any,
    ) -> ExpandedChainResult:
        """
        Policy-driven recursive (bounded) expansion of a potential barrel chain.
        Replicates the semantics and exact output shape of the legacy _follow_reexports
        while adding structure, policy control, and future hooks.

        Phase 2 extension: if "barrel_cache" in context (or engine holds one), performs
        mtimes_snapshot-validated persistent lookup before work and stores rich result
        (including is_partial) + updates reverse index on successful expansion.
        """
        policy = self.policy
        depth_limit = max_depth if max_depth is not None else policy.max_depth

        if visited is None:
            visited = set()

        if depth_limit <= 0:
            return ExpandedChainResult([], [], 0, "none", policy, is_partial=True, partial_reason="depth_limit")

        # --- Phase 2 persistent cache wiring (mtimes-aware) ---
        barrel_cache: Optional[BarrelResolutionCache] = context.get("barrel_cache")
        cache_root: Path = context.get("cache_root") or _get_project_root_fallback(".")
        importer_rel: Optional[str] = context.get("importer_rel")
        # Wave 1 canonical normalization pass: ensure importer_rel is always canonical v1 physical rel
        if importer_rel:
            importer_rel = _brc_canonical(importer_rel, cache_root)
            context["importer_rel"] = importer_rel  # propagate normalized form to recursive + hit paths
        is_top_level = context.get("_bree_top_level", True)  # caller marks first call

        if barrel_cache is None:
            # Use the process-level session cache (loaded once per root) instead
            # of re-reading import_cache.json on every top-level expansion.
            barrel_cache = get_session_barrel_cache(cache_root)
            if barrel_cache is not None:
                # make available to recursive calls via **context
                context["barrel_cache"] = barrel_cache
                context["cache_root"] = cache_root
                if importer_rel:
                    context["importer_rel"] = importer_rel

        # Attempt early hit for this expansion level (keyed on resolved start + spec)
        # We perform the hit logic after first resolve below to have the real resolved_path.

        # Resolve the current specifier using the caller's resolver (keeps resolution
        # logic in javascript.py for now; BREE can take over later via SpecifierResolver)
        # Phase 4 / Gap#1 barrel completeness: resolver may return 2-tuple (display, path)
        # or 3-tuple (display, path, resolution_metadata_dict) when the closure (in
        # javascript.py) delegates to central_resolve. We capture hop_meta here so that
        # terminal leaves constructed below carry the *final hop*'s metadata for res_meta_v1.
        hop_meta: Optional[Dict[str, Any]] = None
        try:
            res_t = resolver_func(start_file, start_specifier)
            if isinstance(res_t, (list, tuple)):
                if len(res_t) >= 3:
                    display, resolved_path, hop_meta = res_t[0], res_t[1], res_t[2]
                elif len(res_t) == 2:
                    display, resolved_path = res_t[0], res_t[1]
                else:
                    display, resolved_path = res_t[0] if res_t else start_specifier, None
            else:
                display, resolved_path = str(res_t), None
        except Exception:
            display, resolved_path = start_specifier, None
            hop_meta = None

        # Wave 1 canonical: use physical canonical form for all BRC keys/ids/snapshots
        resolved_for_brc = _brc_canonical(resolved_path, cache_root) if resolved_path else None

        # E1 fix: anchor the (often project-relative, e.g. central_resolve canonical rel)
        # resolved path to the project root for ALL file IO below (detector content reads,
        # re-export extraction, recursion start file, mtime snapshots). Without this, every
        # run with CWD != project root silently saw "file does not exist": no re-exports
        # extracted (chain stopped at the entry barrel) and an empty mtimes_snapshot.
        resolved_abs: Optional[Path] = None
        if resolved_path:
            try:
                _rp = Path(str(resolved_path))
                resolved_abs = _rp if _rp.is_absolute() else (Path(cache_root) / _rp)
            except Exception:
                resolved_abs = Path(str(resolved_path))
        # E1: tolerate resolvers that return a DIRECTORY for a package/dir import
        # (node-style). Without this, the directory was treated as an unreadable
        # terminal leaf — no re-export extraction, chain never reached the real
        # entry barrel, and leaf churn could not invalidate the consumer.
        if resolved_abs is not None:
            try:
                if resolved_abs.is_dir():
                    for _idx in ("index.js", "index.ts", "index.jsx", "index.tsx", "index.mjs", "index.cjs"):
                        _cand = resolved_abs / _idx
                        if _cand.is_file():
                            resolved_abs = _cand
                            resolved_path = str(_cand)
                            resolved_for_brc = _brc_canonical(resolved_path, cache_root)
                            break
            except Exception:
                pass

        # --- Phase 2: mtime-validated persistent cache hit (after first resolve gives us identity) ---
        cache_hit = False
        cached_entry: Optional[Dict[str, Any]] = None
        if barrel_cache is not None and resolved_for_brc:
            # Key the expansion by the starting resolved barrel file + the specifier that landed on it
            # Use canonical v1 form so ids are stable across symlink layouts
            potential_chain_start = [resolved_for_brc]
            cid = barrel_cache._make_chain_id(potential_chain_start, start_specifier)
            cached_entry = barrel_cache.get(cid)
            if cached_entry and not barrel_cache.is_stale(cached_entry, cache_root):
                # Fresh hit — replay (promote importers if this caller is new)
                if importer_rel and importer_rel not in (cached_entry.get("importers") or []):
                    cached_entry.setdefault("importers", []).append(importer_rel)
                    # also update index lightly
                    barrel_cache.store(
                        chain_id=cid,
                        importers=[importer_rel],
                        barrel_chain=cached_entry.get("barrel_chain"),
                        results=cached_entry.get("results"),
                        mtimes_snapshot=cached_entry.get("mtimes_snapshot"),
                        ctx=context,
                    )
                # Reconstruct ExpandedChainResult from cache (preserve partial flag)
                ch_res = cached_entry.get("results", [])
                ch_chain = cached_entry.get("barrel_chain", [start_specifier])
                ch_detector = cached_entry.get("detector_used", "cached")
                ch_partial = bool(cached_entry.get("is_partial"))
                ch_reason = cached_entry.get("partial_reason")
                cache_hit = True
                return ExpandedChainResult(
                    results=list(ch_res),
                    barrel_chain=list(ch_chain),
                    max_depth_reached=len(ch_chain),
                    detector_used=ch_detector,
                    policy=policy,
                    hops=[],  # hops can be reconstructed from stored if needed; for perf we skip
                    is_partial=ch_partial,
                    partial_reason=ch_reason,
                    # E1: replayed chains expose their full file set too (barrel_chain is canonical)
                    chain_files=[str(c) for c in (cached_entry.get("barrel_chain") or []) if c],
                )

        if not resolved_path:
            # Record the unresolved hop (compat with legacy)
            leaf = {
                "module": display,
                "resolved_path": None,
                "via_barrel": True,
                "barrel_chain": [start_specifier],
                "barrel_depth": 1,
                "is_conditional": False,
                "conditional_context": None,
                # Defensive barrel_v2 synthesis (Gap #1 Option 3 emission audit): every via_barrel
                # creation site must carry barrel_v2 so BRC-stored results, direct BREE consumers,
                # and cache-hit replays are rich-complete (post-processing in javascript._follow
                # will still normalize/overwrite for live parse returns using chain_result flags).
                "barrel_v2": {
                    "via_barrel": True,
                    "barrel_depth": 1,
                    "barrel_chain": [start_specifier],
                    "barrel_detector": "unresolved",
                    "is_partial": True,
                    "partial_reason": "unresolved_start",
                    "hops": [],
                    "mtimes_signature": "",
                },
                # Gap #1 barrel completeness (Option 1): attach resolution_metadata + strategy
                # from this hop's resolver call (if the JS closure provided 3-tuple from central_resolve).
                # For unresolved case, meta may describe the failure strategy.
                "resolution_metadata": hop_meta or {},
                "strategy": (hop_meta or {}).get("strategy", "unresolved"),
            }
            res = ExpandedChainResult([leaf], [start_specifier], 1, "unresolved", policy, is_partial=True, partial_reason="unresolved_start")
            # store partial result for future?
            if barrel_cache is not None and importer_rel:
                barrel_cache.store(
                    importers=[importer_rel] if importer_rel else [],
                    barrel_chain=[],
                    results=[leaf],
                    start_specifier=start_specifier,
                    detector_used="unresolved",
                    is_partial=True,
                    partial_reason="unresolved_start",
                    mtimes_snapshot={},
                    ctx=context,
                )
            return res

        if resolved_path in visited:
            return ExpandedChainResult([], [], 0, "cycle", policy, is_partial=True, partial_reason="cycle_detected")

        # E1: an empty visited set marks the chain-root call (the consumer's own import
        # statement). Used below so the entry barrel itself is also emitted as an edge
        # (legacy edge contract: consumer -> barrel/index.js) in addition to the leaves.
        entry_is_chain_root = not visited

        visited.add(resolved_path)

        # Detect + extract using BREE strategies
        # E1 fix: hand strategies the ROOT-ANCHORED path so file reads work from any CWD.
        detect_path = str(resolved_abs) if resolved_abs is not None else str(resolved_path)
        barrel_info = self.is_barrel(
            detect_path,
            content=context.get("content"),
            lightweight_reexports=None,  # filled below
            **context,
        )

        reexports = self.extract_reexports(detect_path, **context)

        # If the detector didn't see reexports yet, give lightweight results to detectors
        if not barrel_info.is_barrel and reexports:
            barrel_info = self.is_barrel(
                detect_path,
                lightweight_reexports=reexports,
                **context,
            )

        results: List[Dict[str, Any]] = []
        hops: List[ReexportHop] = []
        sub_chain_files: List[str] = []  # E1: intermediate barrel hops + sub-leaves from recursion
        current_depth = 1
        detector_name = barrel_info.detector_name if barrel_info.is_barrel else "none"

        if reexports and depth_limit > 1 and barrel_info.is_barrel:
            # E1: at the chain root, FIRST emit the entry barrel itself as a regular
            # via_barrel edge (consumer -> barrel/index.js). Expansion then appends
            # the transitive leaves after it. This preserves the legacy edge contract
            # (the entry barrel is the consumer's direct dependency) while the leaves
            # carry the deep-chain information.
            if entry_is_chain_root:
                results.append({
                    "module": display,
                    "resolved_path": resolved_path,
                    "via_barrel": True,
                    "barrel_chain": [start_specifier],
                    "barrel_depth": current_depth,
                    "is_conditional": False,
                    "conditional_context": None,
                    "barrel_detector": detector_name,
                    "barrel_v2": {
                        "via_barrel": True,
                        "barrel_depth": current_depth,
                        "barrel_chain": [start_specifier],
                        "barrel_detector": detector_name,
                        "is_partial": False,
                        "partial_reason": None,
                        "hops": [],
                        "mtimes_signature": "",
                    },
                    "resolution_metadata": hop_meta or {},
                    "strategy": (hop_meta or {}).get("strategy", "bree-entry"),
                })
            fanout = 0
            for reexp in reexports:
                if fanout >= policy.max_fanout_per_hop:
                    break
                fanout += 1

                hop = ReexportHop(
                    raw_specifier=reexp.get("raw_module", ""),
                    statement_type=reexp.get("statement_type", "unknown"),
                    is_conditional=bool(reexp.get("is_conditional")),
                    conditional_context=reexp.get("conditional_context"),
                )
                hops.append(hop)

                # Improved propagation on reexport recursion (final squeeze, BRC side): explicit copy + ensure
                # importer_rel (the top consumer's) reaches every leaf hop in chain (e.g. index reexporting leaf).
                # Combined with defensive ctx handling in store(), guarantees file_index + importers populated
                # for leaf/intermediates pointing back to original importer_rel for proof's synth + symlink canon + del cases.
                sub_context = dict(context)
                if importer_rel:
                    sub_context["importer_rel"] = importer_rel
                sub_res = self.expand_chain(
                    # E1 fix: recurse with the root-anchored file so the resolver
                    # (e.g. central_resolve via javascript closure) gets a real
                    # importer path regardless of CWD.
                    resolved_abs if resolved_abs is not None else Path(resolved_path),
                    reexp.get("raw_module", ""),
                    resolver_func,
                    max_depth=depth_limit - 1,
                    visited=visited,
                    **sub_context,
                )
                # E1: accumulate every file the sub-expansion traversed (intermediate
                # barrels + leaves) so the top-level snapshot/index covers the FULL chain.
                try:
                    for scf in (getattr(sub_res, "chain_files", None) or []):
                        if scf and scf not in sub_chain_files:
                            sub_chain_files.append(str(scf))
                except Exception:
                    pass
                for sub in sub_res.results:
                    # Prepend current hop to chain (exactly as legacy did)
                    chain = sub.get("barrel_chain", [])
                    chain.insert(0, start_specifier)
                    sub["barrel_chain"] = chain
                    sub["barrel_depth"] = sub.get("barrel_depth", 0) + 1

                    # Conditional OR propagation (Limitation #6 fidelity)
                    if hop.is_conditional:
                        sub["is_conditional"] = bool(sub.get("is_conditional") or True)
                        if not sub.get("conditional_context"):
                            sub["conditional_context"] = hop.conditional_context
                    else:
                        sub.setdefault("is_conditional", False)

                    # Enrich with BREE metadata (additive)
                    sub.setdefault("barrel_detector", detector_name)

                    results.append(sub)
        else:
            # Terminal leaf
            leaf = {
                "module": display,
                "resolved_path": resolved_path,
                "via_barrel": True,
                "barrel_chain": [start_specifier],
                "barrel_depth": current_depth,
                "is_conditional": False,
                "conditional_context": None,
                "barrel_detector": detector_name,
                # Defensive barrel_v2 synthesis (Gap #1 Option 3 emission audit): every via_barrel
                # creation site must carry barrel_v2 so BRC-stored results, direct BREE consumers,
                # and cache-hit replays are rich-complete (post-processing in javascript._follow
                # will still normalize/overwrite for live parse returns using chain_result flags).
                "barrel_v2": {
                    "via_barrel": True,
                    "barrel_depth": current_depth,
                    "barrel_chain": [start_specifier],
                    "barrel_detector": detector_name,
                    "is_partial": False,
                    "partial_reason": None,
                    "hops": [h.__dict__ if hasattr(h, "__dict__") else h for h in (hops or [])],
                    "mtimes_signature": "",
                },
                # Gap #1 barrel completeness (Option 1): attach resolution_metadata/strategy
                # captured from *this* level's resolver_func return (the final hop for this leaf).
                # This is populated when the closure in javascript._follow_reexports delegates
                # to central_resolve; enables res_meta_v1 emission for all barrel-tagged leaves
                # without requiring post-hoc re-resolution. Sub-chain results carry their own
                # (deeper) hop metadata via recursion.
                "resolution_metadata": hop_meta or {},
                "strategy": (hop_meta or {}).get("strategy", "bree-leaf"),
            }
            results.append(leaf)

        # --- Phase 2: build mtimes snapshot for the chain we just expanded (or partial) ---
        # Snapshot covers the entry barrel + every intermediate barrel hop traversed during
        # recursion (sub_chain_files) + every leaf resolved_path in results.
        # Wave 1: canonicalize all barrel paths (barrel_chain + mtimes_snapshot keys) via to_canonical_rel v1
        # E1 fix: (a) include intermediate hops, (b) anchor relative paths to cache_root before
        # the exists()/mtime probe (they are project-relative canonical forms, NOT CWD-relative),
        # (c) per-item tolerance — one bad path must not empty the whole snapshot.
        mtimes_snap: Dict[str, int] = {}
        all_chain_files: List[str] = []  # ordered: entry barrel first, then deterministic rest
        _seen_cf: set = set()

        def _add_chain_file(x: Any) -> None:
            s = str(x) if x else ""
            if s and s not in _seen_cf:
                _seen_cf.add(s)
                all_chain_files.append(s)

        if resolved_path:
            _add_chain_file(resolved_path)
        for f in sorted(str(s) for s in sub_chain_files if s):
            _add_chain_file(f)
        for r in results:
            rp = r.get("resolved_path") if isinstance(r, dict) else None
            if rp:
                _add_chain_file(rp)
        canon_chain_files: List[str] = []
        for f in all_chain_files:
            try:
                c = _brc_canonical(f, cache_root)
                if c and c not in canon_chain_files:
                    canon_chain_files.append(c)
                fp = Path(f)
                if not fp.is_absolute():
                    fp = Path(cache_root) / fp
                if fp.exists():
                    key = c or str(f)
                    if key not in mtimes_snap:
                        # float for sub-second churn detection (see is_stale)
                        mtimes_snap[key] = float(fp.stat().st_mtime)
            except Exception:
                continue  # tolerate this path; keep snapshotting the rest of the chain

        chain_for_id = [str(resolved_path)] if resolved_path else []
        # For full chain we can enrich from results' barrel_chain but start with entry
        full_barrel_chain = [c for c in canon_chain_files if c] or ([str(resolved_path)] if resolved_path else [])
        # In deeper runs the sub results already have prepended chains; for top store we use what we have
        # (they will be normalized on their own store; top-level also normalizes below)

        final_is_partial = bool(len(results) == 0 or any((r.get("resolved_path") is None if isinstance(r, dict) else False) for r in results))

        if barrel_cache is not None:
            imps_list = [importer_rel] if importer_rel else []
            # E1 fix: store under the SAME chain_id the lookup above computes
            # ([entry barrel] + specifier). The full multi-file barrel_chain would
            # otherwise hash to a different id, so hits/promotions would target a
            # different entry than the one stored here.
            explicit_cid: Optional[str] = None
            if resolved_for_brc:
                try:
                    explicit_cid = barrel_cache._make_chain_id([resolved_for_brc], start_specifier)
                except Exception:
                    explicit_cid = None
            barrel_cache.store(
                chain_id=explicit_cid,
                importers=imps_list,
                barrel_chain=full_barrel_chain or [str(resolved_path)] if resolved_path else [],
                hops=[h.__dict__ if hasattr(h, "__dict__") else (h if isinstance(h, dict) else {"raw": str(h)}) for h in (hops or [])],
                results=results,
                start_specifier=start_specifier,
                detector_used=detector_name,
                is_partial=final_is_partial,
                partial_reason="partial_chain" if final_is_partial else None,
                mtimes_snapshot=mtimes_snap,
                ctx=context,
            )
            # Defer persistence: mark the session dirty and let the parse-run
            # boundary flush once (per file in pipe mode, per run in batch mode).
            # Foreign caches passed in via context manage their own persistence.
            if barrel_cache is _BRC_SESSION["brc"]:
                mark_session_dirty(barrel_cache)
            else:
                try:
                    _ensure_import_cache_helpers()
                    from .. import import_cache as _ic
                    cdict = _ic.load_cache(cache_root)
                    barrel_cache.to_cache_updates(cdict)
                    _ic.save_cache(cache_root, cdict)
                except Exception:
                    pass  # best effort; cache still consistent in mem for this run

        return ExpandedChainResult(
            results=results,
            barrel_chain=[start_specifier],
            max_depth_reached=current_depth,
            detector_used=detector_name,
            policy=policy,
            hops=hops,
            is_partial=final_is_partial,
            partial_reason="partial_chain" if final_is_partial else None,
            # E1: expose the canonical file set so PARENT expansions can fold our
            # entry barrel (their intermediate hop) + leaves into their snapshot.
            chain_files=list(canon_chain_files),
        )

    def clear_memo(self) -> None:
        self._memo.clear()

    # Precomputation hook (Phase 4 skeleton)
    def build_barrel_index(
        self,
        files: List[str],
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> Dict[str, List[ReexportHop]]:
        """Cheap pre-scan using lightweight extractor. Result can be fed to policy."""
        index: Dict[str, List[ReexportHop]] = {}
        total = len(files)
        for i, f in enumerate(files):
            try:
                hops_raw = self.extract_reexports(f)
                index[f] = [
                    ReexportHop(
                        h.get("raw_module", ""),
                        h.get("statement_type", "unknown"),
                        bool(h.get("is_conditional")),
                        h.get("conditional_context"),
                    )
                    for h in hops_raw
                ]
            except Exception:
                index[f] = []
            if progress_cb and i % 50 == 0:
                progress_cb(i, total)
        self._barrel_index = index
        return index

    def get_precomputed_hops(self, filepath: str) -> List[ReexportHop]:
        return self._barrel_index.get(filepath, [])


# Singleton factory (simple, thread-unsafe is fine for CLI/MCP usage pattern)
_ENGINE: Optional[BarrelReexportAnalysisEngine] = None


def get_bree_engine(policy: Optional[ExpansionPolicy] = None) -> BarrelReexportAnalysisEngine:
    """Primary entry point for all consumers."""
    global _ENGINE
    if _ENGINE is None or policy is not None:
        _ENGINE = BarrelReexportAnalysisEngine(policy=policy)
    return _ENGINE


def reset_bree_engine() -> None:
    """Test / diagnostic helper.

    E1 fix: clearing the registry used to leave it EMPTY for the rest of the
    process (defaults were registered exactly once at import), which silently
    disabled barrel detection/extraction — chains stopped at the entry barrel
    and importers were never invalidated on leaf edits. We now re-register the
    module-level default instances (the same objects javascript.py wires its
    authoritative EXPORT_PATTERNS into, so that injection survives resets).
    Also flushes + detaches the process-level BRC session so per-root state
    cannot leak across resets (flush-then-discard preserves store semantics).
    """
    global _ENGINE
    _ENGINE = None
    # Persist any pending session barrel state before discarding it.
    try:
        flush_barrel_cache()
    except Exception:
        pass
    _BRC_SESSION.update({"root": None, "brc": None, "dirty": False, "batch": False})
    BREERegistry.clear()
    # Restore the default strategy wiring (same singleton instances as import time).
    BREERegistry.register_detector(_default_detector1, priority=100)
    BREERegistry.register_detector(_default_detector2, priority=50)
    BREERegistry.register_detector(_default_detector3, priority=30)
    BREERegistry.register_extractor("lightweight-regex", _default_light_extractor)
    BREERegistry.register_extractor("ast-full", ASTReexportExtractor())
    BREERegistry.register_exports_handler("default-exports-map", _default_exports)


# Convenience: show registered strategies (useful for debugging / library.md)
def describe_bree() -> Dict[str, Any]:
    eng = get_bree_engine()
    return {
        "detectors": [d.name for d in BREERegistry.get_detectors()],
        "extractors": list(BREERegistry._extractors.keys()),
        "exports_handlers": list(BREERegistry._exports_handlers.keys()),
        "current_policy": eng.policy.__dict__,
    }


# Late registration for SpecifierResolver (Agent 2 integration) — after all classes defined
try:
    _spec_res = DefaultSpecifierResolver()
    # If registry grows a map for specifiers in future, it would be registered here.
    # For now the adapter class is available for direct use or wiring into expand_chain resolver_func.
    BREERegistry._specifier_resolvers = getattr(BREERegistry, "_specifier_resolvers", {})
    BREERegistry._specifier_resolvers[_spec_res.name] = _spec_res
except Exception:
    pass


# =============================================================================
# Example of future exotic registration (commented — shows extensibility)
# =============================================================================
"""
# In a future plugin or monorepo-specific config:

from wikifier.parsers.bree import BREERegistry, BarrelDetector, BarrelInfo

class MyFrameworkBarrelDetector:
    name = "my-framework-barrel"
    def detect(self, filepath, **ctx):
        if "my-internal-barrel" in Path(filepath).read_text(errors="ignore"):
            return BarrelInfo(True, 0.99, self.name, ["framework-convention"])
        return BarrelInfo(False, 0.0, self.name)

BREERegistry.register_detector(MyFrameworkBarrelDetector(), priority=80)
"""
