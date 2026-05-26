"""
Wikifier MCP Server - Rich Edition

This is a first-class Model Context Protocol (MCP) server for Wikifier.

It is designed to be used by agents (Claude, Cline, Cursor, etc.) as a
powerful, transparent, and conservative codebase memory system.

Run with:
    python -m wikifier.mcp.server
    or
    wikifier-mcp
"""

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field
import subprocess
import re
import os
import sys
from pathlib import Path
from typing import Literal, Optional, List
from datetime import datetime

# R6: reuse the canonical script locator (avoids hard ./wikifier.sh assumption in external installs)
# Gap #1 External: reuse the unified discover_project_root (CLI + shell mirrored) so MCP benefits from
# the same robust marker/common-project logic and never falls back to package dir for PROJECT_ROOT.
try:
    from wikifier.cli import (
        get_script_path as _get_wikifier_script_path,
        discover_project_root as _cli_discover_project_root,
        _get_effective_root as _cli_get_effective_root,  # Workstream E: central shared helper for clean API + thin MCP/CLI consumers
    )
except Exception:
    _get_wikifier_script_path = None
    _cli_discover_project_root = None
    _cli_get_effective_root = None

mcp = FastMCP("Wikifier")


def _discover_project_root() -> Path:
    """
    Determine the target project root for this Wikifier MCP instance.

    Delegates to the unified canonical helper in cli.py (Gap #1 External/Packaged robustness).
    The helper implements marker-driven + common-project-root discovery and safe CWD fallback.
    Kept for backward compat + any MCP-specific extras (e.g. .mcp.json detection).
    """
    if _cli_discover_project_root is not None:
        try:
            return _cli_discover_project_root()
        except Exception:
            pass  # fall through to local logic

    # Local fallback (kept for resilience if cli import failed); includes the .mcp.json extra
    # 1. Explicit override via environment variable
    env_root = os.environ.get("WIKIFIER_PROJECT_ROOT")
    if env_root:
        p = Path(env_root).expanduser().resolve()
        if p.exists():
            return p

    # 2. Walk upward from current working directory
    cwd = Path.cwd().resolve()
    for parent in [cwd] + list(cwd.parents):
        if (parent / "monitored_paths.txt").exists() or (parent / ".wikifier").is_dir():
            return parent

    # 3. Try to detect from common MCP connection files (e.g. .mcp.json in project root)
    for parent in [cwd] + list(cwd.parents):
        mcp_config = parent / ".mcp.json"
        if mcp_config.exists():
            try:
                import json
                with open(mcp_config) as f:
                    config = json.load(f)
                if "wikifier" in config.get("mcpServers", {}):
                    return parent
            except Exception:
                pass

    # 4. Sensible default: CWD (never the old package dir for external packaged reliability)
    return cwd


WIKIFIER_ROOT = _discover_project_root()


def _get_effective_root(project_root: Optional[str] = None) -> Path:
    """
    Resolve the project root to use for a given operation.
    Workstream E (clean public API): thin delegation to shared _get_effective_root in cli.py
    (the library implementation). Falls back to local logic only if import failed at load.
    This eliminates duplication and ensures parity between library callers and MCP tools.
    """
    if _cli_get_effective_root is not None:
        try:
            return _cli_get_effective_root(project_root)
        except Exception:
            pass  # fall to local resilience
    # Fallback (import failed or error): original MCP logic (explicit/env + startup root)
    if project_root:
        p = Path(project_root).expanduser().resolve()
        if p.exists():
            return p
    env_root = os.environ.get("WIKIFIER_PROJECT_ROOT")
    if env_root:
        p = Path(env_root).expanduser().resolve()
        if p.exists():
            return p
    return WIKIFIER_ROOT  # the one discovered at startup


# =============================================================================
# Pydantic Models for Structured Output
# =============================================================================

class DependencyInfo(BaseModel):
    module: str
    resolved_file: Optional[str] = None
    is_resolved: bool = False


class FileDependencies(BaseModel):
    file: str
    dependencies: List[DependencyInfo]
    dependents: List[str] = Field(default_factory=list)


class ProjectHealthSummary(BaseModel):
    total_files: int
    green: int
    yellow: int
    red: int
    pending_updates: int
    last_check: Optional[str] = None
    health_score: str  # e.g. "Good", "Needs Attention", "Critical"


class ResolutionQuality(BaseModel):
    total_internal_imports: int
    resolved: int
    unresolved: int
    resolution_rate: float
    assessment: str


class UpdateMapsResult(BaseModel):
    """Structured result from running update_maps.

    Wave 5: now supports use_python_primary for direct run_full_update (deeper pure-Py
    pipeline + barrel/creative) without shell; falls back to sh path otherwise.
    """
    success: bool
    project_root: str
    full_rebuild: bool
    files_analyzed: int
    edges_drawn: int
    duration_seconds: Optional[float] = None
    message: str
    incremental: bool = True  # whether it used the cache or was a full rebuild
    used_python_primary: bool = False  # Wave 5: indicates direct pure path was taken
    files_to_reparse: int = 0
    persist_exercised: bool = False
    barrel_creative_tied: bool = False  # Wave 6: Gap#1 barrel + creative signals exercised under pure primary path (for ACS/CIABRE surfaces)


# =============================================================================
# Helper Functions
# =============================================================================

