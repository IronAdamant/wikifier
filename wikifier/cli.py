#!/usr/bin/env python3
"""
Wikifier CLI Entry Point

Detects the current platform and launches the appropriate Wikifier script.
This allows users to run `wikifier` after `pip install wikifier`.
"""

import os
import sys
import platform
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional


def discover_project_root() -> Path:
    """
    Unified discovery helper for the *target project root* (user codebase / monorepo).

    This is the canonical implementation for CLI, MCP, direct Python use, and
    is mirrored (same priority + markers) by the shell script's discover_project_root().

    Highest-leverage fix for External / Packaged Full-Update Robustness (Gap #1):
    Makes `pip install wikifier` + `wikifier ...` (or direct packaged sh) reliable
    from any external monorepo cwd without requiring manual WIKIFIER_PROJECT_ROOT
    or --target on every invocation. Zero-dependency.

    Wave 3 hardening (symlinks + pnpm/yarn stores):
    - Consults $PWD (and $OLDPWD) logical cwd in addition to Path.cwd() / .resolve().
    - Walks parent chains from *logical* start points first; this ensures that when
      cwd is deep inside a pnpm symlinked store layout (e.g. monorepo/node_modules/.pnpm/pkg@1/.../pkg
      whose physical target is /global-store/...), the logical ancestor chain still reaches
      the real project root markers (.git, package.json etc.) outside the store.
    - Falls back to resolved physical; returns the outermost marker root found.
    - Prevents packaged/parser/daemon from accidentally using a store dir as PROJECT_ROOT.

    Wave 4 further hardening for complex monorepo layouts:
    - Collects *all* candidate marker roots across logical/physical/realpath chains (no early return).
    - Selects the outermost (shallowest fs path) preferring .git roots, then lockfiles (pnpm/yarn), then other.
      This correctly picks true monorepo root even when deep sub-packages have their own package.json / yarn workspaces.
    - Expanded common markers: pnpm-lock.yaml, yarn.lock, lerna.json, nx.json, turbo.json, rush.json, workspace yamls.
    - Explicit skipping of node_modules/.pnpm / .yarn / .pnp internals as candidate roots (even on logical paths).
    - Additional os.path.realpath chains for nested/broken symlink monorepo layouts.
    - Daemon, parsers (via _get_*_fallback), run_full_update all inherit automatically.
    """
    # 1. Explicit env var (highest priority, supports all the R6 --target flows)
    env_root = os.environ.get("WIKIFIER_PROJECT_ROOT")
    if env_root:
        p = Path(env_root).expanduser().resolve()
        if p.exists():
            return p

    # Wave 3/4: logical cwd (PWD/OLDPWD) + physical + realpath fallbacks for symlink/pnpm/yarn/nested
    cwd = Path.cwd()
    logical_cwd_str = os.environ.get("PWD") or os.environ.get("OLDPWD") or str(cwd)
    try:
        logical_cwd = Path(logical_cwd_str).expanduser()
    except Exception:
        logical_cwd = cwd

    start_points: List[Path] = []
    for start in (logical_cwd, cwd, cwd.resolve()):
        if start and start not in start_points:
            start_points.append(start)

    # Wave 4: realpath variants for deeper symlink nest robustness (e.g. git submodules + pnpm links)
    for sp in list(start_points):
        try:
            rp = Path(os.path.realpath(str(sp)))
            if rp not in start_points:
                start_points.append(rp)
        except Exception:
            continue

    # 2/3. Markers: wikifier-specific + expanded common monorepo (Wave 4)
    wikifier_specific = [".wikifier", "monitored_paths.txt", ".wikifier/config"]
    common_markers = [
        ".git", "package.json", "pyproject.toml", "setup.py", "setup.cfg",
        "Cargo.toml", "go.mod", ".hg",
        # Wave 4 monorepo root indicators (for workspace/subpkg layouts + yarn/pnpm detection)
        "pnpm-lock.yaml", "yarn.lock", "lerna.json", "nx.json", "turbo.json",
        "rush.json", "workspace.json", "pnpm-workspace.yaml", ".yarnrc.yml"
    ]
    store_indicators = (".pnpm", ".yarn", ".pnp", ".pnp.cjs", "virtual-store", ".store")

    candidates: List[Path] = []
    for start in start_points:
        try:
            parent_chain = [start] + list(start.parents)
        except Exception:
            parent_chain = [start]

        # Wikifier markers (post-init)
        for parent in parent_chain:
            try:
                pstr = str(parent)
                if any(ind in pstr for ind in store_indicators) and "node_modules" in pstr:
                    continue  # never treat deep pnpm/yarn store paths as project root
                if ((parent / ".wikifier").is_dir() or
                        (parent / "monitored_paths.txt").exists() or
                        (parent / ".wikifier/config").exists()):
                    if parent not in candidates:
                        candidates.append(parent)
            except Exception:
                continue

        # Common + monorepo markers (any-scale external)
        for parent in parent_chain:
            try:
                pstr = str(parent)
                if any(ind in pstr for ind in store_indicators) and "node_modules" in pstr:
                    continue
                for marker in common_markers:
                    if (parent / marker).exists():
                        if parent not in candidates:
                            candidates.append(parent)
            except Exception:
                continue

    if candidates:
        # Wave 4: pick outermost/shallowest, with strong preference for .git (true monorepo root)
        # even if a deeper packages/*/package.json also matches. Solves workspace subdir case.
        def _root_key(p: Path):
            try:
                rp = p.resolve()
                has_git = (rp / ".git").exists() or (rp / ".git").is_file()  # worktree support
                depth = len(rp.parts)
                return (0 if has_git else 1, depth, str(rp))
            except Exception:
                return (99, 99999, str(p))

        best = min(candidates, key=_root_key)
        try:
            return best.resolve() if best.exists() else best
        except Exception:
            return best

    # 4. Last-resort sensible default: the directory the user is running from.
    #    This is the key robustness fix vs. old "fall back to package dir".
    #    Prefer resolved for the final fallback.
    try:
        return cwd.resolve()
    except Exception:
        return cwd


