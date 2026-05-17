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
from pathlib import Path
from typing import Literal, Optional, List
from datetime import datetime

mcp = FastMCP("Wikifier")


def _discover_project_root() -> Path:
    """
    Determine the target project root for this Wikifier MCP instance.

    This function has been hardened for reliable multi-project use in
    environments like Grok Build, Claude Desktop, Cursor, etc.

    Priority order:
    1. WIKIFIER_PROJECT_ROOT environment variable (highest priority)
    2. Walk upward from CWD looking for Wikifier markers
       (monitored_paths.txt or .wikifier/ directory)
    3. If running inside a project that has a .mcp.json with Wikifier config, use that project
    4. Fall back to the directory containing the installed Wikifier package
    """
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
    # This helps when Grok Build / other hosts connect the MCP to a specific project
    for parent in [cwd] + list(cwd.parents):
        mcp_config = parent / ".mcp.json"
        if mcp_config.exists():
            try:
                import json
                with open(mcp_config) as f:
                    config = json.load(f)
                # If this project has a wikifier entry in its MCP config, treat it as the target
                if "wikifier" in config.get("mcpServers", {}):
                    return parent
            except Exception:
                pass

    # 4. Final fallback: the package installation directory
    package_root = Path(__file__).parent.parent.parent.resolve()
    return package_root


WIKIFIER_ROOT = _discover_project_root()


def _get_effective_root(project_root: Optional[str] = None) -> Path:
    """
    Resolve the project root to use for a given operation.

    Resolution order (highest to lowest priority):
    1. Explicit `project_root` parameter passed to the tool
    2. WIKIFIER_PROJECT_ROOT environment variable
    3. Auto-discovered root (from CWD walk or package fallback)
    """
    if project_root:
        p = Path(project_root).expanduser().resolve()
        if p.exists():
            return p
        # If the provided path doesn't exist, fall back gracefully

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
    """Structured result from running update_maps."""
    success: bool
    project_root: str
    full_rebuild: bool
    files_analyzed: int
    edges_drawn: int
    duration_seconds: Optional[float] = None
    message: str
    incremental: bool = True  # whether it used the cache or was a full rebuild


# =============================================================================
# Helper Functions
# =============================================================================