def _run_wikifier_command(cmd: str, args: list[str] | None = None, check: bool = True, root: Optional[Path] = None) -> str:
    """
    Run a wikifier command against a specific project root (R6 hardened for external/monorepo).

    Uses the installed script path (not fragile ./wikifier.sh in cwd) + explicit
    WIKIFIER_PROJECT_ROOT in env. This eliminates "sh-not-found" on pip-installed
    usage against external codebases and large monorepos.
    """
    root = root or WIKIFIER_ROOT
    args = args or []

    # Prefer canonical installed script locator; fall back to PATH "wikifier" or python -m
    if _get_wikifier_script_path is not None:
        try:
            script = str(_get_wikifier_script_path())
            full_cmd = [script, cmd] + args
        except Exception:
            full_cmd = ["wikifier", cmd] + args
    else:
        full_cmd = ["wikifier", cmd] + args

    # Always force the target project via env (sh and inner python now respect it)
    child_env = os.environ.copy()
    child_env["WIKIFIER_PROJECT_ROOT"] = str(root)

    try:
        result = subprocess.run(
            full_cmd,
            cwd=root,  # still useful for relative finds inside some commands
            capture_output=True,
            text=True,
            check=check,
            env=child_env,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        error_msg = (e.stderr or "").strip() or str(e)
        if check:
            raise RuntimeError(f"Wikifier command '{cmd}' failed on {root}: {error_msg}")
        return f"Error: {error_msg}"
    except FileNotFoundError:
        # Last resort: try python -m invocation (covers some packaged layouts)
        try:
            py_cmd = [sys.executable, "-m", "wikifier", cmd] + args
            result = subprocess.run(
                py_cmd,
                cwd=root,
                capture_output=True,
                text=True,
                check=check,
                env=child_env,
            )
            return result.stdout.strip()
        except Exception as ee:
            raise RuntimeError(f"Wikifier command failed: could not locate wikifier launcher for project {root} ({ee})")
    except Exception as e:
        raise RuntimeError(f"Unexpected error running '{cmd}' in {root}: {str(e)}")


def _read_file_safe(relative_path: str, root: Optional[Path] = None) -> str:
    """Read a file relative to a specific project root."""
    root = root or WIKIFIER_ROOT
    path = root / relative_path
    if path.exists():
        return path.read_text(encoding="utf-8")
    return f"File not found: {relative_path}"


def _parse_resolved_dependencies(root: Optional[Path] = None) -> dict[str, list[str]]:
    """Parse the Resolved Internal Dependencies table from library.md."""
    root = root or WIKIFIER_ROOT
    library = _read_file_safe("library.md", root=root)
    if "Resolved Internal Dependencies" not in library:
        return {}

    # Find the table section
    match = re.search(
        r"## Resolved Internal Dependencies.*?\n\| Source File.*?\n\|---.*?\n(.*?)(?=\n##|\Z)",
        library,
        re.DOTALL
    )
    if not match:
        return {}

    table_body = match.group(1)
    reverse_map: dict[str, list[str]] = {}

    for line in table_body.strip().splitlines():
        if not line.strip() or not line.startswith("|"):
            continue
        parts = [p.strip() for p in line.split("|") if p.strip()]
        if len(parts) < 2:
            continue
        source = parts[0]
        # Format is usually: "module → target_file"
        if "→" in parts[1]:
            target = parts[1].split("→")[-1].strip()
            if target not in reverse_map:
                reverse_map[target] = []
            reverse_map[target].append(source)

    return reverse_map


def _get_resolved_from_cache(file: str, root: Path) -> list[dict]:
    """
    Fallback: Get resolved dependencies for a file directly from import_cache.json.
    R2/P2: returns the *full* rich per-edge model (ACS canonical + CDIA + Resolution + diagnostics):
    - ACS (via contracts R2): confidence_score, confidence_reasons, confidence_explanation (prescriptive)
    - CDIA: conditional_analysis/dynamic_analysis with tags + real analysis_trace evidence
    - Phase 4: strategy + resolution_metadata
    - All fields enable high-quality agent decisions at any scale.
    """
    try:
        import wikifier.import_cache as import_cache
        cache = import_cache.load_cache(root)
        data = cache.get(file, {})
        pairs = data.get("resolved_pairs", [])
        if pairs:
            rich = []
            for p in pairs:
                if not p.get("resolved"):
                    continue
                item = {
                    "raw": p.get("raw"),
                    "resolved": p.get("resolved"),
                    "confidence": p.get("confidence", "medium"),
                    "is_dynamic": p.get("is_dynamic", False),
                    "dynamic_type": p.get("dynamic_type", "static"),
                    "is_conditional": p.get("is_conditional", False),
                    "conditional_context": p.get("conditional_context"),
                    "via_barrel": p.get("via_barrel", False),
                    "barrel_depth": p.get("barrel_depth"),
                    "barrel_chain": p.get("barrel_chain"),
                    # P2 ACS + rich signals (now first-class in output) + F2 explanation
                    "confidence_score": p.get("confidence_score"),
                    "confidence_reasons": p.get("confidence_reasons", []),
                    "confidence_explanation": p.get("confidence_explanation"),
                    "strategy": p.get("strategy"),
                    "resolution_metadata": p.get("resolution_metadata"),
                    "conditional_analysis": p.get("conditional_analysis") or (p.get("cdia", {}).get("conditional_analysis") if isinstance(p.get("cdia"), dict) else None),
                    "dynamic_analysis": p.get("dynamic_analysis") or (p.get("cdia", {}).get("dynamic_analysis") if isinstance(p.get("cdia"), dict) else None),
                    "diagnostic": p.get("diagnostic"),
                    "cdia": p.get("cdia"),
                    "expr_raw": p.get("expr_raw"),
                    "analysis_notes": p.get("analysis_notes"),
                }
                rich.append(item)
            return rich
        # Fallback to flat list (older cache format)
        resolved = data.get("resolved", [])
        return [{"raw": None, "resolved": r, "confidence": "medium", "confidence_reasons": []} for r in resolved]
    except Exception:
        return []


# =============================================================================
# Core Tools
# =============================================================================

@mcp.tool()
def check_changes(project_root: Optional[str] = None) -> dict:
    """
    Scan for file changes and update the health matrix (Workstream E: thin library consumer).

    Delegates directly to the Python library `wikifier.check_changes` (pure primary path,
    structured return, locking, journal/pending/health side effects). No subprocess shell
    for this core mandatory tool. Falls back to sh only on import/runtime error.
    """
    root = _get_effective_root(project_root)
    try:
        from wikifier.cli import check_changes as _lib_check
        res = _lib_check(project_root=str(root))
        # Enrich with MCP-specific barrel view if not present (best effort, non breaking)
        if "barrel_invalidation_summary" not in res or not res.get("barrel_invalidation_summary"):
            try:
                import wikifier.import_cache as ic
                cache = ic.load_cache(root) or {}
                res["barrel_invalidation_summary"] = ic.get_barrel_cache_summary(cache) or {}
            except Exception:
                pass
        res.setdefault("rich_auto_yellow_via", "Python library check_changes (MCP thin)")
        return res
    except Exception as e:
        # Resilient fallback to previous sh path (preserves behavior if lib unavailable)
        try:
            output = _run_wikifier_command("check-changes", root=root)
            return {
                "success": True,
                "project_root": str(root),
                "message": output,
                "recommendation": "Read file_health.md and pending_updates.md, then prioritize Red → Yellow files.",
                "fallback": "sh",
                "error_detail": str(e),
            }
        except Exception as e2:
            return {"success": False, "project_root": str(root), "error": f"lib+sh failed: {e} / {e2}"}


@mcp.tool()
def record_change(file: str, reason: str, project_root: Optional[str] = None) -> dict:
    """Record a semantic change. Required after edits. Returns structured result.
    (Workstream E: thin direct call to library; no shell for core mandatory workflow.)
    """
    root = _get_effective_root(project_root)
    try:
        from wikifier.cli import record_change as _lib_record
        return _lib_record(file=file, reason=reason, project_root=str(root))
    except Exception as e:
        # Fallback for resilience
        try:
            output = _run_wikifier_command("record-change", [file, reason], root=root)
            return {"success": True, "file": file, "message": output, "project_root": str(root), "fallback": "sh", "error_detail": str(e)}
        except Exception as e2:
            return {"success": False, "file": file, "project_root": str(root), "error": f"lib+sh: {e}/{e2}"}


@mcp.tool()
def record_deletion(file: str, reason: str, project_root: Optional[str] = None) -> dict:
    """Record the deletion of a file with a reason. Returns structured result (final robustness).
    (Workstream E thin library consumer.)
    """
    root = _get_effective_root(project_root)
    try:
        from wikifier.cli import record_deletion as _lib_del
        return _lib_del(file=file, reason=reason, project_root=str(root))
    except Exception as e:
        try:
            output = _run_wikifier_command("record-deletion", [file, reason], root=root)
            return {"success": True, "file": file, "message": output, "project_root": str(root), "fallback": "sh"}
        except Exception as e2:
            return {"success": False, "file": file, "project_root": str(root), "error": f"lib+sh: {e}/{e2}"}


@mcp.tool()
def mark_green(file: str, reason: str = "", project_root: Optional[str] = None) -> dict:
    """Mark a file as Green after updating its wiki summary. Returns structured result.
    (Workstream E: thin library consumer.)
    """
    root = _get_effective_root(project_root)
    try:
        from wikifier.cli import mark_green as _lib_mark
        return _lib_mark(file=file, reason=reason, project_root=str(root))
    except Exception as e:
        try:
            args = [file, reason] if reason else [file]
            output = _run_wikifier_command("mark-green", args, root=root)
            return {"success": True, "file": file, "message": output, "project_root": str(root), "fallback": "sh"}
        except Exception as e2:
            return {"success": False, "file": file, "project_root": str(root), "error": f"lib+sh: {e}/{e2}"}


@mcp.tool()
def prepare_edit(file: str, project_root: Optional[str] = None) -> dict:
    """Stage current mtime before editing a file. Returns structured result (final robustness)."""
    root = _get_effective_root(project_root)
    try:
        output = _run_wikifier_command("prepare-edit", [file], root=root)
        return {
            "success": True,
            "file": file,
            "message": output,
            "project_root": str(root),
            "next_step": "Perform your edit, then call record_change + mark_green."
        }
    except Exception as e:
        return {
            "success": False,
            "file": file,
            "error": str(e),
            "project_root": str(root)
        }


@mcp.tool()
def update_maps(project_root: Optional[str] = None, full: bool = False, use_python_primary: bool = False) -> UpdateMapsResult:
    """Rebuild library.md with fresh dependency analysis for the target project.

    Wave 5: `use_python_primary=True` wires direct run_full_update() (deeper pipeline
    from cli.py: dirty+parse+persist+barrel/creative tie-in, no sh) for packaged
    external robustness. Falls back to robust _run_wikifier_command (sh) if not or error.
    Explicit flag matches CLI --python-primary and daemon wiring.
    """
    root = _get_effective_root(project_root)
    used_primary = False
    files_reparse = 0
    persist_done = False

    if use_python_primary:
        try:
            from wikifier.cli import run_full_update
            import time
            start = time.time()
            res = run_full_update(
                root=root,
                force_full=full,
                verbose=False,
                use_canonical=True,
                use_python_primary=True,
            )
            duration = time.time() - start
            used_primary = True
            files_reparse = res.get("files_to_reparse", 0)
            persist_done = bool(res.get("persist_pipeline_exercised"))
            # Construct rich message from the pure path result
            msg = f"Python-primary: success={res.get('success')} files={files_reparse} persist={persist_done} barrel_creative_tied={res.get('barrel_creative_tied_in_pure_path')} note={res.get('note','')[:200]}"
            return UpdateMapsResult(
                success=bool(res.get("success")),
                project_root=str(root),
                full_rebuild=full,
                files_analyzed=files_reparse,
                edges_drawn=0,  # full edges in library.md side effect of persist
                duration_seconds=round(duration, 2),
                message=msg,
                incremental=not full,
                used_python_primary=True,
                files_to_reparse=files_reparse,
                persist_exercised=persist_done,
                barrel_creative_tied=bool(res.get("barrel_creative_tied_in_pure_path")),
            )
        except Exception as ex:
            # fall through to sh path (best-effort, still robust)
            pass

    # Original sh path (R6 hardened)
    args = []
    if full:
        args = ["--full"]

    import time
    start = time.time()
    output = _run_wikifier_command("update-maps", args, root=root)
    duration = time.time() - start

    # Try to extract some stats from the output
    edges = 0
    files_analyzed = 0
    for line in output.splitlines():
        if "edges drawn" in line:
            try:
                edges = int(line.split()[-2])
            except:
                pass
        if "Files analyzed" in line or "Python:" in line:
            # Rough extraction
            pass

    return UpdateMapsResult(
        success=True,
        project_root=str(root),
        full_rebuild=full,
        files_analyzed=files_analyzed or 0,
        edges_drawn=edges,
        duration_seconds=round(duration, 2),
        message=output[-500:] if len(output) > 500 else output,  # last part of output
        incremental=not full,
        used_python_primary=False,
        files_to_reparse=0,
        persist_exercised=False,
        barrel_creative_tied=False,
    )


@mcp.tool()
def health(
    project_root: Optional[str] = None,
    directory: Optional[str] = None,
    format: Literal["text", "json", "summary"] = "text"
) -> str | dict:
    """
    Return the current Documentation Health Matrix.

    This now uses the fast scalable Python backend (wikifier.health) for
    large repositories.

    R2 ACS + CIABRE surfacing uniformity: when format="json", includes "dependency_intel"
    with _acs_summary (avg/low-conf + full sample confidence_explanation Recommendations)
    + CIABRE summaries + cycles_reuse (via get_cycles_reuse_stats: graph_signature + reused/reuse_reason + node_identity_version for delta Tarjan short-circuit + canonical v1 prep).
    Primary trust surface for agents alongside get_project_status. Wave 3 complete + canonical prep.

    Args:
        project_root: Target a different project.
        directory: Only return health for files under this subdirectory (e.g. "src/").
        format: "text" (default, pretty Markdown), "summary" (counts only), 
            "healing-stats" (stub pollution + healing opportunities), or "json".
    """
    root = _get_effective_root(project_root)

    try:
        import wikifier.health as health_module

        if format == "summary":
            summary = health_module.get_summary(root, directory)
            return summary

        if format == "healing-stats":
            stats = health_module.get_healing_statistics(root)
            return stats

        if format == "json":
            health_data = health_module.load_health(root)
            entries = health_data.get("entries", {})
            if directory:
                entries = {k: v for k, v in entries.items() if k.startswith(directory.rstrip("/") + "/")}
            # ACS+CIABRE + Wave 2 Barrel/BRC + Wave 3 cycles reuse surfacing: attach lightweight summaries to health JSON (uniformity for agents using health tool)
            dep_intel = {}
            try:
                import wikifier.import_cache as ic
                cache = ic.load_cache(root)
                # On-demand persistence guarantee for _acs_summary (Gap #1 ACS surfacing wave; mirrors cycles)
                acs = ic.ensure_acs_summary_persisted(cache, root)
                cyc = ic.get_cycle_analyses(cache) or {}
                barrel = ic.get_barrel_cache_summary(cache) or {}
                # Use central broad surfacing helper (now includes canonical v1 prep + delta reuse)
                cycles_reuse = ic.get_cycles_reuse_stats(cache)
                sample_barrel_reports = []
                if barrel.get("has_brc"):
                    try:
                        # Richer MCP observability (continuation wave): up to 5 samples for health(json) + get_project_status (now with detector/partial/chain details in text too).
                        # Agents see concrete importer + barrels + reason + detector/partial/chains directly (richer structured samples + _barrel_invalidation_log awareness).
                        reps = ic.get_barrel_invalidation_reports(cache, root, changed_files=None) or []
                        sample_barrel_reports = reps[:5]
                    except Exception:
                        sample_barrel_reports = []
                if acs or cyc or barrel.get("has_brc") or cycles_reuse.get("has_cycles"):
                    dep_intel = {
                        "acs_summary": acs,
                        "ciabre_summary": cyc.get("summary") or {},
                        "ciabre_version": cyc.get("analysis_version"),
                        "barrel_invalidation_summary": barrel,
                        "cycles_reuse": cycles_reuse,
                        "sample_barrel_reports": sample_barrel_reports,  # basic observability in health(json)
                    }
            except Exception:
                pass
            return {
                "project_root": str(root),
                "directory": directory or ".",
                "total_files": len(entries),
                "entries": entries,
                "dependency_intel": dep_intel
            }

        # Default: text output (human readable)
        # We still return the generated Markdown for familiarity
        return health_module._read_file_safe("file_health.md", root=root)  # type: ignore[attr-defined]

    except Exception as e:
        # Fallback to old shell behavior if Python module has issues
        root = _get_effective_root(project_root)
        args = []
        if directory:
            args = ["--dir", directory]
        output = _run_wikifier_command("health", args, root=root)
        return output


@mcp.tool()
def list_healable_stubs(
    project_root: Optional[str] = None,
    directory: Optional[str] = None,
    min_wiki_length: int = 350,
    format: Literal["text", "json"] = "text"
) -> str | dict:
    """
    List health entries that are still marked as 'Initial stub' but now have
    a substantial wiki summary and are eligible for auto-healing.

    Returns quality signals (headings, purpose section, length, overall score)
    so agents can decide smart healing strategy (Yellow vs direct Green).

    This helps agents discover and clean up "stub pollution".
    """
    root = _get_effective_root(project_root)
    try:
        import wikifier.health as health_module
        candidates = health_module.get_healable_stubs(
            root, min_wiki_length=min_wiki_length, directory=directory
        )
        if format == "json":
            return {
                "project_root": str(root),
                "count": len(candidates),
                "healable_stubs": candidates,
                "min_wiki_length": min_wiki_length
            }
        if not candidates:
            return "No healable stub entries found."
        lines = [f"Found {len(candidates)} healable stub entries:\n"]
        for item in candidates:
            q = item.get("quality", "?")
            score = item.get("quality_score", 0)
            lines.append(f"  {item['file']}")
            lines.append(f"     Quality: {q} (score={score}) | Wiki: {item['wiki_size']} bytes")
            if item.get("has_headings"):
                lines.append("     + Has headings")
            if item.get("has_purpose"):
                lines.append("     + Has purpose/overview section")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        if format == "json":
            return {"error": str(e), "healable_stubs": []}
        return f"Error listing healable stubs: {e}"


@mcp.tool()
def heal_stubs(
    project_root: Optional[str] = None,
    dry_run: bool = False,
    min_wiki_length: int = 350,
    format: Literal["text", "json"] = "text"
) -> str | dict:
    """
    Automatically heal outdated 'Initial stub' health entries that now have
    substantial wiki summaries.

    Uses quality heuristics (headings, purpose sections, length, structure)
    to decide whether to promote to 🟡 Yellow or directly to 🟢 Green.

    This is the agent-actionable version of `wikifier heal-stubs`.
    """
    root = _get_effective_root(project_root)
    try:
        import wikifier.health as health_module
        count = health_module.heal_outdated_stubs(
            root, min_wiki_length=min_wiki_length, dry_run=dry_run
        )
        action = "Would have healed" if dry_run else "Healed"
        if format == "json":
            return {
                "project_root": str(root),
                "healed_count": count,
                "dry_run": dry_run,
                "min_wiki_length": min_wiki_length,
                "message": f"{action} {count} outdated stub entries."
            }
        return f"{action} {count} outdated 'Initial stub' entries."
    except Exception as e:
        if format == "json":
            return {"error": str(e), "healed_count": 0}
        return f"Error during heal_stubs: {e}"


@mcp.tool()
def validate(project_root: Optional[str] = None, format: Literal["text", "json"] = "text") -> str | dict:
    """
    Ensure every monitored file has at least a health entry.

    Supports structured JSON output and targeting different projects.
    """
    root = _get_effective_root(project_root)
    try:
        output = _run_wikifier_command("validate", root=root)
        if format == "json":
            return {
                "success": True,
                "project_root": str(root),
                "message": output,
                "action": "Run check-changes + mark-green on any newly discovered files."
            }
        return output
    except Exception as e:
        if format == "json":
            return {"success": False, "project_root": str(root), "error": str(e)}
        return f"Error during validate: {e}"


@mcp.tool()
def journal(date: str = "", project_root: Optional[str] = None, format: Literal["text", "json"] = "text") -> str | dict:
    """Read the journal for a date (YYYY-MM-DD). Defaults to today."""
    root = _get_effective_root(project_root)
    args = [date] if date else []
    try:
        output = _run_wikifier_command("journal", args, root=root)
        if format == "json":
            return {
                "success": True,
                "project_root": str(root),
                "date": date or "today",
                "content": output
            }
        return output
    except Exception as e:
        if format == "json":
            return {"success": False, "project_root": str(root), "error": str(e)}
        return f"Error reading journal: {e}"


@mcp.tool()
def issues(severity: str = "all", project_root: Optional[str] = None, format: Literal["text", "json"] = "text") -> str | dict:
    """List logged issues by severity (simple|moderate|high|critical|all)."""
    root = _get_effective_root(project_root)
    args = [] if severity == "all" else [severity]
    try:
        output = _run_wikifier_command("issues", args, root=root)
        if format == "json":
            return {
                "success": True,
                "project_root": str(root),
                "severity": severity,
                "content": output
            }
        return output
    except Exception as e:
        if format == "json":
            return {"success": False, "project_root": str(root), "error": str(e)}
        return f"Error listing issues: {e}"


# =============================================================================
# Dependency Intelligence Tools (Structured + Text)
# =============================================================================

@mcp.tool()
def get_dependencies(file: str, format: Literal["text", "json"] = "text", project_root: Optional[str] = None, low_confidence_only: bool = False) -> str | dict:
    """
    Get what a file imports (forward dependencies).
    Returns either human-readable text or structured JSON.
    Prefers the rich import_cache data (with confidence) when available.

    R2 ACS Explanations Maturity (canonical single-source via contracts.compute_acs_confidence):
    - confidence_score (0.05-0.95, 2 decimals, identical JS/Python, rich-signal aware)
    - confidence_reasons (stable, filterable/aggregatable tokens: base:*, tag:*, detector:*, strategy:*, cycle_participant, weak/strong_*, complexity:*, barrel_depth=N, via_barrel, ...)
    - confidence_explanation (R2: consistently excellent short narrative + full "Recommendation: ..." prescriptive sentence — PRIMARY DECISION-READY FIELD for agents. Quote verbatim in reports. Handles tiny projects to large monorepos with prioritized risks + evidence traces.)
    - conditional_analysis / dynamic_analysis (semantic_tags, detectors_fired, analysis_trace evidence)
    - resolution_metadata + strategy
    - post-query cycle enrichment now produces canonical Recommendation text

    Decision use: 
      * JSON: filter confidence_score < 0.65 or high-sev reasons; read full explanation + traces + analysis.
      * Text: "why:" lines contain ready-to-quote Recommendation (full action sentence preserved).
    - low_confidence_only=True: server-side ACS filter (post-enrich) to return only low-trust edges (score<0.65 or low/unresolved) for direct risky-dep focus (Gap #1 surfacing polish).
    Scalable, precomputed, trustworthy for autonomous use across all codebase sizes.
    """
    root = _get_effective_root(project_root)

    # Preferred path: rich data from import cache (now includes confidence)
    cached = _get_resolved_from_cache(file, root)
    if cached:
        # Enrich with cycle participation (cross-ref _cycles) - consistent structure handling
        cycle_info = {}
        try:
            import wikifier.import_cache as import_cache
            cache = import_cache.load_cache(root)
            cdata = import_cache.get_cycles(cache)
            did_compute_here = False
            # Wave 4 on-demand canonical (after audit of get_dependencies enrichment path):
            # honor WIKIFIER_USE_CANONICAL env (default True) for v1 physical ids + consistent reuse with get_cycles / sh 3d.
            uc = os.environ.get("WIKIFIER_USE_CANONICAL", "1") not in ("0", "false", "False")
            if not cdata or "sccs" not in cdata:
                cdata = import_cache.compute_cycles(cache, root=root, use_canonical=uc)
                did_compute_here = True
            involved = set(cdata.get("all_cycle_files", []))
            if did_compute_here:
                try:
                    import_cache.set_cycles(cache, cdata)
                    gsig = cdata.get("graph_signature")
                    if gsig:
                        import_cache.set_graph_signature(cache, gsig)
                    import_cache.save_cache(root, cache)
                except Exception:
                    pass
            if not involved:
                # fallback collect from sccs
                for s in cdata.get("sccs", []):
                    involved.update(s.get("nodes", []))
            for item in cached:
                res = item.get("resolved")
                if res and res in involved:
                    item["in_cycle"] = True
                    # R2/P2: surface cycle in reasons + adjust score (parse-time enrichment impossible; query-time is authoritative)
                    reasons = item.get("confidence_reasons") or []
                    if isinstance(reasons, list) and "cycle_participant" not in reasons:
                        reasons = list(reasons) + ["cycle_participant"]
                        item["confidence_reasons"] = reasons
                    # F2: also downgrade the numeric score so JSON consumers see consistent value
                    cs = item.get("confidence_score")
                    if isinstance(cs, (int, float)):
                        new_cs = max(0.05, round(float(cs) - 0.10, 2))
                        item["confidence_score"] = new_cs
                    # R2: append cycle note (newer explanations already contain prescriptive cycle guidance from canonical builder)
                    expl = item.get("confidence_explanation") or ""
                    # R2: use canonical cycle recommendation phrasing for consistency with compute_acs_confidence
                    cycle_rec = "Cycle participant (high refactor risk) — use get_cycles(analysis=True) to retrieve severity, blast radius and weakest-link recommendations; change requires coordinated edit across the SCC."
                    if "cycle_participant" in (item.get("confidence_reasons") or []) and "Cycle participant" not in (expl or ""):
                        if "Recommendation:" in expl:
                            head = expl.split("Recommendation:", 1)[0].rstrip(". ")
                            item["confidence_explanation"] = f"{head}. Recommendation: {cycle_rec}"
                        else:
                            item["confidence_explanation"] = (expl.rstrip(".") + ". Recommendation: " + cycle_rec).strip()
                    elif expl and "cycle" not in expl.lower():
                        # legacy append (rare path)
                        item["confidence_explanation"] = expl.rstrip(".") + ". Cycle participation detected (score downgraded)."
            if file in involved:
                cycle_info["file_in_cycle"] = True
                sccs = cdata.get("sccs", [])
                cycle_info["cycles_count"] = sum(1 for s in sccs if file in s.get("nodes", []))
        except Exception:
            pass

        # ACS low-conf filter (Gap #1 remaining slice + surfacing uniformity): allows direct
        # get_dependencies(..., low_confidence_only=True) for risky edges only, using same
        # heuristic as json low_confidence_count and ensure_acs. Additive, zero-dep on prior.
        if low_confidence_only:
            cached = [
                it for it in cached
                if (it.get("confidence_score") or 1.0) < 0.65
                or str(it.get("confidence") or "").lower() in ("low", "unresolved")
            ]

        if format == "json":
            payload = {
                "file": file,
                "imports": cached,
                "count": len(cached),
                "source": "cache",
                "cycle_participation": cycle_info,
                # P2 ACS: agent-usable aggregate for quick filtering/prioritization
                "low_confidence_count": sum(
                    1 for it in cached
                    if (it.get("confidence_score") or 1.0) < 0.55
                    or (it.get("confidence") or "").lower() in ("low", "unresolved")
                ),
            }
            return payload
        resolved_list = [item.get("resolved") for item in cached if item.get("resolved")]
        text = f"{file} imports ({len(resolved_list)}):\n" + ", ".join(resolved_list)

        # R2: Surface rich actionable ACS metadata (canonical explanations from contracts).
        # Prioritizes the prescriptive confidence_explanation (with Recommendation) for
        # immediate agent decision use. Full structured signals always available in JSON.
        # Truncation tuned for readability on large result sets; complete text in JSON.
        notes = []
        for item in cached:
            resolved = item.get("resolved") or "?"
            expl = item.get("confidence_explanation")
            conf_score = item.get("confidence_score")
            reasons = item.get("confidence_reasons") or []
            ca = item.get("conditional_analysis") or {}
            da = item.get("dynamic_analysis") or {}
            rm = item.get("resolution_metadata") or {}
            meta = []
            if conf_score is not None:
                meta.append(f"conf={conf_score}")
            if expl:
                # R2 matured: always surface the full prescriptive Recommendation (decision-critical); truncate only factor prefix for text readability on large monorepos. Full expl in JSON.
                rec_marker = "Recommendation:"
                if rec_marker in expl:
                    head, rec_part = expl.split(rec_marker, 1)
                    short_head = head[:110].rstrip(". ") + ("..." if len(head) > 110 else "")
                    # full rec always (agents quote this verbatim); no truncation on the action sentence
                    short_expl = f"{short_head}. {rec_marker} {rec_part.strip()}"
                else:
                    short_expl = expl[:220] + ("..." if len(expl) > 220 else "")
                meta.append(f"why: {short_expl}")
            elif reasons:
                informative = [r for r in reasons if not str(r).startswith("base:")][:4]
                if informative:
                    meta.append("why:" + "|".join(str(x) for x in informative))
            if item.get("is_conditional"):
                meta.append("conditional")
                tags = ca.get("semantic_tags") or []
                if tags:
                    meta.append("tags:" + ",".join(tags[:3]))
            if item.get("via_barrel"):
                depth = item.get("barrel_depth") or "?"
                meta.append(f"via barrel depth={depth}")
            if item.get("is_dynamic"):
                meta.append(f"dynamic:{item.get('dynamic_type','?')}")
            if item.get("in_cycle"):
                meta.append("⚠️ cycle")
            strat = item.get("strategy")
            if strat and not str(strat).startswith(("legacy", "bare")):
                meta.append(f"via:{strat}")
            if isinstance(rm, dict):
                if rm.get("matched_condition"):
                    meta.append(f"matched:{rm.get('matched_condition')}")
                if rm.get("workspace_pkg"):
                    meta.append(f"pkg:{rm.get('workspace_pkg')}")
            # Trace evidence (rich CDIA signals)
            for analysis in (ca, da):
                for tr in (analysis.get("analysis_trace") or [])[:1]:
                    if isinstance(tr, dict) and tr.get("evidence"):
                        ev = str(tr.get("evidence"))[:40]
                        meta.append(f"ev:{ev}")
            if meta:
                notes.append(f"{resolved} ({', '.join(meta)})")

        if notes:
            text += "\n\nNotes (R2 canonical ACS explanations + rich signals):\n" + "\n".join(f"  - {n}" for n in notes)
        if cycle_info.get("file_in_cycle"):
            text += f"\n⚠️  {file} itself participates in circular dependency(ies)."
        return text

    # Fallback: parse the markdown table
    library = _read_file_safe("library.md", root=root)
    pattern = rf"\| {re.escape(file)} \| (.*?) \|"
    match = re.search(pattern, library)

    if match:
        imports_str = match.group(1)
        if format == "json":
            return {
                "file": file,
                "imports": [x.strip() for x in imports_str.split(",") if x.strip()],
                "source": "table"
            }
        return f"{file} imports:\n{imports_str}"

    if format == "json":
        return {"file": file, "imports": [], "message": "No resolved internal dependencies found.", "source": "none"}
    return f"No resolved internal dependencies found for {file}."


@mcp.tool()
def get_dependents(file: str, format: Literal["text", "json"] = "text", project_root: Optional[str] = None) -> str | dict:
    """
    Get files that import this file (reverse dependencies).
    One of the most valuable tools for understanding impact.
    Now includes cache fallback (Fix 6) for resilience when the main table is sparse.
    """
    root = _get_effective_root(project_root)
    # Preferred fast path: use the persisted _reverse_dependencies structure (new in M2-Rem-08)
    try:
        import wikifier.import_cache as import_cache
        cache = import_cache.load_cache(root)
        reverse_map = import_cache.get_reverse_dependencies(cache)
        if file in reverse_map:
            dependents = reverse_map[file]
            if format == "json":
                return {
                    "file": file,
                    "dependents": dependents,
                    "count": len(dependents),
                    "source": "reverse_cache"
                }
            return f"Files that import {file} ({len(dependents)}):\n" + "\n".join(f"- {d}" for d in dependents)
    except Exception:
        pass

    # Fallback 1: Parse the markdown table
    reverse_map = _parse_resolved_dependencies(root)
    dependents = reverse_map.get(file, [])

    if not dependents:
        # Fallback 2: Full scan of import_cache.json (older method)
        try:
            import wikifier.import_cache as import_cache
            cache = import_cache.load_cache(root)
            for source, data in cache.items():
                if source.startswith("_"):  # skip internal keys like _reverse_dependencies
                    continue
                pairs = data.get("resolved_pairs", [])
                for p in pairs:
                    if p.get("resolved") == file:
                        if source not in dependents:
                            dependents.append(source)
        except Exception:
            pass

    if format == "json":
        return {
            "file": file,
            "dependents": dependents,
            "count": len(dependents),
            "source": "table" if reverse_map.get(file) else "cache_fallback"
        }

    if not dependents:
        return f"No files currently import {file} (or it has not been resolved yet)."

    return f"Files that import {file} ({len(dependents)}):\n" + "\n".join(f"- {d}" for d in dependents)


@mcp.tool()
def get_cycles(
    analysis: bool = False,
    max_items: Optional[int] = None,
    format: Literal["text", "json"] = "text",
    project_root: Optional[str] = None,
    use_canonical: bool = True,
) -> str | dict:
    """
    Retrieve circular dependency (cycle) intelligence from the persisted _cycles
    (Phase 1 of Gap #1 dependency graph integrity).

    Returns rich SCC data + per-cluster signals (dynamic/conditional/barrel edges).
    - analysis=True: returns full analyses from CIABRE v1.2 (R5): severity scoring (tuned on real dogfood dyn+barrel+blast),
      external blast radius, weakest links (risk-ranked), and ranked practical refactoring recommendations with
      detailed rationale/hint/safety notes tied to signals (v1.3 registry ext + hardened ACS-referencing rationales). JSON includes "cycle_analyses" + "ciabre_version". Top recs now surfaced full (no truncation) in text.
    - format="json": full machine-readable _cycles structure (+ analyses when analysis=True); now also surfaces top-level "graph_signature", "reused", "reuse_reason" (Wave 2 delta support).
    - use_canonical=True (default, Wave 4): requests v1 canonical physical node ids (via canonical_for_bree) for stable graphs/signatures across symlinks/workspaces. False yields v0 raw for compat. Public surface (MCP + CLI + run_full_update prep) per gap1_cycles_longterm_strategy.
    - Integrates with library.md "Circular Dependencies" (SEVERITY + rich rec with rationale), CLI `wikifier cycles`,
      and Mermaid cycleNode styling. Scoring + extensible registry rules in import_cache.py CIABRE section.
    - Wave 2/3/4: graph_signature + reuse info (reused=True on match; short-circuits iterative Tarjan + CIABRE in compute + main 3d update-maps path; default now v1 in sh 3d + on-demand). Canonical v1 active. get_cycles_reuse_stats central surfacer used in health/diagnostics/MCP.
    """
    root = _get_effective_root(project_root)
    try:
        import wikifier.import_cache as import_cache
        cache = import_cache.load_cache(root)
        cdata = import_cache.get_cycles(cache)
        did_compute_cycles = False
        if not cdata or "sccs" not in cdata:
            cdata = import_cache.compute_cycles(cache, root=root, use_canonical=use_canonical)
            did_compute_cycles = True
        integrity = cache.get("_graph_integrity") or import_cache.compute_graph_integrity(cache)

        # P3 CIABRE: load (or compute on-demand) cycle analyses for severity/recommendations when requested
        cycle_analyses = {}
        did_compute_analyses = False
        if analysis:
            cycle_analyses = import_cache.get_cycle_analyses(cache)
            if not cycle_analyses or "analyses" not in cycle_analyses:
                cycle_analyses = import_cache.compute_cycle_analyses(cache, root=root, use_canonical=use_canonical)
                did_compute_analyses = True

        # Guaranteed persistence hardening (Gap #1 cycles area):
        # If any on-demand compute occurred (e.g. pre-persistence cache, partial sh path,
        # direct Python use of MCP without recent update-maps), write the results back
        # under the reserved keys + graph_signature so that library.md, CLI `cycles`,
        # future queries, and incremental/delta logic see them without re-work.
        # Safe: save_cache uses the M2 locking; best-effort on error.
        if did_compute_cycles or did_compute_analyses or not cache.get("_graph_integrity"):
            try:
                if did_compute_cycles:
                    import_cache.set_cycles(cache, cdata)
                    gsig = cdata.get("graph_signature")
                    if gsig:
                        import_cache.set_graph_signature(cache, gsig)
                if integrity and not cache.get("_graph_integrity"):
                    import_cache.set_graph_integrity(cache, integrity)
                if did_compute_analyses:
                    import_cache.set_cycle_analyses(cache, cycle_analyses)
                import_cache.save_cache(root, cache)
            except Exception:
                pass  # never let a read/query path fail due to persist side-effect

        stats = cdata.get("stats", {})
        sccs = cdata.get("sccs", [])
        limit = max_items or (20 if not analysis else 100)
        items = sccs[:limit]

        if format == "json":
            payload = {
                "count": stats.get("cyclic_scc_count", len(sccs)),
                "cycles": cdata,  # full rich structure (now includes graph_signature + reused/reuse_reason for delta)
                "sccs": items,
                "integrity": integrity,
                "analysis": analysis,
                "source": "import_cache",
                "stats": stats,
                "graph_signature": cdata.get("graph_signature"),
                "reused": cdata.get("reused", False),
                "reuse_reason": cdata.get("reuse_reason"),
                "cycle_analyses": cycle_analyses if analysis else None,  # CIABRE: severity, blast, weakest, ranked recs (+ reuse fields)
                "ciabre_version": cycle_analyses.get("analysis_version") if analysis and cycle_analyses else None,
            }
            return payload

        # Human text - polished professional formatting
        out = []
        cluster_count = stats.get("cyclic_scc_count", len(sccs))
        file_count = stats.get("total_files_in_cycles", 0)
        largest = stats.get("largest_scc_size", 0)
        out.append("=== Circular Dependencies Report ===")
        out.append(f"Clusters: {cluster_count}   |   Files involved: {file_count}   |   Largest: {largest}")
        summary = integrity.get("summary", "N/A")
        out.append(f"Graph Integrity: {summary}")
        gsig = cdata.get("graph_signature", "N/A")
        reused = cdata.get("reused", False)
        reuse_note = " (reused: delta/incremental safe, no Tarjan recompute)" if reused else ""
        out.append(f"Graph signature: {gsig}{reuse_note}")
        out.append("")
        if not items:
            out.append("✅ No circular dependencies detected in the current dependency graph.")
        else:
            out.append("Detected cyclic clusters (rich signals):")
            # build quick lookup for CIABRE analyses by sorted nodes tuple
            a_map = {}
            if analysis and cycle_analyses:
                for aa in (cycle_analyses.get("analyses") or []):
                    a_map[tuple(sorted(aa.get("nodes", [])))] = aa
            for i, c in enumerate(items, 1):
                ex = c.get("example_path") or " → ".join(c.get("nodes", [])[:5])
                out.append(f"  {i}. size={c.get('size')}  {ex}")
                if analysis:
                    sig = c.get("signals", {})
                    out.append(f"     signals: dyn={sig.get('dynamic_edge_count',0)} cond={sig.get('conditional_edge_count',0)} barrel={sig.get('barrel_edge_count',0)}  (conf: {sig.get('confidence_breakdown', {})})")
                    # P3 CIABRE enrichment in text when analysis=True
                    key = tuple(sorted(c.get("nodes", [])))
                    a = a_map.get(key, {})
                    if a.get("severity"):
                        w = (a.get("weakest_links") or [{}])[0]
                        rec0 = (a.get("recommendations") or [{}])[0]
                        out.append(f"     SEVERITY: {a.get('severity')} (score={a.get('score')}, blast={a.get('external_blast_radius')}) | weakest: {w.get('from','?')}→{w.get('to','?')} (risk={w.get('risk_score','?')})")
                        if rec0.get("strategy"):
                            # Surfacing uniformity (ACS+CIABRE audit): full text for top rec (rationale/hint/safety) so agents quote verbatim; truncation only for huge lists
                            rat = rec0.get("rationale") or ""
                            hnt = rec0.get("hint") or ""
                            saf = rec0.get("safety") or ""
                            out.append(f"     TOP REC: {rec0.get('strategy')} — {rat} (hint: {hnt}; safety: {saf})")
            if len(sccs) > len(items):
                out.append(f"  ... ({len(sccs) - len(items)} more; use analysis=True or raise max_items for full list)")
        out.append("")
        out.append("MCP: get_cycles(format=\"json\", analysis=True) + get_project_status (ACS+CIABRE summaries)  |  CLI: wikifier cycles  |  library.md \"Circular Dependencies\" + \"ACS Risk Snapshot\" | Use full confidence_explanation Recommendation sentences as decision oracle")
        return "\n".join(out)
    except Exception as ex:
        if format == "json":
            return {"error": str(ex), "data": None, "count": 0, "sccs": []}
        return f"get_cycles failed: {ex}. Run `wikifier update-maps` to populate intelligence."


@mcp.tool()
def get_resolution_diagnostics(
    file: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 20,
    format: Literal["text", "json"] = "text",
    project_root: Optional[str] = None,
) -> str | dict:
    """
    Resolution diagnostics & failure transparency (Limitation #5 / diagnostics layer).
    Shows why certain imports resolved to low/medium/unresolved confidence, dynamic, conditional etc.
    Per-file or global aggregates + bounded samples. Complements library.md "Conditional & Dynamic Intelligence" and get_cycles signals.
    """
    root = _get_effective_root(project_root)
    try:
        import wikifier.import_cache as import_cache
        cache = import_cache.load_cache(root)
        if file:
            # per-file view from its pairs
            data = cache.get(file.lstrip("./"), {}) or {}
            pairs = data.get("resolved_pairs", [])
            lowish = [p for p in pairs if (p.get("confidence") or "").lower() not in ("high", "")]
            summary = {"file": file, "total_imports": len(pairs), "non_high_count": len(lowish), "samples": lowish[:limit]}
            if format == "json": return summary
            # text with samples
            lines = [f"=== Resolution Diagnostics for {file} ==="]
            lines.append(f"Imports: {len(pairs)}  |  Non-high confidence: {len(lowish)}")
            if lowish:
                lines.append("Sample low/partial resolutions:")
                for p in lowish[:min(5, limit)]:
                    conf = p.get("confidence", "?")
                    raw = p.get("raw", "")[:40]
                    diag_info = p.get("diagnostic") or {}
                    cat = diag_info.get("category") if isinstance(diag_info, dict) else "?"
                    reason = (diag_info.get("reason") if isinstance(diag_info, dict) else "")[:60]
                    lines.append(f"  - [{conf}] {raw} → {p.get('resolved','?')}  cat={cat}  {reason}")
            else:
                lines.append("All imports resolved at high confidence (no diagnostics needed).")
            lines.append("Use format=json for full samples + details.")
            return "\n".join(lines)
        # global
        diag = import_cache.get_resolution_diagnostics(cache)
        if not diag or diag.get("total_imports", 0) == 0:
            diag = import_cache.ensure_diagnostics_aggregate(cache)
        # Wave 3+: reuse central stats helper for broader surfacing (incl. canonical v1 node_identity_version)
        reuse_stats = import_cache.get_cycles_reuse_stats(cache)
        gsig = reuse_stats.get("graph_signature") or "N/A"
        c_reused = reuse_stats.get("reused", False)
        c_gsig = reuse_stats.get("graph_signature")
        c_ver = reuse_stats.get("node_identity_version", "v0")
        if category:
            # filter samples
            cats = diag.get("by_category", {})
            diag = {**diag, "filtered_to": category, "count_in_cat": cats.get(category, 0)}
        if format == "json":
            return {**diag, "graph_signature": gsig, "cycles_graph_signature": c_gsig, "cycles_reused": c_reused, "cycles_node_identity_version": c_ver}
        # text summary - polished
        bc = diag.get("by_category", {})
        top = ", ".join(diag.get("top_categories", [])) or "none"
        low = diag.get("low_or_unresolved_count", 0)
        tot = diag.get("total_imports", 0)
        lines = ["=== Resolution Diagnostics ==="]
        lines.append(f"Total imports analyzed: {tot}")
        lines.append(f"Low or unresolved: {low} ({(low/tot*100):.1f}% of total)" if tot else "Low or unresolved: 0")
        lines.append(f"Top categories: {top}")
        lines.append(f"Breakdown: {bc}")
        lines.append(f"Graph structure (cycles): signature={gsig} reused={c_reused} (see get_cycles for delta details + full CIABRE)")
        samples = diag.get("samples", [])[:5]
        if samples:
            lines.append("Top samples (see JSON for more):")
            for s in samples:
                lines.append(f"  - {s.get('src','?')} [{s.get('confidence','?')}] {s.get('raw','')[:30]} → cat={s.get('category','?')}")
        lines.append("See also: library.md \"Conditional & Dynamic Intelligence\" + get_cycles for related signals (Wave 2: graph_signature + reuse surfaced here too).")
        return "\n".join(lines)
    except Exception as ex:
        if format == "json": return {"error": str(ex)}
        return f"Diagnostics unavailable: {ex}"


@mcp.tool()
def get_file_wiki(file: str, format: Literal["text", "json"] = "text", project_root: Optional[str] = None) -> str | dict:
    """
    Retrieve the wiki/documentation summary for a specific file.

    This is a significantly hardened version designed for reliability across
    different project layouts and large codebases.
    """
    root = _get_effective_root(project_root)
    file = file.strip().lstrip("./")

    # Normalize
    base_with_ext = file
    base_no_ext = file.rsplit('.', 1)[0] if '.' in file else file

    candidates = []

    # === 1. Wiki file right next to the source file (best convention) ===
    # Try both with and without the original extension
    candidates.extend([
        f"{base_with_ext}.wiki.md",
        f"{base_with_ext}.md",
        f"{base_no_ext}.wiki.md",
        f"{base_no_ext}.md",
    ])

    # === 2. Wiki file in the same directory as the source (very useful) ===
    file_path = Path(file)
    if file_path.parent != Path('.'):
        parent = str(file_path.parent)
        candidates.extend([
            f"{parent}/{base_no_ext}.wiki.md",
            f"{parent}/{base_no_ext}.md",
            f"{parent}/{base_with_ext}.wiki.md",
            f"{parent}/{base_with_ext}.md",
        ])

    # === 3. Standard wiki directories (with and without sanitized paths) ===
    wiki_dirs = ["docs/wiki", "docs", "wiki", "documentation", ".wiki"]
    for d in wiki_dirs:
        candidates.extend([
            f"{d}/{base_with_ext}.md",
            f"{d}/{base_with_ext}.wiki.md",
            f"{d}/{base_no_ext}.md",
            f"{d}/{base_no_ext}.wiki.md",
        ])
        # Sanitized versions (e.g. src-services-mealPlannerService.wiki.md)
        sanitized = base_no_ext.replace("/", "-").replace("\\", "-")
        candidates.extend([
            f"{d}/{sanitized}.md",
            f"{d}/{sanitized}.wiki.md",
        ])

    # === 4. Recursive search inside wiki directories (last resort but powerful) ===
    for d in wiki_dirs:
        wiki_path = root / d
        if wiki_path.exists() and wiki_path.is_dir():
            for md_file in list(wiki_path.rglob("*.md")) + list(wiki_path.rglob("*.wiki.md")):
                name = md_file.name.lower()
                if base_no_ext.lower() in name or base_with_ext.lower() in name:
                    rel_path = str(md_file.relative_to(root))
                    if rel_path not in candidates:
                        candidates.append(rel_path)

    # === 5. Also look for any .md / .wiki.md file in the exact same directory as the source ===
    # This is very common in real projects (people often drop descriptive .md files next to the code)
    source_dir = root / Path(base_no_ext).parent
    if source_dir.exists() and source_dir.is_dir():
        for md_file in list(source_dir.glob("*.md")) + list(source_dir.glob("*.wiki.md")):
            name = md_file.name.lower()
            if base_no_ext.lower() in name or base_with_ext.lower() in name:
                rel_path = str(md_file.relative_to(root))
                if rel_path not in candidates:
                    candidates.append(rel_path)

    # Deduplicate while preserving priority order
    seen = set()
    final_candidates = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            final_candidates.append(c)

    # === Try candidates ===
    for candidate in final_candidates:
        content = _read_file_safe(candidate, root=root)
        if not content.startswith("File not found"):
            if format == "json":
                return {
                    "file": file,
                    "source": candidate,
                    "content": content,
                    "project_root": str(root),
                    "confidence": "high" if "wiki" in candidate.lower() else "medium",
                    "suggestions": []
                }
            return f"=== Wiki for {file} (from {candidate}) ===\n\n{content}"

    # === Fallback: Smarter extraction from library.md ===
    library = _read_file_safe("library.md", root=root)
    search_terms = [base_no_ext, base_with_ext]
    if file in library or any(term in library for term in search_terms):
        lines = library.splitlines()
        best_context = None
        best_score = 0

        for i, line in enumerate(lines):
            score = 0
            if any(term in line for term in search_terms):
                score += 1
                # Strongly prefer lines from the Resolved Internal Dependencies section
                if "Resolved Internal Dependencies" in "\n".join(lines[max(0, i-10):i]):
                    score += 3
                if "→" in line:
                    score += 2
                # Also like lines from the Source Files table
                if "Source File" in "\n".join(lines[max(0, i-5):i]) or "Imports" in line:
                    score += 1

                context = "\n".join(lines[max(0, i-2): min(len(lines), i+5)])

                if score > best_score:
                    best_score = score
                    best_context = context

        if best_context:
            if format == "json":
                return {
                    "file": file,
                    "source": "library.md (extracted)",
                    "content": best_context,
                    "project_root": str(root),
                    "confidence": "medium" if best_score >= 3 else "low",
                    "suggestions": []
                }
            return f"=== Mentions of {file} in library.md ===\n\n{best_context}"

    # === Nothing found (final robustness) ===
    if format == "json":
        return {
            "file": file,
            "source": None,
            "content": None,
            "project_root": str(root),
            "confidence": "none",
            "message": "No dedicated wiki summary found for this file.",
            "candidates_tried": final_candidates[:20],
            "suggestions": [
                f"Create {base_no_ext}.wiki.md right next to the source file (best practice)",
                f"Create docs/wiki/{base_no_ext}.md or wiki/{base_no_ext}.wiki.md",
                "After writing the summary, run mark_green on the file"
            ]
        }
    return f"Could not find a dedicated wiki summary for {file}. Tried many locations. Consider creating {base_no_ext}.wiki.md next to the source."

    return (
        f"No dedicated wiki summary found for {file}.\n\n"
        "Recommended locations (best to good):\n"
        f"  1. {base_no_ext}.wiki.md or {base_with_ext}.wiki.md   (next to the source file — highest reliability)\n"
        f"  2. docs/wiki/{base_no_ext}.md\n"
        f"  3. wiki/{base_no_ext}.md\n\n"
        "Using the `.wiki.md` convention right next to the source file is strongly recommended for agents."
    )


@mcp.tool()
def get_files_needing_attention(
    status: Literal["red", "yellow", "all"] = "all",
    directory: Optional[str] = None,
    project_root: Optional[str] = None,
    format: Literal["text", "json"] = "text"
) -> str | dict:
    """
    Return files that need attention (Red or Yellow).

    Uses the fast scalable Python backend (wikifier.health).
    Supports directory filtering — very useful on large monorepos.
    """
    root = _get_effective_root(project_root)

    try:
        import wikifier.health as health_module

        status_filter = None
        if status == "red":
            status_filter = "[RED]"
        elif status == "yellow":
            status_filter = "[YELLOW]"

        files = health_module.get_files_needing_attention(root, status_filter, directory)

        if format == "json":
            # Light ACS context (Gap #1 uniformity): include low-conf edge count for agents to correlate file attention with dep-risk filtering
            acs_ctx = {}
            try:
                import wikifier.import_cache as ic
                c = ic.load_cache(root)
                a = ic.ensure_acs_summary_persisted(c, root)
                if a.get("low_conf_edges", 0):
                    acs_ctx = {"low_conf_edges": a.get("low_conf_edges"), "avg_confidence": a.get("avg_confidence"), "acs_version": a.get("acs_version")}
            except Exception:
                pass
            return {
                "project_root": str(root),
                "directory": directory or ".",
                "status_filter": status,
                "files": files,
                "count": len(files),
                "acs_low_conf_context": acs_ctx or None
            }

        if not files:
            return "No files currently need attention."

        red = [f for f in files if "[RED]" in f]  # This won't work well since we only have paths
        # Better: we don't have status here easily. Let's just list them.
        return "Files needing attention:\n" + "\n".join(f"- {f}" for f in files)

    except Exception:
        # Fallback
        root = _get_effective_root(project_root)
        output = _run_wikifier_command("health", root=root)
        lines = []
        for line in output.splitlines():
            if "[RED]" in line or "[YELLOW]" in line:
                if directory and not line.strip().startswith(f"| {directory}"):
                    continue
                if status == "red" and "[RED]" not in line:
                    continue
                if status == "yellow" and "[YELLOW]" not in line:
                    continue
                lines.append(line.strip())
        return "\n".join(lines) if lines else "No files currently need attention."


@mcp.tool()
def get_project_status(
    format: Literal["text", "json"] = "text",
    project_root: Optional[str] = None,
    directory: Optional[str] = None
) -> str | ProjectHealthSummary:
    """Return a high-level overview of project documentation health.

    Uses the fast scalable Python backend when possible.
    """
    root = _get_effective_root(project_root)

    try:
        import wikifier.health as health_module
        summary = health_module.get_summary(root, directory)
        pending = _read_file_safe("pending_updates.md", root=root)

        pending_count = len([l for l in pending.splitlines() if l.strip() and not l.startswith("#")])

        # ACS + CIABRE + Wave 2 Barrel/BRC surfacing uniformity: lightweight stats + invalidation reports foundation in project status (MCP primary for agents)
        dep_intel = {}
        try:
            import wikifier.import_cache as ic
            cache = ic.load_cache(root)
            # On-demand persistence guarantee for _acs_summary (Gap #1 ACS surfacing wave; mirrors cycles guaranteed persist)
            acs = ic.ensure_acs_summary_persisted(cache, root)
            cyc = ic.get_cycle_analyses(cache) or {}
            barrel = ic.get_barrel_cache_summary(cache) or {}
            sample_barrel_reports = []
            if barrel.get("has_brc"):
                try:
                    # Richer MCP observability (continuation wave): up to 5 samples + richer text (5 lines now, det/partial/chains) in get_project_status + health.
                    # Full structured (incl. chains, partial, detector) + _barrel_invalidation_log audit awareness for "why reparse" traceability at scale.
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
                    "barrel_invalidation_summary": barrel,  # Wave 2: num_chains, v1 coverage, partials, indexed barrels (for "why" via get_barrel_invalidation_reports when dirty)
                    "sample_barrel_reports": sample_barrel_reports,  # basic observability added (get_project_status + health)
                }
        except Exception:
            pass

        if format == "json":
            base = ProjectHealthSummary(
                total_files=summary["total"],
                green=summary["green"],
                yellow=summary["yellow"],
                red=summary["red"],
                pending_updates=pending_count,
                health_score="Good" if summary["red"] == 0 and summary["yellow"] < 5 else "Needs Attention" if summary["red"] < 3 else "Critical"
            )
            # attach dep intel (additive, agents can now use for ACS filtering without separate calls)
            if isinstance(base, dict):
                base["dependency_intel"] = dep_intel
            else:
                try:
                    base.dependency_intel = dep_intel  # type: ignore[attr-defined]
                except Exception:
                    pass
            return base

        dir_str = f" (in {directory})" if directory else ""
        dep_lines = ""
        if dep_intel.get("acs_summary") or dep_intel.get("barrel_invalidation_summary"):
            a = dep_intel.get("acs_summary") or {}
            c = dep_intel.get("ciabre_summary", {})
            b = dep_intel.get("barrel_invalidation_summary", {}) or {}
            barrel_line = ""
            if b.get("has_brc"):
                barrel_line = f"\n  Barrel/BRC (v{b.get('version','bree-v2')}): {b.get('num_chains',0)} chains (v1:{b.get('v1_canonical_chains',0)}, partials:{b.get('partial_chains',0)}) | indexed barrels:{b.get('num_indexed_barrels',0)}"
            dep_lines = f"""
Dependency Intelligence (ACS v{a.get('acs_version','1.0') or '1.0'} + CIABRE v{dep_intel.get('ciabre_version','1.3') or '1.3'}):{barrel_line}
  ACS: {a.get('total_scored_edges',0)} edges | avg={a.get('avg_confidence',0)} | low<0.65: {a.get('low_conf_edges',0)}
  CIABRE: {c.get('high_severity_count',0)} high-sev cycles | max_blast={c.get('max_blast_radius',0)}
  (see library.md "ACS Risk Snapshot", get_cycles(analysis=True), or full JSON for sample Recommendations + barrel_invalidation_summary)"""
            if barrel_line:
                dep_lines += "\n  (BRC pruning/GC + reports available via health prune-barrels + check-changes auto-Yellow)"
            # Richer samples (continuation wave): up to 5 detailed lines (was 3) with importer + barrels + reason + detector/partial/chains for richer "why" in get_project_status text (matches JSON 5 + _log)
            sbr = dep_intel.get("sample_barrel_reports") or []
            if sbr:
                dep_lines += "\n  Recent barrel invalidation samples (rich reports; see JSON for full 5 + _barrel_invalidation_log audit):"
                for i, r in enumerate(sbr[:5]):
                    imp = r.get("importer", "?") if isinstance(r, dict) else getattr(r, "importer", "?")
                    trigs = ",".join((r.get("triggering_barrels", []) or [])[:2]) if isinstance(r, dict) else ",".join(getattr(r, "triggering_barrels", [])[:2])
                    rsn = (r.get("reason", "") or "")[:50] if isinstance(r, dict) else ""
                    det = (r.get("detector", "") or "")[:20] if isinstance(r, dict) else ""
                    part = r.get("partial", False) if isinstance(r, dict) else False
                    nch = len(r.get("chain_ids", []) or []) if isinstance(r, dict) else 0
                    nv = r.get("node_identity_version", "v1") if isinstance(r, dict) else "v1"
                    dep_lines += f"\n    - {imp} via [{trigs}] (det={det}, partial={part}, chains={nch}, v{nv}): {rsn}"
                    # richer 5-sample detail for continuation (importer+full reason+audit context now in MCP text/JSON)
                # surface log presence for audit visibility in text too
                try:
                    cache = ic.load_cache(root)
                    logn = len(cache.get("_barrel_invalidation_log") or [])
                    if logn:
                        dep_lines += f"\n  (BRC audit log: {logn} historical invalidation events persisted)"
                except Exception:
                    pass
        return f"""Project Documentation Health{dir_str}
-----------------------------
[GREEN] Green:   {summary['green']}
[YELLOW] Yellow:  {summary['yellow']}
[RED] Red:     {summary['red']}

Pending updates: {pending_count}
{dep_lines}

Use get_files_needing_attention() for the actual list. Use get_cycles(analysis=True) + get_dependencies(format="json") for ACS confidence_explanation Recommendations."""

    except Exception:
        # Fallback to shell + text parsing
        root = _get_effective_root(project_root)
        health = _run_wikifier_command("health", root=root)
        pending = _read_file_safe("pending_updates.md", root=root)

        red = health.count("[RED]")
        yellow = health.count("[YELLOW]")
        green = health.count("[GREEN]")
        pending_count = len([l for l in pending.splitlines() if l.strip() and not l.startswith("#")])

        if format == "json":
            return ProjectHealthSummary(
                total_files=green + yellow + red,
                green=green,
                yellow=yellow,
                red=red,
                pending_updates=pending_count,
                health_score="Good" if red == 0 and yellow < 5 else "Needs Attention" if red < 3 else "Critical"
            )

        dir_str = f" (in {directory})" if directory else ""
        return f"""Project Documentation Health{dir_str}
-----------------------------
[GREEN] Green:   {green}
[YELLOW] Yellow:  {yellow}
[RED] Red:     {red}

Pending updates: {pending_count}

Use get_files_needing_attention() for the actual list."""


