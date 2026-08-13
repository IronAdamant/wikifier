"""MCP Workflow Tools — Core daily workflow (check/record/mark/update).

Signatures match wikifier.api / Agent Protocol v0.6 (no invented format= kwargs).
"""

from __future__ import annotations

from typing import Literal, Optional


def register_tools(mcp):
    """Register workflow tools with the MCP server instance."""

    @mcp.tool()
    def check_changes(project_root: Optional[str] = None) -> dict:
        """Check for dirty/stale files needing attention (content-honest)."""
        try:
            from wikifier.api import check_changes as _fn
            return _fn(project_root=project_root)
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def record_change(file: str, reason: str, project_root: Optional[str] = None) -> dict:
        """Record meaningful file change (mandatory after edits)."""
        try:
            from wikifier.api import record_change as _fn
            return _fn(file, reason, project_root=project_root)
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def record_deletion(file: str, reason: str, project_root: Optional[str] = None) -> dict:
        """Record file deletion."""
        try:
            from wikifier.api import record_deletion as _fn
            return _fn(file, reason, project_root=project_root)
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def mark_green(file: str, reason: str = "", project_root: Optional[str] = None) -> dict:
        """Mark file as green (wiki verified accurate)."""
        try:
            from wikifier.api import mark_green as _fn
            return _fn(file, reason, project_root=project_root)
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def prepare_edit(file: str, project_root: Optional[str] = None) -> dict:
        """Get file context before editing (wiki/deps/dependents)."""
        try:
            from wikifier.api import prepare_edit as _fn
            return _fn(file, project_root=project_root)
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def session_bootstrap(
        project_root: Optional[str] = None,
        directory: Optional[str] = None,
    ) -> dict:
        """Bootstrap session (one-shot status + dispatchable actions)."""
        try:
            from wikifier.api import session_bootstrap as _fn
            return _fn(project_root=project_root, directory=directory)
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def search_journal(
        query: Optional[str] = None,
        project_root: Optional[str] = None,
        file: Optional[str] = None,
        max_results: int = 20,
    ) -> dict:
        """Search journal entries."""
        try:
            from wikifier.api import search_journal as _fn
            return _fn(project_root=project_root, query=query, file=file, max_results=max_results)
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def why_file(
        file: str,
        project_root: Optional[str] = None,
        max_results: int = 10,
    ) -> dict:
        """Get file change history/rationale."""
        try:
            from wikifier.api import why_file as _fn
            return _fn(file, project_root=project_root, max_results=max_results)
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def seed_source_content_hashes(
        project_root: Optional[str] = None,
        only_green: bool = True,
        force: bool = False,
        directory: Optional[str] = None,
    ) -> dict:
        """Seed content hashes for existing green files."""
        try:
            from wikifier.api import seed_source_content_hashes as _fn
            return _fn(
                project_root=project_root,
                only_green=only_green,
                force=force,
                directory=directory,
            )
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def list_core_tools() -> dict:
        """List core daily tools."""
        try:
            from wikifier.api import list_core_tools as _fn
            return _fn()
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def update_maps(
        full: bool = False,
        directory: Optional[str] = None,
        max_files: Optional[int] = None,
        project_root: Optional[str] = None,
        use_python_primary: bool = True,
    ) -> dict:
        """Rebuild dependency map."""
        try:
            from wikifier.api import update_maps as _fn
            return _fn(
                project_root=project_root,
                full=full,
                directory=directory,
                max_files=max_files,
                use_python_primary=use_python_primary,
            )
        except Exception as e:
            return {"success": False, "error": str(e)}
