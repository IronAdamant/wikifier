"""MCP status intel — library work wrapped in an in-process deadline.

Stdlib only (no FastMCP). `server_impl` tools delegate here so
get_project_status / get_files_needing_attention cannot hang behind
timeout_s<=0 short-circuits that skip call_with_deadline.
"""
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, Dict, Optional, Union

from .deadline import (
    MCP_ATTENTION_LIMIT,
    MCP_INPROCESS_DEADLINE_S,
    call_with_deadline,
)


def _read_pending(root: Path) -> str:
    p = Path(root) / "pending_updates.md"
    if p.exists():
        try:
            return p.read_text(encoding="utf-8")
        except Exception:
            return ""
    return ""


def _files_needing_attention_work(
    root: Path,
    status: str,
    directory: Optional[str],
    fmt: str,
) -> Union[str, Dict[str, Any]]:
    health_module = importlib.import_module("wikifier.health")
    status_filter = None
    if status == "red":
        status_filter = "🔴"
    elif status == "yellow":
        status_filter = "🟡"
    files = health_module.get_files_needing_attention(root, status_filter, directory)
    if isinstance(files, list) and len(files) > MCP_ATTENTION_LIMIT:
        files = files[:MCP_ATTENTION_LIMIT]
    if fmt == "json":
        acs_ctx: Dict[str, Any] = {}
        try:
            import wikifier.import_cache as ic
            cache = ic.load_cache(root)
            acs = ic.ensure_acs_summary_persisted(cache, root)
            if acs.get("low_conf_edges", 0):
                acs_ctx = {
                    "low_conf_edges": acs.get("low_conf_edges"),
                    "avg_confidence": acs.get("avg_confidence"),
                    "acs_version": acs.get("acs_version"),
                }
        except Exception:
            pass
        return {
            "success": True,
            "project_root": str(root),
            "directory": directory or ".",
            "status_filter": status,
            "files": files,
            "count": len(files) if isinstance(files, list) else 0,
            "acs_low_conf_context": acs_ctx or None,
        }
    if not files:
        return "No files currently need attention."
    return "Files needing attention:\n" + "\n".join(f"- {f}" for f in files)


def run_files_needing_attention(
    root: Path,
    status: str = "all",
    directory: Optional[str] = None,
    format: str = "text",
    timeout_s: Optional[float] = None,
) -> Union[str, Dict[str, Any]]:
    t = MCP_INPROCESS_DEADLINE_S if timeout_s is None else timeout_s
    res = call_with_deadline(
        _files_needing_attention_work,
        root,
        status,
        directory,
        format,
        timeout_s=t,
    )
    if isinstance(res, dict) and res.get("timed_out"):
        res.setdefault("project_root", str(root))
        if format != "json":
            return "Error: MCP in-process deadline exceeded"
        return res
    return res


