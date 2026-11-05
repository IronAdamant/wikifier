//! Stdio MCP (JSON-RPC) over the same functions as the CLI.

use std::collections::BTreeMap;
use std::io::{BufRead, Write};
use std::path::PathBuf;
use std::sync::mpsc;
use std::time::Duration;

use crate::api::{self, MCP_TOOLS};
use crate::jsonutil::{self, Json};
use crate::mcp_groups::{AgentTools, Selection, DISABLE_VAR, TOOLS_VAR};

/// Tool-group state for this server: the selection, the block's warnings, and the AGENTS.md
/// stamp that [`refresh`] compares before every request.
#[derive(Clone)]
pub struct GroupState {
    pub selection: Selection,
    pub warnings: Vec<String>,
    /// A switch is set or AGENTS.md has an `agent-tools` block. Only then do `initialize`
    /// and `list_core_tools` carry the groups line.
    pub shaped: bool,
    agents: Option<PathBuf>,
    stamp: Option<(std::time::SystemTime, u64)>,
    env_tools: Option<String>,
    env_disable: Option<String>,
}

static STATE: std::sync::Mutex<Option<GroupState>> = std::sync::Mutex::new(None);

/// The notification sent before a response when an AGENTS.md edit changed the tool list.
pub const LIST_CHANGED: &str = r#"{"jsonrpc":"2.0","method":"notifications/tools/list_changed"}"#;

/// The tools this server exposes. Every tool until [`configure`] runs.
pub fn active() -> Selection {
    groups_state().selection
}

pub fn groups_state() -> GroupState {
    STATE
        .lock()
        .ok()
        .and_then(|guard| guard.clone())
        .unwrap_or_else(|| GroupState {
            selection: Selection::all(),
            warnings: Vec::new(),
            shaped: false,
            agents: None,
            stamp: None,
            env_tools: None,
            env_disable: None,
        })
}

impl GroupState {
    fn load(
        agents: Option<PathBuf>,
        env_tools: Option<String>,
        env_disable: Option<String>,
    ) -> Result<Self, String> {
        let stamp = agents.as_deref().and_then(stamp_of);
        let block = agents
            .as_deref()
            .and_then(|path| std::fs::read_to_string(path).ok())
            .map(|text| AgentTools::parse(&text))
            .unwrap_or_default();
        let (selection, warnings) =
            Selection::resolve(env_tools.as_deref(), env_disable.as_deref(), &block)?;
        Ok(GroupState {
            selection,
            warnings,
            shaped: block.found || env_tools.is_some() || env_disable.is_some(),
            agents,
            stamp,
            env_tools,
            env_disable,
        })
    }

    /// Block warnings first, then the groups line.
    pub fn instructions(&self) -> String {
        let mut lines = self.warnings.clone();
        lines.push(self.selection.summary());
        lines.join("\n")
    }
}

fn stamp_of(path: &std::path::Path) -> Option<(std::time::SystemTime, u64)> {
    let meta = std::fs::metadata(path).ok()?;
    Some((meta.modified().ok()?, meta.len()))
}

/// Read `WIKIFIER_TOOLS`, `WIKIFIER_DISABLE`, and the `agent-tools` block of AGENTS.md in
/// the server's project root (`WIKIFIER_PROJECT_ROOT`, else the working directory). `Err`
/// is an environment mistake; the server prints it and exits 2.
pub fn configure() -> Result<(), String> {
    let env = |key: &str| std::env::var(key).ok().filter(|v| !v.trim().is_empty());
    let root = env("WIKIFIER_PROJECT_ROOT")
        .map(PathBuf::from)
        .or_else(|| std::env::current_dir().ok());
    let state = GroupState::load(
        root.map(|root| root.join("AGENTS.md")),
        env(TOOLS_VAR),
        env(DISABLE_VAR),
    )?;
    if let Ok(mut guard) = STATE.lock() {
        *guard = Some(state);
    }
    Ok(())
}

