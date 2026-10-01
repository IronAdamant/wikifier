"""Barrel (re-export) resolution cache: persistence, stale-importer invalidation, pruning."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

from .io import load_cache, save_cache


def get_barrel_resolutions(cache: Dict[str, Any]) -> Dict[str, Any]:
    """Return the persisted _barrel_resolutions dict (or empty)."""
    return (cache or {}).get("_barrel_resolutions", {}) or {}


def get_barrel_file_index(cache: Dict[str, Any]) -> Dict[str, Any]:
    """Return the persisted _barrel_file_index reverse map (or empty)."""
    return (cache or {}).get("_barrel_file_index", {}) or {}


def set_barrel_resolutions(cache: Dict[str, Any], resolutions: Dict[str, Any]) -> None:
    # always materialize the key (empty dict = intentional clear). save_cache()
    # only preserves on-disk barrel state when the key is absent from the saved dict.
    cache["_barrel_resolutions"] = resolutions or {}


def set_barrel_file_index(cache: Dict[str, Any], file_index: Dict[str, Any]) -> None:
    # always materialize the key (empty dict = intentional clear); see save_cache().
    cache["_barrel_file_index"] = file_index or {}


def invalidate_stale_barrel_entries(
    cache: Dict[str, Any],
    root: Path,
    changed_files: Optional[Iterable[Union[str, Path]]] = None,
) -> List[str]:
    """
    Return list of importer relpaths that were using barrel chains now considered stale
    (any file in their mtimes_snapshot has a newer mtime) or, when changed_files is
    supplied, the fast O(#changed) path: for each changed file that is a known barrel
    in the reverse index, return its registered importers.

    This enables the scalable "edit barrel → only affected importers re-analyzed"
    hot path.

    When changed_files is provided (list of str/Path from the just-computed dirty set),
    we use brc.get_affected_importers() via the file_index (no full scan over chains).
    Falls back to full collect_stale_importers(root) only if changed_files is None.

    Used by first-pass to augment the dirty set before re-parsing.
    Non-destructive (does not mutate cache here; caller decides).
    All paths are handled defensively for rel/abs forms (pre-canonical-hardening).
    """
    from ..parsers.bree import BarrelResolutionCache  # local import to avoid cycles at module load

    brc = BarrelResolutionCache.from_cache(cache)

    from ..parsers.bree._bree import _brc_canonical

    if changed_files is not None:
        # Delta path: O(#changed) exact lookups in the reverse index (canonical keys).
        affected: set = set()
        for f in changed_files:
            if not f:
                continue
            affected.update(brc.get_affected_importers(str(f)))
            affected.update(brc.get_affected_importers(_brc_canonical(f, root)))
        if affected:
            return sorted(affected)
        # Reverse index empty (e.g. never flushed): scan via_barrel pairs instead.
        return _importers_via_barrel_pairs(cache, changed_files, root)

    # Legacy / full-rebuild / no-dirty-list path: scan all chains (still safe, #chains << #files)
    stale_importers = brc.collect_stale_importers(root)
    affected = set(stale_importers)
    if not affected:
        affected.update(_importers_via_barrel_pairs(cache, None, root))
    return sorted(affected)


def _strip_dot_slash(path: str) -> str:
    while path.startswith("./"):
        path = path[2:]
    return path


def _importers_via_barrel_pairs(
    cache: Dict[str, Any],
    changed_files: Optional[Iterable[Union[str, Path]]],
    root: Path,
) -> List[str]:
    """Find importers whose persisted via_barrel pairs mention a changed file.

    Used when `_barrel_file_index` is empty but parsers already expanded barrels
    into resolved_pairs (via_barrel + barrel_v2.barrel_chain).
    """
    from ..parsers.bree._bree import _brc_canonical

    changed: set = set()
    if changed_files:
        for f in changed_files:
            if not f:
                continue
            s = str(f).replace("\\", "/")
            changed.add(s)
            changed.add(_brc_canonical(s, Path(root)))
    out: set = set()
    for src, data in (cache or {}).items():
        if not isinstance(src, str) or src.startswith("_") or not isinstance(data, dict):
            continue
        for pair in data.get("resolved_pairs") or []:
            if not isinstance(pair, dict):
                continue
            if not pair.get("via_barrel"):
                continue
            needles = [str(pair.get("resolved") or "").replace("\\", "/")]
            bv = pair.get("barrel_v2") if isinstance(pair.get("barrel_v2"), dict) else {}
            for hop in bv.get("barrel_chain") or []:
                needles.append(_strip_dot_slash(str(hop).replace("\\", "/")))
            if not changed_files:
                out.add(src)
                break
            for n in needles:
                if not n:
                    continue
                n_norm = _strip_dot_slash(n)
                if n_norm in changed or n in changed or Path(n_norm).name in {Path(c).name for c in changed}:
                    # Prefer path suffix match (leaf.js vs barrel/leaf.js)
                    if any(
                        n_norm == c or n_norm.endswith("/" + c) or c.endswith("/" + n_norm) or c == n_norm
                        for c in changed
                    ):
                        out.add(src)
                        break
            if src in out:
                break
    return sorted(out)


def get_barrel_invalidation_reports(
    cache: Dict[str, Any],
    root: Path,
    changed_files: Optional[Iterable[Union[str, Path]]] = None,
) -> List[Dict[str, Any]]:
    """: Return structured BarrelInvalidationReport dicts (importer, triggering_barrels,
    chain_ids, reason, detector_used, is_partial, node_identity_version=v1, ...).
    Enables "why was this re-parsed?" answers in sh debug, diagnostics, MCP, journal.
    Delegates to BRC.build_invalidation_reports for the logic (O(changed) or scan).
    """
    from dataclasses import asdict

    from ..parsers.bree import BarrelResolutionCache

    reports = BarrelResolutionCache.from_cache(cache).build_invalidation_reports(changed_files=changed_files, root=root)
    return [asdict(r) if hasattr(r, "__dataclass_fields__") else (r if isinstance(r, dict) else vars(r)) for r in reports]


def get_barrel_cache_summary(cache: Dict[str, Any]) -> Dict[str, Any]:
    """Lightweight BRC summary stats for health/MCP/diagnostics surfacing.
    Counts only (no content); includes v1 canonical stamp coverage + partials.
    Always safe, fast, zero-dep. Used in get_project_status + health(json) + sh.
    """
    # get_barrel_cache_summary (import_cache ACS/barrel) as first-class O(k) default for 20k+ creative surfaces (MCP health/get_*/suggest, harness, daemon/journal paths); complements format=summary + CIABRE.
    try:
        from ..parsers.bree import BarrelResolutionCache
        brc = BarrelResolutionCache.from_cache(cache)
        resolutions = brc.resolutions or {}
        n_chains = len(resolutions)
        n_index = len(brc.file_index or {})
        v1_count = sum(1 for e in resolutions.values() if isinstance(e, dict) and e.get("node_identity_version") == "v1")
        partial_count = sum(1 for e in resolutions.values() if isinstance(e, dict) and e.get("is_partial"))
        return {
            "num_chains": n_chains,
            "num_indexed_barrels": n_index,
            "v1_canonical_chains": v1_count,
            "partial_chains": partial_count,
            "node_identity_version": "v1",
            "has_brc": bool(n_chains or n_index),
            "version": "bree-v2-wave2",
        }
    except Exception:
        return {"num_chains": 0, "has_brc": False, "error": "unavailable"}


def append_barrel_invalidation_log(
    cache: Dict[str, Any],
    reports: List[Dict[str, Any]],
    max_entries: int = 100,
) -> int:
    """Lightweight audit append for _barrel_invalidation_log.

    Mutates the cache dict in-place with bounded recent structured reports (each augmented
    with 'ts' epoch for ordering). Only grows on real barrel-driven invalidation events.
    Zero-dep, O(reports), safe for hot paths; called from sh delta blocks (both copies),
    check-changes, and any future daemon/MCP direct use of reports.

    The log is human-readable in cache JSON and queryable via load_cache + key for agents
    doing post-mortem on "which barrel edits caused which re-parses over time".
    Bounded to prevent unbounded growth even on long-lived daemons at 50k scale.
    """
    if not reports:
        return 0
    try:
        from dataclasses import asdict
        log = cache.get("_barrel_invalidation_log")
        if not isinstance(log, list):
            log = []
        now = time.time()
        for r in reports:
            if isinstance(r, dict):
                rec = dict(r)
            else:
                try:
                    rec = asdict(r) if hasattr(r, "__dataclass_fields__") else {"raw": str(r)}
                except Exception:
                    rec = {"raw": str(r)}
            rec["ts"] = now
            log.append(rec)
        # keep most recent N
        if len(log) > max_entries:
            log = log[-max_entries:]
        cache["_barrel_invalidation_log"] = log
        return len(reports)
    except Exception:
        # never fail a caller
        return 0


def prune_barrel_resolutions(
    root: Path, max_age_days: float = 90.0, dry_run: bool = False,
    deleted_files: Optional[Iterable[Union[str, Path]]] = None
) -> Dict[str, Any]:
    """Lightweight age-based + deletion-triggered pruning/GC for persistent BarrelResolutionCache.

    Delegates to BRC.prune_aged_entries + new prune_references_to (for record-deletion paths).
    Supports deleted_files for precise removal of chains/importers/index refs mentioning deleted paths.
    Saves under lock only on actual change. Scalable (O(#chains) tiny).
    Returns rich stats; called from check-changes, update-maps, record-deletion (both sh), health CLI.

    Zero-dep, additive to prior age-only behavior (deleted_files=None keeps old contract).
    """
    try:
        from ..parsers.bree import BarrelResolutionCache
        cache = load_cache(root)
        brc = BarrelResolutionCache.from_cache(cache)
        before_chains = len(brc.resolutions)
        before_index = len(brc.file_index)
        del_list = [str(d) for d in (deleted_files or []) if d]
        if dry_run:
            now = time.time()
            cutoff = now - (max_age_days * 86400.0)
            pruned = 0
            for cid, ent in (brc.resolutions or {}).items():
                try:
                    ca = 0.0
                    if isinstance(ent, dict):
                        ca = float(ent.get("created_at", 0) or 0)
                    else:
                        ca = float(getattr(ent, "created_at", 0) or 0)
                    if ca > 0 and ca < cutoff:
                        pruned += 1
                except Exception:
                    continue
            # dry-run also counts potential deletion matches (no mutate)
            for cid, ent in (brc.resolutions or {}).items():
                try:
                    chain_imps = []
                    if isinstance(ent, dict):
                        chain_imps = (ent.get("barrel_chain", []) or []) + (ent.get("importers", []) or [])
                    else:
                        chain_imps = (getattr(ent, "barrel_chain", []) or []) + (getattr(ent, "importers", []) or [])
                    hay = " ".join(str(x) for x in chain_imps)
                    if any(d in hay for d in del_list):
                        pruned += 1  # count as would-be-pruned
                except Exception:
                    continue
            ret = {
                "pruned": pruned,
                "dry_run": True,
                "before_chains": before_chains,
                "before_indexed_barrels": before_index,
                "max_age_days": max_age_days,
            }
            if del_list:
                ret["deleted_files_considered"] = del_list[:5]
            return ret
        pruned_age = brc.prune_aged_entries(max_age_days)
        pruned_del = brc.prune_references_to(del_list) if del_list else 0
        pruned = pruned_age + pruned_del
        saved = False
        if pruned > 0:
            brc.to_cache_updates(cache)
            save_cache(root, cache)
            saved = True
        ret = {
            "pruned": pruned,
            "pruned_age": pruned_age,
            "pruned_by_deletion": pruned_del,
            "dry_run": False,
            "before_chains": before_chains,
            "after_chains": len(brc.resolutions),
            "before_indexed_barrels": before_index,
            "after_indexed_barrels": len(brc.file_index),
            "max_age_days": max_age_days,
            "saved": saved,
        }
        if del_list:
            ret["deleted_files_considered"] = del_list[:5]
        return ret
    except Exception as e:
        return {"pruned": 0, "error": str(e), "max_age_days": max_age_days}
