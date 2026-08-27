#!/usr/bin/env python3
"""
Wikifier CLI — thin dispatcher over wikifier.api + shell fallback.

Python-primary (this module): check-changes, record-change, mark-green,
  record-deletion, suggest-next, session-bootstrap, prepare-edit, why-file,
  search-journal, seed-source-hashes, validate, seed-health, prune-*,
  autonomous-status, cache-status, list-core-tools, health --summary|--json,
  update-maps.
Shell fallback (wikifier.sh via get_script_path): init, monitor, daemon,
  serve, journal, issues, heal-stubs, cycles, plain health matrix text.

Library functions live in wikifier.api and are re-exported here so
`from wikifier.cli import check_changes` keeps working.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Optional

from .api import (  # noqa: F401 — public re-exports
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

try:
    from . import health_pkg as _health_mod
except Exception:
    _health_mod = None


def main(argv=None) -> int:
    """CLI entry: Python-primary workflow commands, then shell fallback."""
    if argv is None:
        argv = sys.argv[1:]
    else:
        argv = list(argv)

    script_path = get_script_path()

    project_root = None
    use_canonical = True
    filtered_argv = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--target", "--project-root") and i + 1 < len(argv):
            project_root = argv[i + 1]
            i += 2
            continue
        if arg.startswith("--target="):
            project_root = arg.split("=", 1)[1]
            i += 1
            continue
        if arg.startswith("--project-root="):
            project_root = arg.split("=", 1)[1]
            i += 1
            continue
        if arg in ("--use-canonical", "--use_canonical"):
            use_canonical = True
            filtered_argv.append(arg)
        elif arg in ("--no-use-canonical", "--no_use_canonical", "--use-canonical=false"):
            use_canonical = False
            filtered_argv.append(arg)
        elif arg.startswith("--use-canonical="):
            val = arg.split("=", 1)[1].lower()
            use_canonical = val not in ("0", "false", "no")
            filtered_argv.append(arg)
        else:
            filtered_argv.append(arg)
        i += 1

    a2_flag_markers = (
        "--stream", "--stream=",
        "--resume", "--resume_token",
        "--max-time", "--max_time",
        "--progress",
        "--partial",
        "--format=stream",
    )
    has_a2_ux_flags = any(
        any(a == m or a.startswith(m) for m in a2_flag_markers) for a in filtered_argv
    )

    if project_root:
        os.environ["WIKIFIER_PROJECT_ROOT"] = project_root
    os.environ["WIKIFIER_USE_CANONICAL"] = "1" if use_canonical else "0"

    if filtered_argv and filtered_argv[0] == "health" and any(
        a in ("--summary", "--json") or a.startswith("--format") for a in filtered_argv[1:]
    ):
        fmt = "summary" if "--summary" in filtered_argv else ("json" if "--json" in filtered_argv else "summary")
        for a in filtered_argv[1:]:
            if a.startswith("--format="):
                fmt = a.split("=", 1)[1] or fmt
        try:
            out = health(project_root=project_root, format=fmt)
            print(json.dumps(out, indent=2, ensure_ascii=False) if isinstance(out, (dict, list)) else out)
            return 0
        except Exception as e:
            print(f"[wikifier] health --{fmt} failed: {e}", file=sys.stderr)
            return 1

    if filtered_argv:
        _cmd0 = filtered_argv[0].replace("_", "-")
        _args = filtered_argv[1:]
        try:
            if _cmd0 == "check-changes":
                res = check_changes(project_root=project_root)
                n = int(res.get("changes_detected") or 0)
                print("[wikifier] Running incremental change detection...")
                if n:
                    print(f"[wikifier] Detected {n} changed file(s). See pending_updates.md and file_health.md.")
                else:
                    print("[wikifier] No new changes detected.")
                if res.get("message"):
                    print(res["message"])
                return 0 if res.get("success", True) else 1
            if _cmd0 == "record-change":
                if not _args or _args[0] in ("--help", "-h", "help"):
                    print('Usage: wikifier record-change <file> "<reason>"')
                    return 0
                if _args[0].startswith("-") or len(_args) < 2:
                    print('Usage: wikifier record-change <file> "<reason>"', file=sys.stderr)
                    return 1
                res = record_change(_args[0], " ".join(_args[1:]), project_root=project_root)
                print(res.get("message") or res)
                return 0 if res.get("success") else 1
            if _cmd0 == "mark-green":
                if not _args or _args[0] in ("--help", "-h", "help"):
                    print("Usage: wikifier mark-green <file> [reason]")
                    return 0
                if _args[0].startswith("-"):
                    print("Usage: wikifier mark-green <file> [reason]", file=sys.stderr)
                    return 1
                reason = " ".join(_args[1:]) if len(_args) > 1 else ""
                res = mark_green(_args[0], reason, project_root=project_root)
                print(res.get("message") or res)
                return 0 if res.get("success") else 1
            if _cmd0 == "record-deletion":
                if not _args or _args[0] in ("--help", "-h", "help"):
                    print('Usage: wikifier record-deletion <file> "<reason>"')
                    return 0
                if _args[0].startswith("-"):
                    print(
                        'Usage: wikifier record-deletion <file> "<reason>"\n'
                        "  <file> must be a project path, not a flag.",
                        file=sys.stderr,
                    )
                    return 1
                reason = " ".join(_args[1:]) if len(_args) > 1 else "removed"
                res = record_deletion(_args[0], reason, project_root=project_root)
                print(res.get("message") or res)
                return 0 if res.get("success") else 1
            if _cmd0 in ("suggest-next", "suggest-next-actions", "suggest"):
                fmt = "text"
                for a in _args:
                    if a in ("--json", "--format=json"):
                        fmt = "json"
                res = suggest_next_actions(project_root=project_root, format=fmt)
                print(json.dumps(res, indent=2, default=str) if isinstance(res, dict) else res)
                return 0
            if _cmd0 in ("session-bootstrap", "session_bootstrap", "bootstrap", "session-start"):
                res = session_bootstrap(project_root=project_root)
                print(json.dumps(res, indent=2, default=str))
                return 0 if res.get("success") else 1
            if _cmd0 in ("cache-status", "cache_status", "cache-info", "cache"):
                res = cache_status(project_root=project_root)
                print(json.dumps(res, indent=2, default=str))
                return 0 if res.get("success") else 1
            if _cmd0 in ("prepare-edit", "prepare_edit", "lookup", "preflight"):
                if not _args:
                    print("Usage: wikifier prepare-edit <file>", file=sys.stderr)
                    return 1
                res = prepare_edit(_args[0], project_root=project_root)
                print(json.dumps(res, indent=2, default=str))
                return 0 if res.get("success") else 1
            if _cmd0 in ("search-journal", "search_journal", "journal-search"):
                q = None
                f = None
                i = 0
                while i < len(_args):
                    if _args[i] in ("--file", "-f") and i + 1 < len(_args):
                        f = _args[i + 1]
                        i += 2
                        continue
                    if _args[i] in ("--query", "-q") and i + 1 < len(_args):
                        q = _args[i + 1]
                        i += 2
                        continue
                    if q is None and not _args[i].startswith("-"):
                        q = _args[i]
                    i += 1
                res = search_journal(project_root=project_root, query=q, file=f)
                print(json.dumps(res, indent=2, default=str))
                return 0 if res.get("success") else 1
            if _cmd0 in ("why-file", "why_file", "why"):
                if not _args:
                    print("Usage: wikifier why-file <file>", file=sys.stderr)
                    return 1
                res = why_file(_args[0], project_root=project_root)
                print(json.dumps(res, indent=2, default=str))
                return 0 if res.get("success") else 1
            if _cmd0 in (
                "seed-source-hashes",
                "seed-source-content-hashes",
                "seed_source_content_hashes",
                "seed-hashes",
            ):
                force = any(a in ("--force", "-f") for a in _args)
                res = seed_source_content_hashes(project_root=project_root, force=force)
                print(json.dumps(res, indent=2, default=str))
                return 0 if res.get("success") else 1
            if _cmd0 in ("list-core-tools", "list_core_tools", "core-tools"):
                res = list_core_tools()
                print(json.dumps(res, indent=2, default=str))
                return 0
            if _cmd0 == "validate":
                if _health_mod is not None:
                    root = _get_effective_root(project_root)
                    res = _health_mod.validate_health(root)
                    print(json.dumps(res, indent=2, default=str))
                    return 0 if res.get("missing_count", 0) == 0 else 1
            if _cmd0 in ("seed-health", "seed-health-from-map"):
                if _health_mod is None:
                    print("[wikifier] health module unavailable", file=sys.stderr)
                    return 1
                root = _get_effective_root(project_root)
                res = _health_mod.seed_health_from_map(root)
                if hasattr(_health_mod, "seed_health_for_monitored_sources"):
                    disk = _health_mod.seed_health_for_monitored_sources(root)
                    res["disk_seeded"] = disk.get("seeded")
                    res["seeded_total"] = int(res.get("seeded") or 0) + int(disk.get("seeded") or 0)
                print(json.dumps(res, indent=2, default=str))
                return 0 if res.get("success") else 1
            if _cmd0 in ("prune-pending", "prune-pending-monitored"):
                if _health_mod is None:
                    print("[wikifier] health module unavailable", file=sys.stderr)
                    return 1
                root = _get_effective_root(project_root)
                res = _health_mod.prune_pending_to_monitored(root)
                print(json.dumps(res, indent=2, default=str))
                return 0 if res.get("success") else 1
            if _cmd0 in ("prune-health-monitored", "prune-health"):
                if _health_mod is None:
                    print("[wikifier] health module unavailable", file=sys.stderr)
                    return 1
                root = _get_effective_root(project_root)
                if any(a in ("--deleted-missing", "--deleted") for a in _args):
                    res = _health_mod.prune_deleted_missing(root)
                else:
                    res = _health_mod.prune_health_outside_monitored(root)
                print(json.dumps(res, indent=2, default=str))
                return 0 if res.get("success") else 1
            if _cmd0 in ("autonomous-status", "autonomous_status", "readiness", "long-horizon"):
                if _health_mod is None or not hasattr(_health_mod, "assess_autonomous_readiness"):
                    print("[wikifier] health.assess_autonomous_readiness unavailable", file=sys.stderr)
                    return 1
                root = _get_effective_root(project_root)
                res = _health_mod.assess_autonomous_readiness(root)
                print(json.dumps(res, indent=2, default=str))
                return 0 if res.get("readiness") != "blocked" else 2
            if _cmd0 in ("metrics-snapshot", "metrics_snapshot", "metrics"):
                if _health_mod is None or not hasattr(_health_mod, "write_metrics_snapshot"):
                    print("[wikifier] write_metrics_snapshot unavailable", file=sys.stderr)
                    return 1
                root = _get_effective_root(project_root)
                res = _health_mod.write_metrics_snapshot(root, source="cli")
                print(json.dumps(res, indent=2, default=str))
                return 0 if res.get("success") else 1
        except Exception as e:
            print(f"[wikifier] Python-primary {_cmd0} failed: {e}", file=sys.stderr)
            return 1

    if project_root:
        try:
            copy_human_dashboards(str(project_root))
        except Exception:
            pass

    python_primary_requested = True
    is_update_maps_cmd = False
    stripped_filtered = []
    for a in filtered_argv:
        if a in ("--python-primary", "--use-python-primary", "--python_primary"):
            python_primary_requested = True
            continue
        if a in ("--sh", "--legacy-sh", "--no-python-primary"):
            print(
                "[wikifier] note: --sh is a deprecated no-op — the legacy shell "
                "update-maps path was retired; the Python pipeline always runs.",
                file=sys.stderr,
            )
            continue
        if a in ("update-maps", "update_maps"):
            is_update_maps_cmd = True
        stripped_filtered.append(a)

    if python_primary_requested and is_update_maps_cmd:
        force_full = any(x in ("--full", "-f", "--force-full", "--full-rebuild") for x in argv)
        directory = None
        max_files = None
        for a in argv:
            if a.startswith("--dir=") or a.startswith("--directory="):
                directory = a.split("=", 1)[1] or None
            elif a.startswith("--max-files=") or a.startswith("--max_files="):
                try:
                    max_files = int(a.split("=", 1)[1])
                except ValueError:
                    pass
        if has_a2_ux_flags:
            print("[wikifier] A2 Python-primary streaming path (delegating to run_update_stream facade)")
            fmt = "summary" if any(a.startswith("--format=summary") for a in argv) else "full"
            try:
                from .import_cache import run_update_stream as _facade
                for event in _facade(
                    root=Path(project_root) if project_root else None,
                    force_full=force_full,
                    directory=directory,
                    max_files=max_files,
                    format=fmt,
                ):
                    if event.get("event_type") == "complete":
                        print(str(event))
            except Exception as e:
                print(f"[wikifier] Streaming delegation error (falling back): {e}")
            return 0
        try:
            res = run_full_update(
                root=Path(project_root) if project_root else None,
                force_full=force_full,
                verbose=True,
                use_canonical=use_canonical,
                use_python_primary=True,
                directory=directory,
                max_files=max_files,
            )
            print(json.dumps(res, indent=2, default=str))
            return 0 if res.get("success", False) else 1
        except Exception as e:
            print(f"[python-primary] direct run_full_update failed: {e}", file=sys.stderr)
            return 1

    if not script_path.exists():
        if not filtered_argv:
            print(
                "Wikifier — zero-dependency agent-to-agent codebase wiki.\n"
                "Commands: check-changes, record-change, mark-green, record-deletion,\n"
                "  prepare-edit, why-file, search-journal, session-bootstrap, suggest-next,\n"
                "  health --summary, update-maps, validate, cache-status, list-core-tools,\n"
                "  autonomous-status. Shell (init/monitor/daemon/serve/journal) needs wikifier.sh.",
                file=sys.stderr,
            )
            return 0
        print(f"Error: Could not find Wikifier script at {script_path}", file=sys.stderr)
        return 1

    system = platform.system().lower()
    if system == "windows":
        if script_path.suffix == ".ps1":
            cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path)] + stripped_filtered
        else:
            cmd = [str(script_path)] + stripped_filtered
    else:
        cmd = [str(script_path)] + stripped_filtered

    try:
        result = subprocess.run(cmd, check=False, env=os.environ.copy())
        return int(result.returncode)
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        print(f"Failed to launch Wikifier: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