/// Stat AGENTS.md (mtime and size) and reload it when it changed. True when the exposed
/// tool list changed, so the caller sends [`LIST_CHANGED`] before its response.
pub fn refresh() -> bool {
    let Ok(mut guard) = STATE.lock() else {
        return false;
    };
    let Some(state) = guard.as_mut() else {
        return false;
    };
    let Some(path) = state.agents.clone() else {
        return false;
    };
    let stamp = stamp_of(&path);
    if stamp == state.stamp {
        return false;
    }
    match GroupState::load(
        Some(path),
        state.env_tools.clone(),
        state.env_disable.clone(),
    ) {
        Ok(next) => {
            let changed = next.selection.enabled() != state.selection.enabled();
            *state = next;
            changed
        }
        Err(_) => {
            state.stamp = stamp;
            false
        }
    }
}

fn extra_props(name: &str) -> Vec<(&'static str, Json)> {
    let boolean = |description: &str| {
        Json::obj(vec![
            ("type", Json::String("boolean".into())),
            ("description", Json::String(description.into())),
        ])
    };
    let integer = |description: &str| {
        Json::obj(vec![
            ("type", Json::String("integer".into())),
            ("description", Json::String(description.into())),
        ])
    };
    let mut props = vec![
        (
            "timeout_s",
            integer(
                "Stop this call after this many seconds. Falls back to WIKIFIER_MCP_DEADLINE_S.",
            ),
        ),
        (
            "format",
            string_prop(
                "text or json. json is the default. text fills the content string with prose.",
            ),
        ),
        (
            "directory",
            string_prop("Limit the result to this project-relative prefix."),
        ),
    ];
    match name {
        "get_dependencies" => props.extend([
            ("detail", string_prop("compact or full. full adds confidence reasons.")),
            ("low_confidence_only", boolean("Keep resolved edges below 0.65 that are not dynamic.")),
            ("unresolved_only", boolean("Keep only imports that did not resolve to a project file.")),
        ]),
        "list_paths" => props.extend([
            ("depth", integer("1 is the folder card. 0 lists every file under the prefix.")),
            ("recursive", boolean("Same as depth 0.")),
            ("max_files", integer("Cap the returned file list.")),
        ]),
        "get_cycles" => props.extend([
            ("max_items", integer("Cap the cycle list.")),
            ("analysis", boolean("Include severity and reverse-dependency ranking. Default true.")),
        ]),
        "health" => props.extend([
            ("limit", integer("Return at most this many entries. entries_total gives the full count.")),
            ("summary", boolean("Return only the green, yellow, and red counts.")),
        ]),
        "session_bootstrap" | "get_project_status" => props.push((
            "limit",
            integer("Cap the files list. Default 100 over MCP; 0 lists every file. files_total gives the count. Orient with map_index and list_paths."),
        )),
        "verify_wikis" | "suggest_next_actions" => {
            props.push(("limit", integer("Cap listed failures or stale rows.")));
        }
        "record_changes" => props.push(("reasons", Json::obj(vec![
            ("type", Json::String("object".into())),
            ("description", Json::String("Map of path, glob, or dir/ to a reason. A string array of PATH=REASON lines also works.".into())),
        ]))),
        "heal_stubs" | "list_healable_stubs" => props.push(("min_wiki_length", integer("Minimum wiki length. Default 350."))),
        "mark_green" => props.push(("force", boolean("Override a failed wiki check. Requires a reason."))),
        "update_maps" => props.extend([
            ("full", boolean("Rehash every file instead of skipping unchanged size and mtime.")),
            ("max_files", integer("Parse at most this many changed files. Re-run while files_remaining_dirty > 0.")),
            ("edges", boolean("Include the whole edge list. Off by default: it runs to hundreds of KB on a mid-size repo. Use get_dependencies for one file.")),
        ]),
        _ => {}
    }
    props
}

/// Files listed by an MCP `session_bootstrap` that passes no `limit`.
const MCP_BOOTSTRAP_FILES: usize = 100;

fn string_prop(description: &str) -> Json {
    Json::obj(vec![
        ("type", Json::String("string".into())),
        ("description", Json::String(description.into())),
    ])
}

