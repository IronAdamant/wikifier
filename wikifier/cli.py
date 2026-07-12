#!/usr/bin/env python3
"""
Wikifier CLI / library entry (agent-first).

AGENT MAP (read this, not the whole file):
  Pure-Python (python -m wikifier …): check-changes, record-change, mark-green,
    record-deletion, suggest-next, validate, health --summary|--json, update-maps
  Shell fallback (wikifier.sh): init, monitor, daemon, journal, issues, serve,
    heal-stubs, cycles, plain health matrix text
  Library: check_changes, record_change, mark_green, record_deletion,
    suggest_next_actions, update_maps, run_full_update, health (fn), discover_project_root
  Scope: monitored_paths → check-changes; exclude_patterns + walk → update-maps
  Self-tests: tests/ + tests/selftest/ (not inlined here)
"""

import os
import sys
import platform
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
from contextlib import nullcontext as _nullcontext

# Canonical discovery lives in project_root (no cli↔cache↔bree load cycle).
# Re-export for public API: `from wikifier.cli import discover_project_root`.
from .project_root import discover_project_root  # noqa: F401


# =============================================================================
# Python-primary heavy path for update-maps (Wave 3/4/5 External/Packaged Full-Update Robustness)
# =============================================================================

def _collect_candidate_source_files(
    root: Path,
    directory: Optional[str] = None,
) -> List[Path]:
    """Thin wrapper → ``wikifier.candidates`` (scoped walk, no per-file resolve)."""
    from .candidates import collect_candidate_source_files
    return collect_candidate_source_files(root, directory=directory)


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


def _pair_from_parser_edge(edge: Dict[str, Any], root: Path) -> Optional[Dict[str, Any]]:
    """Normalize one parser edge into the canonical resolved_pairs shape.

    Canonical pair: project-relative `resolved` path (display module for
    non-path resolutions, "" when unresolved), string `confidence`, real
    booleans, plus passthrough of the rich payloads (barrel_v2,
    resolution_metadata, ACS fields, CDIA analyses) when the parser provided
    them. The per-file cache entry implies the source, so no `src` key.
    """
    if not isinstance(edge, dict):
        return None
    raw = edge.get("raw_module") or edge.get("module") or edge.get("raw") or ""
    resolved = ""
    rp = edge.get("resolved_path")
    if rp:
        try:
            resolved = Path(rp).resolve().relative_to(root).as_posix()
        except Exception:
            resolved = str(rp)
    else:
        mod = edge.get("module")
        if mod and mod != raw:
            resolved = str(mod)
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
    for k in (
        "confidence_score", "confidence_reasons", "confidence_explanation",
        "barrel_v2", "resolution_metadata", "strategy", "cdia_v1",
        "conditional_analysis", "dynamic_analysis", "diagnostic",
        "imported_names", "barrel_leaf_selection",
    ):
        v = edge.get(k)
        if v not in (None, "", [], {}):
            pair[k] = v
    return pair


