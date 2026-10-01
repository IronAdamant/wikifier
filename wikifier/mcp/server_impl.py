from __future__ import annotations

"""
Wikifier MCP server — thin adapter over :mod:`wikifier.api` (optional extra).

Core daily surface (start here every session):
  session_bootstrap → check_changes → prepare_edit → (edit) → record_change → mark_green
  suggest_next_actions for selective work.

Every tool accepts ``project_root``; an explicit root that does not exist is an
error (never a silent fallback). Read tools never write state. Mutating tools
run under an in-process deadline; on ``timed_out`` the operation may still
finish in the background — call ``why_file`` before retrying (journal writes
de-duplicate identical retries).

Run: ``WIKIFIER_PROJECT_ROOT=/path wikifier-mcp`` or ``python -m wikifier.mcp.server``.
"""

try:
    from mcp.server.fastmcp import FastMCP
    from pydantic import BaseModel
except ImportError as _e:  # pragma: no cover - exercised only without the extra
    raise ImportError(
        "The Wikifier MCP server requires the optional 'mcp' extra "
        "(pip install 'wikifier[mcp]', mcp>=1,<2). The core CLI and library work without it."
    ) from _e

import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from wikifier import api
from wikifier import cache_store as cs
from wikifier import health_pkg as health_mod
from wikifier import import_cache as ic
from wikifier.paths import ProjectPathError, ProjectRootError, resolve_root, to_rel

from .deadline import MCP_INPROCESS_DEADLINE_S, call_with_deadline as _call_with_deadline
from .status_ops import run_files_needing_attention, run_project_status

mcp = FastMCP("Wikifier")


def _discover_project_root() -> Path:
    try:
        return resolve_root()
    except ProjectRootError:
        return Path.cwd().resolve()


WIKIFIER_ROOT = _discover_project_root()


def _get_effective_root(project_root: Optional[str] = None) -> Path:
    """Explicit ``project_root`` (must exist) → env → the root discovered at startup."""
    if project_root or os.environ.get("WIKIFIER_PROJECT_ROOT"):
        return resolve_root(project_root)
    return WIKIFIER_ROOT


def _root_error(exc: BaseException, project_root: Optional[str], **extra: Any) -> Dict[str, Any]:
    out = {"success": False, "project_root": str(project_root or ""), "error": str(exc), "error_type": type(exc).__name__}
    out.update(extra)
    return out


def _with_deadline(fn, timeout_s: Optional[float], **kwargs: Any) -> Dict[str, Any]:
    t = MCP_INPROCESS_DEADLINE_S if timeout_s is None else timeout_s
    res = _call_with_deadline(fn, timeout_s=t, timeout=t, **kwargs)
    if isinstance(res, dict) and res.get("timed_out"):
        res.setdefault("project_root", str(kwargs.get("project_root") or ""))
        res["may_still_complete"] = True
        res["hint"] = "The call may finish in the background; check why_file/health before retrying."
    return res


class UpdateMapsResult(BaseModel):
    """Structured update_maps result (map_complete=false means re-run with the same scope)."""
    success: bool
    project_root: str
    full_rebuild: bool
    files_analyzed: int
    edges_drawn: int
    duration_seconds: Optional[float] = None
    message: str
    incremental: bool = True
    used_python_primary: bool = True
    files_to_reparse: int = 0
    persist_exercised: bool = False
    partial: bool = False
    partial_reason: Optional[str] = None
    scope: Optional[Dict[str, Any]] = None
    progress: Optional[Dict[str, Any]] = None
    continuation_hint: Optional[str] = None
    map_complete: Optional[bool] = None
    error: Optional[str] = None


# =============================================================================
# Core workflow
# =============================================================================

@mcp.tool()
def check_changes(project_root: Optional[str] = None, timeout_s: Optional[float] = None) -> dict:
    """Detect content changes under monitored_paths; flag them Yellow (content-honest)."""
    try:
        root = _get_effective_root(project_root)
    except ProjectRootError as exc:
        return _root_error(exc, project_root)
    return _with_deadline(api.check_changes, timeout_s, project_root=str(root))


@mcp.tool()
def record_change(file: str, reason: str, project_root: Optional[str] = None, timeout_s: Optional[float] = None) -> dict:
    """Record why a file was edited (journal + Yellow + pending). Required after every edit."""
    try:
        root = _get_effective_root(project_root)
    except ProjectRootError as exc:
        return _root_error(exc, project_root, file=file)
    return _with_deadline(api.record_change, timeout_s, file=file, reason=reason, project_root=str(root))