@mcp.tool()
def get_current_project_root() -> str:
    """Return the project root currently being used by this Wikifier MCP instance."""
    return str(WIKIFIER_ROOT)


@mcp.tool()
def get_barrel_reports(
    limit: int = 20,
    project_root: Optional[str] = None,
    include_log: bool = True,
) -> dict:
    """Dedicated MCP tool for barrel invalidation reports and audit (Gap #1 Deep Barrel Wave 4/closure).

    Provides richer, on-demand access to structured BRC invalidation data beyond the bounded samples
    embedded in get_project_status / health (where samples may be insufficient for agents debugging
    specific barrel-driven reparse events at monorepo scale).

    Returns:
      - barrel_invalidation_summary: stats (num_chains, v1 coverage, partials, indexed barrels)
      - recent_reports: list of rich BarrelInvalidationReport dicts (importer, triggering_barrels,
        chain_ids, reason, detector, partial, node_identity_version, etc.) — up to `limit`
      - barrel_invalidation_log: recent historical audit entries from _barrel_invalidation_log (if include_log)
        (ts + report snapshots persisted across daemon/check-changes/update-maps runs)
      - note on O(changed) delta path + pruning availability

    Complements existing surfaces; zero new deps, scalable (lens + bounded), safe on missing cache.
    Agents can now directly query "show me the last N barrel edits and exactly which importers were dirtied + why".
    """
    root = _get_effective_root(project_root)
    result: dict = {
        "project_root": str(root),
        "barrel_invalidation_summary": {"has_brc": False, "num_chains": 0},
        "recent_reports": [],
        "barrel_invalidation_log": [],
        "note": "Use get_barrel_reports for full dedicated 'why via barrel' audit trail (see also check-changes + prune-barrels CLI).",
    }
    try:
        import wikifier.import_cache as ic
        cache = ic.load_cache(root) or {}
        summary = ic.get_barrel_cache_summary(cache) or {}
        result["barrel_invalidation_summary"] = summary

        reps = ic.get_barrel_invalidation_reports(cache, root, changed_files=None) or []
        result["recent_reports"] = reps[: max(1, min(limit, 100)) ]

        if include_log:
            log = cache.get("_barrel_invalidation_log") or []
            # Return most recent first (log is append order)
            result["barrel_invalidation_log"] = list(reversed(log[-max(1, min(50, limit * 2)):])) if log else []
            result["log_count"] = len(log)
    except Exception as ex:
        result["note"] = f"barrel reports unavailable: {ex}"
    return result