def _project_status_work(
    root: Path,
    directory: Optional[str],
    fmt: str,
) -> Union[str, Dict[str, Any]]:
    health_module = importlib.import_module("wikifier.health")
    summary = health_module.get_summary(root, directory) or {}
    pending = _read_pending(root)
    if hasattr(health_module, "count_pending"):
        pending_count = int(health_module.count_pending(root))
    else:
        pending_count = len([
            ln for ln in pending.splitlines()
            if ln.strip().startswith("- ") and not ln.strip().startswith("- (")
        ])
    dep_intel: Dict[str, Any] = {}
    try:
        import wikifier.import_cache as ic
        cache = ic.load_cache(root)
        acs = ic.ensure_acs_summary_persisted(cache, root)
        cyc = ic.get_cycle_analyses(cache) or {}
        barrel = ic.get_barrel_cache_summary(cache) or {}
        sample_barrel_reports = []
        if barrel.get("has_brc"):
            try:
                reps = ic.get_barrel_invalidation_reports(cache, root, changed_files=None) or []
                sample_barrel_reports = reps[:5]
            except Exception:
                sample_barrel_reports = []
        if acs.get("total_scored_edges", 0) or cyc or barrel.get("has_brc"):
            dep_intel = {
                "acs_summary": acs,
                "ciabre_summary": cyc.get("summary") or {},
                "ciabre_version": cyc.get("analysis_version"),
                "acs_version": acs.get("acs_version"),
                "barrel_invalidation_summary": barrel,
                "sample_barrel_reports": sample_barrel_reports,
                "reverse_dependency_index": ic.get_reverse_dependency_stats(cache),
            }
            try:
                unresolved_samples = ic.get_unresolved_imports(cache, max_results=5) or []
                lowc_samples = ic.get_low_confidence_edges(cache, max_results=5) or []
                diag_sum = ic.ensure_diagnostics_aggregate(cache) or {}
                if unresolved_samples or lowc_samples or diag_sum.get("low_or_unresolved_count"):
                    dep_intel["resolution_transparency"] = {
                        "low_or_unresolved_count": diag_sum.get("low_or_unresolved_count", 0),
                        "by_category": diag_sum.get("by_category", {}),
                        "sample_unresolved_or_low_conf": unresolved_samples or lowc_samples or diag_sum.get("samples", [])[:5],
                    }
            except Exception:
                pass
    except Exception:
        pass

    green = int(summary.get("green") or 0)
    yellow = int(summary.get("yellow") or 0)
    red = int(summary.get("red") or 0)
    total = int(summary.get("total") or (green + yellow + red))
    health_score = str(
        summary.get("health_score")
        or (
            "Good" if red == 0 and yellow < 5
            else "Needs Attention" if red < 3
            else "Critical"
        )
    )
    if fmt == "json":
        out: Dict[str, Any] = {
            "success": True,
            "project_root": str(root),
            "total_files": total,
            "green": green,
            "yellow": yellow,
            "red": red,
            "pending_updates": pending_count,
            "health_score": health_score,
            "dependency_intel": dep_intel,
        }
        for k in ("stub_yellow", "actionable_yellow", "map_first_note"):
            if k in summary:
                out[k] = summary[k]
        return out

    dir_str = f" (in {directory})" if directory else ""
    dep_lines = ""
    if dep_intel.get("acs_summary") or dep_intel.get("barrel_invalidation_summary"):
        a = dep_intel.get("acs_summary") or {}
        c = dep_intel.get("ciabre_summary", {})
        b = dep_intel.get("barrel_invalidation_summary", {}) or {}
        barrel_line = ""
        if b.get("has_brc"):
            barrel_line = (
                f"\n  Barrel/BRC (v{b.get('version', 'bree-v2')}): "
                f"{b.get('num_chains', 0)} chains"
            )
        dep_lines = (
            f"\nDependency Intelligence (ACS v{a.get('acs_version', '1.0')} "
            f"+ CIABRE v{dep_intel.get('ciabre_version', '1.3')}):{barrel_line}\n"
            f"  ACS: {a.get('total_scored_edges', 0)} edges | "
            f"avg={a.get('avg_confidence', 0)} | low<0.65: {a.get('low_conf_edges', 0)}\n"
            f"  CIABRE: {c.get('high_severity_count', 0)} high-sev cycles"
        )
    return (
        f"Project Documentation Health{dir_str}\n"
        f"-----------------------------\n"
        f"[GREEN] Green:   {green}\n"
        f"[YELLOW] Yellow:  {yellow}\n"
        f"[RED] Red:     {red}\n\n"
        f"Pending updates: {pending_count}\n"
        f"{dep_lines}\n\n"
        "Use get_files_needing_attention() for the actual list."
    )


def run_project_status(
    root: Path,
    directory: Optional[str] = None,
    format: str = "text",
    timeout_s: Optional[float] = None,
) -> Union[str, Dict[str, Any]]:
    t = MCP_INPROCESS_DEADLINE_S if timeout_s is None else timeout_s
    res = call_with_deadline(
        _project_status_work,
        root,
        directory,
        format,
        timeout_s=t,
    )
    if isinstance(res, dict) and res.get("timed_out"):
        res.setdefault("project_root", str(root))
        if format != "json":
            return "Error: MCP in-process deadline exceeded"
        return res
    return res
