"""MCP status tools (stdlib only) run under an in-process deadline.

Summaries come from persisted cache metadata (ACS, cycle analyses, barrel
cache, resolution diagnostics) — no full cache load on the status path.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Union

from wikifier import cache_store as cs
from wikifier import health_pkg as health_mod
from wikifier import import_cache as ic

from .deadline import MCP_ATTENTION_LIMIT, MCP_INPROCESS_DEADLINE_S, call_with_deadline

_STATUS_META_KEYS = (
    "_acs_summary", "_cycle_analyses", "_resolution_diagnostics",
    "_barrel_resolutions", "_barrel_file_index",
)


def _dependency_intel(root: Path) -> Dict[str, Any]:
    meta = cs.load_meta(root, keys=_STATUS_META_KEYS)
    acs = meta.get("_acs_summary") or {}
    analyses = meta.get("_cycle_analyses") or {}
    diagnostics = meta.get("_resolution_diagnostics") or {}
    barrel = ic.get_barrel_cache_summary(meta) or {}
    if not (acs or analyses or barrel.get("has_brc") or diagnostics):
        return {}
    return {
        "acs_summary": acs,
        "acs_version": acs.get("acs_version"),
        "ciabre_summary": analyses.get("summary") or {},
        "ciabre_version": analyses.get("analysis_version"),
        "barrel_invalidation_summary": barrel,
        "resolution_transparency": {
            "low_or_unresolved_count": diagnostics.get("low_or_unresolved_count", 0),
            "by_category": diagnostics.get("by_category", {}),
            "samples": (diagnostics.get("samples") or [])[:5],
        },
    }


def _files_needing_attention_work(root: Path, status: str, directory: Optional[str], fmt: str) -> Union[str, Dict[str, Any]]:
    status_filter = {"red": "🔴", "yellow": "🟡"}.get(status)
    files = health_mod.get_files_needing_attention(root, status_filter, directory)
    total = len(files)
    files = files[:MCP_ATTENTION_LIMIT]
    if fmt == "json":
        acs = cs.load_meta(root, keys=("_acs_summary",)).get("_acs_summary") or {}
        return {
            "success": True,
            "project_root": str(root),
            "directory": directory or ".",
            "status_filter": status,
            "files": files,
            "count": len(files),
            "total": total,
            "truncated": total > len(files),
            "acs_low_conf_context": {
                "actionable_low_conf_edges": acs.get("actionable_low_conf_edges"),
                "low_conf_edges": acs.get("low_conf_edges"),
                "acs_version": acs.get("acs_version"),
            } if acs else None,
        }
    if not files:
        return "No files currently need attention."
    more = f"\n… {total - len(files)} more (use format='json' or a directory filter)" if total > len(files) else ""
    return "Files needing attention:\n" + "\n".join(f"- {f}" for f in files) + more


def _run(fn, root: Path, *args: Any, fmt: str, timeout_s: Optional[float]) -> Union[str, Dict[str, Any]]:
    res = call_with_deadline(fn, root, *args, fmt, timeout_s=MCP_INPROCESS_DEADLINE_S if timeout_s is None else timeout_s)
    if isinstance(res, dict) and res.get("timed_out"):
        res.setdefault("project_root", str(root))
        return res if fmt == "json" else "Error: MCP in-process deadline exceeded"
    return res


def run_files_needing_attention(
    root: Path,
    status: str = "all",
    directory: Optional[str] = None,
    format: str = "text",
    timeout_s: Optional[float] = None,
) -> Union[str, Dict[str, Any]]:
    return _run(_files_needing_attention_work, root, status, directory, fmt=format, timeout_s=timeout_s)


def _project_status_work(root: Path, directory: Optional[str], fmt: str) -> Union[str, Dict[str, Any]]:
    summary = health_mod.get_summary(root, directory)
    intel = _dependency_intel(root)
    if fmt == "json":
        out: Dict[str, Any] = {
            "success": True,
            "project_root": str(root),
            "total_files": summary.get("total", 0),
            "green": summary.get("green", 0),
            "yellow": summary.get("yellow", 0),
            "red": summary.get("red", 0),
            "pending_updates": summary.get("pending_updates", 0),
            "health_score": summary.get("health_score"),
            "dependency_intel": intel,
        }
        for key in ("stub_yellow", "actionable_yellow", "map_first_note"):
            out[key] = summary.get(key)
        return out
    lines = [
        f"Project documentation health{f' (in {directory})' if directory else ''}: {summary.get('health_score')}",
        f"  🟢 {summary.get('green', 0)}   🟡 {summary.get('yellow', 0)} "
        f"({summary.get('actionable_yellow', 0)} actionable, {summary.get('stub_yellow', 0)} stubs)   🔴 {summary.get('red', 0)}",
        f"  pending updates: {summary.get('pending_updates', 0)}",
    ]
    if intel:
        acs = intel.get("acs_summary") or {}
        lines.append(
            f"  dependency intel: {acs.get('total_scored_edges', 0)} scored edges, "
            f"{acs.get('actionable_low_conf_edges', 0)} actionable low-confidence, "
            f"{(intel.get('ciabre_summary') or {}).get('high_severity_count', 0)} high-severity cycles"
        )
    lines.append("Use get_files_needing_attention() for the list.")
    return "\n".join(lines)


def run_project_status(
    root: Path,
    directory: Optional[str] = None,
    format: str = "text",
    timeout_s: Optional[float] = None,
) -> Union[str, Dict[str, Any]]:
    return _run(_project_status_work, root, directory, fmt=format, timeout_s=timeout_s)
