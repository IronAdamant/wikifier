#!/usr/bin/env python3
"""
Wikifier CLI - thin argparse wrapper around wikifier.api

This module provides the command-line interface. All library functionality
has been moved to wikifier.api for clean separation of concerns.
"""

import argparse
import json
import sys
from pathlib import Path

# Import all library functions from api
from .api import (
    discover_project_root,
    run_full_update,
    check_changes,
    record_change,
    record_deletion,
    mark_green,
    suggest_next_actions,
    session_bootstrap,
    prepare_edit,
    search_journal,
    why_file,
    seed_source_content_hashes,
    list_core_tools,
    cache_status,
    update_maps,
    health,
    copy_human_dashboards,
    get_script_path,
    _get_effective_root,
)


def main():
    """CLI entry point with argparse."""
    parser = argparse.ArgumentParser(
        prog="wikifier",
        description="Zero-dependency agent-to-agent codebase wiki",
    )
    parser.add_argument("--target", "--project-root", dest="project_root", help="Project root path")
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # update-maps
    p_update = subparsers.add_parser("update-maps", help="Rebuild dependency map")
    p_update.add_argument("--full", action="store_true", help="Force full rebuild")
    p_update.add_argument("--directory", help="Limit to directory")
    p_update.add_argument("--max-files", type=int, help="Limit number of files")
    
    # check-changes
    subparsers.add_parser("check-changes", help="Check for dirty files")
    
    # record-change
    p_record = subparsers.add_parser("record-change", help="Record file change")
    p_record.add_argument("file", help="File path")
    p_record.add_argument("reason", help="Change reason")
    
    # mark-green
    p_green = subparsers.add_parser("mark-green", help="Mark file as green")
    p_green.add_argument("file", help="File path")
    p_green.add_argument("reason", nargs="?", default="", help="Reason")
    
    # suggest-next
    p_suggest = subparsers.add_parser("suggest-next", help="Suggest next actions")
    p_suggest.add_argument("--json", action="store_true", help="JSON output")
    
    # session-bootstrap
    subparsers.add_parser("session-bootstrap", help="Bootstrap session")
    
    # health
    p_health = subparsers.add_parser("health", help="Health summary")
    p_health.add_argument("--summary", action="store_true", help="Summary only")
    p_health.add_argument("--json", action="store_true", help="JSON output")
    
    # Other commands
    subparsers.add_parser("cache-status", help="Cache status")
    subparsers.add_parser("list-core-tools", help="List core tools")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 0
    
    try:
        root = args.project_root if hasattr(args, "project_root") and args.project_root else None
        
        if args.command == "update-maps":
            result = update_maps(
                project_root=root,
                full=getattr(args, "full", False),
                directory=getattr(args, "directory", None),
                max_files=getattr(args, "max_files", None),
            )
            print(json.dumps(result, indent=2))
            return 0 if result.get("success") else 1
            
        elif args.command == "check-changes":
            result = check_changes(project_root=root)
            print(json.dumps(result, indent=2))
            return 0
            
        elif args.command == "record-change":
            result = record_change(args.file, args.reason, project_root=root)
            print(json.dumps(result, indent=2))
            return 0 if result.get("success") else 1
            
        elif args.command == "mark-green":
            result = mark_green(args.file, args.reason, project_root=root)
            print(json.dumps(result, indent=2))
            return 0 if result.get("success") else 1
            
        elif args.command == "suggest-next":
            fmt = "json" if getattr(args, "json", False) else "text"
            result = suggest_next_actions(project_root=root, format=fmt)
            if isinstance(result, dict):
                print(json.dumps(result, indent=2))
            else:
                print(result)
            return 0
            
        elif args.command == "session-bootstrap":
            result = session_bootstrap(project_root=root)
            print(json.dumps(result, indent=2))
            return 0
            
        elif args.command == "health":
            fmt = None
            if getattr(args, "json", False):
                fmt = "json"
            elif getattr(args, "summary", False):
                fmt = "summary"
            result = health(project_root=root, format=fmt)
            if isinstance(result, dict):
                print(json.dumps(result, indent=2))
            else:
                print(result)
            return 0
            
        elif args.command == "cache-status":
            result = cache_status(project_root=root)
            print(json.dumps(result, indent=2))
            return 0
            
        elif args.command == "list-core-tools":
            result = list_core_tools()
            print(json.dumps(result, indent=2))
            return 0
            
        else:
            print(f"Unknown command: {args.command}")
            return 1
            
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
