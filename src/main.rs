//! `wikifier` CLI. Global `--target` / `--project-root` match the Python launcher.

use std::collections::BTreeMap;
use std::env;
use std::path::PathBuf;
use std::process::ExitCode;

use wikifier::api::{self, CLI_COMMANDS, VERSION};
use wikifier::timeutil::flush_stdout;

fn main() -> ExitCode {
    let mut args: Vec<String> = env::args().skip(1).collect();
    if args.iter().any(|a| a == "--version" || a == "-V") {
        flush_stdout(&format!("wikifier {VERSION}\n"));
        return ExitCode::SUCCESS;
    }
    let (root, explicit_target, rest) = extract_target(&args);
    args = rest;
    if args.is_empty() || args[0] == "--help" || args[0] == "-h" {
        print_help();
        return ExitCode::SUCCESS;
    }
    let command = args.remove(0).replace('_', "-");
    // `<command> --help` and `help <command>` print help and run nothing. Before this,
    // `init --help` ran init and wrote ten files.
    if command == "help" {
        match args.first() {
            Some(topic) => print_command_help(&topic.replace('_', "-")),
            None => print_help(),
        }
        return ExitCode::SUCCESS;
    }
    if args.iter().any(|a| a == "--help" || a == "-h") {
        print_command_help(&command);
        return ExitCode::SUCCESS;
    }
    if command == "mcp" {
        if let Err(e) = wikifier::mcp::serve_stdio() {
            eprintln!("error: {e}");
            return ExitCode::from(1);
        }
        return ExitCode::SUCCESS;
    }
    let mut flags: BTreeMap<String, String> = BTreeMap::new();
    let mut positional = Vec::new();
    let mut i = 0;
    while i < args.len() {
        let a = &args[i];
        if (a == "-r" || a == "--reason" || a == "--only") && i + 1 < args.len() {
            let key = if a == "--only" { "only" } else { "reasons" };
            let cur = flags.entry(key.into()).or_default();
            if !cur.is_empty() {
                cur.push('\n');
            }
            cur.push_str(&args[i + 1]);
            i += 2;
            continue;
        }
        if a == "--reasons" && i + 1 < args.len() {
            let spec = &args[i + 1];
            let text = if spec == "-" {
                let mut body = String::new();
                let _ = std::io::Read::read_to_string(&mut std::io::stdin(), &mut body);
                body
            } else {
                std::fs::read_to_string(spec).unwrap_or_default()
            };
            let cur = flags.entry("reasons".into()).or_default();
            for line in reason_lines(&text) {
                if !cur.is_empty() {
                    cur.push('\n');
                }
                cur.push_str(&line);
            }
            i += 2;
            continue;
        }
        if a == "--json"
            || a == "--full"
            || a == "--summary"
            || a == "--force"
            || a == "--stream"
            || a == "--quiet"
            || a == "--dry-run"
            || a == "--green"
        {
            flags.insert(a.trim_start_matches('-').to_string(), "true".into());
            i += 1;
            continue;
        }
        if let Some(key) = a.strip_prefix("--") {
            if i + 1 < args.len() && !args[i + 1].starts_with('-') {
                flags.insert(key.to_string(), args[i + 1].clone());
                i += 2;
                continue;
            }
            flags.insert(key.to_string(), "true".into());
            i += 1;
            continue;
        }
        positional.push(a.clone());
        i += 1;
    }
    if command == "list-paths" {
        if let Some(p) = positional.first() {
            flags.entry("prefix".into()).or_insert_with(|| p.clone());
        }
    }
    if command == "journal" {
        if let Some(d) = positional.first() {
            flags.entry("date".into()).or_insert_with(|| d.clone());
        }
    }
    let root = if command == "init" && !explicit_target {
        positional.first().map(PathBuf::from).or(root)
    } else {
        root
    };
    let root = match root {
        Some(r) if r.is_dir() => r,
        Some(r) => {
            eprintln!("error: project root does not exist: {}", r.display());
            return ExitCode::from(1);
        }
        None => env::current_dir().unwrap_or_else(|_| PathBuf::from(".")),
    };
    if !CLI_COMMANDS.contains(&command.as_str()) && command != "mcp" {
        // aliases already listed; unknown falls through to dispatch
    }
    let value = api::dispatch(&command, &root, &positional, &flags);
    let success = value
        .get("success")
        .and_then(|s| s.as_bool())
        .unwrap_or(false);
    let textual = flags
        .get("text")
        .map(|s| s == "true" || s == "1")
        .unwrap_or(false)
        || (command == "health" && flags.get("format").map(|s| s == "text").unwrap_or(false));
    if textual {
        if let Some(prose) = wikifier::text_out::render(&command, &value) {
            flush_stdout(&prose);
        } else {
            flush_stdout(&format!("{value}\n"));
        }
    } else {
        flush_stdout(&format!("{value}\n"));
    }
    if success {
        ExitCode::SUCCESS
    } else if value.get("error_type").and_then(|s| s.as_str()) == Some("ScopeError")
        && command == "autonomous-status"
    {
        ExitCode::from(2)
    } else {
        ExitCode::from(1)
    }
}

