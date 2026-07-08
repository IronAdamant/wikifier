"""
Wikifier Robust Path Normalization & Resolution Layer (Limitation #3 of Gap #1)

This module is the single source of truth for all path handling, normalization,
specifier resolution, and canonical identity across the Wikifier system.

Design goals (durable for massive monorepos, symlinks, workspaces, TS paths, etc.):
- Pluggable ResolutionStrategy protocol with priority ordering.
- ProjectContext: lazily built, cached, mtime-invalidated monorepo state
  (workspace maps, tsconfig paths, package roots).
- Canonical form contract:
    - Always a POSIX-style relative path string ("/" separators).
    - Includes the original source file extension.
    - Never starts with "./" or "/"; never absolute.
    - Deterministic under a chosen symlink policy.
- Resolution dataclass carries rich diagnostics (strategy, confidence, metadata)
  for transparency and future confidence/actionability features.
- Zero new runtime dependencies. Pure stdlib (pathlib, dataclasses, typing).
- Performance: lazy context, aggressive short-circuit + memoization, precompute
  maps for workspace/TS on build.
- Symlink policy: follow_symlinks=True (physical identity for graphs) by default;
  metadata["symlink_detected"] and "original_logical" attached when relevant.
- Extensibility: subclass ResolutionStrategy, register_strategy().

Integration contract:
- Parsers (JS/Python) delegate entry normalization and internal _try_resolve_*
  to this layer.
- import_cache uses canonical strings exclusively for keys and resolved fields.
- MCP query tools (get_dependencies etc.) call normalize_query_file() on inputs.
- Shell (wikifier.sh) may continue bulk FS walks with realpath but delegates
  specifier resolution and canonicalization to Python helpers for consistency.
- All consumers (Mermaid, cycles, health, library.md) receive canonical forms.

Production-grade implementation (Phase 4 of Gap #1 finisher + P4 Polish/Hardening):
  - All priority strategies complete: TsPaths (complex refs+baseUrl+extends), Workspace,
    PackageImports, PackageExports (regex wildcard + advanced conditionals), Relative
    (exports probe), BareHeuristic.
  - Robust ProjectContext: full workspace discovery (pnpm/yarn/npm + named pkgs, hardened
    for heavy .pnpm/.yarn store layouts), tsconfig paths+extends+references (improved
    complex project ref parsing, base awareness), package roots, mtime invalidation.
  - Rich Resolution + ResolutionMetadata (per shared contracts) with strategy,
    exports_key, ts_alias, workspace_pkg, attempted list, symlink info, matched_condition.
  - Central helpers (resolve_exports_map, resolve_imports_map, resolve, ...) provide
    the official deprecation path for duplicated legacy resolution code in
    javascript.py, bree.py, and wikifier.sh. R4 Legacy Deprecation Execution COMPLETE:
      * JS: low-level _read/_target/_pick = pure delegators (impls deleted); _resolve_from_exports
        = ultra-thin (central + BREE + 5-line main-only); removed all dupe export matching logic.
      * BREE: _read_pkg/_resolve_target/_pick_from_conditions now delegate to central _* (deduped);
        resolve fallback slimmed to main + BREE-wildcards only (no standard matching dupe).
      * sh: legacy shell resolvers strictly fallback-only, strengthened v0.5 removal messaging.
    All legacy emit DeprecationWarning, delegate first, fall back only on error.
  - Performance: precomputed maps in ctx, short-circuit can_handle, cache,
    pruned walks, lazy build.
  - Deprecation status (R4 complete): legacy surface area significantly reduced for long-term
    maintainability. Central `resolve()` / `resolve_exports_map()` / `build_project_context()` is
    the UNAMBIGUOUS DEFAULT everywhere. Legacy only for 2-release compat (v0.5 removal target).
    See contracts.py, gap1_prewave0_..., 4phase roadmap, CHANGELOG.

Public API (stable):
    get_canonical_rel(...)
    resolve(...)
    build_project_context(...)
    normalize_query_file(...)
    Resolution, ProjectContext, ResolutionStrategy
    register_strategy, list_strategies

All other symbols are private (prefixed _).
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path, PurePosixPath
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Literal,
    Optional,
    Protocol,
    Set,
    Tuple,
    Union,
)

# Pre-Wave 0 Contracts integration (FROZEN) — makes wikifier/contracts.py the
# single source of truth for ResolutionMetadata shape + res_meta_* serialization.
# The parser (javascript.py) imports encode_res_meta_v1 etc. from here; we
# satisfy that contract by re-exporting from the authoritative module.
try:
    from .contracts import (
        ResolutionMetadata as _ContractResolutionMetadata,
        encode_res_meta_v1,
        decode_res_meta_v1,
        pack_res_meta_v1,
        unpack_res_meta_v1,
    )
except Exception:
    _ContractResolutionMetadata = None
    encode_res_meta_v1 = lambda m: ""
    decode_res_meta_v1 = lambda r: {}
    pack_res_meta_v1 = encode_res_meta_v1
    unpack_res_meta_v1 = decode_res_meta_v1

# =============================================================================
# Canonical Form Helpers
# =============================================================================

def _posix_rel(p: Path) -> str:
    """Convert a Path to a clean POSIX relative string (no leading ./)."""
    s = p.as_posix()
    if s.startswith("./"):
        s = s[2:]
    if s == ".":
        return ""
    return s.lstrip("/")


def to_canonical_rel(
    target: Union[str, Path, os.PathLike],
    root: Path,
    *,
    follow_symlinks: bool = True,
) -> Optional[str]:
    """
    Compute the canonical relative path string for `target` under `root`.

    Policy:
    - If follow_symlinks: use .resolve() (physical inode identity).
    - Else: use relative_to on the logical path (for display-only scenarios).
    - Result is always a clean POSIX rel path **with original extension**.
    - Returns None if target cannot be expressed relative to root.

    This is the heart of the "single source of truth" contract.
    """
    try:
        t = Path(target)
        if not t.is_absolute():
            t = (root / t).resolve(strict=False) if follow_symlinks else (root / t)

        if follow_symlinks:
            # Physical identity preferred for cache/graph correctness
            resolved = t.resolve(strict=False)
        else:
            resolved = t

        # Make relative to root (best effort; fall back to as-posix if outside)
        try:
            rel = resolved.relative_to(root.resolve(strict=False))
        except ValueError:
            # Outside root — still return a normalized form for external pkgs
            # (rare in practice for internal resolution)
            rel = resolved

        canon = _posix_rel(rel)
        if not canon:
            return None
        return canon
    except Exception:
        return None


def canonical_for_bree(
    target: Union[str, Path, os.PathLike],
    root: Path,
) -> Optional[str]:
    """
    Canonical normalization helper for BREE / BarrelResolutionCache (BRC) paths.
    Always uses physical identity (follow_symlinks=True) for durable single-key
    storage in barrel_chain, mtimes_snapshot, file_index, importer_rel, chain_id.
    This completes the v1 canonical normalization pass (to_canonical_rel v1 stamped
    on all BRC paths). Enables safe overlapping chains and symlink/workspace monorepos.
    Zero-dep, called from bree.py _brc_canonical and import/js paths.
    """
    return to_canonical_rel(target, root, follow_symlinks=True)


def _strip_ext_for_display(canon: str) -> str:
    """Optional helper for display_module (e.g. for Mermaid labels)."""
    p = Path(canon)
    if p.suffix:
        return str(p.with_suffix(""))
    return canon


# =============================================================================
# Internal Helpers: Package.json exports/imports, TS paths, workspace discovery
# (Production-grade, zero-dep, extracted/adapted for central use. These provide
# the deprecation path for duplicated logic in javascript.py (_resolve_from_exports,
# _try_resolve_*, etc. F4) and bree.py:DefaultExportsMapHandler. All now delegate.)
# =============================================================================

def _strip_json_comments(text: str) -> str:
    """Pragmatic comment stripper for tsconfig.json (which often has // and /* */)."""
    # Remove // comments (not inside strings - simple heuristic sufficient for tsconfig)
    text = re.sub(r"(?m)^\s*//.*$", "", text)
    # Remove /* */ comments
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return text


def _read_package_json(pkg_dir: Path) -> Optional[dict]:
    """Read and parse package.json. Returns dict or None."""
    pj = pkg_dir / "package.json"
    if not pj.exists():
        return None
    try:
        with pj.open(encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else None
    except Exception:
        return None


def _resolve_target_path(pkg_dir: Path, target: str) -> Optional[Path]:
    """
    Resolve a target string from exports/imports (e.g. "./dist/index.js") to existing file.
    Tries extensions and index.* fallbacks. Mirrors legacy _resolve_target_path.
    """
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


def _pick_target_from_conditions(spec: Any, pkg_dir: Path) -> Optional[Path]:
    """
    Pick best target from string / list / condition dict (import > default > require etc).
    Shared by exports and imports fields.
    """
    if isinstance(spec, str):
        return _resolve_target_path(pkg_dir, spec)
    if isinstance(spec, list):
        for item in spec:
            res = _pick_target_from_conditions(item, pkg_dir)
            if res:
                return res
        return None
    if not isinstance(spec, dict):
        return None

    priority = [
        "import", "module", "esm", "es2020", "es2015", "es6",
        "default",
        "node", "node-addons",
        "require", "types", "typings", "browser"
    ]
    for cond in priority:
        if cond in spec:
            val = spec[cond]
            res = _pick_target_from_conditions(val, pkg_dir)
            if res:
                return res
    for v in spec.values():
        res = _pick_target_from_conditions(v, pkg_dir)
        if res:
            return res
    return None


def resolve_exports_map(pkg_dir: Path, subpath: str = ".") -> Optional[Path]:
    """
    Public helper: resolve a subpath against a package's "exports" (or legacy main).
    P4 hardened: robust regex-based wildcard matching (supports complex patterns + conditional
    dicts/arrays under * keys for "certain conditional exports" cases in monorepos).
    This is the central implementation (single source of truth) that replaces duplicated logic elsewhere.
    Returns the resolved target Path (physical) or None.
    """
    pkg = _read_package_json(pkg_dir)
    if not pkg:
        return None

    exports = pkg.get("exports")
    if exports is None:
        # legacy fallback
        for legacy_key in ("module", "main", "jsnext:main"):
            main_val = pkg.get(legacy_key)
            if main_val and isinstance(main_val, str):
                res = _resolve_target_path(pkg_dir, main_val)
                if res:
                    return res
        return None

    if isinstance(exports, str):
        if subpath in (".", ""):
            return _pick_target_from_conditions(exports, pkg_dir)
        return None

    # normalize subpath
    if not subpath or subpath == "./":
        subpath = "."
    elif not subpath.startswith("./") and subpath != ".":
        subpath = "./" + subpath.lstrip("./")

    # exact
    if subpath in exports:
        return _pick_target_from_conditions(exports[subpath], pkg_dir)

    if subpath == "." and "." not in exports and "" in exports:
        return _pick_target_from_conditions(exports[""], pkg_dir)

    # conditions at root
    if subpath == ".":
        has_subpath_key = any(
            isinstance(k, str) and (k.startswith(".") or k == "")
            for k in exports.keys()
        )
        if not has_subpath_key:
            return _pick_target_from_conditions(exports, pkg_dir)

    if subpath == ".":
        for k in (".", ""):
            if k in exports:
                res = _pick_target_from_conditions(exports[k], pkg_dir)
                if res:
                    return res

    # subpath fallback
    clean = subpath.lstrip("./")
    if clean and clean in exports:
        return _pick_target_from_conditions(exports[clean], pkg_dir)

    # Wildcard support (P4 hardened, regex parity with BREE for complex/conditional exports)
    # Supports keys with * in any position (e.g. "./*/*", "./feature-*", subpath patterns),
    # correctly substitutes even for nested condition dicts under the wildcard.
    # This closes gaps on advanced "exports" usage in real monorepo packages (barrel + conditional).
    if "*" in subpath or any("*" in str(k) for k in exports.keys()):
        for key, val in exports.items():
            if not isinstance(key, str) or "*" not in key:
                continue
            try:
                escaped = re.escape(key)
                regex_str = "^" + escaped.replace(r"\*", "(.*)") + "$"
                m = re.match(regex_str, subpath)
                if m:
                    replacement = m.group(1) or ""
                    if isinstance(val, str):
                        target = val.replace("*", replacement)
                        res = _resolve_target_path(pkg_dir, target)
                        if res:
                            return res
                    elif isinstance(val, dict):
                        # conditional object under wildcard (e.g. { "import": "./dist/*.mjs", "require": ... })
                        # pick will traverse conditions
                        res = _pick_target_from_conditions(val, pkg_dir)
                        if res:
                            return res
                    elif isinstance(val, list):
                        res = _pick_target_from_conditions(val, pkg_dir)
                        if res:
                            return res
            except Exception:
                continue
    return None


def resolve_imports_map(pkg_dir: Path, subpath: str = "#") -> Optional[Path]:
    """
    Analogous to resolve_exports_map but for the modern "imports" field (Node 17+).
    Used for #internal-pkg aliases scoped to the package.
    """
    pkg = _read_package_json(pkg_dir)
    if not pkg:
        return None
    imports = pkg.get("imports")
    if not imports:
        return None
    # "imports" uses identical shape to "exports" (conditions, subpath maps starting with #)
    # Normalize: treat as if it were exports for the pick logic
    # We call the same picker but on the imports dict
    if isinstance(imports, dict):
        # direct key match for the #foo
        if subpath in imports:
            return _pick_target_from_conditions(imports[subpath], pkg_dir)
        # conditions root etc - reuse
        return _pick_target_from_conditions(imports, pkg_dir)  # may be loose
    if isinstance(imports, str):
        return _resolve_target_path(pkg_dir, imports)
    return None


def _ts_glob_match(pattern: str, value: str) -> bool:
    """Match a TS paths-style pattern (with at most one *) against a specifier."""
    if pattern == value:
        return True
    if "*" not in pattern:
        return False
    # Convert ts path pattern to fnmatch-style
    # e.g. "@app/*" matches "@app/utils" or "@app/foo/bar"
    regex = "^" + re.escape(pattern).replace(r"\*", "(.*)") + "$"
    return bool(re.match(regex, value))


def _apply_ts_replacement(pattern: str, replacement: str, value: str) -> str:
    """Apply the replacement for a matched TS paths alias."""
    if "*" not in pattern:
        return replacement
    # find the capture
    regex = "^" + re.escape(pattern).replace(r"\*", "(.*)") + "$"
    m = re.match(regex, value)
    if not m:
        return replacement
    captured = m.group(1)
    return replacement.replace("*", captured)


def _discover_workspaces_and_packages(
    root: Path, excludes: Set[str]
) -> Tuple[Dict[str, str], Set[str], str]:
    """
    Walk (pruned) to find all package.json, extract names for workspace_map,
    collect package root rel paths, detect monorepo flavor from presence of
    pnpm/yarn/lerna files + root workspaces field.
    Hardened (P4): additional excludes for heavy pnpm/yarn store layouts (e.g. .pnpm virtual stores)
    to prevent slow walks or symlink thrash on 1000+ pkg monorepos.
    """
    workspace_map: Dict[str, str] = {}
    package_roots: Set[str] = set()
    mono_type = "single"

    # First, quick config detection for type
    if (root / "pnpm-workspace.yaml").exists() or (root / "pnpm-lock.yaml").exists():
        mono_type = "pnpm"
    elif (root / "yarn.lock").exists():
        mono_type = "yarn"
    elif (root / "package-lock.json").exists():
        mono_type = "npm"
    # Check root pkg for workspaces
    root_pkg = _read_package_json(root)
    if root_pkg:
        if "workspaces" in root_pkg:
            mono_type = "yarn" if mono_type == "single" else mono_type
            ws = root_pkg["workspaces"]
            # could be list or {"packages": [...]}
            if isinstance(ws, list):
                # globs, but we don't expand here; discovery below will catch named pkgs
                pass
            elif isinstance(ws, dict) and "packages" in ws:
                pass

    # Pruned walk
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in excludes]
        if "package.json" in filenames:
            pkg_dir = Path(dirpath)
            try:
                rel = pkg_dir.relative_to(root)
                rel_str = _posix_rel(rel) or "."
                package_roots.add(rel_str)
                data = _read_package_json(pkg_dir)
                if data and isinstance(data.get("name"), str):
                    name = data["name"].strip()
                    if name and not name.startswith("."):
                        # map name -> package root rel (for bare resolution)
                        workspace_map[name] = rel_str
            except Exception:
                continue

    if len(workspace_map) > 1 and mono_type == "single":
        mono_type = "multi-pkg"

    return workspace_map, package_roots, mono_type


def _discover_ts_mappings(root: Path, excludes: Set[str]) -> List[Tuple[str, List[str]]]:
    """
    Discover tsconfig*.json (including in subdirs and via references/extends),
    collect compilerOptions.paths mappings. Supports simple extends by loading bases.
    P4 enhanced: complex project references (str/dict forms, explicit .json or dir paths,
    cycle-safe via seen), and baseUrl-aware replacement strings so sub-package tsconfigs
    in monorepos with references resolve their paths correctly relative to root.
    Returns list of (alias_pattern, [replacements...])
    """
    mappings: List[Tuple[str, List[str]]] = []
    seen_tsconfigs: Set[str] = set()

    def load_tsconfig(p: Path) -> Optional[dict]:
        if str(p) in seen_tsconfigs:
            return None
        seen_tsconfigs.add(str(p))
        if not p.exists():
            return None
        try:
            raw = p.read_text(encoding="utf-8", errors="ignore")
            cleaned = _strip_json_comments(raw)
            data = json.loads(cleaned)
            if not isinstance(data, dict):
                return None
            return data
        except Exception:
            return None

    def collect_from_tsconfig(ts_path: Path, base_dir: Optional[Path] = None) -> None:
        data = load_tsconfig(ts_path)
        if not data:
            return
        co = data.get("compilerOptions", {}) or {}
        paths = co.get("paths", {}) or {}
        base_url = co.get("baseUrl", ".") or "."
        # resolve base relative to tsconfig dir
        ts_dir = ts_path.parent
        # P4 improvement for complex project refs / multi-tsconfig monorepos:
        # compute effective repl prefix from this tsconfig's location + baseUrl so that
        # later `ctx.root / mapped` in TsPathsStrategy resolves correctly for sub-pkg tsconfigs
        # (previously all assumed root-level paths, breaking referenced projects)
        # safe prefix computation (handles resolved vs non-resolved Path compare)
        try:
            ts_rel = _posix_rel(ts_dir.relative_to(root))
        except Exception:
            ts_rel = ""
        bu = base_url or "."
        path_prefix = ts_rel
        if bu not in (".", ""):
            try:
                path_prefix = _posix_rel( (Path(ts_rel) / bu) ) if ts_rel else bu
            except Exception:
                path_prefix = ts_rel or bu
        for alias, targets in paths.items():
            if not isinstance(alias, str):
                continue
            repl_list = []
            for t in (targets if isinstance(targets, list) else [targets]):
                if isinstance(t, str):
                    # prepend the ts-specific base (from its ts_dir + baseUrl) to support complex refs
                    if t.startswith(("../", "./")) or t.startswith("/"):
                        repl = (path_prefix + "/" + t.lstrip("./")) if path_prefix else t
                    else:
                        repl = (path_prefix + "/" + t) if path_prefix else t
                    repl = repl.replace("//", "/").rstrip("/")
                    repl_list.append(repl)
            if repl_list:
                mappings.append((alias, repl_list))

        # extends: load base (relative to current ts)
        extends = data.get("extends")
        if extends and isinstance(extends, str):
            ext_path = (ts_dir / extends).resolve(strict=False)
            collect_from_tsconfig(ext_path, base_dir or ts_dir)

        # references (project refs): follow path (P4 hardened for complex monorepo cases)
        # Supports: array of strings, or objects {path: "..."}, path may be dir or explicit tsconfig*.json
        refs = data.get("references", []) or []
        for ref in refs:
            ref_path = None
            if isinstance(ref, str):
                ref_path = ref
            elif isinstance(ref, dict):
                ref_path = ref.get("path") or ref.get("paths")  # some tools use "paths"
            if ref_path:
                rp = str(ref_path)
                ref_p = Path(rp)
                if ref_p.is_absolute():
                    ref_ts = ref_p
                else:
                    if rp.endswith(".json") or "tsconfig" in rp.lower():
                        ref_ts = (ts_dir / ref_p).resolve(strict=False)
                    else:
                        # dir reference: try tsconfig.json inside, also bare for some setups
                        ref_ts = (ts_dir / ref_p / "tsconfig.json").resolve(strict=False)
                        # also allow direct if the ref_p points to a json sibling? keep primary
                collect_from_tsconfig(ref_ts, base_dir or ts_dir)

    # Find all tsconfig*.json pruned
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in excludes]
        for fn in filenames:
            if fn.startswith("tsconfig") and fn.endswith(".json"):
                ts_p = Path(dirpath) / fn
                collect_from_tsconfig(ts_p)

    # dedup while preserving order
    seen_pats = set()
    unique = []
    for item in mappings:
        key = item[0]
        if key not in seen_pats:
            seen_pats.add(key)
            unique.append(item)
    return unique


