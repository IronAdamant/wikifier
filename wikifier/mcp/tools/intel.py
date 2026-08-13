"""MCP Intel Tools — unused by live server (server_impl is registered)."""

from __future__ import annotations

from typing import Literal, Optional

from ._common import *

def register_tools(mcp):
    """Register intel tools with the MCP server instance."""
    
    @mcp.tool()
    def get_dependencies(
        file: str,
        format: Literal["text", "json"] = "text",
        project_root: Optional[str] = None,
        low_confidence_only: bool = False,
        unresolved_only: bool = False
    ) -> str | dict:
        """Get file dependencies."""
        # Placeholder - full implementation would be extracted from server_backup.py
        return {"success": False, "error": "Not yet implemented"}
    
    @mcp.tool()
    def get_dependents(
        file: str,
        format: Literal["text", "json"] = "text",
        project_root: Optional[str] = None
    ) -> str | dict:
        """Get files that depend on this file."""
        return {"success": False, "error": "Not yet implemented"}
    
    @mcp.tool()
    def get_cycles(
        format: Literal["text", "json"] = "text",
        project_root: Optional[str] = None
    ) -> str | dict:
        """Get circular dependencies."""
        return {"success": False, "error": "Not yet implemented"}
    
    @mcp.tool()
    def get_resolution_diagnostics(
        format: Literal["text", "json"] = "text",
        project_root: Optional[str] = None
    ) -> str | dict:
        """Get resolution diagnostics."""
        return {"success": False, "error": "Not yet implemented"}
    
    @mcp.tool()
    def get_file_wiki(
        file: str,
        format: Literal["text", "json"] = "text",
        project_root: Optional[str] = None
    ) -> str | dict:
        """Get file wiki content."""
        return {"success": False, "error": "Not yet implemented"}
    
    @mcp.tool()
    def get_barrel_reports(
        format: Literal["text", "json"] = "text",
        project_root: Optional[str] = None
    ) -> str | dict:
        """Get barrel re-export reports."""
        return {"success": False, "error": "Not yet implemented"}