def run_full_update(
    root: Optional[Path] = None,
    force_full: bool = True,
    verbose: bool = False,
    use_canonical: bool = True,
    use_python_primary: bool = True,
    directory: Optional[str] = None,
    max_files: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Python-primary implementation of `update-maps [--full]` — the full pipeline,
    no shell:

      1. collect candidate sources (git fast-path / pruned walk; honors
         exclude_patterns.txt including file globs)
      2. dirty detection via import_cache.compute_files_needing_reparse,
         merged with barrel-stale importers (BRC reverse index)
      3. parse EVERY dirty file in-process (BREE persistence batched: one
         barrel-cache flush per run, not per chain)
      4. persist canonical per-file entries {mtime, imports, resolved,
         resolved_pairs} into import_cache.json (single save)
      5. rebuild reverse dependencies, cycles + analyses, ACS summary
      6. regenerate library.md atomically (wikifier.library)

    `directory`/`max_files` are explicit scoping. When max_files truncates the
    dirty set, the result reports `files_skipped` — there are no silent caps.

    Returns a dict with: success, root, mode, parseable_files, files_to_reparse,
    files_parsed, files_skipped, edges_persisted, parse_errors (bounded sample),
    cycles, library, dirty_sample, timestamp. `persist_pipeline_exercised` is
    kept for backward compatibility (True whenever the persist step ran).
    """
    if root is None:
        root = discover_project_root()
    root = Path(root).resolve()

    # Ensure env for any child parser/resolution helpers (packaged safety)
    os.environ["WIKIFIER_PROJECT_ROOT"] = str(root)

    if verbose:
        print(f"[run_full_update] target root: {root}")

    from datetime import datetime as _dt
    result: Dict[str, Any] = {
        "success": False,
        "root": str(root),
        "mode": "full" if force_full else "incremental",
        "parseable_files": 0,
        "files_to_reparse": 0,
        "files_parsed": 0,
        "files_skipped": 0,
        "edges_persisted": 0,
        "timestamp": _dt.now().isoformat(),
        "use_canonical": use_canonical,
        "use_python_primary": use_python_primary,
    }

    try:
        from . import import_cache as ic

        # One-time migrate legacy import_cache.json → SQLite so warm paths avoid JSON tax
        try:
            from . import cache_store as cs
            if not cs.has_sqlite(root) and cs.json_path(root).is_file():
                legacy = cs.load_cache_dict(root)
                if legacy:
                    cs.save_cache_dict(root, legacy)
                    result["cache_migrated_to_sqlite"] = True
        except Exception as mig_e:
            result["cache_migrate_note"] = str(mig_e)

        # === 1. Collect stage (index-first; re-list only on fp/count disagreement) ===
        from .candidates import (
            collect_candidate_source_files,
            resolve_candidates,
            candidate_list_meta,
            scope_fingerprint,
        )
        mtime_index: Optional[Dict[str, Any]] = None
        meta_c: Dict[str, Any] = {}
        try:
            from . import cache_store as cs
            loaded_idx = ic.load_mtime_index(root) or {}
            # Empty index must be None so try_cached uses live-count (not false reuse)
            mtime_index = loaded_idx if loaded_idx else None
            meta_c = cs.load_meta(root, keys=("_candidate_list",))
        except Exception:
            mtime_index = None
            meta_c = {}
        cres = resolve_candidates(
            root,
            directory=directory,
            force_full=force_full,
            index=mtime_index,
            meta=meta_c,
        )
        cands: List[Path] = list(cres.get("paths") or [])
        cand_reused = bool(cres.get("reused"))
        index_first = bool(cres.get("index_first"))
        result["parseable_files"] = len(cands)
        result["candidates_reused"] = cand_reused
        result["index_first_dirty"] = index_first
        result["candidates_relisted"] = bool(cres.get("relisted"))
        result["scope_fingerprint"] = cres.get("fingerprint") or scope_fingerprint(
            root, directory
        )
        if directory:
            result["scoped_directory"] = directory
        if verbose:
            print(
                f"[run_full_update] {len(cands)} candidate sources "
                f"(reused={cand_reused} index_first={index_first} "
                f"reason={cres.get('reason')})"
            )

        # === 2. Dirty stage (light mtime index; no full pair load) ===
        # CRITICAL (warm path): do NOT load full pair payloads when dirty is empty.
        # Barrel merge only when mtime-index dirty is non-empty.
        content_stable_updates: list = []
        dirty = ic.compute_files_needing_reparse(
            root,
            cands,
            full_rebuild=force_full,
            content_stable_mtime_updates=content_stable_updates,
        ) or []
        if dirty:
            try:
                from . import cache_store as _cs_barrel
                barrel_cache: Dict[str, Any] = {}
                if _cs_barrel.has_sqlite(root):
                    barrel_cache = _cs_barrel.load_meta(
                        root,
                        keys=(
                            "_barrel_resolutions",
                            "_barrel_file_index",
                            "_barrel_invalidation_log",
                        ),
                    )
                else:
                    # Legacy JSON only: unavoidable full read once (no sqlite yet)
                    barrel_cache = ic.load_cache(root) or {}
                if barrel_cache.get("_barrel_resolutions") or barrel_cache.get(
                    "_barrel_file_index"
                ):
                    barrel_stale = ic.invalidate_stale_barrel_entries(
                        barrel_cache, root, changed_files=[str(p) for p in dirty]
                    ) or []
                    seen = {str(Path(p).resolve()) for p in dirty}
                    for rel in barrel_stale:
                        if rel:
                            p = (root / rel).resolve()
                            if p.exists() and str(p) not in seen:
                                dirty.append(p)
                                seen.add(str(p))
            except Exception:
                pass  # barrel merge is best-effort; mtime dirty set is authoritative
        dirty_total: int = len(dirty)
        result["dirty_total"] = dirty_total
        result["files_to_reparse"] = dirty_total
        result["dirty_sample"] = [str(p) for p in dirty[:3]]
        if content_stable_updates:
            result["content_stable_mtime_refreshes"] = len(content_stable_updates)

        if max_files is not None:
            try:
                cap = int(max_files)
                if len(dirty) > cap:
                    result["files_skipped"] = len(dirty) - cap
                    dirty = dirty[:cap]
            except (TypeError, ValueError):
                pass

        # === 2b. Zero-dirty fast path (agent warm maps) ===
        # Light path: mtime index + meta only — do NOT load multi-MB pair payloads.
        if not dirty and not force_full:
            try:
                from . import cache_store as cs
            except Exception:
                cs = None  # type: ignore
            mtime_refreshed = 0
            if content_stable_updates and cs is not None:
                try:
                    mtime_refreshed = cs.update_file_index_rows(
                        root,
                        [(r, int(m), h) for r, m, h in content_stable_updates],
                    )
                except Exception:
                    mtime_refreshed = 0
            result["files_parsed"] = 0
            result["edges_persisted"] = 0
            result["languages_parsed"] = {}
            result["zero_dirty_fast_path"] = True
            result["content_stable_mtime_refreshes"] = mtime_refreshed or len(
                content_stable_updates or []
            )
            backend = "json"
            try:
                if cs is not None:
                    backend = cs.backend_name(root)
            except Exception:
                pass
            result["cache_backend"] = backend
            # ACS from meta only when already v1.3+; else full load + ensure
            acs: Dict[str, Any] = {}
            try:
                meta = cs.load_meta(root, keys=("_acs_summary", "_cycles")) if cs else {}
                acs = meta.get("_acs_summary") if isinstance(meta.get("_acs_summary"), dict) else {}
                needs_full = (
                    not acs
                    or str(acs.get("acs_version") or "") < "1.3"
                    or "reason_code_counts" not in acs
                )
                if needs_full:
                    cache = ic.load_cache(root) or {}
                    acs = ic.ensure_acs_summary_persisted(cache, root) or {}
                    cy = cache.get("_cycles") if isinstance(cache.get("_cycles"), dict) else {}
                else:
                    cy = meta.get("_cycles") if isinstance(meta.get("_cycles"), dict) else {}
                result["acs"] = {
                    "acs_version": acs.get("acs_version"),
                    "actionable_low_conf_edges": acs.get("actionable_low_conf_edges"),
                    "low_conf_edges": acs.get("low_conf_edges"),
                    "reason_code_counts": acs.get("reason_code_counts"),
                }
            except Exception as ae:
                result["acs_error"] = str(ae)
                cy = {}
            sccs = cy.get("sccs") if isinstance(cy, dict) else []
            result["cycles"] = {
                "count": len(sccs or []),
                "reused": True,
                "fast_path": True,
            }
            lib_path = root / "library.md"
            if lib_path.is_file():
                result["library"] = {
                    "success": True,
                    "path": str(lib_path),
                    "skipped": True,
                    "reason": "zero_dirty_reuse",
                }
            else:
                try:
                    from .library import write_library_md
                    cache = ic.load_cache(root) or {}
                    result["library"] = write_library_md(root, cache)
                except Exception as e:
                    result["library"] = {"success": False, "error": str(e)}
            result["health_stubs_seeded"] = 0
            result["persist_pipeline_exercised"] = True
            result["map_coverage"] = ic.build_map_coverage(
                dirty_total=0,
                files_parsed=0,
                files_skipped=0,
                files_to_reparse=0,
                max_files=max_files,
                parseable_files=int(result.get("parseable_files") or 0),
                zero_dirty_fast_path=True,
                acs_version=(result.get("acs") or {}).get("acs_version"),
                cache_backend=backend,
                directory=directory,
            )
            try:
                if cs is not None:
                    cs.save_meta_key(root, "_map_coverage", result["map_coverage"])
                    # Persist candidate list for next warm (fp reuse) when freshly collected
                    if not cand_reused and cands:
                        cs.save_meta_key(
                            root,
                            "_candidate_list",
                            candidate_list_meta(root, directory, cands),
                        )
                    # Prune leftover full-tree index keys after map_paths narrow
                    # so migration cannot poison reuse forever.
                    try:
                        from .candidates import resolve_map_scope as _rms
                        _sc = _rms(root, directory)
                        if not _sc.is_full_tree:
                            pruned_n = cs.prune_file_index_outside_scope(
                                root,
                                list(_sc.rel_prefixes),
                                is_full_tree=False,
                            )
                            if pruned_n:
                                result["index_pruned_outside_scope"] = pruned_n
                    except Exception:
                        pass
            except Exception:
                pass
            result["success"] = True
            if verbose:
                print(
                    f"[run_full_update] zero-dirty fast path: backend={backend} "
                    f"mtime_refreshes={mtime_refreshed}, library_skipped={lib_path.is_file()}"
                )
            return result

        # === 3. Parse every dirty file (in-process, BREE batched) ===
        from .parsers import javascript as js_parser
        from .parsers import python as py_parser
        try:
            from .parsers import rust as rust_parser
        except Exception:
            rust_parser = None
        try:
            from .parsers import go_lang as go_parser
        except Exception:
            go_parser = None
        try:
            from .parsers import c_cpp as c_cpp_parser
        except Exception:
            c_cpp_parser = None
        try:
            from .parsers import csharp as csharp_parser
        except Exception:
            csharp_parser = None
        try:
            from .parsers import java as java_parser
        except Exception:
            java_parser = None
        try:
            from .parsers import bree as bree_mod
        except Exception:
            bree_mod = None
        try:
            from .resolution import to_canonical_rel as _canon
        except Exception:
            _canon = None

        def _rel(p: Path) -> Optional[str]:
            try:
                if _canon is not None:
                    c = _canon(p, root, follow_symlinks=True)
                    if c:
                        return c
            except Exception:
                pass
            try:
                return Path(p).resolve().relative_to(root).as_posix()
            except Exception:
                return None

        def _parse_file(fstr: str, low: str):
            if low.endswith((".js", ".ts", ".jsx", ".tsx")):
                return js_parser.parse_javascript_imports(fstr) or []
            if low.endswith(".py"):
                return py_parser.parse_python_imports(fstr) or []
            if low.endswith(".rs") and rust_parser is not None:
                return rust_parser.parse_rust_imports(fstr) or []
            if low.endswith(".go") and go_parser is not None:
                return go_parser.parse_go_imports(fstr) or []
            if low.endswith((".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".hh")) and c_cpp_parser is not None:
                return c_cpp_parser.parse_c_cpp_imports(fstr) or []
            if low.endswith(".cs") and csharp_parser is not None:
                return csharp_parser.parse_csharp_imports(fstr) or []
            if low.endswith(".java") and java_parser is not None:
                return java_parser.parse_java_imports(fstr) or []
            return None

        new_entries: Dict[str, Dict[str, Any]] = {}
        edges_total = 0
        parsed_count = 0
        parse_errors: List[Dict[str, str]] = []
        lang_counts: Dict[str, int] = {}

        if bree_mod is not None:
            try:
                bree_mod.begin_batch()
            except Exception:
                bree_mod = None
        try:
            for f in dirty:
                fstr = str(f)
                low = fstr.lower()
                try:
                    edges = _parse_file(fstr, low)
                    if edges is None:
                        continue
                except Exception as pe:
                    parse_errors.append({"file": fstr, "error": f"{type(pe).__name__}: {pe}"})
                    continue
                rel = _rel(Path(fstr))
                if not rel:
                    continue
                pairs = [p for p in (_pair_from_parser_edge(e, root) for e in edges) if p]
                fpath = Path(fstr)
                chash = None
                try:
                    chash = ic.compute_file_content_hash(fpath)
                except Exception:
                    chash = None
                new_entries[rel] = {
                    "mtime": ic.get_mtime(fpath),
                    "imports": [p.get("raw", "") for p in pairs],
                    "resolved": [p["resolved"] for p in pairs if p.get("resolved")],
                    "resolved_pairs": pairs,
                }
                if chash:
                    new_entries[rel]["content_hash"] = chash
                parsed_count += 1
                edges_total += len(pairs)
                ext = Path(low).suffix.lower() or "unknown"
                lang_counts[ext] = lang_counts.get(ext, 0) + 1
                if verbose and parsed_count % 200 == 0:
                    print(f"[run_full_update] parsed {parsed_count}/{len(dirty)}")
        finally:
            if bree_mod is not None:
                try:
                    bree_mod.end_batch()  # one barrel-cache flush for the whole run
                except Exception:
                    pass

        result["files_parsed"] = parsed_count
        result["edges_persisted"] = edges_total
        result["languages_parsed"] = lang_counts
        if parse_errors:
            result["parse_errors"] = parse_errors[:10]
            result["parse_error_count"] = len(parse_errors)

        # === 4. Persist (single save; reload first to pick up the barrel flush) ===
        cache = ic.load_cache(root) or {}
        cache.update(new_entries)
        if force_full:
            # Drop ghosts: per-file entries whose source no longer exists in scope.
            # Only safe on an unscoped full rebuild (scoped runs see partial candidates).
            if not directory and not max_files:
                valid = {r for r in (_rel(Path(p)) for p in cands) if r}
                for stale_key in [k for k in cache if not k.startswith("_") and k not in valid]:
                    cache.pop(stale_key, None)

        # === 5. Graph intelligence (reverse deps, cycles, ACS) ===
        try:
            rev = ic.rebuild_reverse_dependencies(cache)
            ic.set_reverse_dependencies(cache, rev)
        except Exception as e:
            result["reverse_index_error"] = str(e)
        try:
            cycles_payload = ic.compute_cycles(cache, root=root, use_canonical=use_canonical)
            cache["_cycles"] = cycles_payload
            result["cycles"] = {
                "count": len(cycles_payload.get("sccs", []) or []),
            }
            try:
                cache["_cycle_analyses"] = ic.compute_cycle_analyses(cache, root=root, use_canonical=use_canonical)
            except Exception:
                pass
        except Exception as e:
            result["cycles"] = {"error": str(e)}
        ic.save_cache(root, cache)
        result["persist_pipeline_exercised"] = True
        try:
            ic.ensure_acs_summary_persisted(cache, root)
        except Exception:
            pass

        # === 5b. Map-first health stubs (always backfill; warm cache safe) ===
        # 0-dirty incremental runs never used to create file_health.json — fixed here.
        health_seeded = 0
        if _health_mod is not None and hasattr(_health_mod, "seed_health_from_map"):
            try:
                max_seed = int(os.environ.get("WIKIFIER_HEALTH_SEED_MAX", "20000") or "20000")
                map_keys = [k for k in cache if isinstance(k, str) and k and not k.startswith("_")]
                seed_res = _health_mod.seed_health_from_map(
                    root, map_keys=map_keys, max_new=max_seed,
                )
                health_seeded = int(seed_res.get("seeded") or 0)
                if hasattr(_health_mod, "seed_health_for_monitored_sources"):
                    disk_res = _health_mod.seed_health_for_monitored_sources(
                        root, max_new=max_seed,
                    )
                    health_seeded += int(disk_res.get("seeded") or 0)
            except Exception as se:
                result["health_seed_error"] = str(se)
                health_seeded = 0
        result["health_stubs_seeded"] = health_seeded

        # === 6. library.md (atomic; pure Python) ===
        try:
            from .library import write_library_md
            result["library"] = write_library_md(root, cache)
        except Exception as e:
            result["library"] = {"success": False, "error": str(e)}

        # map_coverage for agents (partial budget ≠ complete)
        try:
            from . import cache_store as cs
            backend = cs.backend_name(root)
        except Exception:
            backend = "json"
        acs_ver = None
        try:
            acs_ver = (cache.get("_acs_summary") or {}).get("acs_version")
        except Exception:
            pass
        result["cache_backend"] = backend
        result["map_coverage"] = ic.build_map_coverage(
            dirty_total=int(result.get("dirty_total") or result.get("files_to_reparse") or 0),
            files_parsed=int(result.get("files_parsed") or 0),
            files_skipped=int(result.get("files_skipped") or 0),
            files_to_reparse=int(result.get("files_to_reparse") or 0),
            max_files=max_files,
            parseable_files=int(result.get("parseable_files") or 0),
            zero_dirty_fast_path=False,
            acs_version=acs_ver,
            cache_backend=backend,
            directory=directory,
        )
        try:
            cache["_map_coverage"] = result["map_coverage"]
            if cands:
                cache["_candidate_list"] = candidate_list_meta(root, directory, cands)
            from . import cache_store as cs
            if cs.has_sqlite(root):
                cs.save_meta_key(root, "_map_coverage", result["map_coverage"])
                if cands:
                    cs.save_meta_key(
                        root, "_candidate_list", cache["_candidate_list"]
                    )
                try:
                    from .candidates import resolve_map_scope as _rms
                    _sc = _rms(root, directory)
                    if not _sc.is_full_tree:
                        pruned_n = cs.prune_file_index_outside_scope(
                            root,
                            list(_sc.rel_prefixes),
                            is_full_tree=False,
                        )
                        if pruned_n:
                            result["index_pruned_outside_scope"] = pruned_n
                except Exception:
                    pass
            else:
                ic.save_cache(root, cache)
        except Exception:
            pass

        result["success"] = True
    except Exception as ex:
        result["error"] = str(ex)
        result["note"] = "run_full_update failed; the shell update-maps path remains available as fallback."

    if verbose:
        print(f"[run_full_update] done: parsed {result.get('files_parsed')}/{result.get('files_to_reparse')} "
              f"dirty files, {result.get('edges_persisted')} edges, library={result.get('library', {}).get('success')}")

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
        # Consume --target / --project-root so the *command* remains filtered_argv[0]
        # (previously left --target as argv[0] → "Unknown command: --target").
        if arg in ("--target", "--project-root") and i + 1 < len(argv):
            project_root = argv[i + 1]
            i += 2
            continue
        elif arg.startswith("--target="):
            project_root = arg.split("=", 1)[1]
            i += 1
            continue
        elif arg.startswith("--project-root="):
            project_root = arg.split("=", 1)[1]
            i += 1
            continue
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

    # Micro-step 2 (A2 CLI wiring): detect streaming UX flags after parsing.
    # --max-files / --directory are normal run_full_update scoping options and
    # must NOT force the stream facade (agents expect batch JSON + files_skipped).
    a2_flag_markers = (
        "--stream", "--stream=",
        "--resume", "--resume_token",
        "--max-time", "--max_time",
        "--progress",
        "--partial",
        "--format=stream",
    )
    has_a2_ux_flags = any(any(a == m or a.startswith(m) for m in a2_flag_markers) for a in filtered_argv)

    if project_root:
        os.environ["WIKIFIER_PROJECT_ROOT"] = project_root
    # Wave 4: expose use_canonical to sh 3d blocks + on-demand (MCP/CLI cycles) via env for public surface
    os.environ["WIKIFIER_USE_CANONICAL"] = "1" if use_canonical else "0"

    # `health --summary|--json|--format=...` routes to the Python library
    # implementation; the sh path prints the full matrix and ignores flags.
    if filtered_argv and filtered_argv[0] == "health" and any(
        a in ("--summary", "--json") or a.startswith("--format") for a in filtered_argv[1:]
    ):
        fmt = "summary" if "--summary" in filtered_argv else ("json" if "--json" in filtered_argv else "summary")
        for a in filtered_argv[1:]:
            if a.startswith("--format="):
                fmt = a.split("=", 1)[1] or fmt
        try:
            import json as _json
            out = health(project_root=project_root, format=fmt)
            print(_json.dumps(out, indent=2, ensure_ascii=False) if isinstance(out, (dict, list)) else out)
            return 0
        except Exception as e:
            print(f"[wikifier] health --{fmt} failed: {e}", file=sys.stderr)
            return 1

    # Mandatory workflow commands: pure-Python primary (updates file_health.json + md).
    # Shell upsert_health only patches the .md and on macOS `realpath --relative-to`
    # is unavailable, so it used to store absolute paths as health keys.
    if filtered_argv:
        _cmd0 = filtered_argv[0].replace("_", "-")
        _args = filtered_argv[1:]
        try:
            if _cmd0 == "check-changes":
                res = check_changes(project_root=project_root)
                n = int(res.get("changes_detected") or 0)
                print("[wikifier] Running incremental change detection...")
                if n:
                    print(f"[wikifier] Detected {n} changed file(s). See pending_updates.md and file_health.md.")
                else:
                    print("[wikifier] No new changes detected.")
                if res.get("message"):
                    print(res["message"])
                return 0 if res.get("success", True) else 1
            if _cmd0 == "record-change":
                if not _args or _args[0] in ("--help", "-h", "help"):
                    print('Usage: wikifier record-change <file> "<reason>"')
                    return 0
                if _args[0].startswith("-") or len(_args) < 2:
                    print('Usage: wikifier record-change <file> "<reason>"', file=sys.stderr)
                    return 1
                res = record_change(_args[0], " ".join(_args[1:]), project_root=project_root)
                print(res.get("message") or res)
                return 0 if res.get("success") else 1
            if _cmd0 == "mark-green":
                if not _args or _args[0] in ("--help", "-h", "help"):
                    print("Usage: wikifier mark-green <file> [reason]")
                    return 0
                if _args[0].startswith("-"):
                    print("Usage: wikifier mark-green <file> [reason]", file=sys.stderr)
                    return 1
                reason = " ".join(_args[1:]) if len(_args) > 1 else ""
                res = mark_green(_args[0], reason, project_root=project_root)
                print(res.get("message") or res)
                return 0 if res.get("success") else 1
            if _cmd0 == "record-deletion":
                # Guard: `record-deletion --help` must not treat `--help` as a file path
                # (that polluted health with a 🔴 DELETED "--help" key).
                if not _args or _args[0] in ("--help", "-h", "help"):
                    print('Usage: wikifier record-deletion <file> "<reason>"')
                    return 0
                if _args[0].startswith("-"):
                    print(
                        'Usage: wikifier record-deletion <file> "<reason>"\n'
                        "  <file> must be a project path, not a flag.",
                        file=sys.stderr,
                    )
                    return 1
                reason = " ".join(_args[1:]) if len(_args) > 1 else "removed"
                res = record_deletion(_args[0], reason, project_root=project_root)
                print(res.get("message") or res)
                return 0 if res.get("success") else 1
            if _cmd0 in ("suggest-next", "suggest-next-actions", "suggest"):
                import json as _json
                fmt = "text"
                for a in _args:
                    if a in ("--json", "--format=json"):
                        fmt = "json"
                res = suggest_next_actions(project_root=project_root, format=fmt)
                print(_json.dumps(res, indent=2, default=str) if isinstance(res, dict) else res)
                return 0
            if _cmd0 in ("session-bootstrap", "session_bootstrap", "bootstrap", "session-start"):
                import json as _json
                res = session_bootstrap(project_root=project_root)
                print(_json.dumps(res, indent=2, default=str))
                return 0 if res.get("success") else 1
            if _cmd0 in ("cache-status", "cache_status", "cache-info", "cache"):
                import json as _json
                res = cache_status(project_root=project_root)
                print(_json.dumps(res, indent=2, default=str))
                return 0 if res.get("success") else 1
            if _cmd0 in ("prepare-edit", "prepare_edit", "lookup", "preflight"):
                import json as _json
                if not _args:
                    print("Usage: wikifier prepare-edit <file>", file=sys.stderr)
                    return 1
                res = prepare_edit(_args[0], project_root=project_root)
                print(_json.dumps(res, indent=2, default=str))
                return 0 if res.get("success") else 1
            if _cmd0 in ("search-journal", "search_journal", "journal-search"):
                import json as _json
                q = None
                f = None
                i = 0
                while i < len(_args):
                    if _args[i] in ("--file", "-f") and i + 1 < len(_args):
                        f = _args[i + 1]
                        i += 2
                        continue
                    if _args[i] in ("--query", "-q") and i + 1 < len(_args):
                        q = _args[i + 1]
                        i += 2
                        continue
                    if q is None and not _args[i].startswith("-"):
                        q = _args[i]
                    i += 1
                res = search_journal(project_root=project_root, query=q, file=f)
                print(_json.dumps(res, indent=2, default=str))
                return 0 if res.get("success") else 1
            if _cmd0 in ("why-file", "why_file", "why"):
                import json as _json
                if not _args:
                    print("Usage: wikifier why-file <file>", file=sys.stderr)
                    return 1
                res = why_file(_args[0], project_root=project_root)
                print(_json.dumps(res, indent=2, default=str))
                return 0 if res.get("success") else 1
            if _cmd0 in (
                "seed-source-hashes",
                "seed-source-content-hashes",
                "seed_source_content_hashes",
                "seed-hashes",
            ):
                import json as _json
                force = any(a in ("--force", "-f") for a in _args)
                res = seed_source_content_hashes(project_root=project_root, force=force)
                print(_json.dumps(res, indent=2, default=str))
                return 0 if res.get("success") else 1
            if _cmd0 in ("list-core-tools", "list_core_tools", "core-tools"):
                import json as _json
                res = list_core_tools()
                print(_json.dumps(res, indent=2, default=str))
                return 0 if res.get("success") else 1
            if _cmd0 == "validate":
                import json as _json
                if _health_mod is not None:
                    root = _get_effective_root(project_root)
                    res = _health_mod.validate_health(root)
                    print(_json.dumps(res, indent=2, default=str))
                    # Map-first: exit 0 when map is covered (or no map + no monitored source gaps)
                    return 0 if res.get("missing_count", 0) == 0 else 1
            if _cmd0 in ("seed-health", "seed-health-from-map"):
                import json as _json
                if _health_mod is None:
                    print("[wikifier] health module unavailable", file=sys.stderr)
                    return 1
                root = _get_effective_root(project_root)
                res = _health_mod.seed_health_from_map(root)
                if hasattr(_health_mod, "seed_health_for_monitored_sources"):
                    disk = _health_mod.seed_health_for_monitored_sources(root)
                    res["disk_seeded"] = disk.get("seeded")
                    res["seeded_total"] = int(res.get("seeded") or 0) + int(disk.get("seeded") or 0)
                print(_json.dumps(res, indent=2, default=str))
                return 0 if res.get("success") else 1
            if _cmd0 in ("prune-pending", "prune-pending-monitored"):
                import json as _json
                if _health_mod is None:
                    print("[wikifier] health module unavailable", file=sys.stderr)
                    return 1
                root = _get_effective_root(project_root)
                res = _health_mod.prune_pending_to_monitored(root)
                print(_json.dumps(res, indent=2, default=str))
                return 0 if res.get("success") else 1
            if _cmd0 in ("prune-health-monitored", "prune-health"):
                import json as _json
                if _health_mod is None:
                    print("[wikifier] health module unavailable", file=sys.stderr)
                    return 1
                root = _get_effective_root(project_root)
                res = _health_mod.prune_health_outside_monitored(root)
                print(_json.dumps(res, indent=2, default=str))
                return 0 if res.get("success") else 1
            if _cmd0 in (
                "autonomous-status",
                "autonomous_status",
                "readiness",
                "long-horizon",
            ):
                import json as _json
                if _health_mod is None or not hasattr(_health_mod, "assess_autonomous_readiness"):
                    print("[wikifier] health.assess_autonomous_readiness unavailable", file=sys.stderr)
                    return 1
                root = _get_effective_root(project_root)
                res = _health_mod.assess_autonomous_readiness(root)
                print(_json.dumps(res, indent=2, default=str))
                # exit 0 only when not blocked
                return 0 if res.get("readiness") != "blocked" else 2
            if _cmd0 in ("metrics-snapshot", "metrics_snapshot", "metrics"):
                import json as _json
                if _health_mod is None or not hasattr(_health_mod, "write_metrics_snapshot"):
                    print("[wikifier] write_metrics_snapshot unavailable", file=sys.stderr)
                    return 1
                root = _get_effective_root(project_root)
                res = _health_mod.write_metrics_snapshot(root, source="cli")
                print(_json.dumps(res, indent=2, default=str))
                return 0 if res.get("success") else 1
        except Exception as e:
            print(f"[wikifier] Python-primary {_cmd0} failed: {e}", file=sys.stderr)
            return 1

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
    # update-maps defaults to the pure-Python pipeline (full parse + canonical
    # persist + cycles/ACS + atomic library.md). The shell path remains available
    # via --sh / --legacy-sh (it is slower; kept as a fallback).
    python_primary_requested = True
    is_update_maps_cmd = False
    stripped_filtered = []
    for a in filtered_argv:
        if a in ("--python-primary", "--use-python-primary", "--python_primary"):
            python_primary_requested = True
            continue  # consume, do not forward to sh
        if a in ("--sh", "--legacy-sh", "--no-python-primary"):
            # The in-shell update-maps implementation was retired (2026-06-10
            # thin-shell rework); wikifier.sh itself now delegates here.
            print("[wikifier] note: --sh is a deprecated no-op — the legacy shell "
                  "update-maps path was retired; the Python pipeline always runs.",
                  file=sys.stderr)
            continue  # consume; stay on the Python pipeline
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
        for a in argv:
            if a.startswith("--dir=") or a.startswith("--directory="):
                directory = a.split("=", 1)[1] or None
            elif a.startswith("--max-files=") or a.startswith("--max_files="):
                try:
                    max_files = int(a.split("=", 1)[1])
                except ValueError:
                    pass
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
    """Append to pending_updates.md via health helpers (normalized empty/items)."""
    try:
        if _health_mod is not None and hasattr(_health_mod, "add_to_pending"):
            # Caller may already hold project lock (re-entrant).
            _health_mod._do_add_to_pending(root, file, msg) if hasattr(
                _health_mod, "_do_add_to_pending"
            ) else _health_mod.add_to_pending(root, file, msg)
            return
        p = root / "pending_updates.md"
        line = f"- {file}: {msg}\n"
        with open(p, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def _remove_from_pending(root: Path, file: str) -> None:
    """Best-effort removal (used by mark_green). Prefers health normalizer."""
    try:
        if _health_mod is not None and hasattr(_health_mod, "_do_remove_from_pending"):
            _health_mod._do_remove_from_pending(root, file)
            return
        if _health_mod is not None and hasattr(_health_mod, "remove_from_pending"):
            _health_mod.remove_from_pending(root, file)
            return
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

            # Cap is configurable: WIKIFIER_CHECK_CHANGES_MAX (default 2000; was hard 200).
            # Huge monorepos with monitored_paths=. can still thrash — prefer lean monitored paths.
            try:
                max_dirty = int(os.environ.get("WIKIFIER_CHECK_CHANGES_MAX", "2000") or "2000")
            except ValueError:
                max_dirty = 2000
            max_dirty = max(1, min(max_dirty, 50000))
            try:
                max_ghosts = int(os.environ.get("WIKIFIER_CHECK_CHANGES_GHOST_MAX", "200") or "200")
            except ValueError:
                max_ghosts = 200
            max_ghosts = max(1, min(max_ghosts, 10000))

            dirty_list = list(dirty or [])
            dirty_truncated = len(dirty_list) > max_dirty
            dirty_batch = dirty_list[:max_dirty]

            changed_count = 0
            skipped_mtime_only = 0
            seeded_baselines = 0
            ghosts_marked = 0
            if _health_mod is None:
                result["message"] = "check_changes: health module unavailable"
            if _health_mod is not None:
                root_res = root.resolve()
                # Prefer unlocked helpers while we already hold project lock
                _upsert = getattr(_health_mod, "_do_upsert_entry", None) or _health_mod.upsert_entry
                classify = getattr(_health_mod, "classify_content_dirty", None)
                compute_src = getattr(_health_mod, "compute_source_content_hash", None)
                health_data = None
                try:
                    health_data = _health_mod.load_health(root)
                except Exception:
                    health_data = {"entries": {}}
                entries = health_data.setdefault("entries", {}) if isinstance(health_data, dict) else {}
                health_dirty = False
                for p in dirty_batch:
                    try:
                        pr = Path(p).resolve()
                        if not str(pr).startswith(str(root_res)):
                            continue
                        rel = str(pr.relative_to(root_res))
                    except Exception:
                        continue
                    # Content-honest dirty: mtime candidates still filtered by source hash
                    stored_hash = None
                    ent = entries.get(rel) if isinstance(entries, dict) else None
                    if isinstance(ent, dict):
                        stored_hash = ent.get("source_content_hash")
                    verdict = {"content_dirty": True, "reason": "no_classifier", "seed_baseline": False, "hash": None}
                    if classify is not None:
                        try:
                            verdict = classify(pr, stored_hash)
                        except Exception:
                            pass
                    elif compute_src is not None:
                        try:
                            live = compute_src(pr)
                            if stored_hash and live and stored_hash == live:
                                verdict = {"content_dirty": False, "reason": "content_unchanged", "seed_baseline": False, "hash": live}
                            elif not stored_hash and live:
                                # no baseline → dirty (do not seed post-edit hash)
                                verdict = {"content_dirty": True, "reason": "no_baseline", "seed_baseline": False, "hash": live}
                            elif live and stored_hash and stored_hash != live:
                                verdict = {"content_dirty": True, "reason": "content_changed", "seed_baseline": False, "hash": live}
                        except Exception:
                            pass

                    if not verdict.get("content_dirty") and verdict.get("reason") == "content_unchanged":
                        skipped_mtime_only += 1
                        continue
                    # Content changed, no baseline, or unclassifiable: Yellow.
                    # Never write source_content_hash here — only mark_green sets the
                    # trusted baseline (avoids seeding post-edit bytes and staying Green).
                    reason = (
                        "content changed since last trusted baseline (check_changes content-honest)"
                        if verdict.get("reason") == "content_changed"
                        else "content change or no baseline (check_changes content-honest auto-detect)"
                    )
                    _upsert(root, rel, "🟡 Yellow", reason)
                    try:
                        health_data = _health_mod.load_health(root)
                        entries = health_data.setdefault("entries", {})
                        health_dirty = False  # upsert already saved
                    except Exception:
                        pass
                    _add_to_pending(root, rel, "Content change auto-detected — review and run mark-green after wiki update")
                    _ensure_journal_entry(root, "auto-detected", rel, reason)
                    changed_count += 1
                # Keep pending queue aligned with lean monitored_paths (no flood outside scope)
                if hasattr(_health_mod, "prune_pending_to_monitored"):
                    try:
                        pr = _health_mod.prune_pending_to_monitored(root)
                        result["pending_pruned"] = pr.get("removed", 0)
                    except Exception:
                        pass

                # G7: surface ghost health entries (tracked path missing on disk, not already DELETED)
                try:
                    if hasattr(_health_mod, "find_ghost_entries"):
                        ghosts_all = _health_mod.find_ghost_entries(root) or []
                        for g in ghosts_all[:max_ghosts]:
                            _health_mod.upsert_entry(
                                root, g, "🔴 Red",
                                "DELETED — path missing on disk (check_changes ghost detection)"
                            )
                            _add_to_pending(
                                root, g,
                                "File missing on disk — run record-deletion or archival cleanup"
                            )
                            ghosts_marked += 1
                except Exception:
                    pass

            msg = (
                f"Python-primary check_changes complete: {changed_count} files marked/updated"
                + (f", {skipped_mtime_only} mtime-only skip(s)" if skipped_mtime_only else "")
                + (f", {seeded_baselines} content baseline(s) seeded" if seeded_baselines else "")
                + (f", {ghosts_marked} ghost(s) marked Red" if ghosts_marked else "")
                + ". Health + pending + journal touched."
            )
            if dirty_truncated:
                msg += (
                    f" Note: dirty set truncated to {max_dirty} of {len(dirty_list)} "
                    f"(set WIKIFIER_CHECK_CHANGES_MAX or lean monitored_paths.txt)."
                )
            result.update({
                "success": True,
                "changes_detected": changed_count,
                "dirty_total": len(dirty_list),
                "dirty_truncated": dirty_truncated,
                "max_dirty": max_dirty,
                "ghosts_marked": ghosts_marked,
                "skipped_mtime_only": skipped_mtime_only,
                "seeded_content_baselines": seeded_baselines,
                "content_honest": True,
                "message": msg,
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
    """Python-primary record_deletion (symmetric to record_change).

    G7: marks 🔴 DELETED, pending + journal, and best-effort prunes barrel cache
    references so deleted paths do not keep invalidating importers forever.
    Rejects flag-like paths (`--help`) so CLI misuse cannot pollute health.
    """
    root = _get_effective_root(project_root)
    result: Dict[str, Any] = {"success": False, "file": file, "project_root": str(root), "action": "deletion"}
    if not file or str(file).startswith("-") or str(file) in ("--help", "-h", "help"):
        result["error"] = "file must be a project path, not a flag/empty string"
        return result
    try:
        lock_ctx = (locking.file_lock(root) if locking is not None else _nullcontext())
        with lock_ctx:
            rel = file
            try:
                pp = Path(file)
                if pp.is_absolute():
                    rel = str(pp.resolve().relative_to(root.resolve()))
            except Exception:
                rel = file
            if _health_mod is not None:
                # Prefer unlocked upsert when we already hold the project lock.
                if hasattr(_health_mod, "_do_upsert_entry"):
                    _health_mod._do_upsert_entry(root, rel, "🔴 Red", f"DELETED — {reason}")
                else:
                    _health_mod.upsert_entry(root, rel, "🔴 Red", f"DELETED — {reason}")
            _add_to_pending(root, rel, f"File was deleted. Consider wiki archival. {reason}")
            _ensure_journal_entry(root, "record-deletion", rel, reason or "No reason provided.")
            prune_stats: Dict[str, Any] = {}
            if _ic_mod is not None:
                try:
                    prune_stats = _ic_mod.prune_barrel_resolutions(
                        root, deleted_files=[rel]
                    ) or {}
                except Exception as pe:
                    prune_stats = {"error": str(pe)}
            result.update({
                "success": True,
                "file": rel,
                "message": "Recorded deletion (Python primary).",
                "barrel_prune": prune_stats,
            })
    except Exception as e:
        result["error"] = str(e)
    return result


def mark_green(file: str, reason: str = "", project_root: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """Python-primary mark_green (completes the edit→record→wiki→green ritual).

    Captures source_content_hash baseline (via health.mark_green when available)
    so subsequent mtime-only thrash does not re-Yellow content-clean files.
    """
    root = _get_effective_root(project_root)
    result: Dict[str, Any] = {"success": False, "file": file, "project_root": str(root)}
    rsn = reason or "Summary updated and verified accurate."
    try:
        lock_ctx = (locking.file_lock(root) if locking is not None else _nullcontext())
        with lock_ctx:
            if _health_mod is not None and hasattr(_health_mod, "mark_green"):
                # Prefer health.mark_green (wiki hash + source_content_hash)
                if hasattr(_health_mod, "_do_mark_green"):
                    _health_mod._do_mark_green(root, file, rsn)
                else:
                    _health_mod.mark_green(root, file, rsn)
            elif _health_mod is not None:
                _health_mod.upsert_entry(root, file, "🟢 Green", rsn)
                # Best-effort source baseline without full health.mark_green
                try:
                    compute = getattr(_health_mod, "compute_source_content_hash", None)
                    if compute:
                        src = root / file
                        h = compute(src if src.is_file() else Path(file))
                        if h:
                            data = _health_mod.load_health(root)
                            ent = data.setdefault("entries", {}).get(file) or {}
                            if isinstance(ent, dict):
                                ent["status"] = "🟢 Green"
                                ent["reason"] = rsn
                                ent["source_content_hash"] = h
                                data["entries"][file] = ent
                                _health_mod.save_health(root, data)
                except Exception:
                    pass
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

    G3: Prioritize 🔴 then 🟡 only — never suggest re-wiki of green or full-tree
    re-summarize. G4: ACS suggestions use actionable_low_conf_edges (excludes
    stdlib/external bare noise).
    """
    root = _get_effective_root(project_root)
    try:
        red = yellow = stub_y = action_y = 0
        health_sum: Dict[str, Any] = {}
        if _health_mod is not None:
            health_sum = _health_mod.get_summary(root, directory) or {}
            red = int(health_sum.get("red", 0) or 0)
            yellow = int(health_sum.get("yellow", 0) or 0)
            stub_y = int(health_sum.get("stub_yellow", 0) or 0)
            action_y = int(health_sum.get("actionable_yellow", yellow - stub_y) or 0)

        suggestions: List[str] = []
        n = 1
        if red > 0:
            suggestions.append(
                f"{n}. Tackle the {red} 🔴 Red file(s) first (get_files_needing_attention status=red). "
                "Do not re-wiki 🟢 Green files."
            )
            n += 1
        if action_y > 0:
            suggestions.append(
                f"{n}. Review {action_y} *actionable* 🟡 Yellow file(s) "
                "(content/record-change/barrel — not Initial stubs). "
                "record-change → wiki that file → mark-green. Skip green."
            )
            n += 1
        if stub_y > 0 and action_y == 0 and red == 0:
            suggestions.append(
                f"{n}. Map-first OK: {stub_y} 🟡 Initial stubs mean \"on the map\", "
                "NOT \"wiki this tree now\". Lookup via prepare_edit/get_file_wiki; "
                "write prose only when you edit a file, then mark-green."
            )
            n += 1
        elif stub_y > 0 and action_y > 0:
            suggestions.append(
                f"{n}. Ignore {stub_y} map-first stubs for bulk work; only actionable yellows need wiki."
            )
            n += 1
        if red == 0 and yellow == 0:
            suggestions.append(
                f"{n}. Health is clean (no red/yellow). Do not re-summarize the tree; use the map for lookup only."
            )
            n += 1
        # Scope hygiene
        scope_warnings: List[str] = []
        if _health_mod is not None and hasattr(_health_mod, "detect_scope_risks"):
            try:
                scope = _health_mod.detect_scope_risks(root) or {}
                scope_warnings = list(scope.get("warnings") or [])
                for w in scope_warnings[:2]:
                    suggestions.append(f"{n}. SCOPE: {w}")
                    n += 1
            except Exception:
                pass
        suggestions.append(
            f"{n}. Run `update_maps(directory=...)` only if imports/structure changed (not for wiki-only edits)."
        )
        n += 1
        suggestions.append(
            f"{n}. On yellow/red hotspots, prepare_edit(file) / dependents before editing callers."
        )
        n += 1
        suggestions.append(
            f"{n}. Long-horizon: `wikifier autonomous-status` before unattended daemon; "
            "lean monitored_paths; never parent multi-repo folders as project_root."
        )

        acs_note = ""
        actionable = 0
        map_coverage: Dict[str, Any] = {}
        if _ic_mod is not None:
            try:
                # Prefer light meta (sqlite) over full pair deserialize
                try:
                    from . import cache_store as cs
                    meta = cs.load_meta(root, keys=("_acs_summary", "_map_coverage"))
                    acs = meta.get("_acs_summary") if isinstance(meta.get("_acs_summary"), dict) else {}
                    map_coverage = (
                        meta.get("_map_coverage")
                        if isinstance(meta.get("_map_coverage"), dict)
                        else {}
                    )
                except Exception:
                    acs = {}
                if not acs or "actionable_low_conf_edges" not in acs:
                    cache = _ic_mod.load_cache(root) or {}
                    acs = _ic_mod.ensure_acs_summary_persisted(cache, root) or {}
                    if not map_coverage and isinstance(cache.get("_map_coverage"), dict):
                        map_coverage = cache["_map_coverage"]
                actionable = int(acs.get("actionable_low_conf_edges", 0) or 0)
                raw_low = int(acs.get("low_conf_edges", 0) or 0)
                noise = int(acs.get("external_noise_edges", 0) or 0)
                rem = int(map_coverage.get("files_remaining_dirty") or 0)
                if map_coverage.get("complete") is False or rem > 0:
                    n += 1
                    suggestions.append(
                        f"{n}. MAP INCOMPLETE: files_remaining_dirty={rem}, "
                        f"complete={map_coverage.get('complete')}. "
                        "Re-run update_maps (same directory/max_files) until "
                        "map_coverage.complete=true — success alone is not done."
                    )
                if actionable > 0:
                    n += 1
                    suggestions.append(
                        f"{n}. Review {actionable} actionable low-confidence *project* edges "
                        f"(prefer actionable_low_conf_edges + reason_code_counts; "
                        f"raw low_conf={raw_low} includes noise)."
                    )
                    acs_note = (
                        f" ACS actionable_low={actionable} (raw_low={raw_low}, external_noise={noise}, "
                        f"avg={acs.get('avg_confidence')})."
                    )
                elif raw_low > 0:
                    acs_note = (
                        f" ACS: {raw_low} low-conf edges are mostly external/stdlib noise "
                        f"(actionable=0); no agent action required for those."
                    )
            except Exception:
                pass

        # Dispatchable structured actions (agent-first)
        red_files: List[str] = []
        action_yellow_files: List[str] = []
        try:
            from .agent_loop import build_structured_actions
            if _health_mod is not None:
                data = _health_mod.load_health(root)
                for f, e in (data.get("entries") or {}).items():
                    if directory and not str(f).startswith(str(directory).rstrip("/") + "/"):
                        continue
                    st = str((e or {}).get("status") or "")
                    reason = str((e or {}).get("reason") or "")
                    if "Red" in st or "🔴" in st:
                        red_files.append(f)
                    elif ("Yellow" in st or "🟡" in st) and "Initial stub" not in reason:
                        action_yellow_files.append(f)
            actions = build_structured_actions(
                red_files=red_files,
                actionable_yellow_files=action_yellow_files,
                stub_yellow=stub_y,
                actionable_yellow=action_y,
                red=red,
                acs_actionable=actionable,
                scope_warnings=scope_warnings,
                clean=(red == 0 and yellow == 0),
                map_coverage=map_coverage,
            )
        except Exception:
            actions = []

        if format == "json":
            return {
                "success": True,
                "project_root": str(root),
                "red": red,
                "yellow": yellow,
                "stub_yellow": stub_y,
                "actionable_yellow": action_y,
                "health_score": health_sum.get("health_score"),
                "suggestions": suggestions,
                "actions": actions,
                "health_summary": health_sum,
                "acs_note": acs_note,
                "map_coverage": map_coverage,
                "selective_work": True,
                "map_first": True,
            }
        # Text: prose + compact action lines
        lines = list(suggestions)
        if map_coverage:
            lines.append(
                f"map_coverage: complete={map_coverage.get('complete')} "
                f"remaining_dirty={map_coverage.get('files_remaining_dirty')}"
            )
        if actions:
            lines.append("Actions (dispatchable):")
            for a in actions[:12]:
                tgt = a.get("file") or "—"
                lines.append(f"  [{a.get('priority')}] {a.get('action')} {tgt}: {a.get('reason')}")
        return "\n".join(lines) + (acs_note or "")
    except Exception as e:
        if format == "json":
            return {"success": False, "error": str(e), "project_root": str(root)}
        return f"suggest_next_actions error (Python): {e}"


def session_bootstrap(
    project_root: Optional[Union[str, Path]] = None,
    directory: Optional[str] = None,
) -> Dict[str, Any]:
    """One-shot agent session start (delegates to agent_loop.session_bootstrap)."""
    from .agent_loop import session_bootstrap as _sb
    return _sb(project_root=project_root, directory=directory)


def prepare_edit(
    file: str,
    project_root: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Single-file preflight lookup (wiki/status/deps/dependents)."""
    from .agent_loop import prepare_edit as _pe
    return _pe(file, project_root=project_root)


def search_journal(
    project_root: Optional[Union[str, Path]] = None,
    query: Optional[str] = None,
    file: Optional[str] = None,
    max_results: int = 20,
) -> Dict[str, Any]:
    """Search journal semantic trail."""
    from .agent_loop import search_journal as _sj
    return _sj(project_root=project_root, query=query, file=file, max_results=max_results)


def why_file(
    file: str,
    project_root: Optional[Union[str, Path]] = None,
    max_results: int = 10,
) -> Dict[str, Any]:
    """Why is this file yellow/red — health reason + journal matches."""
    from .agent_loop import why_file as _wf
    return _wf(file, project_root=project_root, max_results=max_results)


def seed_source_content_hashes(
    project_root: Optional[Union[str, Path]] = None,
    only_green: bool = True,
    force: bool = False,
    directory: Optional[str] = None,
) -> Dict[str, Any]:
    """Seed source_content_hash baselines without mass Yellow (migration helper)."""
    root = _get_effective_root(project_root)
    if _health_mod is None or not hasattr(_health_mod, "seed_source_content_hashes"):
        return {"success": False, "project_root": str(root), "error": "health.seed_source_content_hashes unavailable"}
    return _health_mod.seed_source_content_hashes(
        root, only_green=only_green, force=force, directory=directory
    )


def list_core_tools() -> Dict[str, Any]:
    """Core daily agent tool listing (prefer over full MCP catalog)."""
    from .agent_loop import list_core_tools as _lct
    return _lct()


def cache_status(
    project_root: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Dual-cache ops surface: backend, bytes, ACS version, map_coverage (no full pair load)."""
    root = _get_effective_root(project_root)
    try:
        from . import cache_store as cs
        out = cs.cache_status(root)
        out["success"] = True
        return out
    except Exception as e:
        return {
            "success": False,
            "project_root": str(root),
            "error": str(e),
        }


def update_maps(
    project_root: Optional[Union[str, Path]] = None,
    full: bool = False,
    directory: Optional[str] = None,
    use_python_primary: bool = True,
    verbose: bool = False,
    max_files: Optional[int] = None,
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
            directory=directory,
            max_files=max_files,
        )
        res = dict(res)  # copy
        res["library_facade"] = True
        res["scoped_directory"] = directory
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
# short summaries, folder browser, copy buttons for tree/snapshot, a "Quick actions" toolbar
# with copy buttons for main commands (check-changes, update-maps, monitor &), and prominent
# buttons + session-guarded auto-copy of update-maps in empty states for easy first-run setup.
# (data-driven from its file_health.* + library.md after check-changes + update-maps).
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
        pkg_files = files("wikifier")  # now ships index.html inside the wikifier/ package dir (Phase 2 packaging hygiene); resources finds it for installed wheels too
        for name in ("index.html",):  # only the generic human wiki viewer for the *target*; diagnostics.html is Wikifier maintainer-only (never copied)
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
    # Fallback: source tree (editable or direct); support both legacy root layout and html now under wikifier/ package dir
    try:
        here = Path(__file__).parent  # wikifier/ dir (preferred post-Phase2; contains index.html for proper package data)
        for name in ("index.html",):
            src = here / name
            if src.exists():
                dst = Path(target_dir) / name
                if not dst.exists():
                    shutil.copy(src, dst)
                continue  # prefer the inner one if present
        # also try grandparent for root-level copy in source tree (this project's own dashboard location)
        here2 = Path(__file__).parent.parent
        for name in ("index.html",):
            src = here2 / name
            if src.exists():
                dst = Path(target_dir) / name
                if not dst.exists():
                    shutil.copy(src, dst)
    except Exception:
        pass