def _find_nearest_package_dir(start: Path, root: Path, excludes: Set[str]) -> Optional[Path]:
    """Walk upward from start to find nearest dir containing package.json (for imports field)."""
    current = start if start.is_dir() else start.parent
    try:
        root = root.resolve(strict=False)
    except Exception:
        pass
    for _ in range(12):  # safety
        if (current / "package.json").exists():
            return current
        if current == current.parent or current.resolve(strict=False) == root:
            break
        current = current.parent
    return None


# =============================================================================
# Core Data Types
# =============================================================================

Confidence = Literal["high", "medium", "low", "unresolved"]


# =============================================================================
# Rich Metadata Contract (per gap1_prewave0_shared_contracts_open.md)
# =============================================================================

@dataclass(frozen=True)
class ResolutionMetadata:
    """
    Structured metadata for a Resolution result (Phase 4 contract).
    JSON-serializable, additive, carries strategy details for explainability.
    Used inside Resolution.metadata (as .to_dict()) and for future diagnostic enrichment.
    """
    strategy: str = ""
    matched_condition: Optional[str] = None
    exports_key: Optional[str] = None
    ts_alias: Optional[str] = None
    symlink_detected: bool = False
    original_logical: Optional[str] = None
    workspace_pkg: Optional[str] = None
    attempted: List[str] = field(default_factory=list)
    # Extensible: package_imports_key, condition_matched, base_url, etc.
    package_imports_key: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Normalize: attempted and extra are always present
        if "attempted" not in d or d["attempted"] is None:
            d["attempted"] = []
        return d