fn tool_spec(
    name: &str,
) -> (
    &'static str,
    &'static [&'static str],
    &'static [&'static str],
) {
    match name {
        "check_changes" => (
            "Compare mapped files and Green baselines and report content drift.",
            &["project_root"],
            &[],
        ),
        "record_change" => (
            "Record a semantic edit against one file and mark that file actionable.",
            &["project_root", "file", "reason"],
            &[],
        ),
        "record_deletion" => (
            "Record that a mapped file was removed and should leave the health matrix.",
            &["project_root", "file", "reason"],
            &[],
        ),
        "mark_green" => (
            "Mark a file Green after its wiki names the file's public symbols.",
            &["project_root", "file"],
            &["reason"],
        ),
        "record_changes" => (
            "Record git changes in one batch. Pass per-file reasons when you have them.",
            &["project_root"],
            &[],
        ),
        "verify_wikis" => (
            "Check every Green wiki against the public symbols currently in the source.",
            &["project_root"],
            &[],
        ),
        "prepare_edit" => (
            "Look up health, wiki text, dependencies, and dependents before editing a file.",
            &["project_root", "file"],
            &[],
        ),
        "session_bootstrap" => (
            "Return readiness, health, suggested actions, and the mapped file list for this root.",
            &["project_root"],
            &[],
        ),
        "suggest_next_actions" => (
            "Return the next agent actions, highest priority first.",
            &["project_root"],
            &[],
        ),
        "list_core_tools" => (
            "List the daily core tools and the full MCP tool catalogue.",
            &["project_root"],
            &[],
        ),
        "list_paths" => (
            "List mapped files under a project-relative prefix.",
            &["project_root"],
            &["prefix"],
        ),
        "search_journal" => (
            "Search journal entries by file path or reason text.",
            &["project_root", "query"],
            &["text"],
        ),
        "why_file" => (
            "Return the journal reasons recorded for one file.",
            &["project_root", "file"],
            &[],
        ),
        "get_dependencies" => (
            "Return internal edges, external imports, and unresolved imports for one file.",
            &["project_root", "file"],
            &[],
        ),
        "get_dependents" => (
            "Return the mapped files that import a given file.",
            &["project_root", "file"],
            &[],
        ),
        "get_cycles" => (
            "Return import cycles in the mapped graph.",
            &["project_root"],
            &[],
        ),
        "get_resolution_diagnostics" => (
            "Return resolution and barrel diagnostics for the current map.",
            &["project_root"],
            &[],
        ),
        "get_file_wiki" => (
            "Return the wiki markdown stored beside a source file.",
            &["project_root", "file"],
            &[],
        ),
        "get_files_needing_attention" => (
            "Return files whose health is Red or an actionable Yellow.",
            &["project_root"],
            &[],
        ),
        "get_project_status" => (
            "Return the same readiness snapshot as session bootstrap.",
            &["project_root"],
            &[],
        ),
        "get_current_project_root" => (
            "Return the absolute project root this call is using.",
            &["project_root"],
            &[],
        ),
        "get_barrel_reports" => (
            "Return barrel and incremental-resolution status for the current map.",
            &["project_root"],
            &[],
        ),
        "get_incremental_status" => (
            "Return whether the map is incremental and which barrels are recorded.",
            &["project_root"],
            &[],
        ),
        "update_maps" => (
            "Parse the scoped tree and commit one cache generation for the whole run.",
            &["project_root"],
            &[],
        ),
        "health" => (
            "Return the health matrix entries and the green, yellow, and red counts.",
            &["project_root"],
            &[],
        ),
        "validate" => (
            "Check health coverage and that the forward and reverse cache indexes agree.",
            &["project_root"],
            &[],
        ),
        "list_healable_stubs" => (
            "List Initial-stub files whose wiki is long enough to heal.",
            &["project_root"],
            &[],
        ),
        "heal_stubs" => (
            "Promote Initial stubs that already have a long enough wiki.",
            &["project_root"],
            &[],
        ),
        "seed_source_content_hashes" => (
            "Seed health rows from the current map without rewriting wikis.",
            &["project_root"],
            &[],
        ),
        "journal" => (
            "Return journal entries, optionally for one date.",
            &["project_root"],
            &[],
        ),
        "issues" => (
            "Return the same prioritized actions as suggest_next_actions.",
            &["project_root"],
            &[],
        ),
        _ => (
            "Run one Wikifier agent operation against project_root.",
            &["project_root"],
            &[],
        ),
    }
}