fn reason_lines(text: &str) -> Vec<String> {
    let trimmed = text.trim();
    if trimmed.starts_with('{') {
        if let Ok(wikifier::Json::Object(map)) = wikifier::jsonutil::parse(trimmed) {
            return map
                .into_iter()
                .filter_map(|(key, value)| value.as_str().map(|reason| format!("{key}={reason}")))
                .collect();
        }
    }
    text.lines()
        .filter_map(|line| {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') {
                None
            } else {
                Some(line.to_string())
            }
        })
        .collect()
}

fn extract_target(args: &[String]) -> (Option<PathBuf>, bool, Vec<String>) {
    let mut root = env::var("WIKIFIER_PROJECT_ROOT").ok().map(PathBuf::from);
    let mut explicit = false;
    let mut rest = Vec::new();
    let mut moved = Vec::new();
    let mut i = 0;
    while i < args.len() {
        let a = &args[i];
        // `--worktree` may come before the command, like `--target`; it is moved after it,
        // where the command's own flags are read.
        if (a == "--worktree" || a == "--worktree-root") && i + 1 < args.len() {
            moved.push(a.clone());
            moved.push(args[i + 1].clone());
            i += 2;
            continue;
        }
        if a.starts_with("--worktree=") || a.starts_with("--worktree-root=") {
            let (key, value) = a.split_once('=').unwrap_or((a, ""));
            moved.push(key.to_string());
            moved.push(value.to_string());
            i += 1;
            continue;
        }
        if (a == "--target" || a == "--project-root") && i + 1 < args.len() {
            root = Some(PathBuf::from(&args[i + 1]));
            explicit = true;
            i += 2;
            continue;
        }
        if let Some(v) = a
            .strip_prefix("--target=")
            .or_else(|| a.strip_prefix("--project-root="))
        {
            root = Some(PathBuf::from(v));
            explicit = true;
            i += 1;
            continue;
        }
        rest.push(a.clone());
        i += 1;
    }
    rest.extend(moved);
    (root, explicit, rest)
}

fn print_help() {
    let mut names = CLI_COMMANDS.to_vec();
    names.sort();
    flush_stdout(&format!(
        "wikifier {VERSION}\n\nUsage: wikifier [--target DIR] <command> [args]\n\nCommands:\n{}\n",
        names
            .iter()
            .map(|n| format!("  {n}"))
            .collect::<Vec<_>>()
            .join("\n")
    ));
}