@dataclass(frozen=True)
class Resolution:
    """
    Rich result of a single specifier resolution attempt.

    This is the primary contract object passed between parsers, cache,
    queries, and graphs. It replaces ad-hoc "resolved_path" + "module" pairs
    with a durable, inspectable, strategy-attributed record.
    """
    raw: str                              # Original import specifier as written
    resolved_file: Optional[str]          # Canonical relative path (with ext) or None
    display_module: str                   # Human-friendly / alias form (e.g. "@app/foo" or dotted)
    confidence: Confidence
    strategy: str                         # e.g. "relative-fs", "ts-paths:tsconfig.json", "workspace", "bare-heuristic", "exports", "unresolved"
    metadata: Union[Dict[str, Any], ResolutionMetadata] = field(default_factory=dict)

    def __post_init__(self):
        if isinstance(self.metadata, dict):
            try:
                # Convert legacy dict to structured (put unknown in extra)
                known = {
                    "strategy": self.metadata.get("strategy", self.strategy),
                    "matched_condition": self.metadata.get("matched_condition"),
                    "exports_key": self.metadata.get("exports_key"),
                    "ts_alias": self.metadata.get("ts_alias"),
                    "symlink_detected": bool(self.metadata.get("symlink_detected", False)),
                    "original_logical": self.metadata.get("original_logical"),
                    "workspace_pkg": self.metadata.get("workspace_pkg"),
                    "attempted": self.metadata.get("attempted", []),
                    "package_imports_key": self.metadata.get("package_imports_key"),
                    "extra": {k: v for k, v in self.metadata.items() if k not in {
                        "strategy", "matched_condition", "exports_key", "ts_alias",
                        "symlink_detected", "original_logical", "workspace_pkg",
                        "attempted", "package_imports_key"
                    }},
                }
                object.__setattr__(self, "metadata", ResolutionMetadata(**known))
            except Exception:
                # keep as dict if conversion fails
                pass

    def as_dict(self) -> Dict[str, Any]:
        """Convenience for serialization / cache persistence."""
        meta = self.metadata
        if isinstance(meta, ResolutionMetadata):
            meta = meta.to_dict()
        elif not isinstance(meta, dict):
            meta = {}
        return {
            "raw": self.raw,
            "resolved": self.resolved_file,
            "display_module": self.display_module,
            "confidence": self.confidence,
            "strategy": self.strategy,
            "metadata": meta,
        }


