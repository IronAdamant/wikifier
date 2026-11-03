//! Prose for `wikifier --text`. The default CLI print stays JSON.

use crate::jsonutil::Json;

pub fn render(command: &str, value: &Json) -> Option<String> {
    if value.get("success").and_then(|s| s.as_bool()) == Some(false) {
        let error = value
            .get("error")
            .and_then(|v| v.as_str())
            .unwrap_or("failed");
        let mut text = format!("error: {error}\n");
        if let Some(Json::Array(issues)) = value.get("issues") {
            for issue in issues {
                if let Some(line) = issue.as_str() {
                    text.push_str(&format!("  - {line}\n"));
                }
            }
        }
        return Some(text);
    }
    match command {
        "check-changes" | "check_changes" => {
            let n = int_of(value, "dirty_total");
            Some(format!(
                "check_changes: {n} file(s) newly flagged Yellow.\n"
            ))
        }
        "record-change" | "record_change" => {
            let file = text_of(value, "file");
            if value.get("duplicate_skipped").and_then(|v| v.as_bool()) == Some(true) {
                Some(format!(
                    "Recorded change to {file} was already journaled in the last 120 seconds.\n"
                ))
            } else {
                Some(format!("Recorded change to {file}: Yellow, pending + journal updated. Refresh its wiki, then mark_green.\n"))
            }
        }
        "mark-green" | "mark_green" => {
            let file = text_of(value, "file");
            let verification = text_of(value, "verification");
            Some(format!("Marked {file} Green ({verification}).\n"))
        }
        "record-deletion" | "record_deletion" => Some(format!(
            "Recorded deletion of {}.\n",
            text_of(value, "file")
        )),
        "health" => Some(health_text(value)),
        "suggest-next" | "suggest" | "suggest-next-actions" | "suggest_next_actions" => {
            Some(actions_text(value))
        }
        "cycles" | "get_cycles" => Some(cycles_text(value)),
        "journal" => Some(journal_text(value)),
        "init" => Some(init_text(value)),
        "heal-stubs" | "heal_stubs" => {
            let n = int_of(value, "healed_count");
            let verb = if value.get("dry_run").and_then(|v| v.as_bool()) == Some(true) {
                "Would heal"
            } else {
                "Healed"
            };
            let noun = if n == 1 { "entry" } else { "entries" };
            Some(format!("{verb} {n} stub {noun}.\n"))
        }
        "daemon" => Some(daemon_text(value)),
        "issues" => Some(actions_text(value)),
        _ => None,
    }
}

fn health_text(value: &Json) -> String {
    if value.get("entries").is_none() {
        if let Some(summary) = value.get("health_summary") {
            return format!("# Health summary\n\n{summary}\n");
        }
        return format!("{value}\n");
    }
    let mut lines = vec!["# Documentation Health Matrix".to_string(), String::new()];
    let entries = value
        .get("entries")
        .and_then(|v| v.as_array())
        .map(|items| items.to_vec())
        .unwrap_or_default();
    for entry in entries.iter().take(60) {
        let file = entry.get("file").and_then(|v| v.as_str()).unwrap_or("");
        let status = entry.get("status").and_then(|v| v.as_str()).unwrap_or("");
        let updated = entry
            .get("last_updated")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let reason = entry.get("reason").and_then(|v| v.as_str()).unwrap_or("");
        let reason = if reason.chars().count() > 80 {
            reason.chars().take(80).collect()
        } else {
            reason.to_string()
        };
        lines.push(format!("- {file}: {status} | {updated} | {reason}"));
    }
    if entries.len() > 60 {
        lines.push(format!(
            "... ({} more; use --json or --summary)",
            entries.len() - 60
        ));
    }
    lines.push(String::new());
    lines.join("\n")
}

fn actions_text(value: &Json) -> String {
    let actions = value
        .get("actions")
        .and_then(|v| v.as_array())
        .map(|items| items.to_vec())
        .unwrap_or_default();
    if actions.is_empty() {
        return "No suggested actions.\n".into();
    }
    let mut lines = Vec::new();
    for (i, action) in actions.iter().enumerate() {
        let reason = action.get("reason").and_then(|v| v.as_str()).unwrap_or("");
        let file = action.get("file").and_then(|v| v.as_str()).unwrap_or("");
        if file.is_empty() {
            lines.push(format!("{}. {reason}", i + 1));
        } else {
            lines.push(format!("{}. {file}: {reason}", i + 1));
        }
    }
    lines.push(String::new());
    lines.join("\n")
}