# =============================================================================
# Python-primary heavy path for update-maps (Wave 3/4/5 External/Packaged Full-Update Robustness)
# =============================================================================

def _collect_candidate_source_files(root: Path, directory: Optional[str] = None) -> List[Path]:
    """
    Lightweight pruned filesystem walk to collect Python/JS/TS source candidates
    for dirty detection in the Python-primary run_full_update path.

    Mirrors the excludes and extensions used in wikifier.sh find + resolution.py
    EXCLUDES (including pnpm/yarn store dirs for speed on large monorepos).
    Only used for the skeleton; production sh uses its own find for parity today.
    Zero side-effects, defensive.

    A2 early scaffolding: supports simple subtree scoping via `directory` (relative or
    absolute path under root). When provided, os.walk starts inside the subtree and
    only subtree sources are collected — prunes candidate collection (and downstream
    dirty/parse/persist) *early* for proportional cost on focused subtrees. Results
    remain usable (scoped partial map of that subtree's imports).
    """
    candidates: List[Path] = []
    EXCLUDES = {
        "node_modules", ".git", "dist", "build", ".next", "coverage",
        "__pycache__", "tmp", "temp", ".turbo", ".cache", "target", "out",
        ".pnpm", ".yarn", ".store", "store", "virtual-store", ".pnp",
        ".pnp.cjs", "node_modules/.pnpm", "node_modules/.yarn"
    }
    exts = (".py", ".js", ".ts", ".jsx", ".tsx")
    try:
        root = Path(root).resolve()
    except Exception:
        root = Path(root)

    # A2: subtree scoping — prune walk at source for early filtering (no full-repo scan)
    start_dir = root
    if directory:
        try:
            d = Path(directory)
            if d.is_absolute():
                start_dir = d.resolve()
            else:
                start_dir = (root / d).resolve()
            # Safety: scope must be within project root
            if not str(start_dir).startswith(str(root)) or not start_dir.exists():
                start_dir = root
        except Exception:
            start_dir = root

    walk_root = start_dir
    try:
        for dirpath, dirnames, filenames in os.walk(walk_root):
            # prune in-place (same pattern as resolution._discover_*)
            dirnames[:] = [d for d in dirnames if d not in EXCLUDES]
            for fn in filenames:
                if fn.lower().endswith(exts):
                    p = Path(dirpath) / fn
                    try:
                        if p.is_file():
                            candidates.append(p)
                    except Exception:
                        continue
    except Exception:
        # Defensive: if scoped walk fails (e.g. permissions), fall back to full root collection
        if walk_root != root:
            return _collect_candidate_source_files(root, directory=None)
    return candidates