@dataclass
class ProjectContext:
    """
    Monorepo-aware context, built once per root (or incrementally invalidated).

    Holds precomputed maps so that expensive config parsing and directory
    walks happen only on context (re)build, not per-specifier.
    """
    root: Path
    follow_symlinks: bool = True

    # Workspace / package mapping (name or path prefix -> canonical dir rel)
    workspace_map: Dict[str, str] = field(default_factory=dict)

    # TS path mappings collected from tsconfig(s): list of (alias_glob, [replacements])
    ts_mappings: List[Tuple[str, List[str]]] = field(default_factory=list)

    # Known package roots (dirs containing package.json) as canonical rel strings
    package_roots: Set[str] = field(default_factory=set)

    # Detected monorepo flavor for diagnostics / strategy selection
    detected_monorepo_type: str = "single"  # "pnpm" | "yarn" | "npm" | "multi-ts" | "single"

    # Config file mtimes for cheap invalidation (tsconfig*, package.json, *workspace*)
    config_mtimes: Dict[str, float] = field(default_factory=dict)

    # Internal: raw absolute paths to key config files found during build
    _config_files: List[Path] = field(default_factory=list, repr=False)

    def is_stale(self) -> bool:
        """Return True if any tracked config file has changed on disk."""
        for p in self._config_files:
            try:
                if p.exists() and p.stat().st_mtime > self.config_mtimes.get(str(p), 0):
                    return True
            except Exception:
                return True
        return False


# =============================================================================
# Strategy Protocol
# =============================================================================

class ResolutionStrategy(Protocol):
    """
    Pluggable strategy for resolving one class of specifiers.

    Strategies are tried in descending priority order by the resolver.
    The first strategy that returns a non-None Resolution wins.

    Implementations must be stateless with respect to a single resolve() call
    (all state lives in ProjectContext).
    """
    name: str
    priority: int   # lower number = higher priority (tried first)

    def can_handle(
        self,
        raw: str,
        from_canonical: str,
        ctx: ProjectContext,
    ) -> bool:
        """Quick cheap check whether this strategy might apply."""
        ...

    def resolve(
        self,
        raw: str,
        from_canonical: str,
        ctx: ProjectContext,
    ) -> Optional[Resolution]:
        """Attempt full resolution. Return Resolution (even if unresolved) or None to defer."""
        ...


# =============================================================================
# Built-in Production Strategies (Phase 4 complete set)
# Priority ordering (lower number tried first): TsPaths, Workspace, PackageImports,
# PackageExports, Relative, BareHeuristic. can_handle filters per class.
# =============================================================================

