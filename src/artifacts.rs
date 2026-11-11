//! Read Python 4.7 health, journal, pending, and path-list files as they are.

use std::fs;
use std::path::{Path, PathBuf};

use crate::jsonutil::Json;
use crate::timeutil::{date_parts, local_stamp};

#[derive(Clone, Debug)]
pub struct HealthRow {
    pub file: String,
    pub status: String,
    pub last_updated: String,
    pub reason: String,
    pub source_hash: String,
    pub verification: String,
    pub public_symbols: String,
    pub wiki_hash: String,
    pub source_mtime_ns: String,
    /// Inclusive 1-based ranges in the current file since the last green snapshot.
    pub changed_lines: Vec<(u32, u32)>,
}

impl HealthRow {
    pub fn new(
        file: impl Into<String>,
        status: impl Into<String>,
        last_updated: impl Into<String>,
        reason: impl Into<String>,
        source_hash: impl Into<String>,
        verification: impl Into<String>,
    ) -> Self {
        Self {
            file: file.into(),
            status: status.into(),
            last_updated: last_updated.into(),
            reason: reason.into(),
            source_hash: source_hash.into(),
            verification: verification.into(),
            public_symbols: String::new(),
            wiki_hash: String::new(),
            source_mtime_ns: String::new(),
            changed_lines: Vec::new(),
        }
    }

    pub fn keep_baseline_from(&mut self, old: &HealthRow) {
        if self.public_symbols.is_empty() {
            self.public_symbols = old.public_symbols.clone();
        }
        if self.wiki_hash.is_empty() {
            self.wiki_hash = old.wiki_hash.clone();
        }
        if self.source_mtime_ns.is_empty() {
            self.source_mtime_ns = old.source_mtime_ns.clone();
        }
    }
}

fn changed_lines_json(ranges: &[(u32, u32)]) -> Json {
    Json::Array(
        ranges
            .iter()
            .map(|(start, end)| {
                Json::obj(vec![
                    ("start", Json::Int(*start as i64)),
                    ("end", Json::Int(*end as i64)),
                ])
            })
            .collect(),
    )
}

fn parse_changed_lines(value: Option<&Json>) -> Vec<(u32, u32)> {
    let Some(Json::Array(items)) = value else {
        return Vec::new();
    };
    let mut out = Vec::new();
    for item in items {
        let (start, end) = match item {
            Json::Array(pair) => (
                pair.first().and_then(json_line),
                pair.get(1).and_then(json_line),
            ),
            _ => (
                item.get("start").and_then(json_line),
                item.get("end").and_then(json_line),
            ),
        };
        if let (Some(start), Some(end)) = (start, end) {
            if start > 0 && end >= start {
                out.push((start, end));
            }
        }
    }
    out
}

fn json_line(value: &Json) -> Option<u32> {
    match value {
        Json::Int(n) if *n > 0 && *n <= i64::from(u32::MAX) => Some(*n as u32),
        _ => None,
    }
}

/// Replace a user-facing state file (health, journal, pending) atomically and durably: temp
/// file, sync, rename, directory flush. Unlike the derived cache, these hold the agents'
/// recorded reasons and baselines and cannot be rebuilt from the sources.
pub fn write_durable(path: &Path, bytes: &[u8]) -> Result<(), String> {
    crate::cache::atomic_write(path, bytes)
}

pub fn read_health(root: &Path) -> Vec<HealthRow> {
    let json_path = root.join("file_health.json");
    if json_path.is_file() {
        if let Some(rows) = read_health_json(&json_path) {
            if !rows.is_empty() {
                return rows;
            }
        }
    }
    read_health_md(&root.join("file_health.md"))
}

fn read_health_json(path: &Path) -> Option<Vec<HealthRow>> {
    let text = fs::read_to_string(path).ok()?;
    let json = crate::jsonutil::parse(&text).ok()?;
    let entries = json.get("entries")?.as_object()?;
    let mut rows = Vec::new();
    for (file, ent) in entries {
        let mut row = HealthRow::new(
            file.clone(),
            ent.get("status").and_then(|s| s.as_str()).unwrap_or(""),
            ent.get("last_updated")
                .and_then(|s| s.as_str())
                .unwrap_or(""),
            ent.get("reason").and_then(|s| s.as_str()).unwrap_or(""),
            ent.get("source_content_hash")
                .and_then(|s| s.as_str())
                .unwrap_or(""),
            ent.get("verification")
                .and_then(|s| s.as_str())
                .unwrap_or(""),
        );
        row.public_symbols = symbols_field(ent.get("public_symbols"));
        row.wiki_hash = ent
            .get("wiki_hash")
            .and_then(|s| s.as_str())
            .unwrap_or("")
            .to_string();
        row.source_mtime_ns = ent
            .get("source_mtime_ns")
            .and_then(|s| s.as_str())
            .unwrap_or("")
            .to_string();
        row.changed_lines = parse_changed_lines(ent.get("changed_lines"));
        rows.push(row);
    }
    rows.sort_by(|a, b| a.file.cmp(&b.file));
    Some(rows)
}