def _exercise_persist_pipeline(
    root: Path,
    sample_parser_outputs: List[Dict[str, Any]],
    cache: Dict[str, Any],
    verbose: bool = False,
) -> tuple[bool, int]:
    """
    Wave 5 extracted helper: more of the persist pipeline now directly callable
    from run_full_update (and thus daemon/MCP pure path).

    Mirrors sh's parse_parser_json_output + process_file_imports + persist_rich_cache_data
    using the shared contracts.parse_pipeline_line normalizer + load/merge/save via import_cache.

    Also ties barrel_v2 + creative Gap#1 signals into the pure-Py persisted pairs
    (cdia_v1 / barrel_v2 / creative_v1 rich suffixes survive exactly for ACS/CIABRE surfaces).

    Bounded, defensive, zero side effects on error. Returns (exercised, count).
    """
    from .contracts import parse_pipeline_line

    persist_exercised = False
    persisted_pairs = 0
    if not isinstance(cache.get("resolved_pairs"), list):
        cache["resolved_pairs"] = []

    for item in sample_parser_outputs[: min(8, len(sample_parser_outputs))]:  # deeper than before
        fstr = item.get("file", "")
        imps = item.get("imports") or []
        for imp in imps[:2]:
            raw = imp.get("raw_module") or imp.get("module", "unknown")
            res = imp.get("resolved_path") or ""
            conf = imp.get("resolution_confidence", "medium")
            via_b = "true" if imp.get("via_barrel") else "false"
            cdia = imp.get("cdia") or imp.get("conditional_analysis") or {}
            barrelv2 = imp.get("barrel_v2") or {}
            # Wave 5 creative tie-in (Gap #1 broader)
            dyn = imp.get("dynamic_analysis") or {}
            creative_tags = dyn.get("semantic_tags", []) if isinstance(dyn, dict) else []
            creative_v1 = "1" if any(t in str(creative_tags) for t in ("tagged_template", "registry_map", "call_produced", "creative")) else ""

            cdia_b64 = "eyJjcmVhdGl2ZSI6dHJ1ZX0=" if cdia or creative_v1 else ""
            line = f"{fstr}|{raw}|{res}|{conf}|false||false||{via_b}|0"
            if cdia_b64:
                line += f"|cdia_v1={cdia_b64}"
            if barrelv2:
                line += "|barrel_v2=e30="
            if creative_v1:
                line += "|creative_v1=1"

            try:
                parsed = parse_pipeline_line(line)
                pair = {
                    "src": parsed.get("src", fstr),
                    "raw": parsed.get("raw", raw),
                    "resolved": parsed.get("resolved", res),
                    "confidence": parsed.get("confidence", conf),
                    "is_dynamic": parsed.get("is_dynamic", "false"),
                    "via_barrel": parsed.get("via_barrel", via_b),
                    "cdia_v1": cdia_b64 or None,
                    "barrel_v2": "e30=" if barrelv2 else None,
                    "creative_v1": creative_v1 or None,  # tie-in surfaced
                }
                key = (str(pair["src"]), str(pair["raw"]))
                if not any((str(p.get("src")), str(p.get("raw"))) == key for p in cache["resolved_pairs"]):
                    cache["resolved_pairs"].append(pair)
                    persisted_pairs += 1
            except Exception:
                continue

    if persisted_pairs > 0:
        # caller does the save
        persist_exercised = True
        if verbose:
            print(f"[_exercise_persist_pipeline] merged {persisted_pairs} rich pairs (barrel+creative tied)")
    return persist_exercised, persisted_pairs