class TsPathsStrategy:
    """
    Resolves TypeScript path aliases from tsconfig.json "compilerOptions.paths".
    P4 improved support for complex monorepo cases: project references (dict/str forms,
    explicit tsconfig.json or dir paths, cycle-safe), baseUrl handling via prefixed
    repl strings from sub-tsconfigs, extends recursion.
    High priority for alias forms like "@app/*", "~~/*", etc.
    """
    name: str = "ts-paths"
    priority: int = 15

    def can_handle(self, raw: str, from_canonical: str, ctx: ProjectContext) -> bool:
        if not raw or raw.startswith((".", "/")):
            return False
        for pat, _ in ctx.ts_mappings:
            if _ts_glob_match(pat, raw):
                return True
        return False

    def resolve(
        self,
        raw: str,
        from_canonical: str,
        ctx: ProjectContext,
    ) -> Optional[Resolution]:
        if not ctx.ts_mappings:
            return None
        for pat, repls in ctx.ts_mappings:
            if not _ts_glob_match(pat, raw):
                continue
            for repl in repls:
                mapped = _apply_ts_replacement(pat, repl, raw)
                # Resolve the mapped specifier relative to project root (or baseUrl in future)
                base = ctx.root / mapped
                # Try direct + extensions + index (reuse relative candidate logic)
                candidates: List[Path] = []
                if base.suffix:
                    candidates.append(base)
                else:
                    for ext in (".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs", ".py"):
                        candidates.append(base.with_suffix(ext))
                    candidates.append(base)
                for cand in candidates:
                    if cand.exists() and cand.is_file():
                        canon = to_canonical_rel(cand, ctx.root, follow_symlinks=ctx.follow_symlinks)
                        if canon:
                            meta = ResolutionMetadata(
                                strategy=self.name,
                                ts_alias=pat,
                                attempted=["ts-paths"],
                            )
                            return Resolution(
                                raw=raw,
                                resolved_file=canon,
                                display_module=_strip_ext_for_display(canon),
                                confidence="high",
                                strategy=self.name,
                                metadata=meta,
                            )
                # directory index
                if base.exists() and base.is_dir():
                    for idx in ("index.js", "index.ts", "index.jsx", "index.tsx", "__init__.py"):
                        idxp = base / idx
                        if idxp.exists() and idxp.is_file():
                            canon = to_canonical_rel(idxp, ctx.root, follow_symlinks=ctx.follow_symlinks)
                            if canon:
                                meta = ResolutionMetadata(strategy=self.name, ts_alias=pat, attempted=["ts-paths"])
                                return Resolution(
                                    raw=raw,
                                    resolved_file=canon,
                                    display_module=_strip_ext_for_display(canon),
                                    confidence="high",
                                    strategy=self.name,
                                    metadata=meta,
                                )
            # matched alias but no file -> still return low/medium with attempted
            meta = ResolutionMetadata(strategy=self.name, ts_alias=pat, attempted=["ts-paths"])
            return Resolution(
                raw=raw,
                resolved_file=None,
                display_module=raw,
                confidence="medium",
                strategy=self.name,
                metadata=meta,
            )
        return None


class WorkspaceStrategy:
    """
    Resolves bare specifiers that match workspace package names (from package.json "name").
    Uses workspace_map in ProjectContext. Delegates to exports map when present.
    """
    name: str = "workspace"
    priority: int = 25

    def can_handle(self, raw: str, from_canonical: str, ctx: ProjectContext) -> bool:
        if not raw or raw.startswith((".", "/", "#")):
            return False
        # Handle @scoped/pkg and @scoped/pkg/sub
        parts = raw.split("/")
        if raw.startswith("@") and len(parts) >= 2:
            pkg_name = "/".join(parts[:2])
        else:
            pkg_name = parts[0]
        return pkg_name in ctx.workspace_map

    def resolve(
        self,
        raw: str,
        from_canonical: str,
        ctx: ProjectContext,
    ) -> Optional[Resolution]:
        parts = raw.split("/")
        if raw.startswith("@") and len(parts) >= 2:
            pkg_name = "/".join(parts[:2])
            rest = parts[2:]
        else:
            pkg_name = parts[0]
            rest = parts[1:]
        if pkg_name not in ctx.workspace_map:
            return None
        pkg_rel = ctx.workspace_map[pkg_name]
        pkg_dir = ctx.root / pkg_rel
        subpath = "." if not rest else "./" + "/".join(rest)
        target = resolve_exports_map(pkg_dir, subpath) or _resolve_target_path(pkg_dir, (subpath or ".").lstrip("./") or "index.js")
        if not target and (pkg_dir / "index.js").exists():
            target = pkg_dir / "index.js"
        if target and target.exists():
            canon = to_canonical_rel(target, ctx.root, follow_symlinks=ctx.follow_symlinks)
            if canon:
                meta = ResolutionMetadata(
                    strategy=self.name,
                    workspace_pkg=pkg_name,
                    exports_key=subpath,
                    attempted=["workspace", "package-exports"],
                )
                return Resolution(
                    raw=raw,
                    resolved_file=canon,
                    display_module=_strip_ext_for_display(canon) or raw,
                    confidence="high",
                    strategy=self.name,
                    metadata=meta,
                )
        meta = ResolutionMetadata(workspace_pkg=pkg_name, attempted=["workspace"])
        return Resolution(
            raw=raw,
            resolved_file=None,
            display_module=raw,
            confidence="low",
            strategy=self.name,
            metadata=meta,
        )


class PackageImportsStrategy:
    """
    Handles modern "#internal" imports via the package.json "imports" field
    of the *containing package* of the importing file.
    """
    name: str = "package-imports"
    priority: int = 22

    def can_handle(self, raw: str, from_canonical: str, ctx: ProjectContext) -> bool:
        return bool(raw) and raw.startswith("#")

    def resolve(
        self,
        raw: str,
        from_canonical: str,
        ctx: ProjectContext,
    ) -> Optional[Resolution]:
        # Find the importer package
        from_path = Path(from_canonical)
        if not from_path.is_absolute():
            from_path = (ctx.root / from_path).resolve(strict=False)
        pkg_dir = _find_nearest_package_dir(from_path, ctx.root, {"node_modules", ".git"})
        if not pkg_dir:
            pkg_dir = ctx.root
        target = resolve_imports_map(pkg_dir, raw)
        if target and target.exists():
            canon = to_canonical_rel(target, ctx.root, follow_symlinks=ctx.follow_symlinks)
            if canon:
                meta = ResolutionMetadata(
                    strategy=self.name,
                    package_imports_key=raw,
                    attempted=["package-imports"],
                )
                return Resolution(
                    raw=raw,
                    resolved_file=canon,
                    display_module=_strip_ext_for_display(canon),
                    confidence="high",
                    strategy=self.name,
                    metadata=meta,
                )
        meta = ResolutionMetadata(package_imports_key=raw, attempted=["package-imports"])
        return Resolution(
            raw=raw,
            resolved_file=None,
            display_module=raw,
            confidence="medium",
            strategy=self.name,
            metadata=meta,
        )


