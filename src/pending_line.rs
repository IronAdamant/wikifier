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

/// The line an empty queue shows. It goes when the first item arrives and comes back when
/// the last one leaves, so the file never says "no pending items" above a list of items.
pub const EMPTY_NOTE: &str = "(no pending items — run check-changes after making edits)";

/// Append `message` for `rel` when that file is not already listed.
pub fn append_item(text: &str, rel: &str, message: &str) -> String {
    if text.lines().any(|line| file_of(line) == Some(rel)) {
        return text.to_string();
    }
    let mut out = if text.trim().is_empty() {
        "# Pending Updates\n\n".to_string()
    } else {
        text.lines()
            .filter(|line| line.trim() != EMPTY_NOTE)
            .map(|line| format!("{line}\n"))
            .collect()
    };
    out.push_str(&format_item(rel, message));
    out
}

/// `text` without the item for `rel`. The empty-queue note returns with the last item.
pub fn remove_item(text: &str, rel: &str) -> String {
    let mut out = String::new();
    for line in text.lines() {
        if file_of(line) != Some(rel) {
            out.push_str(line);
            out.push('\n');
        }
    }
    let empty = out.lines().all(|line| file_of(line).is_none());
    if empty && !out.contains(EMPTY_NOTE) {
        if !out.ends_with("\n\n") {
            out.push('\n');
        }
        out.push_str(EMPTY_NOTE);
        out.push('\n');
    }
    out
}

/// A `record-change` item: the agent's reason, then what closes the item.
pub fn record_message(reason: &str) -> String {
    format!("{reason} — refresh the wiki, then mark-green")
}

pub const CHECK_MESSAGE: &str = "Content change detected — review, refresh wiki, then mark-green";