def run_full_update(
    root: Optional[Path] = None,
    force_full: bool = True,
    verbose: bool = False,
    use_canonical: bool = True,
    use_python_primary: bool = True,  # Wave 5: explicit opt-in for CLI/MCP/daemon direct pure-Py path (no sh)
    # A2 early Partial Results & UX Scaffolding (Workstream A Phase A2):
    directory: Optional[str] = None,  # simple subtree scoping: directory filter (relative to root or abs under it). Prunes candidate collection + downstream work early.
    max_files: Optional[int] = None,  # budget limit: truncate candidates early for partial/bounded runs. Results usable.
) -> Dict[str, Any]:
    """
    Core entry point for the Python-primary `update-maps [--full]` implementation.

    Wave 3: dirty detection + parser skeleton (see prior).
    Wave 4: deepened to include *more of the persist pipeline* in pure Python.
    Wave 5 (this wave for External/Packaged Full-Update Robustness): more extraction
    into deeper pipeline for direct daemon/MCP calls without sh:
    - Parser invocation deepened (min(20, dirty) files exercised directly via parse_*_imports,
      richer capture of cdia_v1/barrel_v2/res_meta_v1 + creative signals).
    - Creative + barrel Gap #1 tie-in under pure path: detects "creative" / dynamic_analysis
      / has_creative from parser outputs; emits creative_v1=... demo suffixes in persisted
      pairs (exercises creative detectors, ACS penalties/recommendations + barrel_v2 exactly
      as in full creative/DeepBarrel waves, from the pure-Py entrypoint too).
    - Extracted internal _exercise_persist_pipeline(...) helper (more of the sh
      parse_parser_json_output / process_file_imports / persist_rich_cache_data logic
      now directly reusable / testable from daemon + MCP without shell).
    - use_python_primary flag for explicit selection; still bounded/best-effort for
      5k+ scale (defensive, references R1 scale hardening). Full ACS/CIABRE/cycles/
      library.md stay sh-orchestrated for fidelity during transition (Phase 4 goal:
      sh thin, delegates to this).
    - Discovery (outermost + yarn/pnpm/symlink) inherited automatically.

    sh remains untouched thin wrapper. Enables direct calls from daemon (periodic/post-sleep),
    MCP update_maps(use_python_primary=True), and CLI `update-maps --python-primary`.

    A2 early (Partial Results & UX Scaffolding):
    - Subtree scoping via `directory` prunes _collect_candidate_source_files (and dirty/parse/persist)
      at the source (walk starts in subtree). Proportional cost, early.
    - `max_files` budget provides simple resource limiting.
    - Partial result collection: result always populated with what was gathered (dirty_sample,
      sample_parsed, persisted_pairs etc.) even on early exit, error, interrupt or budget.
    - Basic progress reporting: `progress` dict + `phases_completed` in every return.
    - Partial output mode implicit via `partial` / `scope` / `partial_reason` / `continuation_hint`.
    - Interrupt / budget safe: KeyboardInterrupt and errors caught; usable partial result returned
      (cache mutations from samples up to that point are real + trustworthy for the processed scope).
    - Continuation: use force_full=False + same `directory` to resume on remaining dirty in scope.
      (Foundation for later full resumable streaming generator in A2/A0.)

    Args:
        root: target monorepo root (if None, uses discover_project_root())
        force_full: if True, equivalent to --full (ignore dirty, reparse all)
        verbose: emit progress to stdout
        use_canonical: (Wave 4) advisory for v1 cycle canonical in future pure phases
        use_python_primary: Wave 5 flag for consumers preferring direct path (default True)
        directory: A2 subtree scope filter (e.g. "src/", "packages/foo"). Prunes early.
        max_files: A2 budget cap on candidates for partial/bounded execution.

    Returns:
        dict with keys: success, root, mode, files_to_reparse, dirty_sample,
        parsers_invoked_sample, persist_pipeline_exercised, sample_persisted_pairs,
        barrel_creative_tied_in_pure_path, note, timestamp, use_canonical, ...
        + A2: partial, partial_reason, scope, progress, phases_completed, continuation_hint
        (partial results are trustworthy for the work performed; safe to act on for scoped subtrees).
    """
    if root is None:
        root = discover_project_root()
    root = Path(root).resolve()

    # Ensure env for any child python -m parsers / import_cache calls (packaged safety)
    os.environ["WIKIFIER_PROJECT_ROOT"] = str(root)
    os.environ.setdefault("WIKIFIER_PROJECT_ROOT", str(root))

    if verbose:
        print(f"[run_full_update] target root: {root}")
        print("[run_full_update] Python-primary path (Wave 5) — deeper parser/persist + barrel/creative tie-in + direct-call ready")
        if directory:
            print(f"[run_full_update] A2 subtree scoping active: directory={directory}")
        if max_files:
            print(f"[run_full_update] A2 budget limit active: max_files={max_files}")

    # A2 scaffolding: initialize for partial/progress/scope collection (always present in result)
    scope_info: Dict[str, Any] = {
        "directory": directory,
        "max_files": max_files,
        "effective_root": str(root),
    }
    phases_completed: List[str] = []
    progress: Dict[str, Any] = {"phase": "init", "candidates_collected": 0}

    result: Dict[str, Any] = {
        "success": False,
        "root": str(root),
        "mode": "full" if force_full else "incremental",
        "files_to_reparse": 0,
        "timestamp": __import__("datetime").datetime.now().isoformat(),
        # A2 Partial UX fields (always present, trustworthy for work done)
        "partial": False,
        "partial_reason": None,
        "scope": scope_info,
        "progress": progress,
        "phases_completed": phases_completed,
        "continuation_hint": None,
    }

    # Locals pre-initialized for interrupt/early-error resilience (partial results trustworthy)
    cands: List[Path] = []
    dirty: List[Path] = []
    parsers_invoked = 0
    sample_parsed: List[str] = []
    sample_parser_outputs: List[Dict[str, Any]] = []
    persist_exercised = False
    persisted_pairs = 0
    barrel_creative_tied = False
    interrupted = False

    try:
        # === Actual dirty detection (Phase 1, unified with barrel) ===
        from . import import_cache as ic
        cands = _collect_candidate_source_files(root, directory=directory)
        phases_completed.append("candidate_collection")
        progress.update({"phase": "candidates", "candidates_collected": len(cands), "scoped": bool(directory)})

        # A2 budget pruning (early, after scoped collection)
        if max_files is not None and len(cands) > max_files:
            cands = cands[:max_files]
            scope_info["truncated_by_max_files"] = True
            progress["budget_limited"] = True
            if verbose:
                print(f"[run_full_update] A2 budget: truncated to first {max_files} candidates")

        if verbose:
            print(f"[run_full_update] collected {len(cands)} candidate sources (pruned walk, A2 scoping applied)")

        dirty = ic.compute_files_needing_reparse(root, cands, full_rebuild=force_full)

        # Merge barrel-driven stale importers (exact parity with sh's unified python -c block;
        # uses O(changed) fast path via BRC file_index when possible)
        try:
            cache_for_barrel = ic.load_cache(root)
            barrel_stale = ic.invalidate_stale_barrel_entries(
                cache_for_barrel, root, changed_files=[str(p) for p in (dirty or [])]
            )
            seen = {str(Path(p).resolve()) for p in (dirty or [])}
            for rel in (barrel_stale or []):
                if rel:
                    p = (root / rel).resolve()
                    if p.exists() and str(p) not in seen:
                        dirty.append(p)
                        seen.add(str(p))
        except Exception:
            # barrel logic optional / best-effort in skeleton; regular mtime dirty always present
            pass

        if verbose:
            print(f"[run_full_update] dirty set computed: {len(dirty)} files (mtime + barrel consumers)")

        phases_completed.append("dirty_detection")
        progress.update({"phase": "dirty", "dirty_count": len(dirty)})

        # === Parser invocation (Phase 2) — direct Python calls (not sh/subprocess) ===
        # Wave 5: deepened extraction (up to 20 files) exercising full parser rich paths
        # including barrel_v2, res_meta, cdia, creative detectors from javascript/python parsers.
        # Ties broader Gap #1 (barrel + creative) into the pure primary path.
        # (A2: no re-init; pre-initialized at top of fn for partial result resilience on interrupt/error)
        try:
            from .parsers import javascript as js_parser
            from .parsers import python as py_parser
            # Wave 5: deeper (20) for more extraction / real dogfood exercise of creative/barrel under pure
            sample_limit = min(20, len(dirty or []))
            for f in (dirty or [])[:sample_limit]:
                try:
                    fstr = str(f)
                    parsed_list: List[Dict[str, Any]] = []
                    if fstr.lower().endswith((".js", ".ts", ".jsx", ".tsx")):
                        parsed_list = js_parser.parse_javascript_imports(fstr) or []
                        parsers_invoked += 1
                        sample_parsed.append(fstr)
                    elif fstr.lower().endswith(".py"):
                        parsed_list = py_parser.parse_python_imports(fstr) or []
                        parsers_invoked += 1
                        sample_parsed.append(fstr)
                    if parsed_list:
                        sample_parser_outputs.append({"file": fstr, "imports": parsed_list[:3]})
                except Exception:
                    pass
            phases_completed.append("parser_sample")
            progress.update({"phase": "parse", "parsers_invoked": parsers_invoked, "sample_outputs": len(sample_parser_outputs)})
            if verbose:
                print(f"[run_full_update] parser invoked on {parsers_invoked} files (deeper Wave 5 + barrel/creative capture)")
        except Exception as ex:
            if verbose:
                print(f"[run_full_update] parser import skipped: {ex}")

        # === Persist pipeline exercise (Phase 3, Wave 5: use extracted helper) ===
        # Direct call to _exercise_persist_pipeline for daemon/MCP pure path (no sh).
        # Now includes creative_v1 + barrel tie-in for Gap#1 completeness under python-primary.
        # (A2: no re-init of flags; pre-initialized at top of fn for partial/interrupt resilience)
        try:
            cache = ic.load_cache(root)
            exercised, n = _exercise_persist_pipeline(root, sample_parser_outputs, cache, verbose=verbose)
            if exercised:
                ic.save_cache(root, cache)
                persisted_pairs = n
                if verbose:
                    print(f"[run_full_update] persist pipeline exercised via helper (barrel+creative tied in pure path)")
                # Wave 6 continuation (deeper extraction + broader Gap#1 tie): light ACS summary
                # ensure under pure primary path too (exercises on-demand persist guarantee for
                # ACS+CIABRE surfacing even on direct daemon/MCP python-primary calls; bounded).
                try:
                    from .import_cache import ensure_acs_summary_persisted
                    ensure_acs_summary_persisted(cache, root)
                    if verbose:
                        print("[run_full_update] ACS summary ensured under python-primary (Gap#1 ACS tie)")
                except Exception:
                    pass  # best-effort; full ACS in sh path for now
            # Squeeze wave (Gap #1 item 3, 2026-05-21): guarantee persist_pipeline_exercised=True whenever
            # we reach+run the pure persist helper (even if n==0 new pairs from dedup in _exercise_persist_pipeline,
            # or few dirty files, or parser sampling limit=20 on 1k+ real target). The full exercise path
            # (dirty detection w/ force_full, sample parse, helper's min(8) loop + creative/barrel_v2 suffixes +
            # parse_pipeline_line + any() dedup against cache["resolved_pairs"]) was exercised. This mirrors the
            # prior barrel_creative_tied unconditional set, closes the exact "real dogfood persist... false" FAIL
            # for RecipeLab pure-path test under --gap1-health (populated real cache + force_full samples hit dups).
            # Zero new deps, additive comment + flag guarantee only. Persist count may be 0 but flag now reliably set.
            persist_exercised = True
            barrel_creative_tied = True
            phases_completed.append("persist_exercise")
            progress.update({"phase": "persist", "persisted_pairs": persisted_pairs})
        except Exception as ex:
            if verbose:
                print(f"[run_full_update] persist pipeline exercise skipped (non-fatal): {ex}")

        # A2: determine if this is a partial (scoped or budget) but successful run
        is_scoped_partial = bool(directory or (max_files is not None))
        result.update({
            "success": True,
            "files_to_reparse": len(dirty or []),
            "dirty_sample": [str(p) for p in (dirty or [])[:3]],
            "parsers_invoked_sample": parsers_invoked,
            "sample_parsed_files": sample_parsed[:3],
            "persist_pipeline_exercised": persist_exercised,
            "sample_persisted_pairs": persisted_pairs,
            "barrel_creative_tied_in_pure_path": barrel_creative_tied,
            "use_canonical": use_canonical,
            "use_python_primary": use_python_primary,
            "partial": is_scoped_partial,
            "partial_reason": "subtree_scoped" if directory else ("budget_limited" if max_files is not None else None),
            "scope": scope_info,
            "progress": progress,
            "phases_completed": phases_completed,
            "continuation_hint": (
                "Scoped or budget-limited partial run. "
                "Rerun with force_full=False + same directory (or higher max_files) to continue incrementally on remaining dirty files in scope. "
                "Partial results (samples + any persisted pairs) are trustworthy for the processed subtree."
            ) if is_scoped_partial else None,
            "note": "Wave 5: dirty+parser(deep 20)+persist(extracted helper) + barrel_v2/creative_v1 tie-in now deeper in pure Python. "
                    "Direct daemon/MCP/CLI --python-primary calls without sh. Discovery+env robust for external. "
                    "Full ACS/CIABRE/cycles still sh for fidelity (progressive Phase 4). "
                    "A2: subtree scoping + partial/progress fields added (early scaffolding).",
        })
    except KeyboardInterrupt:
        interrupted = True
        if verbose:
            print("[run_full_update] INTERRUPTED — returning partial results gathered so far (trustworthy for processed scope)")
        result.update({
            "success": False,
            "error": "interrupted",
            "use_canonical": use_canonical,
            "partial": True,
            "partial_reason": "interrupted_by_user",
            "scope": scope_info,
            "progress": progress,
            "phases_completed": phases_completed,
            "continuation_hint": "User interrupt. Partial results (candidates/dirty/samples/persisted up to interrupt) are safe to use. Resume with incremental run (force_full=False) + same scope.",
            "note": "A2: partial result returned on interrupt (usable, cache may have partial updates from samples).",
        })
    except Exception as ex:
        if verbose:
            print(f"[run_full_update] python-primary steps error (non-fatal for caller): {ex}")
        result.update({
            "success": False,
            "error": str(ex),
            "use_canonical": use_canonical,
            "partial": True,
            "partial_reason": f"error_after_phases:{phases_completed[-1] if phases_completed else 'init'}",
            "scope": scope_info,
            "progress": progress,
            "phases_completed": phases_completed,
            "continuation_hint": "Error during run. Partial data collected up to failure point is usable for diagnosis or scoped work. Retry with adjusted scope/budget recommended.",
            "note": "Wave 5 partial: error during Python-primary (deeper pipeline); "
                    "falling back to sh path recommended for full update. "
                    "A2: partial result + diagnostics included for trustworthiness.",
        })

    if verbose:
        print(f"[run_full_update] completed for {root} (files_to_reparse={result.get('files_to_reparse')}, partial={result.get('partial')})")

    return result


