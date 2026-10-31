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
        rows.push(HealthRow {
            file: file.clone(),
            status: ent.get("status").and_then(|s| s.as_str()).unwrap_or("").to_string(),
            last_updated: ent.get("last_updated").and_then(|s| s.as_str()).unwrap_or("").to_string(),
            reason: ent.get("reason").and_then(|s| s.as_str()).unwrap_or("").to_string(),
            source_hash: ent.get("source_content_hash").and_then(|s| s.as_str()).unwrap_or("").to_string(),
            verification: ent.get("verification").and_then(|s| s.as_str()).unwrap_or("").to_string(),
        });
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
        let cells: Vec<&str> = line.trim_matches('|').split('|').map(|c| c.trim()).collect();
        if cells.len() < 4 || cells[0] == "File" {
            continue;
        }
        rows.push(HealthRow {
            file: cells[0].to_string(),
            status: cells[1].to_string(),
            last_updated: cells[2].to_string(),
            reason: cells[3].to_string(),
            source_hash: String::new(),
            verification: String::new(),
        });
    }
    rows
}

pub fn write_health(root: &Path, rows: &[HealthRow]) -> Result<(), String> {
    let mut entries = Vec::new();
    for row in rows {
        let mut obj = Vec::new();
        obj.push(("status".into(), Json::String(row.status.clone())));
        obj.push(("last_updated".into(), Json::String(row.last_updated.clone())));
        obj.push(("reason".into(), Json::String(row.reason.clone())));
        if !row.source_hash.is_empty() {
            obj.push(("source_content_hash".into(), Json::String(row.source_hash.clone())));
        }
        if !row.verification.is_empty() {
            obj.push(("verification".into(), Json::String(row.verification.clone())));
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
        ("entries", Json::from_pairs(
            rows.iter()
                .map(|row| {
                    let mut obj = vec![
                        ("status".into(), Json::String(row.status.clone())),
                        ("last_updated".into(), Json::String(row.last_updated.clone())),
                        ("reason".into(), Json::String(row.reason.clone())),
                    ];
                    if !row.source_hash.is_empty() {
                        obj.push(("source_content_hash".into(), Json::String(row.source_hash.clone())));
                    }
                    if !row.verification.is_empty() {
                        obj.push(("verification".into(), Json::String(row.verification.clone())));
                    }
                    (row.file.clone(), Json::from_pairs(obj))
                })
                .collect(),
        )),
    ]);
    fs::write(root.join("file_health.json"), stable.to_string()).map_err(|e| e.to_string())?;
    let mut md = String::from("# Documentation Health Matrix\n\n| File | Status | Last Updated | Reason / Intent |\n|------|--------|--------------|-----------------|\n");
    let mut ordered = rows.to_vec();
    ordered.sort_by(|a, b| a.file.cmp(&b.file));
    for row in ordered {
        md.push_str(&format!("| {} | {} | {} | {} |\n", row.file, row.status, row.last_updated, row.reason.replace('|', "/")));
    }
    fs::write(root.join("file_health.md"), md).map_err(|e| e.to_string())?;
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
                cur = Some(JournalEntry { stamp, action, file: String::new(), reason: String::new() });
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

pub fn append_journal(root: &Path, action: &str, file: &str, reason: &str) -> Result<String, String> {
    let stamp = local_stamp();
    let path = journal_path(root, &stamp);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let block = format!("## [{stamp}] {action}\n**File:** {file}\n**Reason:** {reason}\n\n");
    let mut existing = fs::read_to_string(&path).unwrap_or_default();
    existing.push_str(&block);
    fs::write(&path, existing).map_err(|e| e.to_string())?;
    Ok(stamp)
}

pub fn read_pending(root: &Path) -> String {
    fs::read_to_string(root.join("pending_updates.md")).unwrap_or_default()
}

pub fn folder_card(root: &Path, prefix: &str) -> Option<String> {
    let rel = if prefix.is_empty() || prefix == "." {
        root.join(".wikifier_staging").join("maps").join("_root.json")
    } else {
        root.join(".wikifier_staging").join("maps").join(prefix).join("_index.json")
    };
    fs::read_to_string(rel).ok().or_else(|| {
        let alt = root.join(".wikifier_staging").join("maps").join("_root.json");
        if prefix.is_empty() {
            fs::read_to_string(alt).ok()
        } else {
            None
        }
    })
}