fn read_health_md(path: &Path) -> Vec<HealthRow> {
    let text = fs::read_to_string(path).unwrap_or_default();
    let mut rows = Vec::new();
    for line in text.lines() {
        let line = line.trim();
        if !line.starts_with('|') || line.contains("---") || line.contains("File |") {
            continue;
        }
        let cells: Vec<&str> = line
            .trim_matches('|')
            .split('|')
            .map(|c| c.trim())
            .collect();
        if cells.len() < 4 || cells[0] == "File" {
            continue;
        }
        rows.push(HealthRow::new(
            cells[0], cells[1], cells[2], cells[3], "", "",
        ));
    }
    rows
}

pub fn write_health(root: &Path, rows: &[HealthRow]) -> Result<(), String> {
    let mut entries = Vec::new();
    for row in rows {
        let mut obj = Vec::new();
        obj.push(("status".into(), Json::String(row.status.clone())));
        obj.push((
            "last_updated".into(),
            Json::String(row.last_updated.clone()),
        ));
        obj.push(("reason".into(), Json::String(row.reason.clone())));
        if !row.source_hash.is_empty() {
            obj.push((
                "source_content_hash".into(),
                Json::String(row.source_hash.clone()),
            ));
        }
        if !row.verification.is_empty() {
            obj.push((
                "verification".into(),
                Json::String(row.verification.clone()),
            ));
        }
        entries.push((row.file.clone(), Json::from_pairs(obj)));
    }
    let body = Json::obj(vec![
        ("version", Json::Int(2)),
        ("last_updated", Json::String(local_stamp())),
        ("entries", Json::from_pairs(entries)),
    ]);
    // last_updated inside body uses now, which changes bytes. Callers that need stability pass rows only.
    let _ = body;
    let stable = Json::obj(vec![
        ("version", Json::Int(2)),
        (
            "entries",
            Json::from_pairs(
                rows.iter()
                    .map(|row| {
                        let mut obj = vec![
                            ("status".into(), Json::String(row.status.clone())),
                            (
                                "last_updated".into(),
                                Json::String(row.last_updated.clone()),
                            ),
                            ("reason".into(), Json::String(row.reason.clone())),
                        ];
                        if !row.source_hash.is_empty() {
                            obj.push((
                                "source_content_hash".into(),
                                Json::String(row.source_hash.clone()),
                            ));
                        }
                        if !row.verification.is_empty() {
                            obj.push((
                                "verification".into(),
                                Json::String(row.verification.clone()),
                            ));
                        }
                        if !row.public_symbols.is_empty() {
                            obj.push((
                                "public_symbols".into(),
                                Json::String(row.public_symbols.clone()),
                            ));
                        }
                        if !row.wiki_hash.is_empty() {
                            obj.push(("wiki_hash".into(), Json::String(row.wiki_hash.clone())));
                        }
                        if !row.source_mtime_ns.is_empty() {
                            obj.push((
                                "source_mtime_ns".into(),
                                Json::String(row.source_mtime_ns.clone()),
                            ));
                        }
                        if !row.changed_lines.is_empty() {
                            obj.push((
                                "changed_lines".into(),
                                changed_lines_json(&row.changed_lines),
                            ));
                        }
                        (row.file.clone(), Json::from_pairs(obj))
                    })
                    .collect(),
            ),
        ),
    ]);
    write_durable(
        &root.join("file_health.json"),
        stable.to_string().as_bytes(),
    )?;
    let mut md = String::from("# Documentation Health Matrix\n\n| File | Status | Last Updated | Reason / Intent |\n|------|--------|--------------|-----------------|\n");
    let mut ordered = rows.to_vec();
    ordered.sort_by(|a, b| a.file.cmp(&b.file));
    for row in ordered {
        md.push_str(&format!(
            "| {} | {} | {} | {} |\n",
            row.file,
            row.status,
            row.last_updated,
            row.reason.replace('|', "/")
        ));
    }
    write_durable(&root.join("file_health.md"), md.as_bytes())?;
    Ok(())
}

pub fn upsert_health_row(root: &Path, row: HealthRow) -> Result<(), String> {
    let mut rows = read_health(root);
    if let Some(existing) = rows.iter_mut().find(|r| r.file == row.file) {
        *existing = row;
    } else {
        rows.push(row);
    }
    write_health(root, &rows)
}

#[derive(Clone, Debug)]
pub struct JournalEntry {
    pub stamp: String,
    pub action: String,
    pub file: String,
    pub reason: String,
}

pub fn journal_path(root: &Path, stamp: &str) -> PathBuf {
    let (y, m, d) = date_parts(stamp).unwrap_or(("1970".into(), "01".into(), "01".into()));
    root.join("journal").join(y).join(m).join(format!("{d}.md"))
}