@mcp.tool()
def record_deletion(file: str, reason: str, project_root: Optional[str] = None) -> dict:
    """Record an intentional deletion (Red audit row, journal, graph cleanup)."""
    try:
        root = _get_effective_root(project_root)
    except ProjectRootError as exc:
        return _root_error(exc, project_root, file=file)
    return api.record_deletion(file, reason, project_root=str(root))


@mcp.tool()
def mark_green(
    file: str,
    reason: str = "",
    force: bool = False,
    project_root: Optional[str] = None,
    timeout_s: Optional[float] = None,
) -> dict:
    """Mark a file Green after refreshing its wiki. The wiki is checked against the
    code first: if public symbols were added/removed and the wiki does not reflect
    it, this fails with issues[] (force=True + reason overrides, recorded as forced)."""
    try:
        root = _get_effective_root(project_root)
    except ProjectRootError as exc:
        return _root_error(exc, project_root, file=file)
    return _with_deadline(api.mark_green, timeout_s, file=file, reason=reason, force=force, project_root=str(root))


@mcp.tool()
def record_changes(
    reasons: Optional[Dict[str, str]] = None,
    default_reason: Optional[str] = None,
    since: Optional[str] = None,
    green: bool = False,
    dry_run: bool = False,
    only: Optional[List[str]] = None,
    project_root: Optional[str] = None,
    timeout_s: Optional[float] = None,
) -> dict:
    """Record every file git reports as changed in one call. reasons maps a path,
    glob (tests/*.py) or dir/ prefix to a reason; default_reason covers the rest.
    Missing reasons → nothing written, template returned. since = git ref
    (default HEAD). green=True then marks each Green (wiki checks apply).
    only limits the batch to paths/globs/dir/ (skip changes you did not make)."""
    try:
        root = _get_effective_root(project_root)
    except ProjectRootError as exc:
        return _root_error(exc, project_root)
    return _with_deadline(
        api.record_changes, timeout_s, reasons=reasons, default_reason=default_reason,
        since=since, green=green, dry_run=dry_run, only=only, project_root=str(root),
    )


@mcp.tool()
def verify_wikis(directory: Optional[str] = None, limit: int = 200, project_root: Optional[str] = None) -> dict:
    """Check Green files' wikis against their code (read-only): failing files,
    Green breakdown (verified / no_wiki / unchecked / forced / legacy), coverage."""
    try:
        return api.verify_wikis(project_root=str(_get_effective_root(project_root)), directory=directory, limit=limit)
    except ProjectRootError as exc:
        return _root_error(exc, project_root)


@mcp.tool()
def prepare_edit(file: str, project_root: Optional[str] = None) -> dict:
    """Single-file preflight: status, wiki, dependencies, dependents, cycle flag."""
    try:
        return api.prepare_edit(file, project_root=str(_get_effective_root(project_root)))
    except ProjectRootError as exc:
        return _root_error(exc, project_root, file=file)


@mcp.tool()
def session_bootstrap(project_root: Optional[str] = None, directory: Optional[str] = None) -> dict:
    """One-shot session start: root, readiness, health, attention, actions[], folder map."""
    try:
        return api.session_bootstrap(project_root=str(_get_effective_root(project_root)), directory=directory)
    except ProjectRootError as exc:
        return _root_error(exc, project_root)


@mcp.tool()
def suggest_next_actions(
    project_root: Optional[str] = None,
    directory: Optional[str] = None,
    format: Literal["text", "json"] = "json",
) -> str | dict:
    """Selective next steps: 🔴 then actionable 🟡 (never full-tree re-wiki); JSON has actions[]."""
    try:
        root = _get_effective_root(project_root)
    except ProjectRootError as exc:
        return _root_error(exc, project_root) if format == "json" else f"Error: {exc}"
    return api.suggest_next_actions(project_root=str(root), directory=directory, format=format)


@mcp.tool()
def list_core_tools() -> dict:
    """Core daily tools vs advanced intel (prefer Core every session)."""
    return api.list_core_tools()


# =============================================================================
# Lookup
# =============================================================================

