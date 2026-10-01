"""
Wikifier library API — the functions agents call (the CLI and MCP server are thin
wrappers over these).

Workflow  check_changes → edit → record_change → refresh wiki → mark_green
Maps      update_maps / run_full_update
Lookup    session_bootstrap, prepare_edit, suggest_next_actions, why_file,
          search_journal, list_paths, get_dependencies, get_dependents, cycles_report
Setup     init_project, health, cache_status, heal_stubs, journal, issues

Contract: every function returns a dict containing ``success``. Operational
failures (unknown project root, missing file, lock timeout, I/O errors) return
``{"success": False, "error": ..., "error_type": ...}`` — they never fall back
to another directory or report success after a failed write.
"""

from __future__ import annotations

import fnmatch
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional, Union

from . import cache_store as cs
from . import health_pkg as health_mod
from . import import_cache as ic
from . import journal as journal_mod
from . import locking
from .candidates import (
    candidate_list_meta,
    collect_candidate_source_files,
    resolve_candidates,
    resolve_map_scope,
    scope_fingerprint,
)
from .paths import ProjectPathError, ProjectRootError, resolve_root, to_rel
from .project_root import discover_project_root  # noqa: F401 — public re-export

PathArg = Union[str, Path]

# Historical private name used by the MCP layer and older callers.
_get_effective_root = resolve_root

GREEN = health_mod.GREEN
YELLOW = health_mod.YELLOW
RED = health_mod.RED


def _fail(result: Dict[str, Any], exc: BaseException) -> Dict[str, Any]:
    """Mark ``result`` failed with a typed, human-readable error."""
    result["success"] = False
    result["error"] = str(exc) or type(exc).__name__
    result["error_type"] = type(exc).__name__
    if isinstance(exc, locking.LockTimeoutError):
        result["timed_out"] = True
    return result


def _in_directory(path: str, directory: Optional[str]) -> bool:
    if not directory:
        return True
    prefix = directory.rstrip("/")
    return path == prefix or path.startswith(prefix + "/")


# =============================================================================
# update-maps pipeline
# =============================================================================

def _pair_from_parser_edge(edge: Dict[str, Any], root: Path) -> Optional[Dict[str, Any]]:
    """Normalize one parser edge into the canonical ``resolved_pairs`` shape.

    ``resolved`` is a project-relative path, or "" when unresolved (never the
    display module name — that would invent fake internal edges).
    """
    if not isinstance(edge, dict):
        return None
    raw = edge.get("raw_module") or edge.get("module") or edge.get("raw") or ""
    resolved = ""
    target = edge.get("resolved_path")
    if target:
        path = Path(target)
        if not path.is_absolute():  # parsers may report root-relative targets
            path = root / path
        try:
            resolved = path.resolve().relative_to(root).as_posix()
        except ValueError:
            resolved = ""  # outside the project: external, not an internal edge
    pair: Dict[str, Any] = {
        "raw": str(raw),
        "resolved": resolved,
        "confidence": str(edge.get("resolution_confidence") or edge.get("confidence") or "low"),
        "is_dynamic": bool(edge.get("is_dynamic")),
        "is_conditional": bool(edge.get("is_conditional")),
        "via_barrel": bool(edge.get("via_barrel")),
        "barrel_depth": int(edge.get("barrel_depth") or 0),
    }
    if edge.get("dynamic_type"):
        pair["dynamic_type"] = edge["dynamic_type"]
    for key in (
        "confidence_score", "confidence_reasons", "confidence_explanation",
        "barrel_v2", "resolution_metadata", "strategy", "cdia_v1",
        "conditional_analysis", "dynamic_analysis", "diagnostic",
        "imported_names", "barrel_leaf_selection", "line",
    ):
        value = edge.get(key)
        if value not in (None, "", [], {}):
            pair[key] = value
    return pair