pub fn tool_schema(name: &str) -> Json {
    let (description, required, optional) = tool_spec(name);
    let mut props = vec![(
        "project_root".into(),
        string_prop("Absolute project root. Pass it on every call."),
    )];
    let mut fields: Vec<&str> = required
        .iter()
        .copied()
        .chain(optional.iter().copied())
        .filter(|field| *field != "project_root")
        .collect();
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
    for (field, schema) in extra_props(name) {
        props.push((field.into(), schema));
    }
    Json::obj(vec![
        ("name", Json::String(name.into())),
        ("description", Json::String(description.into())),
        (
            "inputSchema",
            Json::obj(vec![
                ("type", Json::String("object".into())),
                ("properties", Json::from_pairs(props)),
                (
                    "required",
                    Json::Array(
                        required
                            .iter()
                            .map(|field| Json::String((*field).into()))
                            .collect(),
                    ),
                ),
            ]),
        ),
    ])
}

pub fn handle_message(msg: &Json) -> Option<Json> {
    let id = msg.get("id").cloned();
    let method = msg.get("method").and_then(|m| m.as_str()).unwrap_or("");
    id.as_ref()?;
    let result = match method {
        "initialize" => initialize(),
        "tools/list" => Json::obj(vec![(
            "tools",
            Json::Array(
                MCP_TOOLS
                    .iter()
                    .filter(|n| active().allows(n))
                    .map(|n| tool_schema(n))
                    .collect(),
            ),
        )]),
        "resources/list" => resources_list(),
        "prompts/list" => prompts_list(),
        "resources/read" => resource_read(msg),
        "prompts/get" => prompt_get(msg),
        "tools/call" => call_tool(msg),
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

fn initialize() -> Json {
    let state = groups_state();
    // listChanged is always advertised: an agent may add an agent-tools block mid-session.
    // It is the one field that differs from 5.1.0 when no switch and no block are set.
    let tools = Json::obj(vec![("listChanged", Json::Bool(true))]);
    let mut value = Json::obj(vec![
        ("protocolVersion", Json::String("2024-11-05".into())),
        (
            "capabilities",
            Json::obj(vec![
                ("tools", tools),
                ("resources", Json::obj(vec![])),
                ("prompts", Json::obj(vec![])),
            ]),
        ),
        (
            "serverInfo",
            Json::obj(vec![
                ("name", Json::String("wikifier".into())),
                ("version", Json::String(api::VERSION.into())),
            ]),
        ),
    ]);
    if state.shaped {
        value.insert("instructions", Json::String(state.instructions()));
    }
    value
}

fn resources_list() -> Json {
    Json::obj(vec![(
        "resources",
        Json::Array(
            [
                "wikifier://library",
                "wikifier://health",
                "wikifier://pending",
                "wikifier://journal",
            ]
            .into_iter()
            .map(|u| {
                Json::obj(vec![
                    ("uri", Json::String(u.into())),
                    ("name", Json::String(u.into())),
                ])
            })
            .collect(),
        ),
    )])
}

fn prompts_list() -> Json {
    Json::obj(vec![(
        "prompts",
        Json::Array(
            [
                "review_pending_changes",
                "audit_project_health",
                "plan_refactoring",
                "find_architectural_smells",
                "understand_codebase_structure",
                "review_recent_changes",
                "generate_project_health_report",
                "onboard_to_module",
            ]
            .into_iter()
            .map(|n| Json::obj(vec![("name", Json::String(n.into()))]))
            .collect(),
        ),
    )])
}

fn call_tool(msg: &Json) -> Json {
    let params = msg.get("params");
    let name = params
        .and_then(|p| p.get("name"))
        .and_then(|n| n.as_str())
        .unwrap_or("")
        .to_string();
    let args = params.and_then(|p| p.get("arguments")).cloned();
    if !active().allows(&name) {
        let refusal = Json::obj(vec![
            ("success", Json::Bool(false)),
            ("error", Json::String(active().refusal(&name))),
            ("error_type", Json::String("ToolDisabled".into())),
        ]);
        return tool_result(refusal, false, &name);
    }
    if let Some(err) = missing_required(&name, args.as_ref()) {
        return tool_result(err, false, &name);
    }
    let root = args
        .as_ref()
        .and_then(|a| a.get("project_root"))
        .and_then(|r| r.as_str())
        .map(PathBuf::from)
        .or_else(|| {
            std::env::var("WIKIFIER_PROJECT_ROOT")
                .ok()
                .map(PathBuf::from)
        })
        .unwrap_or_else(|| std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")));
    let mut flags = BTreeMap::new();
    let mut positional = Vec::new();
    if let Some(file) = args
        .as_ref()
        .and_then(|a| a.get("file"))
        .and_then(|f| f.as_str())
    {
        positional.push(file.to_string());
    }
    if let Some(reason) = args
        .as_ref()
        .and_then(|a| a.get("reason"))
        .and_then(|f| f.as_str())
    {
        positional.push(reason.to_string());
    }
    copy_str(&args, &mut flags, "prefix");
    if let Some(q) = args
        .as_ref()
        .and_then(|a| a.get("query").or_else(|| a.get("text")))
        .and_then(|f| f.as_str())
    {
        flags.insert("query".into(), q.into());
    }
    copy_str(&args, &mut flags, "directory");
    copy_str(&args, &mut flags, "since");
    copy_str(&args, &mut flags, "default");
    copy_str(&args, &mut flags, "detail");
    copy_str(&args, &mut flags, "format");
    copy_str(&args, &mut flags, "prefix");
    if let Some(depth) = args.as_ref().and_then(|a| a.get("depth")) {
        if let Some(text) = json_text(depth) {
            flags.insert("depth".into(), text);
        }
    }
    if let Some(limit) = args
        .as_ref()
        .and_then(|a| a.get("limit").or_else(|| a.get("max_items")))
    {
        if let Some(text) = json_text(limit) {
            flags.insert("limit".into(), text.clone());
            flags.insert("max-items".into(), text);
        }
    }
    if let Some(min) = args.as_ref().and_then(|a| {
        a.get("min_wiki_length")
            .or_else(|| a.get("min-wiki-length"))
    }) {
        if let Some(text) = json_text(min) {
            flags.insert("min-wiki-length".into(), text);
        }
    }
    if arg_on(args.as_ref(), "recursive") {
        flags.insert("recursive".into(), "true".into());
    }
    if arg_on(args.as_ref(), "low_confidence_only") || arg_on(args.as_ref(), "low-confidence-only")
    {
        flags.insert("low-confidence-only".into(), "true".into());
    }
    if arg_on(args.as_ref(), "unresolved_only") || arg_on(args.as_ref(), "unresolved-only") {
        flags.insert("unresolved-only".into(), "true".into());
    }
    if args
        .as_ref()
        .and_then(|a| a.get("analysis"))
        .and_then(|v| v.as_bool())
        == Some(false)
    {
        flags.insert("no-analysis".into(), "true".into());
    }
    if let Some(max) = args
        .as_ref()
        .and_then(|a| a.get("max_files").or_else(|| a.get("max-files")))
    {
        if let Some(text) = json_text(max) {
            flags.insert("max-files".into(), text);
        }
    }
    for key in [
        "full", "quiet", "stream", "green", "force", "dry_run", "dry-run", "summary",
    ] {
        if arg_on(args.as_ref(), key) {
            let stored = if key == "dry_run" { "dry-run" } else { key };
            flags.insert(stored.into(), "true".into());
        }
    }
    if let Some(only) = args.as_ref().and_then(|a| a.get("only")) {
        match only {
            Json::String(text) => {
                flags.insert("only".into(), text.clone());
            }
            Json::Array(items) => {
                let joined = items
                    .iter()
                    .filter_map(|v| v.as_str())
                    .collect::<Vec<_>>()
                    .join("\n");
                flags.insert("only".into(), joined);
            }
            _ => {}
        }
    }
    if let Some(reasons) = args.as_ref().and_then(|a| a.get("reasons")) {
        match reasons {
            Json::String(text) => {
                flags.insert("reasons".into(), text.clone());
            }
            Json::Array(items) => {
                let joined = items
                    .iter()
                    .filter_map(|v| v.as_str())
                    .collect::<Vec<_>>()
                    .join("\n");
                flags.insert("reasons".into(), joined);
            }
            Json::Object(map) => {
                let joined = map
                    .iter()
                    .filter_map(|(key, value)| {
                        value.as_str().map(|reason| format!("{key}={reason}"))
                    })
                    .collect::<Vec<_>>()
                    .join("\n");
                flags.insert("reasons".into(), joined);
            }
            _ => {}
        }
    }
    // Over MCP the edge list is opt-in. Its size grows with the repo and every byte lands in
    // the agent's context; `edges_persisted` still reports the count.
    if name == "update_maps" && !arg_on(args.as_ref(), "edges") {
        flags.insert("quiet".into(), "true".into());
    }
    // The bootstrap file list grows with the repo (about 21 KB at 587 files). Over MCP it
    // is capped unless the caller asks; map_index already gives the folder counts.
    if matches!(name.as_str(), "session_bootstrap" | "get_project_status")
        && !flags.contains_key("limit")
    {
        flags.insert("limit".into(), MCP_BOOTSTRAP_FILES.to_string());
    }
    let textual = flags.get("format").map(|s| s == "text").unwrap_or(false);
    let tool_name = name.clone();
    let from_arg = args
        .as_ref()
        .and_then(|a| a.get("timeout_s"))
        .and_then(|value| match value {
            Json::Int(n) if *n > 0 => Some(*n as u64),
            Json::Float(n) if *n > 0.0 => Some(*n as u64),
            Json::String(text) => text.parse::<u64>().ok().filter(|n| *n > 0),
            _ => None,
        });
    let deadline = from_arg
        .or_else(|| {
            std::env::var("WIKIFIER_MCP_DEADLINE_S")
                .ok()
                .and_then(|s| s.parse().ok())
        })
        .unwrap_or(60)
        .max(1);
    let (tx, rx) = mpsc::channel();
    std::thread::spawn(move || {
        let value = if !root.is_dir() {
            Json::obj(vec![
                ("success", Json::Bool(false)),
                ("error", Json::String("project root does not exist".into())),
                ("error_type", Json::String("ProjectRootError".into())),
            ])
        } else {
            api::dispatch(&name, &root, &positional, &flags)
        };
        let _ = tx.send(value);
    });
    let value = match rx.recv_timeout(Duration::from_secs(deadline)) {
        Ok(value) => value,
        Err(_) => Json::obj(vec![
            ("success", Json::Bool(false)),
            (
                "error",
                Json::String(format!("mcp call exceeded {deadline}s deadline")),
            ),
            ("error_type", Json::String("DeadlineExceeded".into())),
            ("timed_out", Json::Bool(true)),
            ("may_still_complete", Json::Bool(true)),
        ]),
    };
    let value = if tool_name == "list_core_tools" && groups_state().shaped {
        with_active_groups(value)
    } else {
        value
    };
    tool_result(value, textual, &tool_name)
}

/// `list_core_tools` under `WIKIFIER_TOOLS` / `WIKIFIER_DISABLE`: only the tools this
/// server exposes, plus the one-line group summary.
fn with_active_groups(mut value: Json) -> Json {
    for key in ["core", "tools"] {
        if let Some(Json::Array(items)) = value.get(key) {
            let kept: Vec<Json> = items
                .iter()
                .filter(|item| item.as_str().is_some_and(|name| active().allows(name)))
                .cloned()
                .collect();
            value.insert(key, Json::Array(kept));
        }
    }
    value.insert("groups", Json::String(groups_state().instructions()));
    value
}

/// A required argument the client left out fails the call and names the accepted fields,
/// so an agent that guessed `file_path` or `path` can retry at once. Without this the tool
/// ran with an empty path and answered `success: true` with every field empty.
/// `project_root` is exempt: it falls back to WIKIFIER_PROJECT_ROOT, then the cwd.
fn missing_required(name: &str, args: Option<&Json>) -> Option<Json> {
    if !MCP_TOOLS.contains(&name) {
        return None;
    }
    let (_, required, _) = tool_spec(name);
    let present = |key: &str| {
        let value = args.and_then(|a| a.get(key)).or_else(|| {
            (key == "query")
                .then(|| args.and_then(|a| a.get("text")))
                .flatten()
        });
        matches!(value, Some(Json::String(text)) if !text.trim().is_empty())
    };
    let missing: Vec<&str> = required
        .iter()
        .copied()
        .filter(|field| *field != "project_root" && !present(field))
        .collect();
    if missing.is_empty() {
        return None;
    }
    let names = |value: Option<&Json>| {
        value
            .and_then(|v| v.as_object())
            .map(|map| map.keys().cloned().collect::<Vec<_>>().join(", "))
            .unwrap_or_default()
    };
    let schema = tool_schema(name);
    let accepted = names(schema.get("inputSchema").and_then(|s| s.get("properties")));
    let given = names(args);
    let given = if given.is_empty() {
        "none".to_string()
    } else {
        given
    };
    Some(Json::obj(vec![
        ("success", Json::Bool(false)),
        (
            "error",
            Json::String(format!(
                "{name} needs {} as a non-empty string. Accepted arguments: {accepted}. Received: {given}.",
                missing.join(", ")
            )),
        ),
        ("error_type", Json::String("InvalidArguments".into())),
    ]))
}

fn tool_result(value: Json, textual: bool, tool_name: &str) -> Json {
    let is_error = value.get("success").and_then(|s| s.as_bool()) == Some(false);
    let text = if textual {
        crate::text_out::render(tool_name, &value).unwrap_or_else(|| value.to_string())
    } else {
        value.to_string()
    };
    Json::obj(vec![
        (
            "content",
            Json::Array(vec![Json::obj(vec![
                ("type", Json::String("text".into())),
                ("text", Json::String(text)),
            ])]),
        ),
        ("structuredContent", value),
        ("isError", Json::Bool(is_error)),
    ])
}

fn copy_str(args: &Option<Json>, flags: &mut BTreeMap<String, String>, key: &str) {
    if let Some(text) = args
        .as_ref()
        .and_then(|a| a.get(key))
        .and_then(|v| v.as_str())
    {
        flags.insert(key.into(), text.into());
    }
}

fn json_text(value: &Json) -> Option<String> {
    match value {
        Json::String(text) => Some(text.clone()),
        Json::Int(n) => Some(n.to_string()),
        _ => None,
    }
}

fn arg_on(args: Option<&Json>, key: &str) -> bool {
    match args.and_then(|a| a.get(key)) {
        Some(Json::Bool(v)) => *v,
        Some(Json::String(text)) => text == "true" || text == "1",
        _ => false,
    }
}

fn resource_read(msg: &Json) -> Json {
    let params = msg.get("params");
    let uri = params
        .and_then(|p| p.get("uri"))
        .and_then(|u| u.as_str())
        .unwrap_or("");
    let root = params
        .and_then(|p| p.get("project_root"))
        .and_then(|r| r.as_str())
        .map(PathBuf::from)
        .or_else(|| {
            std::env::var("WIKIFIER_PROJECT_ROOT")
                .ok()
                .map(PathBuf::from)
        })
        .unwrap_or_else(|| std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")));
    let text = match uri {
        "wikifier://library" => {
            std::fs::read_to_string(root.join("library.md")).unwrap_or_default()
        }
        "wikifier://health" => {
            std::fs::read_to_string(root.join("file_health.md")).unwrap_or_default()
        }
        "wikifier://pending" => {
            std::fs::read_to_string(root.join("pending_updates.md")).unwrap_or_default()
        }
        "wikifier://journal" => {
            let entries = api::read_journal(&root, None);
            let mut text = String::new();
            for entry in entries {
                let _ = std::fmt::Write::write_fmt(
                    &mut text,
                    format_args!(
                        "## [{}] {}\n**File:** {}\n**Reason:** {}\n",
                        entry.stamp, entry.action, entry.file, entry.reason
                    ),
                );
            }
            text
        }
        _ => {
            return Json::obj(vec![
                ("success", Json::Bool(false)),
                ("error", Json::String(format!("unknown resource {uri}"))),
                ("error_type", Json::String("ResourceNotFound".into())),
            ])
        }
    };
    Json::obj(vec![(
        "contents",
        Json::Array(vec![Json::obj(vec![
            ("uri", Json::String(uri.into())),
            ("mimeType", Json::String("text/markdown".into())),
            ("text", Json::String(text)),
        ])]),
    )])
}

fn prompt_get(msg: &Json) -> Json {
    let name = msg
        .get("params")
        .and_then(|p| p.get("name"))
        .and_then(|n| n.as_str())
        .unwrap_or("");
    if name.is_empty() {
        return Json::obj(vec![
            ("success", Json::Bool(false)),
            ("error", Json::String("missing prompt name".into())),
            ("error_type", Json::String("PromptNotFound".into())),
        ]);
    }
    let text = prompt_text(name).to_string();
    Json::obj(vec![
        ("description", Json::String(name.into())),
        (
            "messages",
            Json::Array(vec![Json::obj(vec![
                ("role", Json::String("user".into())),
                (
                    "content",
                    Json::obj(vec![
                        ("type", Json::String("text".into())),
                        ("text", Json::String(text)),
                    ]),
                ),
            ])]),
        ),
    ])
}

fn prompt_text(name: &str) -> &'static str {
    match name {
        "review_pending_changes" => "Review pending documentation work.\n1. session_bootstrap() for actions[].\n2. For each actionable file: prepare_edit(file), get_file_wiki(file), get_dependents(file).\n3. Refresh the wiki, then mark_green(file). Never skip record_change after code edits.",
        "audit_project_health" => "Audit documentation health.\n1. get_project_status.\n2. get_files_needing_attention.\n3. search_journal for recent activity.\n4. suggest_next_actions and report priorities from actions[].",
        "plan_refactoring" => "Plan a refactor of the target file.\n1. get_dependents for the blast radius.\n2. get_dependencies with detail=full and read confidence.\n3. get_cycles and use severity plus the break hint when the file is in a cycle.",
        "find_architectural_smells" => "Find architectural smells.\nCycles: get_cycles and rank by severity and external_blast_radius.\nFragile edges: get_dependencies with low_confidence_only=true.\nHubs: files with many get_dependents results.",
        "understand_codebase_structure" => "Onboard to this codebase.\n1. session_bootstrap, then list_paths for the folders you need.\n2. prepare_edit, get_dependencies, and get_dependents for the key files.\n3. get_cycles for structural risks.",
        "review_recent_changes" => "Review recent activity.\n1. search_journal and journal for record-change entries.\n2. why_file on each changed file: is it Green again?\n3. Report files that were recorded but not marked green.",
        "generate_project_health_report" => "Write a project health report.\nInclude green, yellow, and red counts, the files needing attention, the most depended-on modules, and cycle severity.",
        "onboard_to_module" => "Understand one module.\n1. get_file_wiki.\n2. get_dependencies with detail=full.\n3. get_dependents.\n4. get_cycles when the file is in a cycle.\nSummarize its role, fragile edges, and blast radius.",
        _ => "Use Wikifier. Call session_bootstrap, then check_changes, then act only on Red and actionable Yellow files.",
    }
}

pub fn serve_stdio() -> Result<(), String> {
    // A typo in WIKIFIER_TOOLS / WIKIFIER_DISABLE stops the server, so the MCP client
    // shows it as failed instead of serving a silently different tool set.
    // A block mistake in AGENTS.md only warns: an agent wrote it and reads the warning.
    if let Err(message) = configure() {
        eprintln!("{message}");
        std::process::exit(2);
    }
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
        if refresh() {
            writeln!(stdout, "{LIST_CHANGED}").map_err(|e| e.to_string())?;
        }
        if let Some(resp) = handle_message(&msg) {
            writeln!(stdout, "{resp}").map_err(|e| e.to_string())?;
            stdout.flush().map_err(|e| e.to_string())?;
        }
    }
    Ok(())
}