@mcp.tool()
def list_paths(
    prefix: Optional[str] = None,
    directory: Optional[str] = None,
    project_root: Optional[str] = None,
    max_files: Optional[int] = None,
    depth: int = 1,
) -> dict:
    """Names-only folder card (depth=1) or recursive listing (depth=0, cap with max_files).

    Child folders hop to list_paths; files hop to prepare_edit.
    """
    try:
        root = _get_effective_root(project_root)
    except ProjectRootError as exc:
        return _root_error(exc, project_root)
    return api.list_paths(prefix=prefix, directory=directory, project_root=str(root), max_files=max_files, depth=depth)


@mcp.tool()
def search_journal(
    query: Optional[str] = None,
    file: Optional[str] = None,
    project_root: Optional[str] = None,
    max_results: int = 20,
) -> dict:
    """Search the journal (semantic audit trail) by text and/or file."""
    try:
        root = _get_effective_root(project_root)
    except ProjectRootError as exc:
        return _root_error(exc, project_root)
    return api.search_journal(project_root=str(root), query=query, file=file, max_results=max_results)


@mcp.tool()
def why_file(file: str, project_root: Optional[str] = None, max_results: int = 10) -> dict:
    """Why a file is Yellow/Red: health reason + recent journal entries."""
    try:
        root = _get_effective_root(project_root)
    except ProjectRootError as exc:
        return _root_error(exc, project_root, file=file)
    return api.why_file(file, project_root=str(root), max_results=max_results)


def _format_edge(item: Dict[str, Any]) -> str:
    target = item.get("resolved") or f"(unresolved: {item.get('raw')})"
    notes = []
    if item.get("confidence_score") is not None:
        notes.append(f"conf={item['confidence_score']}")
    if item.get("is_dynamic"):
        notes.append(f"dynamic:{item.get('dynamic_type') or '?'}")
    if item.get("is_conditional"):
        notes.append("conditional")
    if item.get("via_barrel"):
        notes.append(f"via barrel depth={item.get('barrel_depth') or '?'}")
    if item.get("in_cycle"):
        notes.append("⚠ cycle")
    explanation = str(item.get("confidence_explanation") or "")
    if "Recommendation:" in explanation:
        notes.append("rec: " + explanation.split("Recommendation:", 1)[1].strip())
    return f"{target}" + (f" ({'; '.join(notes)})" if notes else "")


@mcp.tool()
def get_dependencies(
    file: str,
    format: Literal["text", "json"] = "text",
    detail: Literal["compact", "full"] = "compact",
    project_root: Optional[str] = None,
    low_confidence_only: bool = False,
    unresolved_only: bool = False,
) -> str | dict:
    """What a file imports. detail="compact" (default): project files it imports
    (line, imported names, flags only when set), external module names, imports to
    review. detail="full": every per-edge record (confidence explanation, metadata,
    diagnostics) — several times larger; low_confidence_only / unresolved_only
    imply full."""
    try:
        root = _get_effective_root(project_root)
    except ProjectRootError as exc:
        return _root_error(exc, project_root, file=file) if format == "json" else f"Error: {exc}"
    if low_confidence_only or unresolved_only:
        detail = "full"
    res = api.get_dependencies(file, project_root=str(root), detail=detail)
    if not res.get("success"):
        return res if format == "json" else f"Error: {res.get('error')}"
    if not res.get("mapped") and format == "text":
        return f"{res['file']} is not in the dependency map (run update_maps or check map_paths.txt)."
    if detail == "compact":
        if format == "json":
            return res
        lines = [f"{res['file']} imports {res['internal_count']} project file(s):"]
        for edge in res["internal"]:
            flags = [k if v is True else f"{k}={v}" for k, v in edge.items() if k not in ("path", "line", "names")]
            names = f" ({', '.join(edge['names'][:8])}{', …' if len(edge.get('names', [])) > 8 else ''})" if edge.get("names") else ""
            lines.append(f"  - {edge['path']}:{edge['line']}{names}" + (f" [{', '.join(flags)}]" if flags else ""))
        if res["external"]:
            lines.append("external: " + ", ".join(res["external"]))
        for item in res["needs_review"]:
            lines.append(f"review: {item['raw']} (line {item['line']}): {item['category']}")
        if res.get("file_in_cycle"):
            lines.append(f"⚠ {res['file']} participates in a dependency cycle (see get_cycles).")
        return "\n".join(lines)
    imports = res["imports"]
    if low_confidence_only:
        imports = [
            i for i in imports
            if float(i.get("confidence_score") or 1.0) < 0.65 or str(i.get("confidence") or "").lower() in ("low", "unresolved")
        ]
    if unresolved_only:
        imports = [i for i in imports if not i.get("resolved") or i.get("diagnostic")]
    if format == "json":
        res["imports"] = imports
        res["count"] = len(imports)
        res["low_confidence_count"] = sum(1 for i in imports if float(i.get("confidence_score") or 1.0) < 0.65)
        return res
    lines = [f"{res['file']} imports ({len(imports)} shown, {res['internal_count']} internal):"]
    lines.extend(f"  - {_format_edge(i)}" for i in imports)
    if res.get("file_in_cycle"):
        lines.append(f"⚠ {res['file']} participates in a dependency cycle (see get_cycles).")
    return "\n".join(lines)


