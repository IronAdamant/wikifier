//! Stdio MCP (JSON-RPC) over the same functions as the CLI.

use std::collections::BTreeMap;
use std::io::{BufRead, Write};
use std::path::PathBuf;

use crate::api::{self, MCP_TOOLS};
use crate::jsonutil::{self, Json};

fn string_prop(description: &str) -> Json {
    Json::obj(vec![
        ("type", Json::String("string".into())),
        ("description", Json::String(description.into())),
    ])
}

fn tool_spec(name: &str) -> (&'static str, &'static [&'static str], &'static [&'static str]) {
    match name {
        "check_changes" => ("Compare mapped files and Green baselines and report content drift.", &["project_root"], &[]),
        "record_change" => ("Record a semantic edit against one file and mark that file actionable.", &["project_root", "file", "reason"], &[]),
        "record_deletion" => ("Record that a mapped file was removed and should leave the health matrix.", &["project_root", "file", "reason"], &[]),
        "mark_green" => ("Mark a file Green after its wiki names the file's public symbols.", &["project_root", "file"], &["reason"]),
        "record_changes" => ("Record git changes in one batch. Pass per-file reasons when you have them.", &["project_root"], &[]),
        "verify_wikis" => ("Check every Green wiki against the public symbols currently in the source.", &["project_root"], &[]),
        "prepare_edit" => ("Look up health, wiki text, dependencies, and dependents before editing a file.", &["project_root", "file"], &[]),
        "session_bootstrap" => ("Return readiness, health, suggested actions, and the mapped file list for this root.", &["project_root"], &[]),
        "suggest_next_actions" => ("Return the next agent actions, highest priority first.", &["project_root"], &[]),
        "list_core_tools" => ("List the daily core tools and the full MCP tool catalogue.", &["project_root"], &[]),
        "list_paths" => ("List mapped files under a project-relative prefix.", &["project_root"], &["prefix"]),
        "search_journal" => ("Search journal entries by file path or reason text.", &["project_root", "query"], &["text"]),
        "why_file" => ("Return the journal reasons recorded for one file.", &["project_root", "file"], &[]),
        "get_dependencies" => ("Return internal edges, external imports, and unresolved imports for one file.", &["project_root", "file"], &[]),
        "get_dependents" => ("Return the mapped files that import a given file.", &["project_root", "file"], &[]),
        "get_cycles" => ("Return import cycles in the mapped graph.", &["project_root"], &[]),
        "get_resolution_diagnostics" => ("Return resolution and barrel diagnostics for the current map.", &["project_root"], &[]),
        "get_file_wiki" => ("Return the wiki markdown stored beside a source file.", &["project_root", "file"], &[]),
        "get_files_needing_attention" => ("Return files whose health is Red or an actionable Yellow.", &["project_root"], &[]),
        "get_project_status" => ("Return the same readiness snapshot as session bootstrap.", &["project_root"], &[]),
        "get_current_project_root" => ("Return the absolute project root this call is using.", &["project_root"], &[]),
        "get_barrel_reports" => ("Return barrel and incremental-resolution status for the current map.", &["project_root"], &[]),
        "get_incremental_status" => ("Return whether the map is incremental and which barrels are recorded.", &["project_root"], &[]),
        "update_maps" => ("Parse the scoped tree and commit one cache generation for the whole run.", &["project_root"], &[]),
        "health" => ("Return the health matrix entries and the green, yellow, and red counts.", &["project_root"], &[]),
        "validate" => ("Check health coverage and that the forward and reverse cache indexes agree.", &["project_root"], &[]),
        "list_healable_stubs" => ("List Initial-stub files whose wiki is long enough to heal.", &["project_root"], &[]),
        "heal_stubs" => ("Promote Initial stubs that already have a long enough wiki.", &["project_root"], &[]),
        "seed_source_content_hashes" => ("Seed health rows from the current map without rewriting wikis.", &["project_root"], &[]),
        "journal" => ("Return journal entries, optionally for one date.", &["project_root"], &[]),
        "issues" => ("Return the same prioritized actions as suggest_next_actions.", &["project_root"], &[]),
        _ => ("Run one Wikifier agent operation against project_root.", &["project_root"], &[]),
    }
}

pub fn tool_schema(name: &str) -> Json {
    let (description, required, optional) = tool_spec(name);
    let mut props = vec![("project_root".into(), string_prop("Absolute project root. Pass it on every call."))];
    let mut fields: Vec<&str> = required.iter().copied().chain(optional.iter().copied()).filter(|field| *field != "project_root").collect();
    fields.sort();
    fields.dedup();
    for field in fields {
        let desc = match field {
            "file" => "Project-relative source path.",
            "reason" => "Why the file changed, or why a forced mark-green is still accurate.",
            "prefix" => "Project-relative directory prefix. Omit to list the whole map.",
            "query" => "Substring matched against journal file paths and reasons.",
            "text" => "Alias of query.",
            _ => "String argument.",
        };
        props.push((field.into(), string_prop(desc)));
    }
    Json::obj(vec![
        ("name", Json::String(name.into())),
        ("description", Json::String(description.into())),
        ("inputSchema", Json::obj(vec![
            ("type", Json::String("object".into())),
            ("properties", Json::from_pairs(props)),
            ("required", Json::Array(required.iter().map(|field| Json::String((*field).into())).collect())),
        ])),
    ])
}

pub fn handle_message(msg: &Json) -> Option<Json> {
    let id = msg.get("id").cloned();
    let method = msg.get("method").and_then(|m| m.as_str()).unwrap_or("");
    if id.is_none() {
        return None;
    }
    let result = match method {
        "initialize" => Json::obj(vec![
            ("protocolVersion", Json::String("2024-11-05".into())),
            ("capabilities", Json::obj(vec![
                ("tools", Json::obj(vec![])),
                ("resources", Json::obj(vec![])),
                ("prompts", Json::obj(vec![])),
            ])),
            ("serverInfo", Json::obj(vec![
                ("name", Json::String("wikifier".into())),
                ("version", Json::String(api::VERSION.into())),
            ])),
        ]),
        "tools/list" => Json::obj(vec![
            ("tools", Json::Array(MCP_TOOLS.iter().map(|n| tool_schema(n)).collect())),
        ]),
        "resources/list" => Json::obj(vec![
            ("resources", Json::Array(["wikifier://library", "wikifier://health", "wikifier://pending", "wikifier://journal"].into_iter().map(|u| {
                Json::obj(vec![("uri", Json::String(u.into())), ("name", Json::String(u.into()))])
            }).collect())),
        ]),
        "prompts/list" => Json::obj(vec![
            ("prompts", Json::Array([
                "review_pending_changes", "audit_project_health", "plan_refactoring",
                "find_architectural_smells", "understand_codebase_structure", "review_recent_changes",
                "generate_project_health_report", "onboard_to_module",
            ].into_iter().map(|n| Json::obj(vec![("name", Json::String(n.into()))])).collect())),
        ]),
        "tools/call" => {
            let params = msg.get("params");
            let name = params.and_then(|p| p.get("name")).and_then(|n| n.as_str()).unwrap_or("");
            let args = params.and_then(|p| p.get("arguments"));
            let root = args.and_then(|a| a.get("project_root")).and_then(|r| r.as_str()).map(PathBuf::from)
                .unwrap_or_else(|| std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")));
            let mut flags = BTreeMap::new();
            let mut positional = Vec::new();
            if let Some(file) = args.and_then(|a| a.get("file")).and_then(|f| f.as_str()) {
                positional.push(file.to_string());
            }
            if let Some(reason) = args.and_then(|a| a.get("reason")).and_then(|f| f.as_str()) {
                positional.push(reason.to_string());
            }
            if let Some(prefix) = args.and_then(|a| a.get("prefix")).and_then(|f| f.as_str()) {
                flags.insert("prefix".into(), prefix.into());
            }
            if let Some(q) = args.and_then(|a| a.get("query").or_else(|| a.get("text"))).and_then(|f| f.as_str()) {
                flags.insert("query".into(), q.into());
            }
            let value = if !root.is_dir() {
                Json::obj(vec![
                    ("success", Json::Bool(false)),
                    ("error", Json::String("project root does not exist".into())),
                    ("error_type", Json::String("ProjectRootError".into())),
                ])
            } else {
                api::dispatch(name, &root, &positional, &flags)
            };
            Json::obj(vec![
                ("content", Json::Array(vec![Json::obj(vec![
                    ("type", Json::String("text".into())),
                    ("text", Json::String(value.to_string())),
                ])])),
                ("structuredContent", value),
                ("isError", Json::Bool(false)),
            ])
        }
        _ => Json::obj(vec![
            ("success", Json::Bool(false)),
            ("error", Json::String(format!("unknown method {method}"))),
            ("error_type", Json::String("MethodNotFound".into())),
        ]),
    };
    Some(Json::obj(vec![
        ("jsonrpc", Json::String("2.0".into())),
        ("id", id.unwrap_or(Json::Null)),
        ("result", result),
    ]))
}

pub fn serve_stdio() -> Result<(), String> {
    let stdin = std::io::stdin();
    let mut reader = stdin.lock();
    let mut stdout = std::io::stdout().lock();
    loop {
        let mut line = String::new();
        let n = reader.read_line(&mut line).map_err(|e| e.to_string())?;
        if n == 0 {
            break;
        }
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        let msg = match jsonutil::parse(trimmed) {
            Ok(v) => v,
            Err(_) => continue,
        };
        if let Some(resp) = handle_message(&msg) {
            writeln!(stdout, "{resp}").map_err(|e| e.to_string())?;
            stdout.flush().map_err(|e| e.to_string())?;
        }
    }
    Ok(())
}