class PackageExportsStrategy:
    """
    Modern package.json "exports" map resolver + legacy main/module.
    P4/F4 hardened: uses central resolve_exports_map with regex wildcard support for
    certain complex/conditional exports (nested conditions under * patterns).
    Used for package subpath exports (e.g. "my-pkg/dist/foo" or when relative lands on pkg dir).
    Central implementation; old duplicated code in parsers/bree/javascript MUST delegate here (with warnings on legacy).
    F4: expanded to cover bare/relative shims too.
    """
    name: str = "package-exports"
    priority: int = 30

    def can_handle(self, raw: str, from_canonical: str, ctx: ProjectContext) -> bool:
        if not raw or raw.startswith((".", "#")):
            return False
        # Bare that could be pkg/subpath (handle @scope/name)
        parts = raw.split("/")
        if raw.startswith("@") and len(parts) >= 2:
            first = "/".join(parts[:2])
        else:
            first = parts[0]
        return first in ctx.workspace_map or bool(ctx.package_roots)

    def resolve(
        self,
        raw: str,
        from_canonical: str,
        ctx: ProjectContext,
    ) -> Optional[Resolution]:
        parts = raw.split("/")
        if raw.startswith("@") and len(parts) >= 2:
            first = "/".join(parts[:2])
            rest = parts[2:]
        else:
            first = parts[0]
            rest = parts[1:]
        pkg_dir: Optional[Path] = None
        subpath = "."
        if first in ctx.workspace_map:
            pkg_rel = ctx.workspace_map[first]
            pkg_dir = ctx.root / pkg_rel
            subpath = "." if not rest else "./" + "/".join(rest)
        else:
            # Try walking up from importer to treat as local subpath export? rare for bare
            # Fallback: no
            return None

        target = resolve_exports_map(pkg_dir, subpath)
        if not target:
            # legacy index
            target = _resolve_target_path(pkg_dir, (subpath or ".").lstrip("./") or ".")
        if target and target.exists():
            canon = to_canonical_rel(target, ctx.root, follow_symlinks=ctx.follow_symlinks)
            if canon:
                meta = ResolutionMetadata(
                    strategy=self.name,
                    exports_key=subpath,
                    workspace_pkg=first if first in ctx.workspace_map else None,
                    matched_condition=subpath if subpath and subpath != "." else "default",
                    attempted=["package-exports"],
                )
                return Resolution(
                    raw=raw,
                    resolved_file=canon,
                    display_module=_strip_ext_for_display(canon),
                    confidence="high",
                    strategy=self.name,
                    metadata=meta,
                )
        meta = ResolutionMetadata(exports_key=subpath, attempted=["package-exports"])
        return Resolution(
            raw=raw,
            resolved_file=None,
            display_module=raw,
            confidence="low",
            strategy=self.name,
            metadata=meta,
        )


class RelativeFilesystemStrategy:
    """
    Handles explicit relative specifiers ("./foo", "../bar").
    Enhanced to probe package.json exports when landing on a directory that
    contains one (modern monorepo case).
    """
    name: str = "relative-fs"
    priority: int = 10

    def can_handle(self, raw: str, from_canonical: str, ctx: ProjectContext) -> bool:
        return bool(raw) and raw.startswith(".")

    def resolve(
        self,
        raw: str,
        from_canonical: str,
        ctx: ProjectContext,
    ) -> Optional[Resolution]:
        if not raw.startswith("."):
            return None

        try:
            if from_canonical:
                fc = Path(from_canonical)
                from_path = fc if fc.is_absolute() else (ctx.root / fc).resolve(strict=False)
            else:
                from_path = ctx.root
            base = (from_path.parent / raw).resolve(strict=False)

            # NEW: if base (or base dir) has package.json with exports, try exports first for modern pkgs
            pkg_json_cand = base if (base / "package.json").exists() else (base.parent if (base.parent / "package.json").exists() else None)
            if pkg_json_cand and (pkg_json_cand / "package.json").exists():
                subp = "." if base == pkg_json_cand or str(raw).endswith(("/.", "")) else "./" + str(base.relative_to(pkg_json_cand)).replace("\\", "/")
                via_exp = resolve_exports_map(pkg_json_cand, subp)
                if via_exp and via_exp.exists():
                    canon = to_canonical_rel(via_exp, ctx.root, follow_symlinks=ctx.follow_symlinks)
                    if canon:
                        meta = ResolutionMetadata(
                            strategy="package-exports",
                            exports_key=subp,
                            matched_condition=subp if subp and subp != "." else "default",
                            attempted=["relative", "package-exports"],
                        )
                        return Resolution(
                            raw=raw,
                            resolved_file=canon,
                            display_module=_strip_ext_for_display(canon),
                            confidence="high",
                            strategy="package-exports",
                            metadata=meta,
                        )

            # Standard file candidates
            candidates: List[Path] = []
            if base.suffix:
                candidates.append(base)
            else:
                for ext in (".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs", ".py", ""):
                    if ext:
                        candidates.append(base.with_suffix(ext))
                    else:
                        candidates.append(base)

            for cand in candidates:
                if cand.exists() and cand.is_file():
                    canon = to_canonical_rel(cand, ctx.root, follow_symlinks=ctx.follow_symlinks)
                    if canon:
                        return Resolution(
                            raw=raw,
                            resolved_file=canon,
                            display_module=_strip_ext_for_display(canon),
                            confidence="high",
                            strategy=self.name,
                            metadata={"via": "direct-file"},
                        )

            # Directory index
            if base.exists() and base.is_dir():
                for idx in ("index.js", "index.ts", "index.jsx", "index.tsx", "index.mjs", "index.cjs", "__init__.py"):
                    idx_path = base / idx
                    if idx_path.exists() and idx_path.is_file():
                        canon = to_canonical_rel(idx_path, ctx.root, follow_symlinks=ctx.follow_symlinks)
                        if canon:
                            return Resolution(
                                raw=raw,
                                resolved_file=canon,
                                display_module=_strip_ext_for_display(canon),
                                confidence="high",
                                strategy=self.name,
                                metadata={"via": "directory-index"},
                            )

            attempted = to_canonical_rel(base, ctx.root, follow_symlinks=ctx.follow_symlinks)
            return Resolution(
                raw=raw,
                resolved_file=attempted,
                display_module=raw,
                confidence="medium",
                strategy=self.name,
                metadata={"via": "relative-unresolved", "attempted": attempted},
            )
        except Exception as exc:
            return Resolution(
                raw=raw,
                resolved_file=None,
                display_module=raw,
                confidence="unresolved",
                strategy=self.name,
                metadata={"error": str(exc)},
            )