@mcp.tool()
def get_dependents(file: str, format: Literal["text", "json"] = "text", project_root: Optional[str] = None) -> str | dict:
    """Files that import this file (reverse dependencies) — the blast radius of an edit."""
    try:
        root = _get_effective_root(project_root)
    except ProjectRootError as exc:
        return _root_error(exc, project_root, file=file) if format == "json" else f"Error: {exc}"
    res = api.get_dependents(file, project_root=str(root))
    if format == "json" or not res.get("success"):
        return res if format == "json" else f"Error: {res.get('error')}"
    if not res["dependents"]:
        return f"No mapped files import {res['file']}."
    return f"Files that import {res['file']} ({res['count']}):\n" + "\n".join(f"- {d}" for d in res["dependents"])


@mcp.tool()
def get_cycles(
    analysis: bool = False,
    max_items: Optional[int] = None,
    format: Literal["text", "json"] = "text",
    project_root: Optional[str] = None,
    use_canonical: bool = True,
) -> str | dict:
    """Circular dependency clusters (Tarjan SCCs) with dynamic/conditional/barrel signals.

    analysis=True adds severity, external blast radius, weakest links and ranked
    breaking recommendations per cluster. Read-only (computes on demand if needed).
    """
    try:
        root = _get_effective_root(project_root)
    except ProjectRootError as exc:
        return _root_error(exc, project_root) if format == "json" else f"Error: {exc}"
    report = api.cycles_report(project_root=str(root), analysis=analysis, max_items=max_items, use_canonical=use_canonical)
    if format == "json":
        report["analysis"] = analysis
        return report
    return api.format_cycles_report(report)


@mcp.tool()
def get_resolution_diagnostics(
    file: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 20,
    format: Literal["text", "json"] = "text",
    project_root: Optional[str] = None,
) -> str | dict:
    """Why imports resolved at low confidence or not at all (per file or project-wide)."""
    try:
        root = _get_effective_root(project_root)
        if file:
            rel = to_rel(root, file)
            pairs = (cs.load_file_entry(root, rel) or {}).get("resolved_pairs") or []
            weak = [p for p in pairs if str(p.get("confidence") or "").lower() != "high"]
            if category:
                weak = [p for p in weak if (p.get("diagnostic") or {}).get("category") == category]
            summary = {"success": True, "file": rel, "total_imports": len(pairs), "non_high_count": len(weak), "samples": weak[:limit]}
            if format == "json":
                return summary
            lines = [f"=== Resolution diagnostics: {rel} ===", f"Imports: {len(pairs)}  non-high confidence: {len(weak)}"]
            for p in weak[: min(10, limit)]:
                diag = p.get("diagnostic") or {}
                lines.append(f"  - [{p.get('confidence')}] {p.get('raw')} → {p.get('resolved') or '?'}  "
                             f"category={diag.get('category', '?')} {str(diag.get('reason', ''))[:80]}")
            return "\n".join(lines)
        diag = ic.ensure_diagnostics_aggregate(ic.load_cache(root))
    except (ProjectRootError, ProjectPathError) as exc:
        return _root_error(exc, project_root) if format == "json" else f"Error: {exc}"
    if category:
        diag = {**diag, "filtered_to": category, "count_in_category": (diag.get("by_category") or {}).get(category, 0)}
    if format == "json":
        return {"success": True, **diag}
    total = diag.get("total_imports", 0)
    low = diag.get("low_or_unresolved_count", 0)
    lines = [
        "=== Resolution diagnostics ===",
        f"Imports analyzed: {total}",
        f"Low or unresolved: {low}" + (f" ({low / total * 100:.1f}%)" if total else ""),
        f"Top categories: {', '.join(diag.get('top_categories') or []) or 'none'}",
    ]
    for s in (diag.get("samples") or [])[:5]:
        lines.append(f"  - {s.get('src', '?')} [{s.get('confidence', '?')}] {str(s.get('raw', ''))[:40]} → {s.get('category', '?')}")
    return "\n".join(lines)


