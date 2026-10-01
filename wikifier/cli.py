"""
Wikifier command-line interface (``wikifier`` / ``python -m wikifier``).

Every command is implemented in Python; the shell/PowerShell/batch launchers
only exec ``python -m wikifier``. Library functions live in :mod:`wikifier.api`
and are re-exported here so ``from wikifier.cli import check_changes`` works.

Global options (accepted anywhere on the command line):
  --target DIR / --project-root DIR   operate on DIR (must exist)
  --use-canonical / --no-use-canonical
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, List, Optional, Tuple

from . import __version__
from . import health_pkg as health_mod
from .api import (  # noqa: F401 — public re-exports
    _get_effective_root,
    cache_status,
    check_changes,
    copy_human_dashboards,
    cycles_report,
    discover_project_root,
    format_cycles_report,
    get_dependencies,
    get_dependents,
    heal_stubs,
    health,
    init_project,
    issues,
    journal,
    list_core_tools,
    list_paths,
    mark_green,
    prepare_edit,
    record_change,
    record_changes,
    record_deletion,
    run_full_update,
    search_journal,
    seed_source_content_hashes,
    session_bootstrap,
    suggest_next_actions,
    update_maps,
    verify_wikis,
    why_file,
)
from .paths import ProjectRootError, resolve_root

EPILOG = """\
Workflow (agents / new sessions):
  1. wikifier session-bootstrap           (or check-changes)
  2. work 🔴 Red → actionable 🟡 Yellow only
  3. after editing:     wikifier record-change path/to/file "why"
     (many files:       wikifier record-changes -r "src/api.py=why" -r "tests/=why" --green)
  4. after wiki update: wikifier mark-green path/to/file
  5. imports changed:   wikifier update-maps

Configuration (project root):
  monitored_paths.txt   wiki/health watch list (lean roots; files or dirs)
  map_paths.txt         import-map package roots (independent of monitored_paths)
  exclude_patterns.txt  names/globs to skip (node_modules, dist, …)
