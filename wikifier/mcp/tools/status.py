"""MCP Status Tools — unused by live server (server_impl is registered)."""

from __future__ import annotations

from typing import Literal, Optional

from ._common import *

def register_tools(mcp):
    """Register status tools with the MCP server instance."""
    
    @mcp.tool()
    def health(
        format: Optional[Literal["text", "json", "summary"]] = None,
        directory: Optional[str] = None,
        project_root: Optional[str] = None
    ) -> str | dict:
        """Get health matrix."""
        try:
            from wikifier import cli
            return cli.health(project_root=project_root, format=format)
        except Exception as e:
            if format == "json":
                return {"success": False, "error": str(e)}
            return f"Error: {e}"
    
    @mcp.tool()
    def get_files_needing_attention(
        directory: Optional[str] = None,
        project_root: Optional[str] = None
    ) -> dict:
        """Get files needing attention (Red/Yellow)."""
        return {"success": False, "error": "Not yet implemented"}
    
    @mcp.tool()
    def get_project_status(
        project_root: Optional[str] = None
    ) -> dict:
        """Get comprehensive project status."""
        return {"success": False, "error": "Not yet implemented"}
    
    @mcp.tool()
    def suggest_next_actions(
        directory: Optional[str] = None,
        project_root: Optional[str] = None,
        format: Literal["text", "json"] = "json"
    ) -> str | dict:
        """Suggest next actions."""
        try:
            from wikifier import cli
            return cli.suggest_next_actions(project_root=project_root, directory=directory, format=format)
        except Exception as e:
            if format == "json":
                return {"success": False, "error": str(e)}
            return f"Error: {e}"
    
    @mcp.tool()
    def get_incremental_status(project_root: Optional[str] = None) -> dict:
        """Get incremental update status."""
        return {"success": False, "error": "Not yet implemented"}
    
    @mcp.tool()
    def get_current_project_root(project_root: Optional[str] = None) -> str:
        """Get current project root."""
        root = _get_effective_root(project_root)
        return str(root)
