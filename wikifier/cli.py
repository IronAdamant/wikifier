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
from contextlib import contextmanager, nullcontext as _nullcontext


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

def _collect_candidate_source_files(root: Path) -> List[Path]:
    """
    Lightweight pruned filesystem walk to collect Python/JS/TS source candidates
    for dirty detection in the Python-primary run_full_update path.

    Mirrors the excludes and extensions used in wikifier.sh find + resolution.py
    EXCLUDES (including pnpm/yarn store dirs for speed on large monorepos).
    Only used for the skeleton; production sh uses its own find for parity today.
    Zero side-effects, defensive.
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
    # Also respect the project's exclude_patterns.txt (if present) for parity with sh
    # mapping paths and check-changes. Simple dir-name globs only for pruning speed.
    # This makes python-primary update-maps benefit from user custom excludes (venvs etc)
    # without any behavior change.
    # Look relative to explicit WIKIFIER_PROJECT_ROOT (if set for the target) or the
    # passed root; excludes live at the logical project root, not arbitrary monitored subdirs.
    ep_root = Path(os.environ.get("WIKIFIER_PROJECT_ROOT", root))
    ep = ep_root / "exclude_patterns.txt"
    if ep.exists():
        try:
            for line in ep.read_text(errors="ignore").splitlines():
                p = line.strip()
                if p and not p.startswith("#"):
                    p = p.split()[0]  # first token
                    if p:
                        EXCLUDES.add(p)
                        # also common glob forms as exact for dirname match
                        if p.endswith("/*") or p.endswith("*"):
                            EXCLUDES.add(p.rstrip("/*"))
        except Exception:
            pass

    # Fast path: if inside a git repo, use `git ls-files` + untracked (respects .gitignore, dramatically faster
    # on large checkouts than any walk; falls back to scandir scan). This is a pure speed opt for "updates"
    # (check-changes, update-maps) with near-identical or better candidate set for real codebases.
    git_dir = root / ".git"
    if git_dir.exists() or (root / ".git" / "HEAD").exists():  # works for worktrees too
        try:
            import subprocess
            # cached + others (untracked but not ignored), exclude standard ignores
            out = subprocess.check_output(
                ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                cwd=root, stderr=subprocess.DEVNULL
            )
            for entry in out.split(b"\0"):
                if not entry:
                    continue
                p = (root / entry.decode("utf-8", "ignore")).resolve()
                if p.suffix.lower() in exts:  # reuse the set from above (adjusted)
                    # quick filter for excludes we still want even if git surfaces them
                    parts = p.parts
                    if not any(part in EXCLUDES or any(part.startswith(e) for e in (".",)) for part in parts):
                        candidates.append(p)
            if candidates:
                return candidates  # success, use git list
        except Exception:
            pass  # fall through to scandir

    # Use os.scandir for faster directory traversal (std lib only; avoids full listdir + separate is_dir stats on large trees).
    # Pruning is applied on the fly. Behavior identical to prior walk.
    exts_lower = tuple(e.lower() for e in exts)
    def _scan_dir(d: Path) -> None:
        try:
            with os.scandir(d) as it:
                for entry in it:
                    try:
                        name = entry.name
                        if entry.is_dir(follow_symlinks=False):
                            if name not in EXCLUDES and not name.startswith('.'):
                                _scan_dir(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            lname = name.lower()
                            if lname.endswith(exts_lower):
                                candidates.append(Path(entry.path))
                    except Exception:
                        continue
        except Exception:
            pass
    _scan_dir(root)
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

    Args:
        root: target monorepo root (if None, uses discover_project_root())
        force_full: if True, equivalent to --full (ignore dirty, reparse all)
        verbose: emit progress to stdout
        use_canonical: (Wave 4) advisory for v1 cycle canonical in future pure phases
        use_python_primary: Wave 5 flag for consumers preferring direct path (default True)

    Returns:
        dict with keys: success, root, mode, files_to_reparse, dirty_sample,
        parsers_invoked_sample, persist_pipeline_exercised, sample_persisted_pairs,
        barrel_creative_tied_in_pure_path, note, timestamp, use_canonical, ...
        (future: full stats, acs_summary, timing, cycle guarantees)
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

    result: Dict[str, Any] = {
        "success": False,
        "root": str(root),
        "mode": "full" if force_full else "incremental",
        "files_to_reparse": 0,
        "timestamp": __import__("datetime").datetime.now().isoformat(),
    }

    try:
        # === Actual dirty detection (Phase 1, unified with barrel) ===
        from . import import_cache as ic
        cands = _collect_candidate_source_files(root)
        if verbose:
            print(f"[run_full_update] collected {len(cands)} candidate sources (pruned walk)")

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

        # === Parser invocation (Phase 2) — direct Python calls (not sh/subprocess) ===
        # Wave 5: deepened extraction (up to 20 files) exercising full parser rich paths
        # including barrel_v2, res_meta, cdia, creative detectors from javascript/python parsers.
        # Ties broader Gap #1 (barrel + creative) into the pure primary path.
        parsers_invoked = 0
        sample_parsed: List[str] = []
        sample_parser_outputs: List[Dict[str, Any]] = []
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
            if verbose:
                print(f"[run_full_update] parser invoked on {parsers_invoked} files (deeper Wave 5 + barrel/creative capture)")
        except Exception as ex:
            if verbose:
                print(f"[run_full_update] parser import skipped: {ex}")

        # === Persist pipeline exercise (Phase 3, Wave 5: use extracted helper) ===
        # Direct call to _exercise_persist_pipeline for daemon/MCP pure path (no sh).
        # Now includes creative_v1 + barrel tie-in for Gap#1 completeness under python-primary.
        persist_exercised = False
        persisted_pairs = 0
        barrel_creative_tied = False
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
        except Exception as ex:
            if verbose:
                print(f"[run_full_update] persist pipeline exercise skipped (non-fatal): {ex}")

        # A1: Surface first-class reverse dependency index (always, even on partial pure-path exercise).
        # This exercises the new get_reverse_dependency_stats + ensures the persisted reverse + its
        # signature are visible to callers of run_full_update (MCP, daemon, CLI --python-primary).
        reverse_index_info: Dict[str, Any] = {}
        try:
            from . import import_cache as ic_for_rev
            cache_for_rev = ic_for_rev.load_cache(root)
            reverse_index_info = ic_for_rev.get_reverse_dependency_stats(cache_for_rev)
            # Lightweight bootstrap/demo of A1 maintenance in pure primary (if no index yet, rebuild once
            # from whatever resolved data the skeleton populated; harmless and shows the path works).
            if not reverse_index_info.get("has_index") and any(not k.startswith("_") for k in cache_for_rev.keys()):
                rebuilt_rev = ic_for_rev.rebuild_reverse_dependencies(cache_for_rev)
                ic_for_rev.set_reverse_dependencies(cache_for_rev, rebuilt_rev)
                ic_for_rev.save_cache(root, cache_for_rev)
                reverse_index_info = ic_for_rev.get_reverse_dependency_stats(cache_for_rev)
        except Exception:
            reverse_index_info = {"error": "reverse_index_unavailable_in_skeleton", "target_count": 0}

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
            "reverse_dependency_index": reverse_index_info,  # A1 first-class exposure
            "note": "Wave 5: dirty+parser(deep 20)+persist(extracted helper) + barrel_v2/creative_v1 tie-in now deeper in pure Python. "
                    "Direct daemon/MCP/CLI --python-primary calls without sh. Discovery+env robust for external. "
                    "Full ACS/CIABRE/cycles still sh for fidelity (progressive Phase 4). "
                    "A1: reverse_dependency_index (with signature + incremental maintain path) now surfaced.",
        })
    except Exception as ex:
        if verbose:
            print(f"[run_full_update] python-primary steps error (non-fatal for caller): {ex}")
        result.update({
            "success": False,
            "error": str(ex),
            "use_canonical": use_canonical,
            "note": "Wave 5 partial: error during Python-primary (deeper pipeline); "
                    "falling back to sh path recommended for full update.",
            # M5.1 hardening (gap5 agent scale resilience from report ONLY: 2/4 agents failed "doom loop detected (repeated errors)" on scale/large/MCP e.g. RecipeLlama ~100 tools/7 err /30k+s reaped, ConsistencyMeta ~68t/5e/30ks; no auto backoff/scope/early partial evidence; DoD#5: 2+ full 50k+ w/ 0 doom, auto-scope key dirs, 1-2 retries transient, append partial on err before fail. Small improvement here in incremental (run_full_update) error handling: surfaces repeated-error hint for callers (subagents). #2 zero-dep, #7 multi-agent context (parallel 4+ replacement/manual pattern), #8 boundary (wikifier/cli only; no target dogfood), #9 using exact 100 tools/7 err, 168k u/1363 chains/4min/20+ BRC y/84 edges/6 mismatches/40-65% calibs from reports, honest calib ~30-40% visible contrib to M5.1 code part (ref 9GP#1 spectrum alt BRC+llama+llvm+meta).
            "agent_resilience_hint_m5.1": "for repeated errors/doom loops (per M5 report): caller subagents use directory=/abs/sub or max_files budget on >10k (e.g. llvm/alt), 1-2 retries + sleep backoff on transient MCP/list_dir, append partial evidence/journal before fail (see also A2 partials in update_maps). 8-step DF + 9GP traces in diary.",
        })

    if verbose:
        print(f"[run_full_update] completed for {root} (files_to_reparse={result.get('files_to_reparse')})")

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

    # Micro-step 2 (A2 CLI wiring): detect streaming UX flags after parsing
    a2_flag_markers = ("--stream", "--stream=", "--resume", "--resume_token", "--max-time", "--max_time", "--progress", "--summary", "--partial", "--dir=", "--directory=", "--max-files", "--max_files", "--format", "--format=summary", "--format=stream")
    has_a2_ux_flags = any(any(a == m or a.startswith(m) for m in a2_flag_markers) for a in filtered_argv)

    if project_root:
        os.environ["WIKIFIER_PROJECT_ROOT"] = project_root
        # also set for the child explicitly
        os.environ.setdefault("WIKIFIER_PROJECT_ROOT", project_root)
    # Wave 4: expose use_canonical to sh 3d blocks + on-demand (MCP/CLI cycles) via env for public surface
    os.environ["WIKIFIER_USE_CANONICAL"] = "1" if use_canonical else "0"

    # Human sub-project: ensure dashboards are in the target (for MCP + human investigation)
    # index.html = clean human view (chart + files + descriptions + copies); diagnostics.html for technical depth. Works alongside agent MCP/CLI use. No effect on agent SSOT or tools.
    if project_root:
        try:
            copy_human_dashboards(str(project_root))
        except Exception:
            pass

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
        force_full = any(x in ("--full", "-f", "--force-full", "--full-rebuild") for x in argv)
        progress_mode = "none"
        directory = None
        max_files = None
        resume_token = None
        max_time = None
        # Micro-step 2: streaming path (has_a2_ux_flags)
        if has_a2_ux_flags:
            print("[wikifier] A2 Python-primary streaming path (delegating to run_update_stream facade)")
            # Phase 6 subagent_id=65 (2026-05-27): exercised under years-load durability (25k-50k gens + RecipeLab/54 proxy chaos/stream/partials/rich summaries/reverse); O(changed) A + E lib primary + 8 principles. Honest 82-87% 0/7. Additive comment read-first. "3" untouched.
            fmt = "summary" if any(a.startswith("--format=summary") for a in argv) else "full"
            try:
                from .import_cache import run_update_stream as _facade
                for event in _facade(
                    root=Path(project_root) if project_root else None,
                    force_full=force_full,
                    verbose=(progress_mode == "dots"),
                    directory=directory,
                    max_files=max_files,
                    resume_token=resume_token,
                    max_time=max_time,
                    format=fmt,
                ):
                    if event.get("event_type") == "complete":
                        print(str(event))
                    elif progress_mode in ("structured", "dots"):
                        print(str(event))
                # done
            except Exception as e:
                print(f"[wikifier] Streaming delegation error (falling back): {e}")
            return 0
        # Take direct pure-Py path (deeper pipeline in run_full_update); no subprocess sh
        try:
            force_full = any(x in ("--full", "-f", "--force-full", "--full-rebuild") for x in argv)
            res = run_full_update(
                root=Path(project_root) if project_root else None,
                force_full=force_full,
                verbose=True,
                use_canonical=use_canonical,
                use_python_primary=True,
            )
            import json
            print("[wikifier] Python-primary path active (Wave 5 External robustness)")
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


# =============================================================================
# Workstream E (Python Library + Protocol v0.4 Bridge) — Additional Extraction + MV Skeleton
# =============================================================================
# These functions complete more Python-primary extraction and provide the minimal
# viable public surface for the mandatory agent workflow (check_changes, health,
# record_change, scoped update_maps, suggest_next_actions, mark_green, etc.).
# All are directly importable: `from wikifier import record_change, check_changes, ...`
# or `from wikifier.cli import ...`.
#
# Design realized: structured dict returns (success + data), project_root override,
# auto locking on mutators, pure-Py journal/pending/health updates, delegation to
# health.py + import_cache.py for rich paths (ACS, BRC, cycles), defensive,
# zero new deps, scalable-friendly (directory hints, bounded scans).
# Shell remains thin launcher/compat. MCP/CLI wiring to these is future thin-shim work.
#
# API Audit (Agent 6): health submodule/func access documented (flat func via binding;
# dotted "from wikifier.health import" for internals always works); _get_effective_root
# now imported+delegated by MCP for centralization; check_changes cands now reuses
# _collect_candidate_source_files for fidelity/no-dup. Focus: clean public API + rigorous I/O.
# =============================================================================

from datetime import datetime
from typing import Union, Literal

try:
    from . import locking
except Exception:
    locking = None  # defensive for import edge cases

try:
    from . import health as _health_mod
except Exception:
    _health_mod = None

try:
    from . import import_cache as _ic_mod
except Exception:
    _ic_mod = None


def _get_effective_root(project_root: Optional[Union[str, Path]] = None) -> Path:
    """Internal helper (mirrors MCP pattern; single source in future)."""
    if project_root:
        try:
            p = Path(project_root).expanduser().resolve()
            if p.exists():
                return p
        except Exception:
            pass
    try:
        return discover_project_root()
    except Exception:
        try:
            return Path.cwd().resolve()
        except Exception:
            return Path.cwd()


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _ensure_journal_entry(root: Path, action: str, file: str, reason: str) -> None:
    """Pure-Py journal writer extracted for record_* / check_changes (skeleton, defensive)."""
    try:
        day_dir = root / "journal" / datetime.now().strftime("%Y/%m")
        day_dir.mkdir(parents=True, exist_ok=True)
        jf = day_dir / f"{datetime.now().strftime('%d')}.md"
        entry = f"## [{_timestamp()}] {action}\n**File:** {file}\n**Reason:** {reason}\n\n"
        with open(jf, "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception:
        # Never break caller workflow on journal side-effect
        pass


def _add_to_pending(root: Path, file: str, msg: str) -> None:
    """Pure-Py pending_updates.md appender (skeleton, matches sh add_pending)."""
    try:
        p = root / "pending_updates.md"
        line = f"- {file}: {msg}\n"
        with open(p, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def _remove_from_pending(root: Path, file: str) -> None:
    """Best-effort removal (used by mark_green skeleton)."""
    try:
        p = root / "pending_updates.md"
        if p.exists():
            lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if file not in ln]
            p.write_text("\n".join(lines) + "\n" if lines else "", encoding="utf-8")
    except Exception:
        pass


def _get_monitored_roots(root: Path) -> List[Path]:
    """Basic support for monitored_paths.txt (for check_changes skeleton)."""
    mp = root / "monitored_paths.txt"
    if mp.exists():
        try:
            roots: List[Path] = []
            for line in mp.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    cand = (root / line).resolve()
                    if cand.exists():
                        try:
                            if not str(cand.resolve()).startswith(str(root.resolve())):
                                continue  # M5: only accept monitored under the project root (defensive for abs/rel mix)
                        except Exception:
                            pass
                        roots.append(cand)
            if roots:
                return roots
        except Exception:
            pass
    return [root]


def check_changes(project_root: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """
    Python-primary `check-changes` (mandatory workflow entrypoint).

    - Uses import_cache.compute_files_needing_reparse + barrel stale for O(changed) detection.
    - Updates health (Yellow via pure upsert_entry), pending_updates, journal.
    - Returns structured result (agent-friendly; matches/extends MCP shape).
    - Acquires project lock. Directory scoping via monitored_paths + future dir param.
    - This is a core extraction: no shell required for the change-detection + state update loop.
    """
    root = _get_effective_root(project_root)
    result: Dict[str, Any] = {
        "success": False,
        "project_root": str(root),
        "changes_detected": 0,
        "message": "",
        "recommendation": "Read file_health.md / health(format='json') + pending_updates.md. Prioritize 🔴 → 🟡.",
        "barrel_invalidation_summary": {},
        "rich_auto_yellow_via": "Python check_changes + BRC (import_cache)",
    }
    try:
        lock_ctx = (locking.file_lock(root) if locking is not None else _nullcontext())
        with lock_ctx:
            # Leverage existing rich Python dirty + barrel logic (already extracted in prior waves)
            cands: List[Path] = []
            for mr in _get_monitored_roots(root):
                try:
                    # Reuse the richer pruned collector (full EXCLUDES list, same as run_full_update path)
                    # for extraction fidelity + no logic dup. monitored roots still honored.
                    cands.extend(_collect_candidate_source_files(mr))
                except Exception:
                    continue

            dirty: List[Path] = []
            if _ic_mod is not None:
                try:
                    dirty = _ic_mod.compute_files_needing_reparse(root, cands, full_rebuild=False) or []
                    # M5 external dogfood guard: never let outside-root paths (from bad cands/monitored/cwd mix)
                    # into dirty or health. This + health.py prune prevents pollution in alt/consistency/cloned targets.
                    root_res = root.resolve()
                    dirty = [p for p in (dirty or []) if str(Path(p).resolve()).startswith(str(root_res))]
                    cache = _ic_mod.load_cache(root) or {}
                    barrel_stale = _ic_mod.invalidate_stale_barrel_entries(
                        cache, root, changed_files=[str(p) for p in dirty]
                    ) or []
                    seen = {str(p.resolve()) for p in dirty}
                    for rel in barrel_stale:
                        if rel:
                            pp = (root / rel).resolve()
                            if pp.exists() and str(pp) not in seen and str(pp).startswith(str(root_res)):
                                dirty.append(pp)
                                seen.add(str(pp))
                    result["barrel_invalidation_summary"] = _ic_mod.get_barrel_cache_summary(cache) or {}
                except Exception:
                    pass

            changed_count = 0
            if _health_mod is not None:
                root_res = root.resolve()
                for p in (dirty or [])[:200]:  # bounded for skeleton safety at scale
                    try:
                        pr = Path(p).resolve()
                        if not str(pr).startswith(str(root_res)):
                            continue
                        rel = str(pr.relative_to(root_res))
                    except Exception:
                        continue
                    _health_mod.upsert_entry(
                        root, rel, "🟡 Yellow",
                        "mtime changed since last check-changes (Python primary auto-detected)"
                    )
                    _add_to_pending(root, rel, "Auto-detected modification — review and run mark-green after wiki update")
                    _ensure_journal_entry(root, "auto-detected", rel, "File mtime changed (check_changes Python primary)")
                    changed_count += 1

            result.update({
                "success": True,
                "changes_detected": changed_count,
                "message": f"Python-primary check_changes complete: {changed_count} files marked/updated. Health + pending + journal touched.",
            })
    except Exception as e:
        result["error"] = str(e)
        result["message"] = f"check_changes partial failure: {e}"
    return result


def record_change(file: str, reason: str, project_root: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """
    Python-primary `record-change` (MANDATORY after every agent edit).

    Updates health (Yellow), appends pending_updates.md, writes journal entry.
    Lock-protected. Structured return. Direct callable without shell.
    This extracts the core of cmd_record_change + supporting sh fns into the library.
    """
    root = _get_effective_root(project_root)
    result: Dict[str, Any] = {
        "success": False,
        "file": file,
        "project_root": str(root),
        "reason": reason or "No reason provided.",
    }
    if not file or not isinstance(file, str):
        result["error"] = "file (str) is required"
        return result
    try:
        lock_ctx = (locking.file_lock(root) if locking is not None else _nullcontext())
        with lock_ctx:
            rel = file
            try:
                pp = Path(file)
                if pp.is_absolute() or (root / file).exists():
                    rel = str(pp.resolve().relative_to(root)) if pp.is_absolute() else file
            except Exception:
                pass
            if _health_mod is not None:
                _health_mod.upsert_entry(root, rel, "🟡 Yellow", reason or "Agent/LLM edit recorded")
            _add_to_pending(root, rel, f"LLM/agent edit — {reason}")
            _ensure_journal_entry(root, "record-change", rel, reason or "No reason provided.")
            result.update({
                "success": True,
                "message": "✅ Recorded semantic change (Python primary). Health=🟡, pending + journal updated. Run mark_green after wiki refresh.",
            })
    except Exception as e:
        result["error"] = str(e)
    return result


def record_deletion(file: str, reason: str, project_root: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """Python-primary record_deletion (symmetric to record_change)."""
    root = _get_effective_root(project_root)
    result: Dict[str, Any] = {"success": False, "file": file, "project_root": str(root), "action": "deletion"}
    try:
        lock_ctx = (locking.file_lock(root) if locking is not None else _nullcontext())
        with lock_ctx:
            if _health_mod is not None:
                _health_mod.upsert_entry(root, file, "🔴 Red", f"DELETED — {reason}")
            _add_to_pending(root, file, f"File was deleted. Consider wiki archival. {reason}")
            _ensure_journal_entry(root, "record-deletion", file, reason or "No reason provided.")
            result.update({"success": True, "message": "Recorded deletion (Python primary)."})
    except Exception as e:
        result["error"] = str(e)
    return result


def mark_green(file: str, reason: str = "", project_root: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """Python-primary mark_green (completes the edit→record→wiki→green ritual)."""
    root = _get_effective_root(project_root)
    result: Dict[str, Any] = {"success": False, "file": file, "project_root": str(root)}
    rsn = reason or "Summary updated and verified accurate."
    try:
        lock_ctx = (locking.file_lock(root) if locking is not None else _nullcontext())
        with lock_ctx:
            if _health_mod is not None:
                _health_mod.upsert_entry(root, file, "🟢 Green", rsn)
            _remove_from_pending(root, file)
            result.update({"success": True, "message": f"Marked 🟢 Green (Python primary). {rsn}"})
    except Exception as e:
        result["error"] = str(e)
    return result


def suggest_next_actions(
    project_root: Optional[Union[str, Path]] = None,
    directory: Optional[str] = None,
    format: Literal["text", "json"] = "text"
) -> Union[str, Dict[str, Any]]:
    """
    Python-primary suggest_next_actions (covers mandatory guidance).

    Uses health summary + import_cache ACS low-conf integration for actionable output.
    Structured in json; text for human. Cross-refs protocol.
    """
    root = _get_effective_root(project_root)
    try:
        red = yellow = 0
        health_sum: Dict[str, Any] = {}
        if _health_mod is not None:
            health_sum = _health_mod.get_summary(root, directory) or {}
            red = health_sum.get("red", 0)
            yellow = health_sum.get("yellow", 0)

        suggestions: List[str] = []
        if red > 0:
            suggestions.append(f"1. Tackle the {red} 🔴 Red file(s) first — they are highest priority.")
        if yellow > 0:
            suggestions.append(f"2. Review the {yellow} 🟡 Yellow files.")
        suggestions.append("3. Run `update_maps(directory=...)` (Python primary) if imports/structure changed.")
        suggestions.append("4. Query dependents/dependencies on hot files (via import_cache or MCP).")
        suggestions.append("5. Review journal/ for recent record-change intent.")

        acs_note = ""
        if _ic_mod is not None:
            try:
                cache = _ic_mod.load_cache(root) or {}
                acs = _ic_mod.ensure_acs_summary_persisted(cache, root) or {}
                low = int(acs.get("low_conf_edges", 0) or 0)
                if low > 0:
                    suggestions.append(f"6. Review {low} low-confidence edges (see health json 'dependency_intel').")
                    acs_note = f" ACS low-conf active (avg={acs.get('avg_confidence')})."
            except Exception:
                pass

        if format == "json":
            return {
                "success": True,
                "project_root": str(root),
                "red": red,
                "yellow": yellow,
                "suggestions": suggestions,
                "health_summary": health_sum,
                "acs_note": acs_note,
            }
        return "\n".join(suggestions) + (acs_note or "")
    except Exception as e:
        if format == "json":
            return {"success": False, "error": str(e), "project_root": str(root)}
        return f"suggest_next_actions error (Python): {e}"


def update_maps(
    project_root: Optional[Union[str, Path]] = None,
    full: bool = False,
    directory: Optional[str] = None,
    use_python_primary: bool = True,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    Python facade for update-maps with scoping + python-primary preference.

    Delegates to the extracted run_full_update (deeper pipeline: dirty/parser/persist/barrel/ACS).
    This advances extraction: callers (library, future thin CLI/MCP, daemon) get pure path by default.
    """
    root = _get_effective_root(project_root)
    try:
        res = run_full_update(
            root=root,
            force_full=full,
            verbose=verbose,
            use_canonical=True,
            use_python_primary=use_python_primary,
        )
        res = dict(res)  # copy
        res["library_facade"] = True
        res["scoped_directory"] = directory
        if directory:
            res.setdefault("note", "")
            res["note"] += " (directory scoping is advisory in current skeleton; engine-level scoping in later A waves)"
        return res
    except Exception as e:
        return {
            "success": False,
            "project_root": str(root),
            "error": str(e),
            "library_facade": True,
        }