@mcp.tool()
def suggest_next_actions(
    project_root: Optional[str] = None,
    directory: Optional[str] = None,
    format: Literal["text", "json"] = "text"
) -> str | dict:
    """Suggest high-value next actions based on current state.

    Light ACS + CIABRE integration (Gap #1 surfacing uniformity): when low-confidence edges present,
    includes actionable item referencing the on-demand _acs_summary (now guaranteed via ensure in get_project_status/health)
    + full Recommendations for auto low-conf filtering/prioritization by agents. Mirrors cycles/CIABRE patterns.
    """
    suggestions = []

    root = _get_effective_root(project_root)

    try:
        import wikifier.health as health_module
        summary = health_module.get_summary(root, directory)
        red = summary["red"]
        yellow = summary["yellow"]
    except Exception:
        health = _run_wikifier_command("health", root=root)
        red = health.count("🔴")
        yellow = health.count("🟡")

    if red > 0:
        suggestions.append(f"1. Tackle the {red} 🔴 Red file(s) first — they are highest priority.")
    if yellow > 0:
        suggestions.append(f"2. Review the {yellow} 🟡 Yellow files.")

    suggestions.append("3. Run `update_maps()` if structure or imports have changed.")
    suggestions.append("4. Use `get_dependents()` on core or frequently changed files.")
    suggestions.append("5. Review the journal for recent activity.")

    # Light ACS integration for auto low-conf filtering (Gap #1 ACS+CIABRE Surfacing Uniformity next wave).
    # Uses ensure_ for on-demand persistence guarantee so agents always see fresh aggregates + sample Recommendations.
    # High-value: surfaces actionable "review low conf" without requiring separate get_dependencies scan or library grep.
    try:
        import wikifier.import_cache as ic
        cache = ic.load_cache(root)
        acs = ic.ensure_acs_summary_persisted(cache, root)
        low = int(acs.get("low_conf_edges", 0) or 0)
        if low > 0:
            avg = acs.get("avg_confidence", 0)
            top_reasons = list((acs.get("top_risk_reasons") or {}).keys())[:2]
            reasons_str = f" top reasons: {', '.join(top_reasons)}" if top_reasons else ""
            sample = ""
            samples = acs.get("sample_low_conf_explanations") or []
            if samples:
                s0 = samples[0]
                # richer: quote a verbatim Recommendation snippet for immediate action (no extra call)
                if "Recommendation:" in s0:
                    rec_part = s0.split("Recommendation:", 1)[1].strip()[:120]
                    sample = f" e.g. Recommendation: {rec_part}"
            suggestions.append(
                f"6. Review {low} low-confidence dependency edge(s) (ACS avg={avg}; threshold 0.65{reasons_str}{sample}) — "
                f"see get_project_status() (ACS Risk Snapshot + samples) or get_dependencies(format=\"json\", low_confidence_only=True) for full "
                f"confidence_explanation Recommendations (quote verbatim). Use for filtering low-trust edges before refactors. "
                f"Cross with get_cycles(analysis=True) for CIABRE v1.3 recs on affected cycles."
            )
    except Exception:
        pass  # light: never break suggestions on ACS side-load

    if format == "json":
        return {
            "project_root": str(root),
            "directory": directory or ".",
            "red": red,
            "yellow": yellow,
            "suggestions": suggestions
        }

    return "\n".join(suggestions)