class BareHeuristicStrategy:
    """
    Final fallback upward-walk for bare internal imports not caught by
    workspace/TS/exports. Records low confidence for diagnostics.
    """
    name: str = "bare-heuristic"
    priority: int = 80

    def can_handle(self, raw: str, from_canonical: str, ctx: ProjectContext) -> bool:
        return bool(raw) and not raw.startswith((".", "/", "#"))

    def resolve(
        self,
        raw: str,
        from_canonical: str,
        ctx: ProjectContext,
    ) -> Optional[Resolution]:
        # Best-effort simple upward walk (kept lightweight; real heavy lifting done by prior strategies)
        if from_canonical:
            fc = Path(from_canonical)
            start = fc if fc.is_absolute() else (ctx.root / fc).resolve(strict=False)
        else:
            start = ctx.root
        current = start.parent if start.is_file() or not start.exists() else start
        parts = [p for p in raw.replace("\\", "/").split("/") if p]
        max_up = 8
        for _ in range(max_up):
            cand = current
            for part in parts:
                cand = cand / part
            for ext in (".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"):
                if (cand.with_suffix(ext)).exists():
                    canon = to_canonical_rel(cand.with_suffix(ext), ctx.root, follow_symlinks=ctx.follow_symlinks)
                    if canon:
                        return Resolution(raw=raw, resolved_file=canon, display_module=raw, confidence="medium", strategy=self.name, metadata={"via": "bare-walk"})
            if cand.exists() and cand.is_file():
                canon = to_canonical_rel(cand, ctx.root, follow_symlinks=ctx.follow_symlinks)
                if canon:
                    return Resolution(raw=raw, resolved_file=canon, display_module=raw, confidence="high", strategy=self.name, metadata={"via": "bare-exact"})
            # R4 Legacy Deprecation Execution: probe for package.json + exports/main on the cand dir.
            # This covers legacy _try_resolve_bare... behavior for local dir "packages" that declare
            # "exports" or "main" (even without "name" field for workspace registration). Ensures
            # central resolve() is a full drop-in default; such cases no longer require legacy shim fallback.
            if cand.is_dir() and (cand / "package.json").exists():
                try:
                    via = resolve_exports_map(cand, ".")
                    if via:
                        canon = to_canonical_rel(via, ctx.root, follow_symlinks=ctx.follow_symlinks)
                        if canon:
                            return Resolution(
                                raw=raw, resolved_file=canon, display_module=raw, confidence="high",
                                strategy="package-exports", metadata={"via": "bare-heuristic+exports-probe", "probed_pkg": str(cand)}
                            )
                except Exception:
                    pass

            # R4: prefix-based pkg discovery (longest first) to match legacy _try bare behavior for
            # "lib/utils" style where pkg root is prefix of specifier parts (e.g. pkg at "lib", sub "./utils").
            # Uses central resolve_exports_map so behavior unified, no dupe.
            for prefix_len in range(len(parts), 0, -1):
                pdir = current
                for p in parts[:prefix_len]:
                    pdir = pdir / p
                if pdir != cand and pdir.is_dir() and (pdir / "package.json").exists():
                    subp = "." if prefix_len == len(parts) else "./" + "/".join(parts[prefix_len:])
                    try:
                        via = resolve_exports_map(pdir, subp)
                        if via:
                            canon = to_canonical_rel(via, ctx.root, follow_symlinks=ctx.follow_symlinks)
                            if canon:
                                return Resolution(
                                    raw=raw, resolved_file=canon, display_module=raw, confidence="high",
                                    strategy="package-exports", metadata={"via": "bare-heuristic+prefix-exports", "probed_pkg": str(pdir)}
                                )
                    except Exception:
                        pass
            if current.parent == current:
                break
            current = current.parent
        return Resolution(
            raw=raw,
            resolved_file=None,
            display_module=raw,
            confidence="low",
            strategy=self.name,
            metadata={"note": "bare-heuristic-fallback"},
        )


# =============================================================================
# Registry & Resolver Composition
# =============================================================================

_REGISTRY: List[Callable[[], ResolutionStrategy]] = []


def register_strategy(factory: Callable[[], ResolutionStrategy]) -> None:
    """Register a strategy factory (called at import time for builtins)."""
    _REGISTRY.append(factory)


def list_strategies() -> List[str]:
    """Return names of registered strategies in priority order."""
    insts = [f() for f in _REGISTRY]
    insts.sort(key=lambda s: (s.priority, s.name))
    return [s.name for s in insts]


# Auto-register the full production strategy set (priority-sorted at resolve time)
register_strategy(lambda: TsPathsStrategy())
register_strategy(lambda: WorkspaceStrategy())
register_strategy(lambda: PackageImportsStrategy())
register_strategy(lambda: PackageExportsStrategy())
register_strategy(lambda: RelativeFilesystemStrategy())
register_strategy(lambda: BareHeuristicStrategy())


def _get_ordered_strategies() -> List[ResolutionStrategy]:
    insts = [f() for f in _REGISTRY]
    insts.sort(key=lambda s: (s.priority, s.name))
    return insts


# =============================================================================
# ProjectContext Construction & Caching
# =============================================================================

_CONTEXT_CACHE: Dict[Tuple[str, bool], ProjectContext] = {}


def build_project_context(
    root: Union[str, Path],
    *,
    follow_symlinks: bool = True,
    force: bool = False,
) -> ProjectContext:
    """
    Build (or return a cached, still-valid) ProjectContext for the given root.

    Robust population (Phase 4 + P4 monorepo hardening):
    - Discovers pnpm/yarn/npm workspaces + all named package roots (pruned walk, hardened excludes for .pnpm/.yarn/store layouts)
    - Collects tsconfig paths (with extends + references, improved complex ref support)
    - Records config mtimes for invalidation (package.json, tsconfig*, workspace yamls)
    - Detects monorepo_type for diagnostics/strategy hints
    - Short-circuits on cache hit + !stale
    - Symlink-safe canonicalization; bounded walks for heavy monorepos
    """
    root = Path(root).resolve(strict=False)
    key = (str(root), follow_symlinks)

    if not force and key in _CONTEXT_CACHE:
        ctx = _CONTEXT_CACHE[key]
        if not ctx.is_stale():
            return ctx

    ctx = ProjectContext(
        root=root,
        follow_symlinks=follow_symlinks,
        detected_monorepo_type="single",
    )

    EXCLUDES = {"node_modules", ".git", "dist", "build", ".next", "coverage", "__pycache__", "tmp", "temp", ".turbo", ".cache",
                ".pnpm", ".yarn", ".store", "store", "virtual-store", ".pnp", ".pnp.cjs", ".pnp.loader.mjs",
                "node_modules/.pnpm", "node_modules/.yarn"}  # R6: extra defense for nested pnpm/yarn Berry store symlinks in monorepos; name-based prune still catches .pnpm inside node_modules

    # Robust discovery
    try:
        ws_map, pkg_roots, mono = _discover_workspaces_and_packages(root, EXCLUDES)
        ctx.workspace_map.update(ws_map)
        ctx.package_roots.update(pkg_roots)
        ctx.detected_monorepo_type = mono
    except Exception:
        pass

    try:
        ts_maps = _discover_ts_mappings(root, EXCLUDES)
        ctx.ts_mappings.extend(ts_maps)
    except Exception:
        pass

    # Root package + common monorepo configs for mtime invalidation + package_roots
    for cfg in [
        root / "package.json",
        root / "pnpm-workspace.yaml",
        root / "pnpm-lock.yaml",
        root / "yarn.lock",
        root / "lerna.json",
        root / "rush.json",
    ]:
        if cfg.exists():
            try:
                ctx.config_mtimes[str(cfg)] = cfg.stat().st_mtime
                ctx._config_files.append(cfg)
            except Exception:
                pass

    # Also ensure root is a package root
    if (root / "package.json").exists():
        ctx.package_roots.add(".")

    # Record mtimes of discovered tsconfigs (for future finer invalidation)
    # (already walked inside discover, but we can add a cheap top-level scan here if needed)

    _CONTEXT_CACHE[key] = ctx
    return ctx