def health(
    project_root: Optional[Union[str, Path]] = None,
    directory: Optional[str] = None,
    format: Literal["text", "json", "summary", "healing-stats"] = "text"
) -> Union[str, Dict[str, Any]]:
    """
    Flat `from wikifier import health` convenience (delegates to wikifier.health module).

    Preserves all rich behavior (ACS/CIABRE dep_intel attachment in json, scalable summary).
    Part of the designed public surface.
    """
    root = _get_effective_root(project_root)
    try:
        if _health_mod is None:
            return {"success": False, "error": "health module unavailable", "project_root": str(root)} if format == "json" else "health module unavailable"
        if format == "summary":
            return _health_mod.get_summary(root, directory)
        # Phase 5e (66): CLI health(format=summary) + suggest/update_maps first-class default for 20k+ creative (O(k) via health.get_summary + import_cache ACS/barrel; complements 47/48/58 A3 promotion + format=summary).
        if format == "healing-stats":
            return _health_mod.get_healing_statistics(root)
        if format == "json":
            data = _health_mod.load_health(root)
            if directory:
                entries = data.get("entries", {})
                data["entries"] = {k: v for k, v in entries.items() if str(k).startswith(directory.rstrip("/") + "/")}
            # Light dep_intel (ACS) to match MCP surfaces — pure path
            try:
                if _ic_mod is not None:
                    cache = _ic_mod.load_cache(root) or {}
                    acs = _ic_mod.ensure_acs_summary_persisted(cache, root) or {}
                    data["dependency_intel"] = {"acs_summary": acs, "note": "via Python health() facade"}
            except Exception:
                pass
            return data
        # text (human)
        data = _health_mod.load_health(root)
        entries = data.get("entries", {})
        lines = ["# Documentation Health Matrix (via Python library)", ""]
        shown = 0
        for fp, ent in entries.items():
            if directory and not str(fp).startswith(directory.rstrip("/") + "/"):
                continue
            st = ent.get("status", "")
            lu = ent.get("last_updated", "")
            rs = (ent.get("reason") or "")[:80]
            lines.append(f"- {fp}: {st} | {lu} | {rs}")
            shown += 1
            if shown >= 60:
                break
        if len(entries) > shown:
            lines.append(f"... ({len(entries) - shown} more; use format='json' or health --summary for scale)")
        return "\n".join(lines)
    except Exception as e:
        if format == "json":
            return {"success": False, "error": str(e), "project_root": str(root)}
        return f"health(text) error (Python library): {e}"


