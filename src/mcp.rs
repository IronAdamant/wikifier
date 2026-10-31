//! Stdio MCP (JSON-RPC) over the same functions as the CLI.

use std::collections::BTreeMap;
use std::io::{BufRead, Read, Write};
use std::path::PathBuf;

use crate::api::{self, MCP_TOOLS};
use crate::jsonutil::{self, Json};

pub fn tool_schema(name: &str) -> Json {
    let mut props = vec![("project_root".into(), Json::obj(vec![("type", Json::String("string".into()))]))];
    let needs_file = matches!(name,
        "record_change" | "record_deletion" | "mark_green" | "prepare_edit" | "why_file"
        | "get_dependencies" | "get_dependents" | "get_file_wiki");
    if needs_file {
        props.push(("file".into(), Json::obj(vec![("type", Json::String("string".into()))])));
    }
    if matches!(name, "record_change" | "record_deletion" | "mark_green") {
        props.push(("reason".into(), Json::obj(vec![("type", Json::String("string".into()))])));
    }
    if name == "list_paths" {
        props.push(("prefix".into(), Json::obj(vec![("type", Json::String("string".into()))])));
    }
    if name == "search_journal" {
        props.push(("query".into(), Json::obj(vec![("type", Json::String("string".into()))])));
        props.push(("text".into(), Json::obj(vec![("type", Json::String("string".into()))])));
    }
    Json::obj(vec![
        ("name", Json::String(name.into())),
        ("description", Json::String(format!("Wikifier {name}"))),
        ("inputSchema", Json::obj(vec![
            ("type", Json::String("object".into())),
            ("properties", Json::from_pairs(props)),
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
    let mut buffered;
    loop {
        let mut line = String::new();
        let n = reader.read_line(&mut line).map_err(|e| e.to_string())?;
        if n == 0 {
            break;
        }
        if line.to_ascii_lowercase().starts_with("content-length:") {
            let len: usize = line.split(':').nth(1).unwrap_or("0").trim().parse().unwrap_or(0);
            let mut discard = String::new();
            let _ = reader.read_line(&mut discard);
            let mut body = vec![0u8; len];
            reader.read_exact(&mut body).map_err(|e| e.to_string())?;
            buffered = String::from_utf8_lossy(&body).into_owned();
        } else {
            buffered = line;
        }
        let trimmed = buffered.trim();
        if trimmed.is_empty() {
            continue;
        }
        let msg = match jsonutil::parse(trimmed) {
            Ok(v) => v,
            Err(_) => continue,
        };
        if let Some(resp) = handle_message(&msg) {
            let bytes = resp.to_string();
            write!(stdout, "Content-Length: {}\r\n\r\n{}", bytes.len(), bytes).map_err(|e| e.to_string())?;
            stdout.flush().map_err(|e| e.to_string())?;
        }
    }
    Ok(())
}