/// One usage line and one sentence per command, for `wikifier <command> --help`.
fn command_help(command: &str) -> Option<(&'static str, &'static str)> {
    Some(match command {
        "check-changes" => ("check-changes", "Compare watched files with their Green baselines; mark drifted files Yellow and list them."),
        "record-change" => ("record-change FILE WHY", "Journal why FILE changed, mark it actionable, and add its pending item."),
        "mark-green" => ("mark-green FILE [WHY] [--force]", "Check FILE's wiki against its public symbols and mark it Green. --force needs WHY."),
        "record-changes" => ("record-changes [-r PATH=WHY]... [--reasons FILE] [--default WHY] [--only P]... [--since REF] [--green] [--dry-run]", "Record every file git reports as changed, with reasons per path, glob, or dir/."),
        "record-deletion" => ("record-deletion FILE [WHY]", "Journal a removed file, mark it Red, and drop it from the map."),
        "session-bootstrap" => ("session-bootstrap [--directory D] [--limit N]", "Readiness, health counts, next actions, and the mapped files (capped by --limit)."),
        "suggest-next" => ("suggest-next [--json|--text]", "The next agent actions, highest priority first."),
        "prepare-edit" => ("prepare-edit FILE", "Health status, wiki text, dependencies, and dependents of FILE before an edit."),
        "dependencies" => ("dependencies FILE [--full]", "What FILE imports. --full adds per-edge confidence records."),
        "dependents" => ("dependents FILE [--limit N]", "The mapped files that import FILE."),
        "why-file" => ("why-file FILE", "The journal reasons recorded for FILE."),
        "search-journal" => ("search-journal [TEXT] [--file F]", "Journal entries whose path or reason contains TEXT."),
        "list-paths" => ("list-paths [PREFIX] [--depth N|--recursive] [--max-files N]", "The folder card for PREFIX: its files and subfolders."),
        "cycles" => ("cycles [--max-items N] [--no-analysis]", "Import cycles with break hints and the most depended-on files."),
        "journal" => ("journal [YYYY-MM-DD] [--limit N]", "Journal entries for one day (today by default)."),
        "issues" => ("issues", "The same actions list as suggest-next."),
        "update-maps" => ("update-maps [--full] [--directory D] [--max-files N] [--stream] [--quiet]", "Parse changed files and rewrite the dependency map, library.md, and folder cards."),
        "health" => ("health [--summary] [--limit N] [--format text]", "The health matrix: counts and entries (Red and actionable Yellow first under --limit)."),
        "validate" => ("validate", "Check health coverage and that the forward and reverse indexes agree."),
        "rebuild-cache" => ("rebuild-cache", "Rebuild the reverse index from the forward index."),
        "seed-health" => ("seed-health", "Add Initial-stub health rows for mapped files that have none."),
        "seed-source-hashes" => ("seed-source-hashes", "Fill missing source hashes in health rows from the map."),
        "prune-pending" => ("prune-pending", "Drop pending items whose file is gone."),
        "prune-health" => ("prune-health [--deleted-missing]", "Drop health rows for files neither mapped nor watched; --deleted-missing also drops rows whose file is gone."),
        "heal-stubs" => ("heal-stubs [--dry-run] [--min-wiki-length N]", "Promote Initial stubs that already have a long enough wiki."),
        "healable-stubs" => ("healable-stubs [--min-wiki-length N]", "List Initial stubs that heal-stubs would promote."),
        "healing-stats" => ("healing-stats", "Counts of Initial stubs and healed rows."),
        "stale-wikis" => ("stale-wikis [--limit N]", "Files with a wiki whose source changed since mark-green."),
        "verify-wikis" => ("verify-wikis [DIR] [--limit N]", "Re-check every Green wiki against its code; exit 1 if any fail."),
        "prune-barrels" => ("prune-barrels [DAYS] [--max-age-days N] [--dry-run]", "Delete barrel records older than the age limit; --dry-run only counts them."),
        "cache-status" => ("cache-status", "The cache backend and the mapped file count."),
        "autonomous-status" => ("autonomous-status", "Readiness and scope; exit 2 on a scope error."),
        "metrics-snapshot" => ("metrics-snapshot", "Write health counts to .wikifier_staging/metrics_latest.json and append them to metrics_history.jsonl."),
        "list-core-tools" => ("list-core-tools", "The daily core tools and the full MCP tool list."),
        "init" => ("init [DIR] [--no-copy]", "Create the path lists, empty health, pending, library, journal, and index.html in DIR (or --target)."),
        "monitor" => ("monitor [--interval SECONDS]", "Repeat check-changes and the modularity pass until stopped. Default interval is health_interval_s from .wikifier/config (30s). Does not run update-maps."),
        "serve" => ("serve [PORT]", "Serve the dashboard and its read-only JSON API on 127.0.0.1 (default port 8787)."),
        "daemon" => ("daemon start|stop|status|run", "Background loop. The cheap health and modularity pass uses health_interval_s (or WIKIFIER_POLL_INTERVAL). update-maps stays on maps_interval_s (or WIKIFIER_DAEMON_MAPS_INTERVAL, default 600s)."),
        "mcp" => ("mcp", "MCP server on stdio. WIKIFIER_TOOLS / WIKIFIER_DISABLE pick its tool groups."),
        "help" => ("help [COMMAND]", "This help, or one command's help."),
        _ => return None,
    })
}

/// `wikifier <command> --help`: print and touch nothing. An unknown command gets the list.
fn print_command_help(command: &str) {
    match command_help(command) {
        Some((usage, about)) => flush_stdout(&format!(
            "wikifier {VERSION}\n\nUsage: wikifier [--target DIR] {usage}\n\n{about}\n"
        )),
        None => print_help(),
    }
}