def _dedupe_pairs(pairs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Collapse duplicate (raw, resolved) pairs, keeping the most confident one."""
    best: Dict[tuple, Dict[str, Any]] = {}
    order: List[tuple] = []
    for pair in pairs:
        key = (pair.get("raw"), pair.get("resolved"))
        if key not in best:
            best[key] = pair
            order.append(key)
            continue
        current = best[key]
        if float(pair.get("confidence_score") or 0) > float(current.get("confidence_score") or 0):
            merged = dict(pair)
        else:
            merged = dict(current)
        merged["is_dynamic"] = bool(current.get("is_dynamic") or pair.get("is_dynamic"))
        merged["is_conditional"] = bool(current.get("is_conditional") or pair.get("is_conditional"))
        best[key] = merged
    return [best[k] for k in order]


def _resolved_targets_from_entry(entry: Any) -> List[str]:
    """Distinct project-relative targets of a per-file cache entry."""
    if not isinstance(entry, dict):
        return []
    out: List[str] = []
    for pair in entry.get("resolved_pairs") or []:
        target = str(pair.get("resolved") or "") if isinstance(pair, dict) else str(pair or "")
        if target and target not in out:
            out.append(target)
    return out


def _parser_for(path: str):
    """The import parser for a source file, or None for unsupported suffixes."""
    from .parsers import c_cpp, csharp, go_lang, java, javascript, python, rust

    low = path.lower()
    if low.endswith((".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs", ".mts", ".cts")):
        return javascript.parse_javascript_imports
    if low.endswith(".py"):
        return python.parse_python_imports
    if low.endswith(".rs"):
        return rust.parse_rust_imports
    if low.endswith(".go"):
        return go_lang.parse_go_imports
    if low.endswith((".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".hh")):
        return c_cpp.parse_c_cpp_imports
    if low.endswith(".cs"):
        return csharp.parse_csharp_imports
    if low.endswith(".java"):
        return java.parse_java_imports
    return None


def _save_scope_meta(root: Path, result: Dict[str, Any], directory: Optional[str], cands: List[Path], reused: bool) -> None:
    cs.save_meta_key(root, "_map_coverage", result["map_coverage"])
    if cands and not reused:
        cs.save_meta_key(root, "_candidate_list", candidate_list_meta(root, directory, cands))
    scope = resolve_map_scope(root, directory)
    if not scope.is_full_tree:
        pruned = cs.prune_file_index_outside_scope(root, list(scope.rel_prefixes), is_full_tree=False)
        if pruned:
            result["index_pruned_outside_scope"] = pruned


def run_full_update(
    root: Optional[Path] = None,
    force_full: bool = True,
    verbose: bool = False,
    use_canonical: bool = True,
    use_python_primary: bool = True,
    directory: Optional[str] = None,
    max_files: Optional[int] = None,
    time_budget_s: Optional[float] = None,
    progress: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """The update-maps pipeline.

    1. collect candidate sources (map_paths / directory / full walk; exclude_patterns)
    2. dirty detection from the light mtime index, plus importers of stale barrels
    3. parse every dirty file in-process (barrel cache flushed once per run)
    4. persist per-file entries + reverse index, cycles, cycle analyses, ACS
    5. regenerate library.md and the sharded agent folder maps

    ``max_files`` / ``time_budget_s`` cap parsing; the result reports
    ``files_skipped`` and ``map_complete`` — re-run until ``map_complete`` is
    true (already-parsed files are not dirty on the next run, so re-running
    resumes). ``progress`` is called with ``{"file", "edges", "index", "total"}``
    after each parsed file.
    ``use_python_primary`` is accepted for compatibility and ignored.
    """
    root = Path(root).resolve() if root is not None else resolve_root()
    os.environ["WIKIFIER_PROJECT_ROOT"] = str(root)
    result: Dict[str, Any] = {
        "success": False,
        "root": str(root),
        "mode": "full" if force_full else "incremental",
        "parseable_files": 0,
        "files_to_reparse": 0,
        "files_parsed": 0,
        "files_skipped": 0,
        "edges_persisted": 0,
        "timestamp": datetime.now().isoformat(),
        "use_canonical": use_canonical,
    }

    def say(msg: str) -> None:
        if verbose:
            print(f"[update-maps] {msg}")

    try:
        if not cs.has_sqlite(root) and cs.json_path(root).is_file():
            legacy = cs.load_cache_dict(root)
            if legacy:
                cs.save_cache_dict(root, legacy)
                result["cache_migrated_to_sqlite"] = True

        # 1. Collect
        index = ic.load_mtime_index(root) or None
        cres = resolve_candidates(
            root,
            directory=directory,
            force_full=force_full,
            index=index,
            meta=cs.load_meta(root, keys=("_candidate_list",)),
        )
        cands: List[Path] = list(cres.get("paths") or [])
        cand_reused = bool(cres.get("reused"))
        result.update({
            "parseable_files": len(cands),
            "candidates_reused": cand_reused,
            "index_first_dirty": bool(cres.get("index_first")),
            "candidates_relisted": bool(cres.get("relisted")),
            "scope_fingerprint": cres.get("fingerprint") or scope_fingerprint(root, directory),
        })
        if directory:
            result["scoped_directory"] = directory
        say(f"{len(cands)} candidate sources (reused={cand_reused}, reason={cres.get('reason')})")

        # 2. Dirty
        content_stable: List[tuple] = []
        dirty = ic.compute_files_needing_reparse(
            root, cands, full_rebuild=force_full, content_stable_mtime_updates=content_stable
        )
        if dirty:
            barrel_meta = cs.load_meta(
                root, keys=("_barrel_resolutions", "_barrel_file_index", "_barrel_invalidation_log")
            )
            if barrel_meta.get("_barrel_resolutions") or barrel_meta.get("_barrel_file_index"):
                seen = {str(p) for p in dirty}
                for rel in ic.invalidate_stale_barrel_entries(
                    barrel_meta, root, changed_files=[str(p) for p in dirty]
                ) or []:
                    path = (root / rel).resolve()
                    if path.exists() and str(path) not in seen:
                        dirty.append(path)
                        seen.add(str(path))
        result["dirty_total"] = result["files_to_reparse"] = len(dirty)
        result["dirty_sample"] = [str(p) for p in dirty[:3]]
        if max_files is not None and len(dirty) > int(max_files):
            result["files_skipped"] = len(dirty) - int(max_files)
            dirty = dirty[: int(max_files)]
        if content_stable:
            cs.update_file_index_rows(root, [(r, int(m), h) for r, m, h in content_stable])
            result["content_stable_mtime_refreshes"] = len(content_stable)

        # Mapped files that no longer exist on disk must leave the graph on any run.
        vanished = sorted(rel for rel in (index or {}) if not (root / rel).exists())
        if vanished:
            result["files_removed"] = len(vanished)
        if not dirty and not vanished and not force_full:
            return _zero_dirty_result(root, result, directory, max_files, cands, cand_reused)

        # 3. Parse
        from .parsers import bree
        from .resolution import to_canonical_rel

        new_entries: Dict[str, Dict[str, Any]] = {}
        parse_errors: List[Dict[str, str]] = []
        lang_counts: Dict[str, int] = {}
        edges_total = 0
        started = time.monotonic()
        bree.begin_batch()
        try:
            for index, path in enumerate(dirty):
                if time_budget_s is not None and time.monotonic() - started > time_budget_s:
                    result["files_skipped"] = int(result.get("files_skipped") or 0) + len(dirty) - index
                    result["time_budget_hit"] = True
                    break
                fstr = str(path)
                parser = _parser_for(fstr)
                if parser is None:
                    continue
                try:
                    edges = parser(fstr) or []
                except Exception as exc:  # one bad file must not abort the map
                    parse_errors.append({"file": fstr, "error": f"{type(exc).__name__}: {exc}"})
                    continue
                rel = to_canonical_rel(path, root, follow_symlinks=True) or Path(fstr).resolve().relative_to(root).as_posix()
                pairs = _dedupe_pairs([p for p in (_pair_from_parser_edge(e, root) for e in edges) if p])
                entry: Dict[str, Any] = {
                    "mtime": ic.get_mtime_ns(path),
                    "imports": [p.get("raw", "") for p in pairs],
                    "resolved": [p["resolved"] for p in pairs if p.get("resolved")],
                    "resolved_pairs": pairs,
                }
                content_hash = ic.compute_file_content_hash(path)
                if content_hash:
                    entry["content_hash"] = content_hash
                new_entries[rel] = entry
                edges_total += len(pairs)
                if progress is not None:
                    progress({"file": rel, "edges": len(pairs), "index": index + 1, "total": len(dirty)})
                suffix = Path(fstr).suffix.lower() or "unknown"
                lang_counts[suffix] = lang_counts.get(suffix, 0) + 1
                if verbose and len(new_entries) % 200 == 0:
                    say(f"parsed {len(new_entries)}/{len(dirty)}")
        finally:
            bree.end_batch()
        result.update({
            "files_parsed": len(new_entries),
            "edges_persisted": edges_total,
            "languages_parsed": lang_counts,
        })
        if parse_errors:
            result["parse_errors"] = parse_errors[:10]
            result["parse_error_count"] = len(parse_errors)

        # 4. Persist + graph intelligence (reload first to pick up the barrel flush)
        with locking.file_lock(root):
            cache = ic.load_cache(root)
            for rel in vanished:
                ic.remove_file_from_graph(cache, rel)
            old_targets = {src: _resolved_targets_from_entry(cache.get(src)) for src in new_entries}
            cache.update(new_entries)
            if force_full and not directory and not max_files:
                valid = {to_canonical_rel(p, root, follow_symlinks=True) for p in cands}
                for stale in [k for k in cache if not k.startswith("_") and k not in valid]:
                    cache.pop(stale, None)
            if force_full or not ic.get_reverse_dependencies(cache):
                ic.set_reverse_dependencies(cache, ic.rebuild_reverse_dependencies(cache))
                result["reverse_incremental"] = False
            else:
                for src, entry in new_entries.items():
                    ic.maintain_reverse_dependencies_for_source(
                        cache, src, old_targets.get(src) or [], _resolved_targets_from_entry(entry)
                    )
                result["reverse_incremental"] = True
            cycles = ic.compute_cycles(cache, root=root, use_canonical=use_canonical)
            result["cycles"] = {"count": len(cycles.get("sccs") or []), "reused": bool(cycles.get("reused"))}
            cache["_cycle_analyses"] = ic.compute_cycle_analyses(cache, root=root, use_canonical=use_canonical)
            ic.set_graph_integrity(cache)  # integrity is derived on read; drop stale copies
            ic.set_acs_summary(cache, ic.compute_acs_summary(cache))  # edges changed: always recompute
            cache["_resolution_diagnostics"] = ic.get_resolution_diagnostics(cache)
            ic.save_cache(root, cache)
        result["persist_pipeline_exercised"] = True

        # 4b. Map-first health stubs
        max_seed = int(os.environ.get("WIKIFIER_HEALTH_SEED_MAX", "20000") or "20000")
        map_keys = [k for k in cache if isinstance(k, str) and k and not k.startswith("_")]
        seeded = int(health_mod.seed_health_from_map(root, map_keys=map_keys, max_new=max_seed).get("seeded") or 0)
        seeded += int(health_mod.seed_health_for_monitored_sources(root, max_new=max_seed).get("seeded") or 0)
        result["health_stubs_seeded"] = seeded

        # 5. Artifacts
        from .library import write_library_md
        from .map_index import ensure_map_index

        result["library"] = write_library_md(root, cache)
        result["map_index"] = ensure_map_index(root, cache, reuse_if_present=False)
        _finish_coverage(root, result, directory, max_files, zero_dirty=False,
                         acs_version=(cache.get("_acs_summary") or {}).get("acs_version"))
        _save_scope_meta(root, result, directory, cands, reused=False)
        result["success"] = True
    except Exception as exc:
        _fail(result, exc)

    say(
        f"done: parsed {result.get('files_parsed')}/{result.get('files_to_reparse')} dirty files, "
        f"{result.get('edges_persisted')} edges, success={result.get('success')}"
    )
    return result


def _finish_coverage(
    root: Path,
    result: Dict[str, Any],
    directory: Optional[str],
    max_files: Optional[int],
    zero_dirty: bool,
    acs_version: Optional[str],
) -> None:
    backend = cs.backend_name(root)
    result["cache_backend"] = backend
    coverage = ic.build_map_coverage(
        dirty_total=int(result.get("dirty_total") or 0),
        files_parsed=int(result.get("files_parsed") or 0),
        files_skipped=int(result.get("files_skipped") or 0),
        files_to_reparse=int(result.get("files_to_reparse") or 0),
        max_files=max_files,
        parseable_files=int(result.get("parseable_files") or 0),
        zero_dirty_fast_path=zero_dirty,
        acs_version=acs_version,
        cache_backend=backend,
        directory=directory,
    )
    result["map_coverage"] = coverage
    result["map_complete"] = bool(coverage.get("complete"))
    result["map_ready"] = result["map_complete"] and int(coverage.get("files_remaining_dirty") or 0) == 0


def _zero_dirty_result(
    root: Path,
    result: Dict[str, Any],
    directory: Optional[str],
    max_files: Optional[int],
    cands: List[Path],
    cand_reused: bool,
) -> Dict[str, Any]:
    """Warm path: nothing changed — reuse persisted summaries, no payload load."""
    result.update({"files_parsed": 0, "edges_persisted": 0, "languages_parsed": {}, "zero_dirty_fast_path": True})
    meta = cs.load_meta(root, keys=("_acs_summary", "_cycles"))
    acs = meta.get("_acs_summary") if isinstance(meta.get("_acs_summary"), dict) else {}
    cycles = meta.get("_cycles") if isinstance(meta.get("_cycles"), dict) else {}
    if not acs or str(acs.get("acs_version") or "") < "1.3" or "reason_code_counts" not in acs:
        cache = ic.load_cache(root)
        acs = ic.ensure_acs_summary_persisted(cache, root) or {}
        cycles = cache.get("_cycles") or {}
    result["acs"] = {
        "acs_version": acs.get("acs_version"),
        "actionable_low_conf_edges": acs.get("actionable_low_conf_edges"),
        "low_conf_edges": acs.get("low_conf_edges"),
        "reason_code_counts": acs.get("reason_code_counts"),
    }
    result["cycles"] = {"count": len(cycles.get("sccs") or []), "reused": True, "fast_path": True}
    lib_path = root / "library.md"
    if lib_path.is_file():
        result["library"] = {"success": True, "path": str(lib_path), "skipped": True, "reason": "zero_dirty_reuse"}
    else:
        from .library import write_library_md

        result["library"] = write_library_md(root, ic.load_cache(root))
    from .map_index import ensure_map_index

    result["map_index"] = ensure_map_index(root, cache=None, reuse_if_present=True)
    result["health_stubs_seeded"] = 0
    result["persist_pipeline_exercised"] = True
    _finish_coverage(root, result, directory, max_files, zero_dirty=True, acs_version=acs.get("acs_version"))
    _save_scope_meta(root, result, directory, cands, reused=cand_reused)
    result["success"] = True
    return result


def update_maps(
    project_root: Optional[PathArg] = None,
    full: bool = False,
    directory: Optional[str] = None,
    use_python_primary: bool = True,
    verbose: bool = False,
    max_files: Optional[int] = None,
) -> Dict[str, Any]:
    """Rebuild the dependency map (incremental unless ``full``)."""
    try:
        root = resolve_root(project_root)
    except ProjectRootError as exc:
        return _fail({"project_root": str(project_root), "library_facade": True}, exc)
    res = dict(run_full_update(
        root=root, force_full=full, verbose=verbose, directory=directory, max_files=max_files,
    ))
    res["library_facade"] = True
    res["scoped_directory"] = directory
    res["project_root"] = str(root)
    return res


# =============================================================================
# Workflow: check_changes / record_change / record_deletion / mark_green
# =============================================================================

# Files Wikifier itself rewrites; never watched or batch-recorded.
_ARTIFACT_NAMES = frozenset({"file_health.json", "file_health.md", "pending_updates.md", "library.md"})
_ARTIFACT_PREFIXES = ("journal/", ".wikifier_staging/")


def _is_wikifier_artifact(rel: str) -> bool:
    return rel in _ARTIFACT_NAMES or rel.startswith(_ARTIFACT_PREFIXES)


def _watch_candidates(root: Path, entries: Optional[Dict[str, Any]] = None) -> List[Path]:
    """Files check_changes watches, deduplicated:

    - every file on the dependency map (import-cache keys);
    - every file with a trusted baseline (anything ever marked Green);
    - monitored_paths.txt entries: files of any type, parseable sources under
      directories (bare ``.`` walks the whole project).

    monitored_paths.txt only adds to the set — a narrow list can no longer hide
    edits to mapped or Green files. Wikifier's own artifacts are never watched.
    """
    seen: Dict[str, Path] = {}

    def add(path: Path) -> None:
        resolved = path.resolve()
        try:
            if _is_wikifier_artifact(resolved.relative_to(root).as_posix()):
                return
        except ValueError:
            return
        seen.setdefault(str(resolved), resolved)

    monitored = health_mod.scope._read_monitored_rel_roots(root)
    if monitored == ["."]:
        for path in collect_candidate_source_files(root, use_map_paths=False, use_monitored=False):
            add(Path(path))
    else:
        for entry in monitored:
            try:
                rel = to_rel(root, entry)
            except ProjectPathError:
                continue
            path = root / rel
            if path.is_file():
                add(path)
            elif path.is_dir():
                for found in collect_candidate_source_files(root, directory=rel):
                    add(Path(found))
    for rel in ic.load_mtime_index(root) or {}:
        if not str(rel).startswith("_") and (root / rel).is_file():
            add(root / rel)
    if entries is None:
        entries = health_mod.load_health(root).get("entries", {})
    for rel, entry in entries.items():
        if isinstance(entry, dict) and entry.get("source_content_hash") and (root / rel).is_file():
            add(root / rel)
    return list(seen.values())


def _check_changes_locked(root: Path, result: Dict[str, Any]) -> None:
    max_dirty = max(1, min(int(os.environ.get("WIKIFIER_CHECK_CHANGES_MAX", "2000") or "2000"), 50000))
    max_ghosts = max(1, min(int(os.environ.get("WIKIFIER_CHECK_CHANGES_GHOST_MAX", "200") or "200"), 10000))

    health = health_mod.load_health(root)
    entries = health.setdefault("entries", {})
    candidates = _watch_candidates(root, entries)
    # Files with a trusted baseline are compared against the mtime recorded with
    # that baseline, not the parse cache: update-maps advances the parse cache, so
    # an edit followed by update-maps would otherwise never be seen here.
    # Files without a baseline (map-first stubs, untracked) use the parse cache.
    parse_dirty = set(ic.compute_files_needing_reparse(root, candidates, full_rebuild=False))
    dirty: List[Path] = []
    for path in candidates:
        if not _is_inside(root, path):
            continue
        entry = entries.get(to_rel(root, path)) or {}
        if entry.get("source_content_hash"):
            if entry.get("source_mtime_ns") != health_mod.source_mtime_ns(path):
                dirty.append(path)
        elif path in parse_dirty:
            dirty.append(path)
    dirty_truncated = len(dirty) > max_dirty

    flagged: List[tuple] = []
    content_dirty_rels: List[str] = []
    skipped_unchanged = 0
    baseline_touched = False
    for path in dirty[:max_dirty]:
        rel = to_rel(root, path)
        entry = entries.get(rel) or {}
        verdict = health_mod.classify_content_dirty(path, entry.get("source_content_hash"))
        if not verdict.get("content_dirty"):
            skipped_unchanged += 1
            if rel in entries and verdict.get("reason") == "content_unchanged":
                # Touched but identical: remember the mtime so it is not re-hashed.
                entries[rel]["source_mtime_ns"] = health_mod.source_mtime_ns(path)
                baseline_touched = True
            continue
        content_dirty_rels.append(rel)
        status = str(entry.get("status") or "")
        already_flagged = ("🟡" in status and not health_mod.summary._is_map_first_stub_entry(entry)) or "🔴" in status
        if already_flagged:
            continue
        reason = (
            "content changed since last mark-green (check-changes)"
            if verdict.get("reason") == "content_changed"
            else "content change with no trusted baseline (check-changes)"
        )
        flagged.append((rel, YELLOW, reason))

    written = health_mod.upsert_entries_batch(root, flagged, health_data=health) if flagged else 0
    if baseline_touched and not written:
        health_mod._do_save_health(root, health)
    if flagged:
        for rel, _status, reason in flagged:
            health_mod._do_add_to_pending(root, rel, "Content change detected — review, refresh wiki, then mark-green")
            journal_mod.append_entry(root, "auto-detected", rel, reason)

    barrel_marked = 0
    if content_dirty_rels:
        barrel_meta = cs.load_meta(root, keys=("_barrel_resolutions", "_barrel_file_index"))
        if barrel_meta:
            reports = ic.get_barrel_invalidation_reports(barrel_meta, root, changed_files=content_dirty_rels) or []
            current = health_mod.load_health(root).get("entries", {})
            reports = [
                r for r in reports
                if r.get("importer") and "🔴" not in str((current.get(r["importer"]) or {}).get("status") or "")
            ]
            barrel_marked = health_mod.apply_barrel_invalidation_reports(root, reports)
        result["barrel_invalidation_summary"] = ic.get_barrel_cache_summary(barrel_meta or {}) or {}

    watched = {to_rel(root, p) for p in candidates if _is_inside(root, p)}
    pruned = health_mod.prune_pending_to_monitored(root, drop_auto_detected=False, keep=watched)
    result["pending_pruned"] = pruned.get("removed", 0)

    ghosts_marked = 0
    for ghost in health_mod.find_ghost_entries(root)[:max_ghosts]:
        health_mod._do_upsert_entry(root, ghost, RED, "DELETED — path missing on disk (check-changes)")
        health_mod._do_add_to_pending(root, ghost, "File missing on disk — run record-deletion or restore it")
        ghosts_marked += 1

    message = f"check_changes: {len(flagged)} file(s) newly flagged Yellow"
    if skipped_unchanged:
        message += f", {skipped_unchanged} touched-but-unchanged skipped"
    if barrel_marked:
        message += f", {barrel_marked} importer(s) flagged via barrel re-exports"
    if ghosts_marked:
        message += f", {ghosts_marked} missing file(s) marked Red"
    if dirty_truncated:
        message += f". Dirty set truncated to {max_dirty} of {len(dirty)} (WIKIFIER_CHECK_CHANGES_MAX)"
    result.update({
        "success": True,
        "changes_detected": len(flagged),
        "content_dirty": len(content_dirty_rels),
        "changed_files": [rel for rel, _, _ in flagged][:50],
        "dirty_total": len(dirty),
        "dirty_truncated": dirty_truncated,
        "max_dirty": max_dirty,
        "ghosts_marked": ghosts_marked,
        "barrel_importers_marked": barrel_marked,
        "skipped_mtime_only": skipped_unchanged,
        "content_honest": True,
        "message": message + ".",
    })


def _is_inside(root: Path, path: Path) -> bool:
    try:
        Path(path).resolve().relative_to(root)
        return True
    except ValueError:
        return False


def check_changes(project_root: Optional[PathArg] = None, timeout: Optional[float] = None) -> Dict[str, Any]:
    """Detect content changes under monitored_paths and flag them Yellow.

    Content-honest: an mtime touch with identical bytes (vs the mark-green
    baseline) is not a change. Already-flagged rows are not re-journaled.
    Missing files become Red; importers of a changed barrel become Yellow.
    """
    result: Dict[str, Any] = {
        "success": False,
        "project_root": str(project_root or ""),
        "changes_detected": 0,
        "message": "",
        "recommendation": "Read health(format='json') + pending_updates.md. Prioritize 🔴 → 🟡.",
        "barrel_invalidation_summary": {},
    }
    try:
        root = resolve_root(project_root)
        result["project_root"] = str(root)
        with locking.file_lock(root, timeout=timeout):
            _check_changes_locked(root, result)
    except Exception as exc:
        _fail(result, exc)
        result["message"] = f"check_changes failed: {result['error']}"
    return result


def record_change(
    file: str,
    reason: str,
    project_root: Optional[PathArg] = None,
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """Record why ``file`` was edited (journal + Yellow + pending). Required after edits."""
    reason = " ".join(str(reason or "").split()) or "No reason provided."
    result: Dict[str, Any] = {"success": False, "file": file, "project_root": str(project_root or ""), "reason": reason}
    try:
        root = resolve_root(project_root)
        result["project_root"] = str(root)
        rel = to_rel(root, file)
        result["file"] = rel
        if not (root / rel).exists():
            raise FileNotFoundError(f"file not found: {rel} (use record_deletion for removed files)")
        with locking.file_lock(root, timeout=timeout):
            journaled = journal_mod.append_entry(root, "record-change", rel, reason)
            health_mod._do_record_meaningful_edit(root, rel, reason)
            health_mod._do_add_to_pending(root, rel, f"LLM/agent edit — {reason}")
        result.update({
            "success": True,
            "journaled": journaled,
            "duplicate_skipped": not journaled,
            "needs_mark_green": True,
            "message": f"Recorded change to {rel}: Yellow, pending + journal updated. Refresh its wiki, then mark_green.",
        })
    except Exception as exc:
        _fail(result, exc)
    return result


def record_deletion(
    file: str,
    reason: str,
    project_root: Optional[PathArg] = None,
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """Record an intentional deletion: Red audit row, pending, journal, graph cleanup."""
    reason = " ".join(str(reason or "").split()) or "No reason provided."
    result: Dict[str, Any] = {"success": False, "file": file, "project_root": str(project_root or ""), "action": "deletion"}
    try:
        if not file or str(file).startswith("-"):
            raise ProjectPathError("file must be a project path, not a flag or empty string")
        root = resolve_root(project_root)
        result["project_root"] = str(root)
        rel = to_rel(root, file)
        result["file"] = rel
        with locking.file_lock(root, timeout=timeout):
            journal_mod.append_entry(root, "record-deletion", rel, reason)
            health_mod._do_upsert_entry(root, rel, RED, f"DELETED — {reason}")
            health_mod._do_add_to_pending(root, rel, f"File was deleted. Archive or remove its wiki. {reason}")
            graph = {"removed_entry": False}
            if cs.backend_name(root) != "none":
                cache = ic.load_cache(root)
                graph = ic.remove_file_from_graph(cache, rel)
                if graph["removed_entry"]:
                    ic.save_cache(root, cache)
        result.update({
            "success": True,
            "still_exists_on_disk": (root / rel).exists(),
            "graph_cleanup": graph,
            "barrel_prune": ic.prune_barrel_resolutions(root, deleted_files=[rel]) or {},
            "message": f"Recorded deletion of {rel}.",
        })
    except Exception as exc:
        _fail(result, exc)
    return result


def mark_green(
    file: str,
    reason: str = "",
    project_root: Optional[PathArg] = None,
    timeout: Optional[float] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Mark ``file`` Green after its wiki is refreshed (captures content baselines).

    The wiki is first checked against the code (see ``health_pkg.verify``): if
    the public surface changed and the wiki does not reflect it, the call fails
    with ``error_type: "WikiVerificationError"`` and ``issues``. ``force=True``
    overrides with an explicit ``reason`` and records ``verification: "forced"``.
    """
    explicit = " ".join(str(reason or "").split())
    reason = explicit or "Summary updated and verified accurate."
    result: Dict[str, Any] = {"success": False, "file": file, "project_root": str(project_root or "")}
    try:
        root = resolve_root(project_root)
        result["project_root"] = str(root)
        rel = to_rel(root, file)
        result["file"] = rel
        if force and not explicit:
            raise ValueError("force=True needs a reason explaining why the wiki is still accurate")
        with locking.file_lock(root, timeout=timeout):
            check = health_mod._do_mark_green_checked(root, rel, reason, force=force)
        result.update({
            "success": True,
            "verification": check["verification"],
            "warnings": check["warnings"],
            "symbol_coverage": check["coverage"],
            "message": f"Marked {rel} 🟢 Green ({check['verification']}). {reason}",
        })
        if check["verification"] == health_mod.verify.FORCED:
            result["overridden_issues"] = check["issues"]
    except health_mod.WikiVerificationError as exc:
        _fail(result, exc)
        result.update({
            "issues": exc.check["issues"],
            "warnings": exc.check["warnings"],
            "wiki_file": exc.check["wiki_file"],
            "hint": "Update the wiki for the listed symbols, then mark_green again "
                    "(or force=True with a reason if the wiki is already accurate).",
        })
    except Exception as exc:
        _fail(result, exc)
    return result


def _batch_skip(rel: str) -> bool:
    """Wikifier artifacts and wiki files are documentation, not changes to record."""
    return _is_wikifier_artifact(rel) or rel.endswith(".wiki.md")


def _reason_for(rel: str, reasons: Dict[str, str], used: set) -> Optional[str]:
    """Exact path first, then the longest matching glob or ``dir/`` prefix."""
    if reasons.get(rel):
        used.add(rel)
        return reasons[rel]
    best = None
    for pattern, why in reasons.items():
        if not why:
            continue
        hit = (pattern.endswith("/") and rel.startswith(pattern)) or (
            any(ch in pattern for ch in "*?[") and fnmatch.fnmatchcase(rel, pattern)
        )
        if hit and (best is None or len(pattern) > len(best)):
            best = pattern
    if best is None:
        return None
    used.add(best)
    return reasons[best]


def record_changes(
    reasons: Optional[Dict[str, str]] = None,
    default_reason: Optional[str] = None,
    since: Optional[str] = None,
    green: bool = False,
    dry_run: bool = False,
    project_root: Optional[PathArg] = None,
    timeout: Optional[float] = None,
    only: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Record every file git reports as changed, in one call.

    ``reasons`` maps a path, a glob (``tests/*.py``) or a ``dir/`` prefix to a
    reason; exact paths win, then the longest pattern. ``default_reason`` covers
    the rest. If any file is left without a reason nothing is written and the
    result lists ``missing_reasons`` with a fill-in ``template`` — reasons stay
    specific. Deleted and renamed-away files go through ``record_deletion``.

    ``green=True`` then marks each changed file Green through the normal
    wiki verification; files whose wiki does not match stay Yellow and are listed
    in ``verification_failed``. Deleted files whose wiki is gone are retired from
    the health matrix (the journal keeps the deletion).

    ``only`` limits the batch to matching paths (same path / glob / ``dir/``
    rules) — for a working tree that also holds changes you did not make.
    """
    from .gitchanges import changed_files

    result: Dict[str, Any] = {"success": False, "project_root": str(project_root or ""), "dry_run": dry_run}
    try:
        root = resolve_root(project_root)
        result["project_root"] = str(root)
        reasons = {str(k).strip(): " ".join(str(v or "").split()) for k, v in (reasons or {}).items()}
        default_reason = " ".join(str(default_reason or "").split()) or None
        diff = changed_files(root, since)
        result["base"] = diff["base"]

        plan: List[Dict[str, Any]] = []
        skipped: List[str] = []
        used: set = set()

        only_patterns = {str(p).strip(): "x" for p in (only or []) if str(p).strip()}

        def add(rel: str, action: str, status: str, note: str = "") -> None:
            if only_patterns and _reason_for(rel, only_patterns, set()) is None:
                return
            if _batch_skip(rel) or (action == "change" and not (root / rel).is_file()):
                skipped.append(rel)
                return
            why = _reason_for(rel, reasons, used) or default_reason
            plan.append({"file": rel, "action": action, "git_status": status,
                         "reason": (why + note) if why else None})

        for change in diff["changes"]:
            if change["status"] == "deleted":
                add(change["path"], "deletion", "deleted")
            else:
                add(change["path"], "change", change["status"])
            if change["status"] == "renamed":
                add(change["old_path"], "deletion", "renamed", f" (renamed to {change['path']})")

        missing = [p["file"] for p in plan if not p["reason"]]
        result.update({
            "files": len(plan),
            "plan": plan,
            "skipped": skipped,
            "unused_reasons": sorted(k for k in reasons if k not in used),
            "missing_reasons": missing,
        })
        if missing:
            result["template"] = {rel: "" for rel in missing}
        if dry_run:
            result["success"] = True
            result["message"] = f"{len(plan)} file(s) would be recorded; {len(missing)} without a reason."
            return result
        if missing:
            raise ValueError(
                f"{len(missing)} changed file(s) have no reason; pass reasons (path or glob → reason) "
                "or default_reason. Nothing was recorded."
            )

        recorded: List[str] = []
        deleted: List[str] = []
        errors: List[Dict[str, Any]] = []
        greened: List[Dict[str, Any]] = []
        failed: List[Dict[str, Any]] = []
        retired: List[str] = []
        with locking.file_lock(root, timeout=timeout):
            for item in plan:
                fn = record_deletion if item["action"] == "deletion" else record_change
                res = fn(item["file"], item["reason"], project_root=root)
                if not res.get("success"):
                    errors.append({"file": item["file"], "error": res.get("error")})
                elif item["action"] == "deletion":
                    deleted.append(res["file"])
                else:
                    recorded.append(res["file"])
            if green:
                for rel in recorded:
                    reason = next(p["reason"] for p in plan if p["file"] == rel)
                    res = mark_green(rel, f"Wiki checked after: {reason}", project_root=root)
                    if res.get("success"):
                        greened.append({"file": rel, "verification": res["verification"]})
                    else:
                        failed.append({"file": rel, "error_type": res.get("error_type"),
                                       "issues": res.get("issues"), "error": res.get("error")})
                health = health_mod.load_health(root)
                entries = health.get("entries", {})
                for rel in deleted:
                    if rel in entries and not (root / rel).exists() and health_mod._find_existing_wiki_file(root, rel) is None:
                        entries.pop(rel, None)
                        health_mod._do_remove_from_pending(root, rel)
                        retired.append(rel)
                if retired:
                    health_mod._do_save_health(root, health)
        result.update({
            "success": not errors,
            "recorded": recorded,
            "deleted": deleted,
            "errors": errors,
            "marked_green": greened,
            "verification_failed": failed,
            "retired_deletions": retired,
            "message": (
                f"Recorded {len(recorded)} change(s) and {len(deleted)} deletion(s)"
                + (f"; {len(greened)} marked Green, {len(failed)} need wiki updates" if green else "")
                + (f"; {len(errors)} error(s)" if errors else "") + "."
            ),
        })
    except Exception as exc:
        _fail(result, exc)
    return result


def verify_wikis(
    project_root: Optional[PathArg] = None,
    directory: Optional[str] = None,
    limit: int = 200,
) -> Dict[str, Any]:
    """Audit Green files' wikis against their code (read-only): failing files,
    Green breakdown by verification kind, average symbol coverage."""
    result: Dict[str, Any] = {"success": False, "project_root": str(project_root or "")}
    try:
        root = resolve_root(project_root)
        result = health_mod.verify_wikis(root, directory=directory, limit=limit)
        result["project_root"] = str(root)
    except Exception as exc:
        _fail(result, exc)
    return result


# =============================================================================
# Lookup / guidance
# =============================================================================

def suggest_next_actions(
    project_root: Optional[PathArg] = None,
    directory: Optional[str] = None,
    format: Literal["text", "json"] = "text",
) -> Union[str, Dict[str, Any]]:
    """Selective next steps: 🔴 then actionable 🟡 only, plus map/ACS hygiene."""
    try:
        root = resolve_root(project_root)
        summary = health_mod.get_summary(root, directory)
        red = int(summary.get("red", 0))
        yellow = int(summary.get("yellow", 0))
        stub_y = int(summary.get("stub_yellow", 0))
        action_y = int(summary.get("actionable_yellow", 0))
        suggestions: List[str] = []
        if red:
            suggestions.append(f"Tackle the {red} 🔴 Red file(s) first. Do not re-wiki 🟢 Green files.")
        if action_y:
            suggestions.append(
                f"Review {action_y} actionable 🟡 Yellow file(s): refresh the wiki for each, then mark-green."
            )
        if stub_y and not action_y and not red:
            suggestions.append(
                f"Map-first OK: {stub_y} 🟡 Initial stubs mean 'on the map', not 'wiki this now'. "
                "Write prose only when you edit a file."
            )
        elif stub_y and action_y:
            suggestions.append(f"Ignore {stub_y} map-first stubs; only actionable yellows need wiki work.")
        if not red and not yellow:
            suggestions.append("Health is clean. Use the map for lookup; do not re-summarize the tree.")
        scope = health_mod.detect_scope_risks(root)
        scope_warnings = list(scope.get("warnings") or [])
        suggestions.extend(f"SCOPE: {w}" for w in scope_warnings[:2])

        meta = cs.load_meta(root, keys=("_acs_summary", "_map_coverage"))
        acs = meta.get("_acs_summary") if isinstance(meta.get("_acs_summary"), dict) else {}
        coverage = meta.get("_map_coverage") if isinstance(meta.get("_map_coverage"), dict) else {}
        actionable = int(acs.get("actionable_low_conf_edges", 0) or 0)
        raw_low = int(acs.get("low_conf_edges", 0) or 0)
        remaining = int(coverage.get("files_remaining_dirty") or 0)
        if coverage.get("complete") is False or remaining:
            suggestions.append(
                f"MAP INCOMPLETE ({remaining} files remaining): re-run update_maps with the same "
                "scope until map_coverage.complete is true."
            )
        acs_note = ""
        if actionable:
            suggestions.append(f"Review {actionable} actionable low-confidence project edges (get_dependencies).")
            acs_note = f" ACS actionable_low={actionable} (raw_low={raw_low}, avg={acs.get('avg_confidence')})."
        elif raw_low:
            acs_note = f" ACS: {raw_low} low-confidence edges are external/stdlib noise; no action needed."
        suggestions.append("Run update_maps only when imports or structure changed (not for wiki-only edits).")
        suggestions.append("Before editing a hotspot, call prepare_edit(file) to see its dependents.")
        suggestions = [f"{i}. {s}" for i, s in enumerate(suggestions, 1)]

        red_files: List[str] = []
        action_yellow_files: List[str] = []
        for path, entry in health_mod.load_health(root).get("entries", {}).items():
            if not _in_directory(path, directory):
                continue
            status = str(entry.get("status") or "")
            if "🔴" in status:
                red_files.append(path)
            elif "🟡" in status and not health_mod.summary._is_map_first_stub_entry(entry):
                action_yellow_files.append(path)
        from .agent_loop import build_structured_actions

        actions = build_structured_actions(
            red_files=red_files,
            actionable_yellow_files=action_yellow_files,
            stub_yellow=stub_y,
            actionable_yellow=action_y,
            red=red,
            acs_actionable=actionable,
            scope_warnings=scope_warnings,
            clean=(red == 0 and yellow == 0),
            map_coverage=coverage,
        )
        if format == "json":
            return {
                "success": True,
                "project_root": str(root),
                "red": red,
                "yellow": yellow,
                "stub_yellow": stub_y,
                "actionable_yellow": action_y,
                "health_score": summary.get("health_score"),
                "suggestions": suggestions,
                "actions": actions,
                "health_summary": summary,
                "acs_note": acs_note,
                "map_coverage": coverage,
                "selective_work": True,
                "map_first": True,
            }
        lines = list(suggestions)
        if actions:
            lines.append("Actions:")
            for action in actions[:12]:
                lines.append(f"  [{action.get('priority')}] {action.get('action')} {action.get('file') or '—'}: {action.get('reason')}")
        return "\n".join(lines) + acs_note
    except Exception as exc:
        failure = _fail({"project_root": str(project_root or "")}, exc)
        return failure if format == "json" else f"suggest_next_actions error: {failure['error']}"


def session_bootstrap(
    project_root: Optional[PathArg] = None,
    directory: Optional[str] = None,
    map_index_file_budget: Optional[int] = None,
) -> Dict[str, Any]:
    """One-shot session start: root, readiness, health, attention, actions[], folder map."""
    from .agent_loop import session_bootstrap as _bootstrap

    return _bootstrap(project_root=project_root, directory=directory, map_index_file_budget=map_index_file_budget)


def list_paths(
    prefix: Optional[str] = None,
    directory: Optional[str] = None,
    project_root: Optional[PathArg] = None,
    max_files: Optional[int] = None,
    depth: int = 1,
) -> Dict[str, Any]:
    """Names-only folder card (depth=1) or recursive listing (depth=0)."""
    try:
        root = resolve_root(project_root)
    except ProjectRootError as exc:
        return _fail({"project_root": str(project_root)}, exc)
    from .map_index import list_paths as _list_paths

    return _list_paths(root, prefix=prefix or directory, max_files=max_files, depth=depth)


def prepare_edit(file: str, project_root: Optional[PathArg] = None) -> Dict[str, Any]:
    """Single-file preflight: status, wiki, dependencies, dependents, cycle flag."""
    from .agent_loop import prepare_edit as _prepare_edit

    return _prepare_edit(file, project_root=project_root)


def search_journal(
    project_root: Optional[PathArg] = None,
    query: Optional[str] = None,
    file: Optional[str] = None,
    max_results: int = 20,
) -> Dict[str, Any]:
    """Search the journal by text and/or file."""
    from .agent_loop import search_journal as _search

    return _search(project_root=project_root, query=query, file=file, max_results=max_results)


def why_file(file: str, project_root: Optional[PathArg] = None, max_results: int = 10) -> Dict[str, Any]:
    """Health reason + recent journal entries for ``file``."""
    from .agent_loop import why_file as _why

    return _why(file, project_root=project_root, max_results=max_results)


def _compact_imports(imports: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Token-lean view of per-edge records: internal targets with only the flags
    that are set, external modules as one name list, and unresolved-but-internal
    looking imports to review."""
    internal: List[Dict[str, Any]] = []
    external: set = set()
    review: List[Dict[str, Any]] = []
    for item in imports:
        raw = item.get("raw") or ""
        if item.get("resolved"):
            edge: Dict[str, Any] = {"path": item["resolved"], "line": item.get("line")}
            if item.get("imported_names"):
                edge["names"] = item["imported_names"]
            if item.get("is_conditional"):
                edge["conditional"] = True
            if item.get("is_dynamic"):
                edge["dynamic"] = item.get("dynamic_type") or True
            if item.get("via_barrel"):
                edge["via_barrel"] = True
            score = item.get("confidence_score")
            if isinstance(score, (int, float)) and score < 0.65:
                edge["confidence"] = score
            if item.get("in_cycle"):
                edge["in_cycle"] = True
            internal.append(edge)
            continue
        diagnostic = item.get("diagnostic") if isinstance(item.get("diagnostic"), dict) else {}
        category = diagnostic.get("category")
        if category in (None, "external_or_bare") and not raw.startswith("."):
            external.add(raw)
        else:
            review.append({"raw": raw, "line": item.get("line"), "category": category or "unresolved",
                           "suggestion": diagnostic.get("suggestion_for_agent")})
    return {"internal": internal, "external": sorted(external), "needs_review": review}


def get_dependencies(
    file: str,
    project_root: Optional[PathArg] = None,
    detail: Literal["compact", "full"] = "compact",
) -> Dict[str, Any]:
    """What ``file`` imports (indexed lookup).

    ``detail="compact"`` (default): ``internal`` edges (path, line, names and only
    the flags that apply), ``external`` module names, ``needs_review``.
    ``detail="full"``: ``imports`` — every per-edge record with confidence
    explanation, resolution metadata and diagnostics (several times larger).
    """
    if detail not in ("compact", "full"):
        raise ValueError("detail must be 'compact' or 'full'")
    result: Dict[str, Any] = {"success": False, "file": file, "project_root": str(project_root or "")}
    try:
        root = resolve_root(project_root)
        rel = to_rel(root, file)
        entry = cs.load_file_entry(root, rel)
        cycles = cs.load_meta(root, keys=("_cycles",)).get("_cycles") or {}
        in_cycle = set(cycles.get("all_cycle_files") or [])
        imports = []
        for pair in (entry or {}).get("resolved_pairs") or []:
            if not isinstance(pair, dict):
                continue
            item = dict(pair)
            item["resolved_path"] = pair.get("resolved") or None
            item["in_cycle"] = bool(pair.get("resolved") and pair["resolved"] in in_cycle and rel in in_cycle)
            imports.append(item)
        result.update({
            "success": True,
            "project_root": str(root),
            "file": rel,
            "mapped": entry is not None,
            "detail": detail,
            "count": len(imports),
            "internal_count": sum(1 for i in imports if i.get("resolved")),
            "file_in_cycle": rel in in_cycle,
        })
        if detail == "full":
            result["imports"] = imports
        else:
            result.update(_compact_imports(imports))
    except Exception as exc:
        _fail(result, exc)
    return result


def get_dependents(file: str, project_root: Optional[PathArg] = None) -> Dict[str, Any]:
    """Files that import ``file`` (indexed reverse lookup)."""
    result: Dict[str, Any] = {"success": False, "file": file, "project_root": str(project_root or "")}
    try:
        root = resolve_root(project_root)
        rel = to_rel(root, file)
        dependents = cs.load_dependents(root, rel)
        result.update({
            "success": True,
            "project_root": str(root),
            "file": rel,
            "dependents": dependents,
            "count": len(dependents),
        })
    except Exception as exc:
        _fail(result, exc)
    return result


def cycles_report(
    project_root: Optional[PathArg] = None,
    analysis: bool = True,
    max_items: Optional[int] = None,
    use_canonical: bool = True,
) -> Dict[str, Any]:
    """Cycle clusters + (optionally) severity analyses. Computes on demand (read-only)."""
    result: Dict[str, Any] = {"success": False, "project_root": str(project_root or "")}
    try:
        root = resolve_root(project_root)
        meta = cs.load_meta(root, keys=("_cycles", "_cycle_analyses"))
        cycles = meta.get("_cycles") or {}
        analyses = meta.get("_cycle_analyses") or {}
        if "sccs" not in cycles or (analysis and "analyses" not in analyses):
            cache = ic.load_cache(root)
            if "sccs" not in cycles:
                cycles = ic.compute_cycles(dict(cache), root=root, use_canonical=use_canonical)
            if analysis and "analyses" not in analyses:
                analyses = ic.compute_cycle_analyses(cache, root=root, use_canonical=use_canonical)
        sccs = cycles.get("sccs") or []
        limit = max_items or (100 if analysis else 20)
        stats = cycles.get("stats") or {}
        result.update({
            "success": True,
            "project_root": str(root),
            "count": stats.get("cyclic_scc_count", len(sccs)),
            "stats": stats,
            "sccs": sccs[:limit],
            "truncated": len(sccs) > limit,
            "integrity": ic.compute_graph_integrity({"_cycles": cycles}),
            "graph_signature": cycles.get("graph_signature"),
            "reused": bool(cycles.get("reused")),
            "reuse_reason": cycles.get("reuse_reason"),
            "cycle_analyses": analyses if analysis else None,
            "analysis_version": analyses.get("analysis_version") if analysis else None,
        })
    except Exception as exc:
        _fail(result, exc)
    return result


def format_cycles_report(report: Dict[str, Any]) -> str:
    """Human/agent text rendering of :func:`cycles_report`."""
    if not report.get("success"):
        return f"Cycle report unavailable: {report.get('error')}. Run `wikifier update-maps` first."
    stats = report.get("stats") or {}
    lines = [
        "=== Circular Dependencies ===",
        f"Clusters: {report.get('count', 0)}   Files involved: {stats.get('total_files_in_cycles', 0)}   "
        f"Largest: {stats.get('largest_scc_size', 0)}",
        f"Signals in cycles: dynamic={stats.get('dynamic_edges_in_cycles', 0)} "
        f"conditional={stats.get('conditional_edges_in_cycles', 0)} barrel={stats.get('barrel_edges_in_cycles', 0)}",
        f"Graph signature: {report.get('graph_signature') or 'n/a'}"
        + (" (reused: topology unchanged)" if report.get("reused") else ""),
        "",
    ]
    sccs = report.get("sccs") or []
    if not sccs:
        lines.append("✅ No circular dependencies detected.")
        return "\n".join(lines)
    by_nodes = {
        tuple(sorted(a.get("nodes", []))): a
        for a in ((report.get("cycle_analyses") or {}).get("analyses") or [])
    }
    for i, scc in enumerate(sccs, 1):
        signals = scc.get("signals") or {}
        extra = ""
        if signals.get("dynamic_edge_count") or signals.get("conditional_edge_count") or signals.get("barrel_edge_count"):
            extra = (
                f"  (dynamic={signals.get('dynamic_edge_count', 0)} conditional={signals.get('conditional_edge_count', 0)} "
                f"barrel={signals.get('barrel_edge_count', 0)})"
            )
        lines.append(f"  {i}. size={scc.get('size')}: {scc.get('example_path')}{extra}")
        analysis = by_nodes.get(tuple(sorted(scc.get("nodes", []))))
        if analysis and analysis.get("severity"):
            weakest = (analysis.get("weakest_links") or [{}])[0]
            rec = (analysis.get("recommendations") or [{}])[0]
            lines.append(
                f"     severity={analysis.get('severity')} score={analysis.get('score')} "
                f"blast_radius={analysis.get('external_blast_radius')} "
                f"weakest={weakest.get('from', '?')}→{weakest.get('to', '?')}"
            )
            if rec.get("strategy"):
                detail = " — ".join(x for x in (rec.get("rationale"), rec.get("hint")) if x)
                lines.append(f"     fix: {rec.get('strategy')}" + (f" — {detail}" if detail else ""))
    if report.get("truncated"):
        lines.append("  … more clusters omitted (raise max_items or use JSON output)")
    return "\n".join(lines)


def seed_source_content_hashes(
    project_root: Optional[PathArg] = None,
    only_green: bool = True,
    force: bool = False,
    directory: Optional[str] = None,
) -> Dict[str, Any]:
    """Record current source hashes as baselines without changing status (migration)."""
    try:
        root = resolve_root(project_root)
        return health_mod.seed_source_content_hashes(root, only_green=only_green, force=force, directory=directory)
    except Exception as exc:
        return _fail({"project_root": str(project_root or "")}, exc)


def list_core_tools() -> Dict[str, Any]:
    """Core daily agent tools vs advanced intel tools."""
    from .agent_loop import list_core_tools as _list

    return _list()


def cache_status(project_root: Optional[PathArg] = None) -> Dict[str, Any]:
    """Cache backend, size, edge count, ACS version, map coverage (no payload load)."""
    try:
        return cs.cache_status(resolve_root(project_root))
    except Exception as exc:
        return _fail({"project_root": str(project_root or "")}, exc)


def health(
    project_root: Optional[PathArg] = None,
    directory: Optional[str] = None,
    format: Literal["text", "json", "summary", "healing-stats"] = "text",
) -> Union[str, Dict[str, Any]]:
    """Health matrix: ``summary`` counts, ``json`` entries (+ACS), ``text`` table, ``healing-stats``."""
    try:
        root = resolve_root(project_root)
        if format == "summary":
            return health_mod.get_summary(root, directory)
        if format == "healing-stats":
            return health_mod.get_healing_statistics(root)
        data = health_mod.load_health(root)
        entries = {k: v for k, v in data.get("entries", {}).items() if _in_directory(k, directory)}
        if format == "json":
            data["entries"] = entries
            data["success"] = True
            data["project_root"] = str(root)
            acs = cs.load_meta(root, keys=("_acs_summary",)).get("_acs_summary")
            if acs:
                data["dependency_intel"] = {"acs_summary": acs}
            return data
        lines = ["# Documentation Health Matrix", ""]
        for path, entry in list(entries.items())[:60]:
            lines.append(f"- {path}: {entry.get('status', '')} | {entry.get('last_updated', '')} | {(entry.get('reason') or '')[:80]}")
        if len(entries) > 60:
            lines.append(f"... ({len(entries) - 60} more; use --json or --summary)")
        return "\n".join(lines)
    except Exception as exc:
        failure = _fail({"project_root": str(project_root or "")}, exc)
        return failure if format in ("json", "summary", "healing-stats") else f"health error: {failure['error']}"


def heal_stubs(
    project_root: Optional[PathArg] = None,
    dry_run: bool = False,
    min_wiki_length: int = 350,
) -> Dict[str, Any]:
    """Promote Initial stubs whose wiki is now substantial (🟢 high quality, 🟡 medium)."""
    try:
        root = resolve_root(project_root)
        res = health_mod.heal_with_policy(
            root, policy={"targets": ["stubs"], "stub": {"min_wiki_length": min_wiki_length}}, dry_run=dry_run
        )
        res.update({"success": True, "project_root": str(root)})
        return res
    except Exception as exc:
        return _fail({"project_root": str(project_root or "")}, exc)


def journal(date: Optional[str] = None, project_root: Optional[PathArg] = None) -> Dict[str, Any]:
    """Journal entries for ``date`` (YYYY-MM-DD; default today)."""
    try:
        root = resolve_root(project_root)
        res = journal_mod.read_day(root, date)
        res["project_root"] = str(root)
        return res
    except Exception as exc:
        return _fail({"project_root": str(project_root or ""), "date": date}, exc)


def issues(severity: str = "all", project_root: Optional[PathArg] = None) -> Dict[str, Any]:
    """Logged_issues/*.md files (optionally one severity folder)."""
    try:
        root = resolve_root(project_root)
        res = journal_mod.list_issues(root, severity)
        res["project_root"] = str(root)
        return res
    except Exception as exc:
        return _fail({"project_root": str(project_root or ""), "severity": severity}, exc)


# =============================================================================
# Project setup
# =============================================================================

MONITORED_TEMPLATE = """\
# monitored_paths.txt — wiki / health watch list (check-changes thrash bound)
# Prefer lean package roots so check-changes does not thrash on target/,
# node_modules, build/, dist/, caches, etc.
# This is NOT the import map — see map_paths.txt for package roots used by update-maps.
#
# Active default: src/ (lean). Multi-crate / monorepo: replace with package roots first.
# Tiny single-file toys only: uncomment bare "." below (explicit opt-in — not default).
src/
# .
# lib/
# crates/my_crate/src/
# packages/core/src/
# README.md
# docs/
"""

MAP_PATHS_TEMPLATE = """\
# map_paths.txt — import-map package roots for update-maps (independent of monitored_paths)
# List directories that contain parseable source for the dependency map.
# Do not use bare "." on large trees; do not list only wiki/docs files here.
#
# Active default: src/ (replace with this project's package roots).
src/
# crates/my_crate/src/
# packages/core/src/
#
# Leave empty (comments only) to fall back to monitored directory roots / full collect.
# After editing: wikifier update-maps  (then session-bootstrap until readiness=ready_for_daemon)
"""

EXCLUDE_TEMPLATE = "node_modules\n.git\nbuild\ndist\n__pycache__\n*.pyc\ntarget\n"

DASHBOARD_FILES = ("index.html",)


def copy_human_dashboards(target_dir: PathArg) -> List[str]:
    """Copy the read-only dashboard (index.html) into ``target_dir`` if absent.

    diagnostics.html is maintainer-only and never copied. Returns copied names.
    """
    copied: List[str] = []
    package_dir = Path(__file__).resolve().parent  # index.html ships as package data
    for name in DASHBOARD_FILES:
        source = package_dir / name
        destination = Path(target_dir) / name
        if source.is_file() and not destination.exists():
            shutil.copyfile(source, destination)
            copied.append(name)
    return copied


def init_project(target: Optional[PathArg] = None, copy_dashboards: bool = True) -> Dict[str, Any]:
    """Bootstrap Wikifier state in ``target`` (default: the current project root).

    Writes lean templates (monitored_paths.txt / map_paths.txt default to ``src/``),
    empty health/pending/library views, the ``.wikifier/`` discovery marker and,
    unless disabled, the read-only dashboard. Existing files are never overwritten.
    """
    try:
        root = Path(target).expanduser() if target else resolve_root()
        root.mkdir(parents=True, exist_ok=True)
        root = root.resolve()
        created: List[str] = []

        def write_if_absent(rel: str, text: str) -> None:
            path = root / rel
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
                created.append(rel)

        write_if_absent("monitored_paths.txt", MONITORED_TEMPLATE)
        write_if_absent("map_paths.txt", MAP_PATHS_TEMPLATE)
        write_if_absent("exclude_patterns.txt", EXCLUDE_TEMPLATE)
        write_if_absent(
            "file_health.md",
            "# Documentation Health Matrix\n\n| File | Status | Last Updated | Reason / Intent |\n"
            "|------|--------|--------------|-----------------|\n",
        )
        write_if_absent("pending_updates.md", "# Pending Updates\n\n(no pending items — run check-changes after making edits)\n")
        write_if_absent("library.md", "# Library & Imports Map\n\nRun `wikifier update-maps` to populate.\n")
        write_if_absent(".wikifier/config", f"project_root={root}\n")
        for directory in (".wikifier_staging", "journal", "Logged_issues"):
            (root / directory).mkdir(parents=True, exist_ok=True)
        dashboards = copy_human_dashboards(root) if copy_dashboards else []
        return {
            "success": True,
            "project_root": str(root),
            "created": created + dashboards,
            "next_steps": [
                "Edit monitored_paths.txt + map_paths.txt to this project's package roots",
                "wikifier update-maps",
                "wikifier session-bootstrap (until readiness=ready_for_daemon)",
                "wikifier suggest-next",
            ],
        }
    except Exception as exc:
        return _fail({"project_root": str(target or "")}, exc)
