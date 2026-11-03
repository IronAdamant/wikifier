//! Pending-update bullets.
//! New lines use the Python shape `- path: message`.
//! Readers still accept the older `- path — message` lines.

/// File path of a pending bullet, if `line` is an item.
pub fn file_of(line: &str) -> Option<&str> {
    let body = line.trim().strip_prefix("- ")?;
    if let Some((path, _)) = body.split_once(": ") {
        let path = path.trim();
        if !path.is_empty() {
            return Some(path);
        }
    }
    let legacy = body.split(" — ").next().unwrap_or(body);
    let legacy = legacy.split(" - ").next().unwrap_or(legacy).trim();
    if legacy.is_empty() {
        None
    } else {
        Some(legacy)
    }
}

pub fn format_item(rel: &str, message: &str) -> String {
    format!("- {rel}: {message}\n")
}

/// Append `message` for `rel` when that file is not already listed.
pub fn append_item(text: &str, rel: &str, message: &str) -> String {
    if text.lines().any(|line| file_of(line) == Some(rel)) {
        return text.to_string();
    }
    let mut out = if text.trim().is_empty() {
        "# Pending Updates\n\n".to_string()
    } else {
        text.to_string()
    };
    if !out.is_empty() && !out.ends_with('\n') {
        out.push('\n');
    }
    out.push_str(&format_item(rel, message));
    out
}

pub fn record_message(reason: &str) -> String {
    format!("LLM/agent edit — {reason}")
}

pub const CHECK_MESSAGE: &str = "Content change detected — review, refresh wiki, then mark-green";