_WIKI_DIRS = ("docs/wiki", "docs", "wiki", "documentation", ".wiki")


def _wiki_candidates(rel: str) -> List[str]:
    stem = rel.rsplit(".", 1)[0] if "." in Path(rel).name else rel
    flat = stem.replace("/", "-")
    out = [f"{rel}.wiki.md", f"{stem}.wiki.md", f"{rel}.md", f"{stem}.md"]
    for d in _WIKI_DIRS:
        out += [f"{d}/{rel}.md", f"{d}/{rel}.wiki.md", f"{d}/{stem}.md", f"{d}/{stem}.wiki.md",
                f"{d}/{flat}.md", f"{d}/{flat}.wiki.md", f"{d}/{Path(rel).name}.md", f"{d}/{Path(rel).name}.wiki.md"]
    seen: List[str] = []
    for c in out:
        if c != rel and c not in seen:
            seen.append(c)
    return seen


@mcp.tool()
def get_file_wiki(file: str, format: Literal["text", "json"] = "text", project_root: Optional[str] = None) -> str | dict:
    """The wiki summary for a file (sibling ``<file>.wiki.md`` first, then docs/wiki dirs)."""
    try:
        root = _get_effective_root(project_root)
        rel = to_rel(root, file)
    except (ProjectRootError, ProjectPathError) as exc:
        return _root_error(exc, project_root, file=file) if format == "json" else f"Error: {exc}"
    candidates = _wiki_candidates(rel)
    for candidate in candidates:
        path = root / candidate
        if path.is_file():
            content = path.read_text(encoding="utf-8", errors="replace")
            if format == "json":
                return {"success": True, "file": rel, "source": candidate, "content": content, "project_root": str(root),
                        "confidence": "high" if candidate.endswith(".wiki.md") else "medium"}
            return f"=== Wiki for {rel} (from {candidate}) ===\n\n{content}"
    suggestion = f"Create {rel}.wiki.md next to the source, then run mark_green on {rel}."
    if format == "json":
        return {"success": True, "file": rel, "source": None, "content": None, "project_root": str(root),
                "confidence": "none", "candidates_tried": candidates[:20], "suggestions": [suggestion]}
    return f"No wiki summary found for {rel}. {suggestion}"


@mcp.tool()
def get_files_needing_attention(
    status: Literal["red", "yellow", "all"] = "all",
    directory: Optional[str] = None,
    project_root: Optional[str] = None,
    format: Literal["text", "json"] = "text",
    timeout_s: Optional[float] = None,
) -> str | dict:
    """Red/Yellow files (optionally one status and/or directory)."""
    try:
        root = _get_effective_root(project_root)
    except ProjectRootError as exc:
        return _root_error(exc, project_root) if format == "json" else f"Error: {exc}"
    return run_files_needing_attention(root, status=status, directory=directory, format=format, timeout_s=timeout_s)


@mcp.tool()
def get_project_status(
    format: Literal["text", "json"] = "text",
    project_root: Optional[str] = None,
    directory: Optional[str] = None,
    timeout_s: Optional[float] = None,
) -> str | dict:
    """High-level health counts + dependency intelligence summary."""
    try:
        root = _get_effective_root(project_root)
    except ProjectRootError as exc:
        return _root_error(exc, project_root) if format == "json" else f"Error: {exc}"
    return run_project_status(root, directory=directory, format=format, timeout_s=timeout_s)


@mcp.tool()
def get_current_project_root(project_root: Optional[str] = None) -> str:
    """The effective project root (explicit project_root overrides the startup root)."""
    try:
        return str(_get_effective_root(project_root))
    except ProjectRootError as exc:
        return f"Error: {exc}"


