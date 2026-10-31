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
    let (root, rest) = extract_target(&args);
    args = rest;
    if args.is_empty() || args[0] == "--help" || args[0] == "-h" || args[0] == "help" {
        print_help();
        return ExitCode::SUCCESS;
    }
    let command = args.remove(0).replace('_', "-");
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
        if a == "-r" || a == "--reason" {
            if i + 1 < args.len() {
                let cur = flags.entry("reasons".into()).or_default();
                if !cur.is_empty() {
                    cur.push('\n');
                }
                cur.push_str(&args[i + 1]);
                i += 2;
                continue;
            }
        }
        if a == "--json" || a == "--full" || a == "--summary" || a == "--force" || a == "--stream" || a == "--quiet" || a == "--dry-run" || a == "--green" {
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
    let success = value.get("success").and_then(|s| s.as_bool()).unwrap_or(false);
    flush_stdout(&format!("{value}\n"));
    if success {
        ExitCode::SUCCESS
    } else if value.get("error_type").and_then(|s| s.as_str()) == Some("ScopeError") && command == "autonomous-status" {
        ExitCode::from(2)
    } else {
        ExitCode::from(1)
    }
}

fn extract_target(args: &[String]) -> (Option<PathBuf>, Vec<String>) {
    let mut root = env::var("WIKIFIER_PROJECT_ROOT").ok().map(PathBuf::from);
    let mut rest = Vec::new();
    let mut i = 0;
    while i < args.len() {
        let a = &args[i];
        if a == "--target" || a == "--project-root" {
            if i + 1 < args.len() {
                root = Some(PathBuf::from(&args[i + 1]));
                i += 2;
                continue;
            }
        }
        if let Some(v) = a.strip_prefix("--target=").or_else(|| a.strip_prefix("--project-root=")) {
            root = Some(PathBuf::from(v));
            i += 1;
            continue;
        }
        rest.push(a.clone());
        i += 1;
    }
    (root, rest)
}

fn print_help() {
    let mut names = CLI_COMMANDS.to_vec();
    names.sort();
    flush_stdout(&format!(
        "wikifier {VERSION}\n\nUsage: wikifier [--target DIR] <command> [args]\n\nCommands:\n{}\n",
        names.iter().map(|n| format!("  {n}")).collect::<Vec<_>>().join("\n")
    ));
}