# =============================================================================
# Operational / Incremental Tools
# =============================================================================

@mcp.tool()
def get_incremental_status(project_root: Optional[str] = None) -> dict:
    """
    Returns the current state of the incremental update-maps system.
    Useful for debugging and understanding cache health on large projects.
    """
    root = _get_effective_root(project_root)
    cache_path = root / ".wikifier_staging/import_cache.json"
    last_update_path = root / ".wikifier_staging/.last_update_maps"

    try:
        import wikifier.import_cache as import_cache
        cache = import_cache.load_cache(root)
        cached_files = len(cache)
    except Exception:
        cached_files = -1

    last_update = "never"
    if last_update_path.exists():
        try:
            last_update = last_update_path.read_text().strip()
        except:
            last_update = "unreadable"

    return {
        "project_root": str(root),
        "import_cache_exists": cache_path.exists(),
        "cached_files": cached_files,
        "last_update_maps": last_update,
        "cache_path": str(cache_path)
    }


# =============================================================================
# Resources
# =============================================================================

@mcp.resource("wikifier://library")
def get_library() -> str:
    return _read_file_safe("library.md")


@mcp.resource("wikifier://health")
def get_health_matrix() -> str:
    return _read_file_safe("file_health.md")


@mcp.resource("wikifier://pending")
def get_pending_updates() -> str:
    return _read_file_safe("pending_updates.md")