@mcp.tool()
def get_barrel_reports(limit: int = 20, project_root: Optional[str] = None, include_log: bool = True) -> dict:
    """Barrel (re-export) cache: which importers were dirtied by which barrel edits, and why."""
    try:
        root = _get_effective_root(project_root)
    except ProjectRootError as exc:
        return _root_error(exc, project_root)
    meta = cs.load_meta(root, keys=("_barrel_resolutions", "_barrel_file_index", "_barrel_invalidation_log"))
    log = meta.get("_barrel_invalidation_log") or []
    return {
        "success": True,
        "project_root": str(root),
        "barrel_invalidation_summary": ic.get_barrel_cache_summary(meta) or {},
        "recent_reports": (ic.get_barrel_invalidation_reports(meta, root, changed_files=None) or [])[: max(1, min(limit, 100))],
        "barrel_invalidation_log": list(reversed(log[-max(1, min(50, limit * 2)):])) if include_log else [],
        "log_count": len(log),
    }


@mcp.tool()
def get_incremental_status(project_root: Optional[str] = None) -> dict:
    """Cache backend, size, edge count and map coverage (debugging large projects)."""
    try:
        return api.cache_status(project_root=str(_get_effective_root(project_root)))
    except ProjectRootError as exc:
        return _root_error(exc, project_root)


# =============================================================================
# Maps + health maintenance
# =============================================================================

@mcp.tool()
def update_maps(
    project_root: Optional[str] = None,
    full: bool = False,
    use_python_primary: bool = True,
    directory: Optional[str] = None,
    max_files: Optional[int] = None,
    scope: Optional[Dict[str, Any]] = None,
    resume_from: Optional[str] = None,
    time_budget_ms: Optional[float] = None,
) -> UpdateMapsResult:
    """Rebuild the dependency map + library.md (incremental unless full=True).

    directory scopes to a subtree; max_files caps parsing. When map_complete is
    false, re-run with the same scope until it is true.
    """
    if scope and not directory:
        directory = scope.get("directory") or scope.get("dir")
    try:
        root = _get_effective_root(project_root)
    except ProjectRootError as exc:
        return UpdateMapsResult(success=False, project_root=str(project_root or ""), full_rebuild=full,
                                files_analyzed=0, edges_drawn=0, message=str(exc), error=str(exc))
    started = time.time()
    res = api.update_maps(project_root=str(root), full=full, directory=directory, max_files=max_files)
    skipped = int(res.get("files_skipped") or 0)
    return UpdateMapsResult(
        success=bool(res.get("success")),
        project_root=str(root),
        full_rebuild=full,
        files_analyzed=int(res.get("files_parsed") or 0),
        edges_drawn=int(res.get("edges_persisted") or 0),
        duration_seconds=round(time.time() - started, 2),
        message=(
            f"parsed {res.get('files_parsed')}/{res.get('files_to_reparse')} dirty files, "
            f"{res.get('edges_persisted')} edges, map_complete={res.get('map_complete')}"
            if res.get("success") else f"update_maps failed: {res.get('error')}"
        ),
        incremental=not full,
        files_to_reparse=int(res.get("files_to_reparse") or 0),
        persist_exercised=bool(res.get("persist_pipeline_exercised")),
        partial=skipped > 0,
        partial_reason=f"max_files budget: {skipped} files left" if skipped else None,
        scope={"directory": directory, "max_files": max_files},
        progress=res.get("map_coverage"),
        continuation_hint="Re-run update_maps with the same directory/max_files" if skipped else None,
        map_complete=res.get("map_complete"),
        error=res.get("error"),
    )


@mcp.tool()
def health(
    project_root: Optional[str] = None,
    directory: Optional[str] = None,
    format: Literal["text", "json", "summary", "healing-stats"] = "text",
) -> str | dict:
    """Health matrix: text table, summary counts, full JSON entries (+ACS), or healing stats."""
    try:
        root = _get_effective_root(project_root)
    except ProjectRootError as exc:
        return _root_error(exc, project_root) if format != "text" else f"Error: {exc}"
    return api.health(project_root=str(root), directory=directory, format=format)


@mcp.tool()
def validate(project_root: Optional[str] = None, format: Literal["text", "json"] = "text") -> str | dict:
    """Parseable sources under monitored_paths (or mapped in scope) that lack a health row."""
    try:
        root = _get_effective_root(project_root)
    except ProjectRootError as exc:
        return _root_error(exc, project_root) if format == "json" else f"Error: {exc}"
    res = health_mod.validate_health(root)
    res.update({"success": True, "project_root": str(root)})
    if format == "json":
        return res
    if not res["missing_count"]:
        return f"All monitored sources have health entries ({res['total_scanned']} scanned, {res['ghost_count']} ghosts)."
    return f"{res['missing_count']} file(s) lack health entries:\n" + "\n".join(f"- {m}" for m in res["missing"][:50])


