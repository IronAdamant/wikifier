"""MCP Workflow Tools - Core daily workflow (check/record/mark/update)."""

from ._common import *

def register_tools(mcp):
    """Register workflow tools with the MCP server instance."""
    
    @mcp.tool()
    def check_changes(project_root: Optional[str] = None) -> dict:
        """Check for dirty/stale files needing attention (content-honest)."""
        try:
            from wikifier import cli
            return cli.check_changes(project_root=project_root)
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @mcp.tool()
    def record_change(file: str, reason: str, project_root: Optional[str] = None) -> dict:
        """Record meaningful file change (mandatory after edits)."""
        try:
            from wikifier import cli
            return cli.record_change(file, reason, project_root=project_root)
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @mcp.tool()
    def record_deletion(file: str, reason: str, project_root: Optional[str] = None) -> dict:
        """Record file deletion."""
        try:
            from wikifier import cli
            return cli.record_deletion(file, reason, project_root=project_root)
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @mcp.tool()
    def mark_green(file: str, reason: str = "", project_root: Optional[str] = None) -> dict:
        """Mark file as green (wiki verified accurate)."""
        try:
            from wikifier import cli
            return cli.mark_green(file, reason, project_root=project_root)
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @mcp.tool()
    def prepare_edit(file: str, project_root: Optional[str] = None) -> dict:
        """Get file context before editing (wiki/deps/dependents)."""
        try:
            from wikifier import cli
            return cli.prepare_edit(file, project_root=project_root)
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @mcp.tool()
    def session_bootstrap(
        project_root: Optional[str] = None,
        format: Literal["text", "json"] = "json"
    ) -> str | dict:
        """Bootstrap session (one-shot status + dispatchable actions)."""
        try:
            from wikifier import cli
            return cli.session_bootstrap(project_root=project_root, format=format)
        except Exception as e:
            if format == "json":
                return {"success": False, "error": str(e)}
            return f"Error: {e}"
    
    @mcp.tool()
    def search_journal(
        query: str,
        project_root: Optional[str] = None,
        format: Literal["text", "json"] = "json"
    ) -> str | dict:
        """Search journal entries."""
        try:
            from wikifier import cli
            return cli.search_journal(query, project_root=project_root, format=format)
        except Exception as e:
            if format == "json":
                return {"success": False, "error": str(e)}
            return f"Error: {e}"
    
    @mcp.tool()
    def why_file(
        file: str,
        project_root: Optional[str] = None,
        format: Literal["text", "json"] = "json"
    ) -> str | dict:
        """Get file change history/rationale."""
        try:
            from wikifier import cli
            return cli.why_file(file, project_root=project_root, format=format)
        except Exception as e:
            if format == "json":
                return {"success": False, "error": str(e)}
            return f"Error: {e}"
    
    @mcp.tool()
    def seed_source_content_hashes(
        project_root: Optional[str] = None,
        format: Literal["text", "json"] = "json"
    ) -> str | dict:
        """Seed content hashes for existing green files."""
        try:
            from wikifier import cli
            return cli.seed_source_content_hashes(project_root=project_root, format=format)
        except Exception as e:
            if format == "json":
                return {"success": False, "error": str(e)}
            return f"Error: {e}"
    
    @mcp.tool()
    def list_core_tools() -> dict:
        """List core daily tools."""
        try:
            from wikifier import cli
            return cli.list_core_tools()
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
            from wikifier import cli
            return cli.update_maps(
                project_root=project_root,
                full=full,
                directory=directory,
                max_files=max_files,
                use_python_primary=use_python_primary
            )
        except Exception as e:
            return {"success": False, "error": str(e)}
