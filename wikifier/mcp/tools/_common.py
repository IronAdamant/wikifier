"""
Wikifier MCP server — agent-to-agent wiki (optional `pip install wikifier[mcp]`).

AGENT MAP — Core daily surface (start here every session):
  1. session_bootstrap      — one-shot root + health + attention + dispatchable actions
  2. check_changes          — content-honest dirty / ghosts → yellow/red
  3. prepare_edit           — single-file preflight (wiki/status/deps/dependents)
  4. suggest_next_actions   — structured actions[] + selective prose (never full-tree re-wiki)
  5. record_change          — semantic why (mandatory after edits)
  6. mark_green             — trust baseline (captures source content hash)

Also useful core: get_file_wiki, why_file, search_journal, get_files_needing_attention

Advanced intel (non-core): get_dependencies, get_dependents, get_cycles, get_barrel_reports,
  get_resolution_diagnostics, health(format=json) full intel
Always pass project_root= for external trees. Deep import maps: Python + JS/TS.
Run: WIKIFIER_PROJECT_ROOT=/path wikifier-mcp  |  python -m wikifier.mcp.server
"""

try:
    from mcp.server.fastmcp import FastMCP
    from pydantic import BaseModel, Field
except ImportError as _e:
    raise ImportError(
        "The Wikifier MCP server requires the optional 'mcp' dependency. "
        "Install it with: pip install wikifier[mcp]. "
        "The core wikifier CLI and library work without it."
    ) from _e
import subprocess
import re
import os
import sys
from pathlib import Path
from typing import Literal, Optional, List, Dict, Any
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

    A2 early (Partial Results & UX Scaffolding): added directory + max_files passthrough
    to python-primary path for subtree scoping + budget. Result now carries partial,
    scope, progress, partial_reason, continuation_hint etc. when python-primary used
    (enables trustworthy partial results even on interrupt/budget/scoped runs).
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
    # A2 early partial/scoping UX (populated in python-primary path; defaults for sh path)
    partial: bool = False
    partial_reason: Optional[str] = None
    scope: Optional[Dict[str, Any]] = None
    progress: Optional[Dict[str, Any]] = None
    continuation_hint: Optional[str] = None


# =============================================================================
# Helper Functions
# =============================================================================