"""


def _print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def _exit_code(res: Any) -> int:
    return 0 if not isinstance(res, dict) or res.get("success", True) else 1


def _extract_global_options(argv: List[str]) -> Tuple[List[str], Optional[str], Optional[bool]]:
    """Pull --target/--project-root and canonical flags out of argv (any position)."""
    rest: List[str] = []
    project_root: Optional[str] = None
    use_canonical: Optional[bool] = None
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--target", "--project-root") and i + 1 < len(argv):
            project_root = argv[i + 1]
            i += 2
            continue
        if arg.startswith(("--target=", "--project-root=")):
            project_root = arg.split("=", 1)[1]
        elif arg in ("--use-canonical", "--use_canonical"):
            use_canonical = True
        elif arg in ("--no-use-canonical", "--no_use_canonical"):
            use_canonical = False
        elif arg.startswith("--use-canonical="):
            use_canonical = arg.split("=", 1)[1].lower() not in ("0", "false", "no")
        else:
            rest.append(arg)
        i += 1
    return rest, project_root, use_canonical


# ---------------------------------------------------------------------------
# Command handlers: each receives (args, project_root) and returns an exit code
# ---------------------------------------------------------------------------

def _cmd_check_changes(args, root):
    res = check_changes(project_root=root)
    if args.json:
        _print_json(res)
    else:
        print(res.get("message") or res.get("error"))
    return _exit_code(res)


def _cmd_record_change(args, root):
    res = record_change(args.file, " ".join(args.reason), project_root=root)
    print(res.get("message") or f"error: {res.get('error')}")
    return _exit_code(res)


def _cmd_mark_green(args, root):
    res = mark_green(args.file, " ".join(args.reason), project_root=root, force=args.force)
    if args.json:
        _print_json(res)
        return _exit_code(res)
    print(res.get("message") or f"error: {res.get('error')}")
    for issue in res.get("issues") or []:
        print(f"  - {issue['message']}")
    for warning in res.get("warnings") or []:
        print(f"  (warning) {warning['message']}")
    if res.get("hint"):
        print(res["hint"])
    return _exit_code(res)


def _load_reasons(args) -> dict:
    reasons: dict = {}
    if args.reasons:
        text = sys.stdin.read() if args.reasons == "-" else Path(args.reasons).read_text(encoding="utf-8")
        loaded = json.loads(text)
        if not isinstance(loaded, dict):
            raise ValueError("--reasons must be a JSON object mapping path or glob to reason")
        reasons.update(loaded)
    for item in args.reason:
        pattern, sep, why = item.partition("=")
        if not sep:
            raise ValueError(f"--reason expects PATH=REASON, got: {item}")
        reasons[pattern.strip()] = why.strip()
    return reasons


def _cmd_record_changes(args, root):
    try:
        reasons = _load_reasons(args)
    except (OSError, ValueError) as exc:  # json.JSONDecodeError is a ValueError
        _print_json({"success": False, "error": str(exc), "error_type": type(exc).__name__})
        return 1
    res = record_changes(reasons, default_reason=args.default_reason, since=args.since,
                         green=args.green, dry_run=args.dry_run, project_root=root, only=args.only or None)
    _print_json(res)
    return _exit_code(res)


def _cmd_verify_wikis(args, root):
    res = verify_wikis(project_root=root, directory=args.directory, limit=args.limit)
    _print_json(res)
    return 1 if res.get("failing_count") else _exit_code(res)


def _cmd_record_deletion(args, root):
    res = record_deletion(args.file, " ".join(args.reason) or "removed", project_root=root)
    print(res.get("message") or f"error: {res.get('error')}")
    return _exit_code(res)


def _cmd_suggest(args, root):
    as_json = args.json or args.format == "json"
    res = suggest_next_actions(project_root=root, directory=args.directory, format="json" if as_json else "text")
    if isinstance(res, dict):
        _print_json(res)
    else:
        print(res)
    return _exit_code(res)


def _cmd_bootstrap(args, root):
    res = session_bootstrap(project_root=root, directory=args.directory)
    _print_json(res)
    return _exit_code(res)


def _cmd_cache_status(args, root):
    res = cache_status(project_root=root)
    _print_json(res)
    return _exit_code(res)


def _cmd_prepare_edit(args, root):
    res = prepare_edit(args.file, project_root=root)
    _print_json(res)
    return _exit_code(res)


def _cmd_search_journal(args, root):
    res = search_journal(project_root=root, query=args.query or args.text, file=args.file, max_results=args.limit)
    _print_json(res)
    return _exit_code(res)


def _cmd_why_file(args, root):
    res = why_file(args.file, project_root=root)
    _print_json(res)
    return _exit_code(res)


def _cmd_dependencies(args, root):
    res = get_dependencies(args.file, project_root=root, detail="full" if args.full else "compact")
    _print_json(res)
    return _exit_code(res)


def _cmd_dependents(args, root):
    res = get_dependents(args.file, project_root=root)
    _print_json(res)
    return _exit_code(res)


def _cmd_seed_hashes(args, root):
    res = seed_source_content_hashes(project_root=root, force=args.force)
    _print_json(res)
    return _exit_code(res)


def _cmd_core_tools(args, root):
    _print_json(list_core_tools())
    return 0


def _cmd_list_paths(args, root):
    depth = 0 if args.recursive else args.depth
    res = list_paths(prefix=args.prefix or args.prefix_pos or args.directory, project_root=root,
                     max_files=args.max_files, depth=depth)
    _print_json(res)
    return _exit_code(res)


def _project(root: Optional[str]) -> Path:
    return resolve_root(root)


def _cmd_validate(args, root):
    res = health_mod.validate_health(_project(root))
    _print_json(res)
    return 0 if res.get("missing_count", 0) == 0 else 1


def _cmd_seed_health(args, root):
    project = _project(root)
    res = health_mod.seed_health_from_map(project)
    disk = health_mod.seed_health_for_monitored_sources(project)
    res["disk_seeded"] = disk.get("seeded")
    res["seeded_total"] = int(res.get("seeded") or 0) + int(disk.get("seeded") or 0)
    _print_json(res)
    return _exit_code(res)


def _cmd_prune_pending(args, root):
    res = health_mod.prune_pending_to_monitored(_project(root))
    _print_json(res)
    return _exit_code(res)


def _cmd_prune_health(args, root):
    project = _project(root)
    res = health_mod.prune_deleted_missing(project) if args.deleted_missing else health_mod.prune_health_outside_monitored(project)
    _print_json(res)
    return _exit_code(res)


def _cmd_readiness(args, root):
    res = health_mod.assess_autonomous_readiness(_project(root))
    _print_json(res)
    return 2 if res.get("readiness") == "blocked" else 0


def _cmd_metrics(args, root):
    res = health_mod.write_metrics_snapshot(_project(root), source="cli")
    _print_json(res)
    return _exit_code(res)


def _cmd_health(args, root):
    fmt = args.format or ("json" if args.json else "summary" if args.summary else "text")
    res = health(project_root=root, directory=args.directory, format=fmt)
    if isinstance(res, (dict, list)):
        _print_json(res)
    else:
        print(res)
    return _exit_code(res)


def _cmd_update_maps(args, root):
    if args.sh:
        print("[wikifier] note: --sh is a deprecated no-op; the Python pipeline always runs.", file=sys.stderr)
    if args.stream or args.format == "stream":
        from .streaming import run_update_stream

        project = _project(root)
        for event in run_update_stream(root=project, force_full=args.full, directory=args.directory,
                                       max_files=args.max_files, format="summary" if args.format == "summary" else "full"):
            print(json.dumps(event, default=str))
        return 0
    res = update_maps(project_root=root, full=args.full, directory=args.directory,
                      max_files=args.max_files, verbose=not args.quiet)
    _print_json(res)
    return _exit_code(res)


def _cmd_init(args, root):
    target = args.directory or root
    res = init_project(target, copy_dashboards=not args.no_copy)
    if not res.get("success"):
        print(f"error: {res.get('error')}", file=sys.stderr)
        return 1
    print(f"[wikifier] Initialised {res['project_root']}")
    for name in res.get("created") or []:
        print(f"  created {name}")
    print("Next steps:")
    for i, step in enumerate(res.get("next_steps") or [], 1):
        print(f"  {i}. {step}")
    return 0


def _cmd_monitor(args, root):
    interval = args.interval or int(os.environ.get("WIKIFIER_POLL_INTERVAL", "30") or "30")
    print(f"[wikifier] monitor: check-changes every {interval}s (Ctrl+C to stop)")
    try:
        while True:
            res = check_changes(project_root=root)
            stamp = time.strftime("%H:%M:%S")
            print(f"[{stamp}] {res.get('message') or res.get('error')}", flush=True)
            time.sleep(interval)
    except KeyboardInterrupt:
        return 0


def _cmd_serve(args, root):
    from . import serve

    if root:
        os.environ["WIKIFIER_PROJECT_ROOT"] = str(_project(root))
    return serve.main([str(args.port)])


def _cmd_daemon(args, root):
    from . import daemon

    if root:
        os.environ["WIKIFIER_PROJECT_ROOT"] = str(_project(root))
    return daemon.main([args.action] + list(args.rest))


def _cmd_journal(args, root):
    res = journal(args.date, project_root=root)
    if args.json or not res.get("success"):
        _print_json(res)
    elif res.get("exists"):
        print(res["content"].rstrip())
    else:
        print(f"No journal entries for {res['date']} yet.")
    return _exit_code(res)


def _cmd_issues(args, root):
    res = issues(args.severity, project_root=root)
    if args.json or not res.get("success"):
        _print_json(res)
        return _exit_code(res)
    print(f"=== Logged issues (severity: {res['severity']}) ===")
    for path in res["issues"]:
        print(path)
    if res.get("has_map"):
        print("\nSee Logged_issues/map.md for the categorised overview.")
    return 0


def _cmd_cycles(args, root):
    res = cycles_report(project_root=root, analysis=not args.no_analysis, max_items=args.max_items)
    if args.json:
        _print_json(res)
    else:
        print(format_cycles_report(res))
    return _exit_code(res)


def _cmd_heal_stubs(args, root):
    res = heal_stubs(project_root=root, dry_run=args.dry_run, min_wiki_length=args.min_wiki_length)
    if args.json or not res.get("success"):
        _print_json(res)
        return _exit_code(res)
    for change in res.get("changes", []):
        print(f"  {change['file']}  [{change.get('quality', '?')}]  {change['old_status']} → {change['new_status']}")
    verb = "Would heal" if args.dry_run else "Healed"
    print(f"{verb} {res.get('healed_count', 0)} stub entr{'y' if res.get('healed_count') == 1 else 'ies'}.")
    return 0


def _cmd_healable(args, root):
    _print_json(health_mod.get_healable_stubs(_project(root), directory=args.directory))
    return 0


def _cmd_healing_stats(args, root):
    _print_json(health_mod.get_healing_statistics(_project(root)))
    return 0


def _cmd_stale_wikis(args, root):
    _print_json(health_mod.get_stale_wikis(_project(root), directory=args.directory, limit=args.limit))
    return 0


def _cmd_prune_barrels(args, root):
    from .cache import prune_barrel_resolutions

    res = prune_barrel_resolutions(_project(root), max_age_days=args.max_age_days, dry_run=args.dry_run)
    _print_json(res)
    return 0


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wikifier",
        description="Wikifier — zero-dependency agent-to-agent codebase wiki.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"wikifier {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    def add(name: str, handler, help_text: str, aliases: Tuple[str, ...] = ()) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_text, aliases=list(aliases), description=help_text)
        p.set_defaults(handler=handler)
        return p

    # Core workflow
    p = add("check-changes", _cmd_check_changes, "Flag content changes in mapped, Green and monitored files Yellow")
    p.add_argument("--json", action="store_true")
    p = add("record-change", _cmd_record_change, "Record why a file was edited (required after edits)")
    p.add_argument("file")
    p.add_argument("reason", nargs="+")
    p = add("mark-green", _cmd_mark_green, "Mark a file Green after its wiki is refreshed (wiki checked against the code)")
    p.add_argument("file")
    p.add_argument("reason", nargs="*")
    p.add_argument("--force", action="store_true", help="override a failed wiki check (needs a reason)")
    p.add_argument("--json", action="store_true")
    p = add("record-changes", _cmd_record_changes, "Record reasons for every file git reports as changed", ("record-batch",))
    p.add_argument("--since", help="git ref to diff against (default HEAD: uncommitted work)")
    p.add_argument("--reasons", help="JSON file mapping path, glob or dir/ to a reason ('-' reads stdin)")
    p.add_argument("-r", "--reason", action="append", default=[], metavar="PATH=REASON",
                   help="reason for a path, glob or dir/ (repeatable)")
    p.add_argument("--default", dest="default_reason", help="reason for files not matched above")
    p.add_argument("--green", action="store_true", help="then mark each file Green (wiki checks apply)")
    p.add_argument("--dry-run", action="store_true", help="show the plan and missing reasons; write nothing")
    p.add_argument("--only", action="append", default=[], metavar="PATTERN",
                   help="limit to paths, globs or dir/ prefixes (repeatable)")
    p = add("record-deletion", _cmd_record_deletion, "Record an intentional file deletion")
    p.add_argument("file")
    p.add_argument("reason", nargs="*")
    p = add("session-bootstrap", _cmd_bootstrap, "One-shot session start snapshot (JSON)",
            ("bootstrap", "session-start"))
    p.add_argument("--directory", "--dir")
    p = add("suggest-next", _cmd_suggest, "Selective next actions (🔴 then actionable 🟡)",
            ("suggest-next-actions", "suggest"))
    p.add_argument("--json", action="store_true")
    p.add_argument("--format", choices=("text", "json"))
    p.add_argument("--directory", "--dir")
    p = add("prepare-edit", _cmd_prepare_edit, "Preflight one file: status, wiki, deps, dependents",
            ("lookup", "preflight"))
    p.add_argument("file")

    # Lookup
    p = add("dependencies", _cmd_dependencies, "What a file imports (JSON)", ("deps",))
    p.add_argument("file")
    p.add_argument("--full", action="store_true", help="per-edge records with confidence explanations")
    p = add("dependents", _cmd_dependents, "Files that import a file (JSON)", ("importers",))
    p.add_argument("file")
    p = add("why-file", _cmd_why_file, "Health reason + journal history for a file", ("why",))
    p.add_argument("file")
    p = add("search-journal", _cmd_search_journal, "Search the journal", ("journal-search",))
    p.add_argument("text", nargs="?")
    p.add_argument("--query", "-q")
    p.add_argument("--file", "-f")
    p.add_argument("--limit", type=int, default=20)
    p = add("list-paths", _cmd_list_paths, "Folder card (names only) for a prefix", ("map-index", "list-map"))
    p.add_argument("prefix_pos", nargs="?", metavar="prefix")
    p.add_argument("--prefix", "-p")
    p.add_argument("--directory", "--dir")
    p.add_argument("--max-files", type=int)
    p.add_argument("--depth", type=int, default=1)
    p.add_argument("--recursive", "-r", action="store_true")
    p = add("cycles", _cmd_cycles, "Report circular dependencies")
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-analysis", action="store_true", help="skip severity analysis")
    p.add_argument("--max-items", type=int)
    p = add("journal", _cmd_journal, "Show a day's journal (default today)")
    p.add_argument("date", nargs="?", help="YYYY-MM-DD")
    p.add_argument("--json", action="store_true")
    p = add("issues", _cmd_issues, "List Logged_issues (optionally by severity)")
    p.add_argument("severity", nargs="?", default="all")
    p.add_argument("--json", action="store_true")

    # Maps + health
    p = add("update-maps", _cmd_update_maps, "Rebuild the dependency map + library.md")
    p.add_argument("--full", "-f", "--force-full", "--full-rebuild", action="store_true", dest="full")
    p.add_argument("--directory", "--dir")
    p.add_argument("--max-files", type=int)
    p.add_argument("--stream", action="store_true", help="emit progress events (JSON lines)")
    p.add_argument("--format", choices=("full", "summary", "stream"))
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--sh", "--legacy-sh", "--no-python-primary", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--python-primary", "--use-python-primary", action="store_true", help=argparse.SUPPRESS)
    p = add("health", _cmd_health, "Health matrix (text table, --summary or --json)")
    p.add_argument("--summary", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--format", choices=("text", "json", "summary", "healing-stats"))
    p.add_argument("--directory", "--dir")
    p = add("validate", _cmd_validate, "List monitored sources lacking a health row (exit 1 if any)")
    add("seed-health", _cmd_seed_health, "Add 🟡 stubs for mapped files without a row", ("seed-health-from-map",))
    p = add("seed-source-hashes", _cmd_seed_hashes, "Record content baselines without changing status",
            ("seed-source-content-hashes", "seed-hashes"))
    p.add_argument("--force", "-f", action="store_true")
    add("prune-pending", _cmd_prune_pending, "Drop pending items outside monitored_paths", ("prune-pending-monitored",))
    p = add("prune-health", _cmd_prune_health, "Drop health rows outside monitored_paths and the map", ("prune-health-monitored",))
    p.add_argument("--deleted-missing", "--deleted", action="store_true", help="instead drop DELETED rows whose files are gone")
    p = add("heal-stubs", _cmd_heal_stubs, "Promote Initial stubs that now have a real wiki")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--min-wiki-length", type=int, default=350)
    p.add_argument("--json", action="store_true")
    p = add("healable-stubs", _cmd_healable, "List stubs eligible for heal-stubs")
    p.add_argument("directory", nargs="?")
    add("healing-stats", _cmd_healing_stats, "Stub counts by wiki quality", ("stub-stats",))
    p = add("stale-wikis", _cmd_stale_wikis, "Files whose wiki lags their recorded changes", ("detect-stale",))
    p.add_argument("directory", nargs="?")
    p.add_argument("--limit", type=int, default=200)
    p = add("verify-wikis", _cmd_verify_wikis, "Check Green files' wikis against their code (exit 1 if any fail)", ("verify",))
    p.add_argument("directory", nargs="?")
    p.add_argument("--limit", type=int, default=200)
    p = add("prune-barrels", _cmd_prune_barrels, "Drop aged barrel-cache chains", ("prune-brc", "gc-barrels"))
    p.add_argument("max_age_days", nargs="?", type=float, default=90.0)
    p.add_argument("--dry-run", action="store_true")
    add("cache-status", _cmd_cache_status, "Cache backend, size, edges, coverage", ("cache-info", "cache"))
    add("autonomous-status", _cmd_readiness, "Readiness for unattended daemon use (exit 2 if blocked)",
        ("readiness", "long-horizon"))
    add("metrics-snapshot", _cmd_metrics, "Append a metrics sample", ("metrics",))
    add("list-core-tools", _cmd_core_tools, "Core daily tools vs advanced", ("core-tools",))

    # Setup + background
    p = add("init", _cmd_init, "Bootstrap Wikifier state in a project directory")
    p.add_argument("directory", nargs="?")
    p.add_argument("--no-copy", action="store_true", help="do not copy the index.html dashboard")
    p = add("monitor", _cmd_monitor, "Foreground loop: check-changes every N seconds")
    p.add_argument("--interval", type=int)
    p = add("serve", _cmd_serve, "Serve the dashboard on localhost")
    p.add_argument("port", nargs="?", type=int, default=8787)
    p = add("daemon", _cmd_daemon, "Background daemon (start|stop|status|logs|restart|run|install-service|uninstall-service)")
    p.add_argument("action")
    p.add_argument("rest", nargs=argparse.REMAINDER)
    add("help", lambda args, root: (parser.print_help(), 0)[1], "Show this help")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    argv, project_root, use_canonical = _extract_global_options(argv)
    if argv and not argv[0].startswith("-"):
        argv[0] = argv[0].replace("_", "-")
    if use_canonical is not None:
        os.environ["WIKIFIER_USE_CANONICAL"] = "1" if use_canonical else "0"
    parser = _build_parser()
    if not argv:
        parser.print_help()
        return 0
    args = parser.parse_args(argv)
    if project_root:
        try:
            project_root = str(resolve_root(project_root))
        except ProjectRootError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    try:
        return int(args.handler(args, project_root) or 0)
    except ProjectRootError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