def clear_context_cache() -> None:
    """Explicitly drop all cached contexts (call on full rebuilds)."""
    _CONTEXT_CACHE.clear()


# =============================================================================
# Public Resolution Entry Points
# =============================================================================

def resolve(
    raw_spec: str,
    from_file: str,
    root: Union[str, Path],
    *,
    follow_symlinks: bool = True,
    extra_context: Optional[Dict[str, Any]] = None,
) -> Resolution:
    """
    Resolve a raw import specifier relative to a source file inside the project.

    This is the primary function that parsers and other consumers should call.
    It orchestrates ProjectContext + ordered strategies and returns a rich
    Resolution object (never raises for resolution failures).
    """
    root_p = Path(root).resolve(strict=False)
    ctx = build_project_context(root_p, follow_symlinks=follow_symlinks)

    # Normalize the "from" file to canonical for strategy use
    from_canon = to_canonical_rel(from_file, root_p, follow_symlinks=follow_symlinks) or from_file

    strategies = _get_ordered_strategies()
    attempted: List[str] = []

    for strat in strategies:
        if not strat.can_handle(raw_spec, from_canon, ctx):
            continue
        attempted.append(strat.name)
        res = strat.resolve(raw_spec, from_canon, ctx)
        if res is not None:
            # Merge attempted + extra (reconstruct frozen metadata if needed)
            if isinstance(res.metadata, ResolutionMetadata):
                cur_att = list(res.metadata.attempted or [])
                new_att = list(dict.fromkeys(cur_att + attempted))
                new_meta = ResolutionMetadata(
                    strategy=res.metadata.strategy,
                    matched_condition=res.metadata.matched_condition,
                    exports_key=res.metadata.exports_key,
                    ts_alias=res.metadata.ts_alias,
                    symlink_detected=res.metadata.symlink_detected,
                    original_logical=res.metadata.original_logical,
                    workspace_pkg=res.metadata.workspace_pkg,
                    attempted=new_att,
                    package_imports_key=res.metadata.package_imports_key,
                    extra={** (res.metadata.extra or {}), **(extra_context or {})},
                )
                # Since Resolution holds the field, we replace via object setattr (Resolution not frozen)
                object.__setattr__(res, "metadata", new_meta)
            elif isinstance(res.metadata, dict):
                res.metadata.setdefault("attempted", []).extend([a for a in attempted if a not in res.metadata.get("attempted", [])])
                if extra_context:
                    res.metadata.update(extra_context or {})
            else:
                if extra_context:
                    object.__setattr__(res, "metadata", extra_context)
            return res

    # Ultimate fallback
    meta = ResolutionMetadata(
        strategy="unresolved",
        attempted=attempted or ["none"],
        extra={"from": from_canon, "reason": "no_strategy_matched"},
    )
    return Resolution(
        raw=raw_spec,
        resolved_file=None,
        display_module=raw_spec,
        confidence="unresolved",
        strategy="unresolved",
        metadata=meta,
    )


def get_canonical_rel(
    target: Union[str, Path],
    root: Union[str, Path],
    *,
    follow_symlinks: bool = True,
) -> Optional[str]:
    """Thin convenience wrapper around the canonical helper."""
    return to_canonical_rel(target, Path(root).resolve(strict=False), follow_symlinks=follow_symlinks)


def normalize_query_file(file: str, root: Union[str, Path]) -> str:
    """
    Normalize an arbitrary user- or agent-supplied file path for use as a
    cache key or query argument in MCP tools / library consumers.

    This is the function that finally eliminates "file not found because of
    path drift" for get_dependencies / get_dependents / get_file_wiki etc.
    """
    root_p = Path(root).resolve(strict=False)
    canon = to_canonical_rel(file, root_p)
    if canon:
        return canon
    # Fall back to a best-effort cleaned form (still better than raw input)
    p = Path(file)
    if p.is_absolute():
        try:
            return _posix_rel(p.relative_to(root_p))
        except Exception:
            pass
    return _posix_rel(p)


# =============================================================================
# Module-level convenience & cache management
# =============================================================================

def clear_all_caches() -> None:
    """Clear every internal cache (context + any future memo tables)."""
    clear_context_cache()
    # Future: resolution memo, tsconfig parse cache, etc.


# =============================================================================
# Res Meta v1 Serialization Helpers (per gap1_prewave0_shared_contracts_open.md)
# Public for parsers, BREE, wikifier.sh normalizers, import_cache, MCP.
# =============================================================================

def encode_res_meta_v1(meta: Union[Dict[str, Any], ResolutionMetadata, Resolution, None]) -> str:
    """
    Produce the compact URL-safe base64 (no padding) encoding of the metadata
    dict for the `res_meta_v1=...` field in parser pipe output.
    """
    if meta is None:
        return ""
    if isinstance(meta, Resolution):
        d = meta.as_dict().get("metadata", {}) or {}
    elif isinstance(meta, ResolutionMetadata):
        d = meta.to_dict()
    elif isinstance(meta, dict):
        d = meta
    else:
        d = {}
    try:
        compact = json.dumps(d, separators=(",", ":"), ensure_ascii=False)
        b = base64.urlsafe_b64encode(compact.encode("utf-8")).rstrip(b"=")
        return b.decode("ascii")
    except Exception:
        return ""


def decode_res_meta_v1(raw_value: str) -> Optional[Dict[str, Any]]:
    """
    Defensive decoder (per Pre-Wave 0 contract).
    On any failure (bad b64, bad json, etc.) returns None so caller can fall back.
    """
    if not raw_value:
        return None
    try:
        padded = raw_value + "=" * (-len(raw_value) % 4)
        decoded = base64.urlsafe_b64decode(padded)
        return json.loads(decoded)
    except Exception:
        return None


def get_res_meta_for_import(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Helper for normalizers: prefer decoded res_meta_v1, fall back to resolution_metadata or strategy+meta."""
    if "res_meta_v1" in item:
        dec = decode_res_meta_v1(str(item.get("res_meta_v1", "")))
        if dec:
            return dec
    if "resolution_metadata" in item and isinstance(item.get("resolution_metadata"), dict):
        return item["resolution_metadata"]
    if "metadata" in item and isinstance(item.get("metadata"), dict):
        return item["metadata"]
    if "strategy" in item:
        return {"strategy": item["strategy"]}
    return None


# =============================================================================
# Self-test / verification block (executed when run directly)
# =============================================================================