@mcp.tool()
def list_healable_stubs(
    project_root: Optional[str] = None,
    directory: Optional[str] = None,
    min_wiki_length: int = 350,
    format: Literal["text", "json"] = "text",
) -> str | dict:
    """Initial-stub rows whose wiki is now substantial (with quality signals)."""
    try:
        root = _get_effective_root(project_root)
    except ProjectRootError as exc:
        return _root_error(exc, project_root) if format == "json" else f"Error: {exc}"
    stubs = health_mod.get_healable_stubs(root, min_wiki_length=min_wiki_length, directory=directory)
    if format == "json":
        return {"success": True, "project_root": str(root), "count": len(stubs), "healable_stubs": stubs, "min_wiki_length": min_wiki_length}
    if not stubs:
        return "No healable stub entries found."
    return "\n".join(f"- {s['file']}: {s['quality']} (score={s['quality_score']}, {s['wiki_size']} bytes)" for s in stubs)


@mcp.tool()
def heal_stubs(
    project_root: Optional[str] = None,
    dry_run: bool = False,
    min_wiki_length: int = 350,
    format: Literal["text", "json"] = "text",
) -> str | dict:
    """Promote Initial stubs with a real wiki: high quality → 🟢, medium → 🟡."""
    try:
        root = _get_effective_root(project_root)
    except ProjectRootError as exc:
        return _root_error(exc, project_root) if format == "json" else f"Error: {exc}"
    res = api.heal_stubs(project_root=str(root), dry_run=dry_run, min_wiki_length=min_wiki_length)
    if format == "json":
        return res
    verb = "Would heal" if dry_run else "Healed"
    return f"{verb} {res.get('healed_count', 0)} Initial stub entries." if res.get("success") else f"Error: {res.get('error')}"


@mcp.tool()
def seed_source_content_hashes(
    project_root: Optional[str] = None,
    only_green: bool = True,
    force: bool = False,
    directory: Optional[str] = None,
) -> dict:
    """Record current source hashes as baselines without changing status (migration)."""
    try:
        root = _get_effective_root(project_root)
    except ProjectRootError as exc:
        return _root_error(exc, project_root)
    return api.seed_source_content_hashes(project_root=str(root), only_green=only_green, force=force, directory=directory)


@mcp.tool()
def journal(date: str = "", project_root: Optional[str] = None, format: Literal["text", "json"] = "text") -> str | dict:
    """Journal entries for a date (YYYY-MM-DD; default today)."""
    try:
        root = _get_effective_root(project_root)
    except ProjectRootError as exc:
        return _root_error(exc, project_root) if format == "json" else f"Error: {exc}"
    res = api.journal(date or None, project_root=str(root))
    if format == "json" or not res.get("success"):
        return res if format == "json" else f"Error: {res.get('error')}"
    return res["content"] or f"No journal entries for {res['date']} yet."


@mcp.tool()
def issues(severity: str = "all", project_root: Optional[str] = None, format: Literal["text", "json"] = "text") -> str | dict:
    """Logged_issues markdown files (simple|moderate|high|critical|all)."""
    try:
        root = _get_effective_root(project_root)
    except ProjectRootError as exc:
        return _root_error(exc, project_root) if format == "json" else f"Error: {exc}"
    res = api.issues(severity, project_root=str(root))
    if format == "json":
        return res
    return "\n".join(res.get("issues") or []) or "No logged issues."


# =============================================================================
# Resources
# =============================================================================

def _read_root_file(name: str) -> str:
    path = _get_effective_root() / name
    return path.read_text(encoding="utf-8") if path.exists() else f"File not found: {name}"


@mcp.resource("wikifier://library")
def get_library() -> str:
    return _read_root_file("library.md")


@mcp.resource("wikifier://health")
def get_health_matrix() -> str:
    return _read_root_file("file_health.md")


@mcp.resource("wikifier://pending")
def get_pending_updates() -> str:
    return _read_root_file("pending_updates.md")