pub fn read_journal(root: &Path, date: Option<&str>) -> Vec<JournalEntry> {
    let mut files = Vec::new();
    if let Some(date) = date {
        if let Some((y, m, d)) = date_parts(&format!("{date} 00:00:00")) {
            files.push(root.join("journal").join(y).join(m).join(format!("{d}.md")));
        }
    } else if let Ok(years) = fs::read_dir(root.join("journal")) {
        for y in years.flatten() {
            if let Ok(months) = fs::read_dir(y.path()) {
                for m in months.flatten() {
                    if let Ok(days) = fs::read_dir(m.path()) {
                        for d in days.flatten() {
                            if d.path().extension().and_then(|s| s.to_str()) == Some("md") {
                                files.push(d.path());
                            }
                        }
                    }
                }
            }
        }
    }
    files.sort();
    let mut out = Vec::new();
    for f in files {
        out.extend(parse_journal(&fs::read_to_string(&f).unwrap_or_default()));
    }
    out
}

pub fn parse_journal(text: &str) -> Vec<JournalEntry> {
    let mut out = Vec::new();
    let mut cur: Option<JournalEntry> = None;
    for line in text.lines() {
        if let Some(rest) = line.strip_prefix("## [") {
            if let Some(entry) = cur.take() {
                out.push(entry);
            }
            if let Some(end) = rest.find(']') {
                let stamp = rest[..end].trim().to_string();
                let action = rest[end + 1..].trim().to_string();
                cur = Some(JournalEntry {
                    stamp,
                    action,
                    file: String::new(),
                    reason: String::new(),
                });
            }
        } else if let Some(entry) = cur.as_mut() {
            if let Some(v) = line.strip_prefix("**File:**") {
                entry.file = v.trim().to_string();
            } else if let Some(v) = line.strip_prefix("**Reason:**") {
                entry.reason = v.trim().to_string();
            }
        }
    }
    if let Some(entry) = cur {
        out.push(entry);
    }
    out
}

pub struct JournalWrite {
    pub stamp: String,
    pub journaled: bool,
}

pub fn append_journal(
    root: &Path,
    action: &str,
    file: &str,
    reason: &str,
) -> Result<JournalWrite, String> {
    let stamp = local_stamp();
    let path = journal_path(root, &stamp);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let existing = fs::read_to_string(&path).unwrap_or_default();
    if journal_duplicate(&existing, action, file, reason, &stamp) {
        return Ok(JournalWrite {
            stamp,
            journaled: false,
        });
    }
    let block = format!("## [{stamp}] {action}\n**File:** {file}\n**Reason:** {reason}\n\n");
    let mut body = existing;
    body.push_str(&block);
    write_durable(&path, body.as_bytes())?;
    Ok(JournalWrite {
        stamp,
        journaled: true,
    })
}

fn journal_duplicate(existing: &str, action: &str, file: &str, reason: &str, stamp: &str) -> bool {
    let Some(now) = stamp_key(stamp) else {
        return false;
    };
    parse_journal(existing).iter().rev().any(|entry| {
        entry.action == action
            && entry.file == file
            && entry.reason == reason
            && stamp_key(&entry.stamp).is_some_and(|prev| now.saturating_sub(prev) <= 120)
    })
}

fn stamp_key(stamp: &str) -> Option<i64> {
    if stamp.len() < 19 {
        return None;
    }
    let n = |i: usize, j: usize| stamp.get(i..j)?.parse::<i64>().ok();
    let y = n(0, 4)?;
    let mo = n(5, 7)?;
    let d = n(8, 10)?;
    let h = n(11, 13)?;
    let mi = n(14, 16)?;
    let s = n(17, 19)?;
    Some((((y * 366 + mo * 31 + d) * 24 + h) * 60 + mi) * 60 + s)
}

fn symbols_field(value: Option<&Json>) -> String {
    match value {
        Some(Json::String(text)) => text.clone(),
        Some(Json::Array(items)) => items
            .iter()
            .filter_map(|item| item.as_str())
            .filter(|s| !s.is_empty())
            .collect::<Vec<_>>()
            .join("\n"),
        _ => String::new(),
    }
}

pub fn read_pending(root: &Path) -> String {
    fs::read_to_string(root.join("pending_updates.md")).unwrap_or_default()
}

pub fn folder_card(root: &Path, prefix: &str) -> Option<String> {
    let rel = if prefix.is_empty() || prefix == "." {
        root.join(".wikifier_staging")
            .join("maps")
            .join("_root.json")
    } else {
        root.join(".wikifier_staging")
            .join("maps")
            .join(prefix)
            .join("_index.json")
    };
    fs::read_to_string(rel).ok().or_else(|| {
        let alt = root
            .join(".wikifier_staging")
            .join("maps")
            .join("_root.json");
        if prefix.is_empty() {
            fs::read_to_string(alt).ok()
        } else {
            None
        }
    })
}