@mcp.resource("wikifier://journal/{date}")
def get_journal(date: str) -> str:
    path = WIKIFIER_ROOT / "journal" / f"{date[:4]}/{date[5:7]}/{date}.md"
    return path.read_text(encoding="utf-8") if path.exists() else f"No journal entry found for {date}."


# =============================================================================
# Prompts
# =============================================================================

@mcp.prompt()
def review_pending_changes() -> str:
    return """You are reviewing pending changes in a Wikifier-managed project.

Recommended workflow:
1. Call `get_pending_updates()`
2. Call `get_files_needing_attention()`
3. For important files, use `get_file_wiki()` and `get_dependents()`
4. Use `record_change` + `mark_green` after updating documentation

Start by understanding the current state of the health matrix and pending queue."""


@mcp.prompt()
def audit_project_health() -> str:
    return """Perform a full documentation health audit.

Steps:
1. Get overall project status with `get_project_status()`
2. Identify all Red and Yellow files
3. Review recent journal activity
4. Suggest priority areas and next actions

Use `get_red_files()`, `get_yellow_files()`, `journal()`, and `suggest_next_actions()`."""


@mcp.prompt()
def plan_refactoring(target: str) -> str:
    return f"""You are planning a refactoring of '{target}'.

Before making changes (R2 ACS Explanations Maturity — canonical via contracts.compute_acs_confidence; excellent, consistent, decision-ready across scales):
1. Use `get_dependents("{target}")` for blast radius.
2. Use `get_dependencies("{target}", format="json")` (PRIMARY) — every edge carries:
   - confidence_score (0.05-0.95)
   - confidence_explanation (R2 authoritative: narrative + full "Recommendation: ..." — QUOTE VERBATIM in all decisions/reports)
   - confidence_reasons (filter: dev_only|dead_code_guard|cycle_participant|dynamic_expression|weak_resolution_strategy|complexity:opaque|complexity:high|barrel_depth=3+ )
   - conditional_analysis/dynamic_analysis (tags, detectors, trace evidence), resolution_metadata, strategy.
3. Decision rules (trust only these):
   - AUTO-SAFE (no manual review needed for most refactors): score >= 0.75 AND "strong strategy" in expl AND Recommendation starts with "High-fidelity static resolution via strong strategy. Safe for automated"
   - MANUAL-ONLY / REVIEW: Recommendation contains "Deep barrel", "Runtime conditional", "Moderate-to-high", or score in 0.55-0.74
   - AVOID / CRITICAL: Recommendation starts with "CRITICAL:", "Cycle participant", "Opaque or high-complexity", "Weak/fragile", or score < 0.55 or has dev_only/cycle/opaque reasons.
4. Always cross `get_cycles(analysis=True, format="json", use_canonical=True)` for participants (use severity/weakest_links + note reused/graph_signature for delta efficiency on unchanged topology).
5. Use `get_resolution_diagnostics`, library.md, `get_file_wiki`.

Return structured impact analysis. For EVERY edge quote the exact full Recommendation sentence from confidence_explanation + the triggering reasons. Explicitly flag all non-AUTO-SAFE cases."""