@mcp.resource("wikifier://journal/{date}")
def get_journal(date: str) -> str:
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return f"Invalid date {date!r}; expected YYYY-MM-DD."
    res = api.journal(date, project_root=str(_get_effective_root()))
    return res.get("content") or f"No journal entries for {date}."


# =============================================================================
# Prompts
# =============================================================================

@mcp.prompt()
def review_pending_changes() -> str:
    return """Review pending documentation work in this Wikifier-managed project.

1. session_bootstrap() — attention lists and actions[]
2. For each actionable file: prepare_edit(file), get_file_wiki(file), get_dependents(file)
3. Refresh the wiki, then mark_green(file). Never skip record_change after code edits."""


@mcp.prompt()
def audit_project_health() -> str:
    return """Audit documentation health.

1. get_project_status(format="json")
2. get_files_needing_attention(status="red"), then "yellow"
3. search_journal() for recent activity
4. suggest_next_actions(format="json") — report priorities from actions[]"""


@mcp.prompt()
def plan_refactoring(target: str) -> str:
    return f"""Plan a refactoring of '{target}'.

1. get_dependents("{target}") — blast radius.
2. get_dependencies("{target}", format="json") — for each edge read confidence_score and the
   "Recommendation:" sentence in confidence_explanation.
   - score >= 0.75 with a strong strategy: safe for automated edits
   - 0.55–0.74, deep barrel, or runtime-conditional: review manually
   - < 0.55, cycle participant, opaque dynamic: avoid automated edits
3. get_cycles(analysis=True, format="json") if the file is in a cycle — use weakest_links and
   recommendations.
Return an impact analysis that quotes each risky edge's Recommendation sentence."""


@mcp.prompt()
def find_architectural_smells() -> str:
    return """Find architectural smells from the dependency data.

- Cycles: get_cycles(analysis=True, format="json"); rank by severity and external_blast_radius,
  quote recommendations[0] (strategy, rationale, hint, safety) for the worst clusters.
- Fragile edges: get_dependencies(file, format="json", low_confidence_only=True) on hub files;
  look for reasons like cycle_participant, dynamic_expression, weak_resolution_strategy,
  complexity:opaque, barrel_depth>=3.
- God modules: files with many get_dependents results.
Cite the Recommendation sentence and triggering reasons for each smell."""


@mcp.prompt()
def understand_codebase_structure() -> str:
    return """Onboard to this codebase.

1. session_bootstrap() and follow map_index → list_paths(prefix) for the folders you need
2. get_project_status(format="json")
3. For key modules: prepare_edit(file), get_dependencies(file, format="json"), get_dependents(file)
4. get_cycles(analysis=True) for structural risks"""


@mcp.prompt()
def review_recent_changes(days: int = 7) -> str:
    return f"""Review activity over the last {days} days.

1. search_journal() / journal(date) for record-change entries
2. For each changed file: why_file(file) — is it Green again (wiki refreshed)?
3. Report documentation debt: files recorded but not yet mark_green'd."""


@mcp.prompt()
def generate_project_health_report() -> str:
    return """Write a project health report for humans or other agents.

Include: Green/Yellow/Red counts (get_project_status), top files needing attention,
most depended-on modules (get_dependents on hubs), cycles (get_cycles(analysis=True)),
and prioritized recommendations."""


@mcp.prompt()
def onboard_to_module(module_path: str) -> str:
    return f"""Understand the module {module_path}.

1. get_file_wiki("{module_path}")
2. get_dependencies("{module_path}", format="json") — note each risky edge's Recommendation
3. get_dependents("{module_path}") — who relies on it
4. get_cycles(analysis=True, format="json") if it is in a cycle
Summarize its role, safe vs fragile dependencies, and blast radius."""


def main() -> None:
    """Entry point for ``wikifier-mcp``."""
    import argparse

    parser = argparse.ArgumentParser(description="Wikifier MCP server")
    parser.add_argument("--project-root", default=None, help="Target project directory (sets WIKIFIER_PROJECT_ROOT)")
    args = parser.parse_args()
    global WIKIFIER_ROOT
    if args.project_root:
        WIKIFIER_ROOT = resolve_root(args.project_root)
        os.environ["WIKIFIER_PROJECT_ROOT"] = str(WIKIFIER_ROOT)
    else:
        WIKIFIER_ROOT = _discover_project_root()
    mcp.run()


if __name__ == "__main__":
    main()