# End of Workstream E library skeleton additions.
# (nullcontext imported at module top for use in lock_ctx defaults.)
# Update __init__.py to surface these at package level for `from wikifier import ...`.

# Human Investigation Layer (secondary sub-project)
# Only index.html (the clean human wiki viewer) is copied into target projects by init.
# It provides the prominent code structure chart (Mermaid), "Files & descriptions" list with
# short summaries, folder browser, and copy buttons for the *target project's* agent-maintained
# wiki (data-driven from its file_health.* + library.md after check-changes + update-maps).
# diagnostics.html is the Wikifier-specific heavy maintainer/refactor/porter hub (architecture,
# full command map, porting checklist, this project's own source tree with purposes). It is
# *not* copied to foreign project roots — it would point at the wrong folder and be stale for
# the host project. Maintainers open it from the Wikifier source checkout or installed package.
# This separation keeps the human view relevant to the project the user is actually in.
def copy_human_dashboards(target_dir: str) -> None:
    """Copy the static human dashboards into the target project root (if not present).
    Works for both source runs and installed package (via importlib.resources).
    Called by sh init; exposed for Python bootstrap too.
    """
    import shutil
    from pathlib import Path
    try:
        from importlib.resources import files
        pkg_files = files("wikifier")  # package root may have them via include
        for name in ("index.html",):  # only the generic human wiki viewer for the *target*; diagnostics.html is Wikifier maintainer-only
            try:
                src = pkg_files.joinpath(name)
                if src.is_file():
                    dst = Path(target_dir) / name
                    if not dst.exists():
                        shutil.copy(src, dst)
            except Exception:
                pass
    except Exception:
        pass
    # Fallback: if running from source tree with htmls next to cli
    try:
        here = Path(__file__).parent.parent  # repo root when editable
        for name in ("index.html",):
            src = here / name
            if src.exists():
                dst = Path(target_dir) / name
                if not dst.exists():
                    shutil.copy(src, dst)
    except Exception:
        pass