@mcp.prompt()
def find_architectural_smells() -> str:
    return """Analyze the project for architectural smells using dependency data (R2 ACS Explanations Maturity — canonical single-source compute_acs_confidence; trustworthy for autonomous agents on monorepos).

Look for:
- Highly coupled / god modules via dependents counts + get_dependencies.
- Circular risks: ALWAYS start with `get_cycles(analysis=True, format="json", use_canonical=True)` (Wave 4 default v1 canonical physical node ids for symlink-stable graphs/signatures; "reused": true + reuse_reason="graph_signature_match" signals O(1) delta short-circuit / no Tarjan work on unchanged topology, per gap1_cycles_longterm_strategy). Rank clusters by `severity` + `external_blast_radius` + weakest risk. For each high-priority, quote the *full* top `recommendations[0]` (strategy + rationale + hint + safety) — these are now high-quality, signal-specific, and actionable per R5 real-dogfood refinements.
- **Primary actionable smells = low/fragile ACS edges** (R2): Call `get_dependencies(..., format="json")`, filter where:
    confidence_score < 0.65 OR
    reasons contain any of: tag:dev_only, tag:dead_code_guard, cycle_participant, dynamic_expression, weak_resolution_strategy, complexity:opaque, complexity:high, barrel_depth>=3
  The `confidence_explanation` (R2) is ground-truth decision text — quote its *full* "Recommendation: ..." sentence verbatim for every reported smell. These are the exact files/edges to harden first.
- Fragility via conditional_analysis + dynamic_analysis (semantic_tags + analysis_trace evidence) + resolution_metadata.
- Deep barrel chains, weak/unknown strategies.

Use `get_project_status()`, `get_cycles`, `get_dependencies` (JSON for filters + full expls), `get_resolution_diagnostics`, library.md. For each smell, cite the exact Recommendation sentence + the exact triggering reasons/tags. Prioritize by severity of the Recommendation text (CRITICAL > Cycle > Opaque > Weak > Deep barrel)."""