fn cycles_text(value: &Json) -> String {
    let count = int_of(value, "count");
    let mut lines = vec![
        "=== Circular Dependencies ===".to_string(),
        format!("Clusters: {count}"),
    ];
    if let Some(Json::Array(cycles)) = value.get("cycles") {
        if cycles.is_empty() {
            lines.push("No circular dependencies detected.".into());
        }
        for (i, cycle) in cycles.iter().enumerate() {
            let files = cycle
                .get("files")
                .and_then(|v| v.as_array())
                .map(|items| {
                    items
                        .iter()
                        .filter_map(|v| v.as_str())
                        .collect::<Vec<_>>()
                        .join(" → ")
                })
                .unwrap_or_default();
            lines.push(format!("{}. {files}", i + 1));
            if let Some(severity) = cycle.get("severity").and_then(|v| v.as_str()) {
                let score = cycle
                    .get("score")
                    .map(|v| v.to_string())
                    .unwrap_or_default();
                let blast = cycle
                    .get("external_blast_radius")
                    .map(|v| v.to_string())
                    .unwrap_or_default();
                let strategy = cycle
                    .get("recommendation")
                    .and_then(|v| v.get("strategy"))
                    .and_then(|v| v.as_str())
                    .unwrap_or("");
                lines.push(format!(
                    "   severity={severity} score={score} blast={blast} fix={strategy}"
                ));
            }
        }
    }
    if let Some(Json::Array(ranked)) = value.get("reverse_dependencies") {
        if !ranked.is_empty() {
            lines.push(String::new());
            lines.push("Most depended-on files:".into());
            for row in ranked.iter().take(10) {
                let file = row.get("file").and_then(|v| v.as_str()).unwrap_or("");
                let n = row
                    .get("dependents")
                    .map(|v| v.to_string())
                    .unwrap_or_default();
                lines.push(format!("- {file} ({n})"));
            }
        }
    }
    lines.push(String::new());
    lines.join("\n")
}

fn journal_text(value: &Json) -> String {
    let entries = value
        .get("entries")
        .and_then(|v| v.as_array())
        .map(|items| items.to_vec())
        .unwrap_or_default();
    if entries.is_empty() {
        let date = value
            .get("date")
            .and_then(|v| v.as_str())
            .unwrap_or("today");
        return format!("No journal entries for {date} yet.\n");
    }
    let mut text = String::new();
    for entry in entries {
        let stamp = entry.get("stamp").and_then(|v| v.as_str()).unwrap_or("");
        let action = entry.get("action").and_then(|v| v.as_str()).unwrap_or("");
        let file = entry.get("file").and_then(|v| v.as_str()).unwrap_or("");
        let reason = entry.get("reason").and_then(|v| v.as_str()).unwrap_or("");
        text.push_str(&format!(
            "## [{stamp}] {action}\n**File:** {file}\n**Reason:** {reason}\n\n"
        ));
    }
    text
}

fn init_text(value: &Json) -> String {
    let mut lines = vec!["[wikifier] Initialised the project".to_string()];
    if let Some(Json::Array(created)) = value.get("created") {
        for item in created {
            if let Some(name) = item.as_str() {
                lines.push(format!("  created {name}"));
            }
        }
    }
    if value.get("index_copied").and_then(|v| v.as_bool()) == Some(false) {
        lines.push("  left index.html uncopied (--no-copy)".into());
    }
    lines.push("Next steps:".into());
    lines.push("  1. Edit monitored_paths.txt and map_paths.txt".into());
    lines.push("  2. wikifier update-maps".into());
    lines.push("  3. wikifier session-bootstrap".into());
    lines.push(String::new());
    lines.join("\n")
}

fn daemon_text(value: &Json) -> String {
    let action = text_of(value, "action");
    if action == "logs" {
        let log = value.get("log").and_then(|v| v.as_str()).unwrap_or("");
        if log.is_empty() {
            return "No daemon log file found yet.\n".into();
        }
        return format!("{log}\n");
    }
    if action == "status" || action == "start" || action == "stop" || action == "restart" {
        let running = value
            .get("running")
            .and_then(|v| v.as_bool())
            .unwrap_or(false);
        let pid = value.get("pid").map(|v| v.to_string()).unwrap_or_default();
        if running {
            return format!("Wikifier daemon is running (PID {pid}).\n");
        }
        return "Wikifier daemon is not running.\n".into();
    }
    value
        .get("message")
        .and_then(|v| v.as_str())
        .map(|s| format!("{s}\n"))
        .unwrap_or_else(|| format!("{value}\n"))
}

fn text_of(value: &Json, key: &str) -> String {
    value
        .get(key)
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string()
}

fn int_of(value: &Json, key: &str) -> i64 {
    match value.get(key) {
        Some(Json::Int(n)) => *n,
        _ => 0,
    }
}