def _run_wikifier_command(cmd: str, args: list[str] | None = None, check: bool = True, root: Optional[Path] = None) -> str:
    """
    Run a wikifier.sh command against a specific project root (final robustness polish).

    Better error messages and graceful degradation for MCP clients.
    """
    root = root or WIKIFIER_ROOT
    args = args or []
    full_cmd = ["./wikifier.sh", cmd] + args

    try:
        result = subprocess.run(
            full_cmd,
            cwd=root,
            capture_output=True,
            text=True,
            check=check,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        error_msg = (e.stderr or "").strip() or str(e)
        if check:
            raise RuntimeError(f"Wikifier command '{cmd}' failed on {root}: {error_msg}")
        return f"Error: {error_msg}"
    except FileNotFoundError:
        raise RuntimeError(f"Wikifier command failed: wikifier.sh not found in project root {root}")
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
    Returns richer objects with raw + resolved + confidence (Fix 9 polishing).
    """
    try:
        import wikifier.import_cache as import_cache
        cache = import_cache.load_cache(root)
        data = cache.get(file, {})
        pairs = data.get("resolved_pairs", [])
        if pairs:
            return [
                {
                    "raw": p.get("raw"),
                    "resolved": p.get("resolved"),
                    "confidence": p.get("confidence", "medium")
                }
                for p in pairs if p.get("resolved")
            ]
        # Fallback to flat list
        resolved = data.get("resolved", [])
        return [{"raw": None, "resolved": r, "confidence": "medium"} for r in resolved]
    except Exception:
        return []


# =============================================================================
# Core Tools
# =============================================================================

@mcp.tool()
def check_changes(project_root: Optional[str] = None) -> dict:
    """
    Scan for file changes and update the health matrix.

    Returns structured information about what was detected.
    Now supports targeting any project via project_root.
    """
    root = _get_effective_root(project_root)
    try:
        output = _run_wikifier_command("check-changes", root=root)
        # Try to extract how many files changed
        changed = 0
        for line in output.splitlines():
            if "Detected" in line and "changed" in line:
                try:
                    changed = int(line.split()[1])
                except:
                    pass
        return {
            "success": True,
            "project_root": str(root),
            "changes_detected": changed,
            "message": output,
            "recommendation": "Read file_health.md and pending_updates.md, then prioritize Red → Yellow files."
        }
    except Exception as e:
        return {
            "success": False,
            "project_root": str(root),
            "error": str(e)
        }


@mcp.tool()
def record_change(file: str, reason: str, project_root: Optional[str] = None) -> dict:
    """Record a semantic change. Required after edits. Returns structured result."""
    root = _get_effective_root(project_root)
    try:
        output = _run_wikifier_command("record-change", [file, reason], root=root)
        return {
            "success": True,
            "file": file,
            "message": output,
            "project_root": str(root)
        }
    except Exception as e:
        return {
            "success": False,
            "file": file,
            "error": str(e),
            "project_root": str(root)
        }


@mcp.tool()
def record_deletion(file: str, reason: str, project_root: Optional[str] = None) -> dict:
    """Record the deletion of a file with a reason. Returns structured result (final robustness)."""
    root = _get_effective_root(project_root)
    try:
        output = _run_wikifier_command("record-deletion", [file, reason], root=root)
        return {
            "success": True,
            "file": file,
            "action": "deletion",
            "message": output,
            "project_root": str(root)
        }
    except Exception as e:
        return {
            "success": False,
            "file": file,
            "error": str(e),
            "project_root": str(root)
        }


@mcp.tool()
def mark_green(file: str, reason: str = "", project_root: Optional[str] = None) -> dict:
    """Mark a file as Green after updating its wiki summary. Returns structured result."""
    root = _get_effective_root(project_root)
    args = [file, reason] if reason else [file]
    try:
        output = _run_wikifier_command("mark-green", args, root=root)
        return {
            "success": True,
            "file": file,
            "message": output,
            "project_root": str(root)
        }
    except Exception as e:
        return {
            "success": False,
            "file": file,
            "error": str(e),
            "project_root": str(root)
        }


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
def update_maps(project_root: Optional[str] = None, full: bool = False) -> UpdateMapsResult:
    """Rebuild library.md with fresh dependency analysis for the target project.

    Returns structured data including whether it was incremental and basic stats.
    """
    root = _get_effective_root(project_root)
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
        incremental=not full
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
            return {
                "project_root": str(root),
                "directory": directory or ".",
                "total_files": len(entries),
                "entries": entries
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
def get_dependencies(file: str, format: Literal["text", "json"] = "text", project_root: Optional[str] = None) -> str | dict:
    """
    Get what a file imports (forward dependencies).
    Returns either human-readable text or structured JSON.
    Prefers the rich import_cache data (with confidence) when available.
    """
    root = _get_effective_root(project_root)

    # Preferred path: rich data from import cache (now includes confidence)
    cached = _get_resolved_from_cache(file, root)
    if cached:
        if format == "json":
            return {
                "file": file,
                "imports": cached,           # list of {raw, resolved, confidence}
                "count": len(cached),
                "source": "cache"
            }
        resolved_list = [item.get("resolved") for item in cached if item.get("resolved")]
        return f"{file} imports ({len(resolved_list)}):\n" + ", ".join(resolved_list)

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
            return {
                "project_root": str(root),
                "directory": directory or ".",
                "status_filter": status,
                "files": files,
                "count": len(files)
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

        if format == "json":
            return ProjectHealthSummary(
                total_files=summary["total"],
                green=summary["green"],
                yellow=summary["yellow"],
                red=summary["red"],
                pending_updates=pending_count,
                health_score="Good" if summary["red"] == 0 and summary["yellow"] < 5 else "Needs Attention" if summary["red"] < 3 else "Critical"
            )

        dir_str = f" (in {directory})" if directory else ""
        return f"""Project Documentation Health{dir_str}
-----------------------------
[GREEN] Green:   {summary['green']}
[YELLOW] Yellow:  {summary['yellow']}
[RED] Red:     {summary['red']}

Pending updates: {pending_count}

Use get_files_needing_attention() for the actual list."""

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
def suggest_next_actions(
    project_root: Optional[str] = None,
    directory: Optional[str] = None,
    format: Literal["text", "json"] = "text"
) -> str | dict:
    """Suggest high-value next actions based on current state."""
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

Before making changes:
1. Use `get_dependents("{target}")` to understand impact
2. Use `get_dependencies("{target}")` to see what it relies on
3. Check the current wiki summary with `get_file_wiki("{target}")`
4. Consider running `prepare_edit("{target}")` before starting

Return a clear impact analysis and recommended approach."""


@mcp.prompt()
def find_architectural_smells() -> str:
    return """Analyze the project for architectural smells using dependency data.

Look for:
- Highly coupled modules (high number of dependents + dependencies)
- God files (very high number of dependents)
- Circular dependency risks
- Abandoned or poorly documented core modules

Use `get_project_status()`, `get_dependents()` on core files, and review `library.md`."""


@mcp.prompt()
def understand_codebase_structure() -> str:
    return """You are onboarding to this codebase.

Best first actions:
1. Read `library.md` (especially the dependency graph)
2. Call `get_project_status()`
3. Identify the most depended-on files using the Reverse Dependencies section
4. Explore the dependency graph of the most important modules

Start with `get_library()` and `get_dependents()` on key files."""


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
- Actionable recommendations with priority

Use `get_project_status()`, `get_files_needing_attention()`, and the Reverse Dependencies section."""


@mcp.prompt()
def onboard_to_module(module_path: str) -> str:
    return f"""You are helping an agent deeply understand the module: **{module_path}**.

Recommended exploration order:
1. Read its current wiki summary using `get_file_wiki("{module_path}")`
2. Understand what it depends on using `get_dependencies("{module_path}")`
3. Understand what depends on it using `get_dependents("{module_path}")`
4. Review its health status
5. Identify related modules that are also poorly documented

Return a structured onboarding summary for this module."""


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