@mcp.prompt()
def understand_codebase_structure() -> str:
    return """You are onboarding to this codebase.

Best first actions (R2 ACS Explanations Maturity):
1. Read `library.md` (rich sections + Mermaid)
2. Call `get_project_status()`
3. Identify most depended-on via Reverse Dependencies
4. For every key module: `get_dependencies(..., format="json")` — read *every* `confidence_explanation` (R2: full narrative + Recommendation sentence is the decision signal) + reasons + traces + conditional/dynamic_analysis. Use `get_dependents` + `get_cycles(analysis=True, use_canonical=True)` (reused signals cheap delta)

Start with `get_library()` + `get_dependents` on cores. Quote Recommendation sentences for any non-"High-fidelity Safe for automated" edges. Filter low-score in JSON for quick risk map. Use resolution diagnostics for strategy quality."""


@mcp.prompt()
def review_recent_changes(days: int = 7) -> str:
    return f"""Review the project activity and documentation debt over the last {days} days.

Recommended steps:
1. Read recent journal entries using the `journal` tool.
2. Identify files that received `record-change` entries.
3. Check whether those files have up-to-date wiki summaries ([GREEN] status).
4. Flag any areas where documentation has fallen behind recent work.

Provide a concise summary of recent changes and any documentation debt that should be addressed."""


@mcp.prompt()
def generate_project_health_report() -> str:
    return """Generate a clear, professional project documentation health report suitable for sharing with humans or other agents.

Include:
- Overall health summary (counts of Green/Yellow/Red files)
- Top files currently needing attention
- Most depended-on modules (from Reverse Dependencies)
- Areas with strong vs weak documentation
- Notable architectural risks (cycles via `get_cycles(analysis=True, use_canonical=True)` noting reused for delta efficiency, barrel/conditional smells via diagnostics + library sections)
- Actionable recommendations with priority

Use `get_project_status()`, `get_files_needing_attention()`, `get_library()`, `get_cycles(analysis=True)`, and the Reverse Dependencies section of library.md."""


@mcp.prompt()
def onboard_to_module(module_path: str) -> str:
    return f"""You are helping an agent deeply understand the module: **{module_path}**.

Recommended exploration order (R2 ACS Explanations Maturity — use canonical confidence_explanation as decision oracle):
1. Read its current wiki summary using `get_file_wiki("{module_path}")`
2. Use `get_dependencies("{module_path}", format="json")` — for EVERY outgoing edge read the full `confidence_explanation` (R2 narrative + exact "Recommendation: ..." sentence is primary) + `confidence_reasons` + `conditional_analysis`/`dynamic_analysis` traces + strategy. Filter in client for score<0.68 or high-sev reasons.
3. Use `get_dependents("{module_path}")` for blast radius.
4. `get_cycles(analysis=True, format="json", use_canonical=True)` (v1 default; reused field signals cheap delta short-circuit on graph_signature match per cycles long-term strategy + Wave 4 flip) + weakest links.
5. `get_resolution_diagnostics` + health.

Return structured onboarding: quote the full Recommendation sentence from each risky edge's confidence_explanation (CRITICAL/Cycle/Opaque/Deep barrel/Weak first); note dev_only/cycle/opaque/score<0.6 explicitly. Identify safe vs fragile outgoing deps using the exact rec text."""


# =============================================================================
# Main
# =============================================================================

def main():
    """Entry point for the Wikifier MCP server."""
    import argparse

    parser = argparse.ArgumentParser(description="Wikifier MCP Server")
    parser.add_argument(
        "--project-root",
        type=str,
        default=None,
        help="Target project directory (sets WIKIFIER_PROJECT_ROOT)"
    )
    args = parser.parse_args()

    if args.project_root:
        os.environ["WIKIFIER_PROJECT_ROOT"] = args.project_root

    # Re-discover root in case the env var was just set
    global WIKIFIER_ROOT
    WIKIFIER_ROOT = _discover_project_root()

    mcp.run()


if __name__ == "__main__":
    main()