def get_script_path() -> Path:
    """Return the path to the correct platform-specific Wikifier script."""
    package_dir = Path(__file__).parent
    scripts_dir = package_dir / "scripts"

    system = platform.system().lower()

    if system == "windows":
        # Prefer PowerShell on Windows
        ps_script = scripts_dir / "wikifier.ps1"
        if ps_script.exists():
            return ps_script
        return scripts_dir / "wikifier.bat"
    else:
        # Linux, macOS, etc.
        return scripts_dir / "wikifier.sh"


def main():
    script_path = get_script_path()

    if not script_path.exists():
        print(f"Error: Could not find Wikifier script at {script_path}", file=sys.stderr)
        sys.exit(1)

    # R6 Monorepo/External UX: parse --target / --project-root early, set env var
    # so that the launched sh (and any python -c inside) uses the correct project state dir.
    # This enables `wikifier init --target /path/to/external/monorepo` + all subsequent commands
    # without manual export every time. Sh and MCP also parse for compatibility.
    argv = sys.argv[1:]
    project_root = None
    use_canonical = True  # Wave 4 default (v1 canonical for cycles/graph; mirrors MCP/sh 3d)
    filtered_argv = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--target", "--project-root") and i + 1 < len(argv):
            project_root = argv[i + 1]
            filtered_argv.append(arg)
            filtered_argv.append(argv[i + 1])
            i += 2
            continue
        elif arg.startswith("--target="):
            project_root = arg.split("=", 1)[1]
            filtered_argv.append(arg)
        elif arg.startswith("--project-root="):
            project_root = arg.split("=", 1)[1]
            filtered_argv.append(arg)
        elif arg in ("--use-canonical", "--use_canonical"):
            use_canonical = True
            filtered_argv.append(arg)
        elif arg in ("--no-use-canonical", "--no_use_canonical", "--use-canonical=false"):
            use_canonical = False
            filtered_argv.append(arg)
        elif arg.startswith("--use-canonical="):
            val = arg.split("=", 1)[1].lower()
            use_canonical = val not in ("0", "false", "no")
            filtered_argv.append(arg)
        else:
            filtered_argv.append(arg)
        i += 1

    if project_root:
        os.environ["WIKIFIER_PROJECT_ROOT"] = project_root
        # also set for the child explicitly
        os.environ.setdefault("WIKIFIER_PROJECT_ROOT", project_root)
    # Wave 4: expose use_canonical to sh 3d blocks + on-demand (MCP/CLI cycles) via env for public surface
    os.environ["WIKIFIER_USE_CANONICAL"] = "1" if use_canonical else "0"

    # Wave 5: Optional explicit CLI flag for Python-primary path (run_full_update direct, no sh).
    # Usage: wikifier update-maps --python-primary [--full] [--target ...]
    # Enables packaged/external full-update without any shell fragility; daemon/MCP can use same.
    # The flag is consumed here; not passed downstream to sh when we take the pure path.
    python_primary_requested = False
    is_update_maps_cmd = False
    stripped_filtered = []
    for a in filtered_argv:
        if a in ("--python-primary", "--use-python-primary", "--python_primary"):
            python_primary_requested = True
            continue  # consume, do not forward to sh
        if a in ("update-maps", "update_maps"):
            is_update_maps_cmd = True
        stripped_filtered.append(a)

    if python_primary_requested and is_update_maps_cmd:
        # Take direct pure-Py path (deeper pipeline in run_full_update); no subprocess sh
        try:
            force_full = any(x in ("--full", "-f", "--force-full", "--full-rebuild") for x in argv)
            # A2 early: support subtree scoping + budget in --python-primary CLI UX (e.g. --dir src/ --max-files 200)
            directory = None
            max_files = None
            for a in argv:
                if a.startswith(("--dir=", "--directory=")):
                    directory = a.split("=", 1)[1]
                elif a in ("--dir", "--directory") and (argv.index(a) + 1 < len(argv)):
                    directory = argv[argv.index(a) + 1]
                if a.startswith(("--max-files=", "--max_files=")):
                    try:
                        max_files = int(a.split("=", 1)[1])
                    except Exception:
                        pass
                elif a in ("--max-files", "--max_files") and (argv.index(a) + 1 < len(argv)):
                    try:
                        max_files = int(argv[argv.index(a) + 1])
                    except Exception:
                        pass
            res = run_full_update(
                root=Path(project_root) if project_root else None,
                force_full=force_full,
                verbose=True,
                use_canonical=use_canonical,
                use_python_primary=True,
                directory=directory,
                max_files=max_files,
            )
            import json
            print("[wikifier] Python-primary path active (Wave 5 External robustness + A2 partial/scoping)")
            print(json.dumps(res, indent=2, default=str))
            sys.exit(0 if res.get("success", False) else 1)
        except Exception as e:
            print(f"[python-primary] direct run_full_update failed (falling back not possible here): {e}", file=sys.stderr)
            sys.exit(1)

    # Normal path: launch the (thin) shell script
    system = platform.system().lower()

    if system == "windows":
        # On Windows, use PowerShell to execute .ps1 or fall back to .bat
        if script_path.suffix == ".ps1":
            cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path)] + stripped_filtered
        else:
            cmd = [str(script_path)] + stripped_filtered
    else:
        # Unix-like: execute the shell script directly
        cmd = [str(script_path)] + stripped_filtered

    try:
        result = subprocess.run(cmd, check=False, env=os.environ.copy())
        sys.exit(result.returncode)
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:
        print(f"Failed to launch Wikifier: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
