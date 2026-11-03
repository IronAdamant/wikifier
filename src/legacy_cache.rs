//! Read a pre-Rust `import_cache.sqlite` or `import_cache.json` into `wk_cache`
//! when the text cache has no paths yet. Update-maps still re-parses.
//! SQLite is read with the `sqlite3` CLI when it is on PATH. There is no SQLite crate.

use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::Path;
use std::process::Command;

use crate::cache::{self, FileUpdate, Session};
use crate::jsonutil;

pub fn import_if_empty(root: &Path) -> Result<Option<String>, String> {
    if !cache::all_paths(root).is_empty() {
        return Ok(None);
    }
    let sqlite = root.join(".wikifier_staging").join("import_cache.sqlite");
    let json_path = root.join(".wikifier_staging").join("import_cache.json");
    if sqlite.is_file() {
        match import_sqlite(root, &sqlite) {
            Ok(0) => {}
            Ok(_) => {
                let _ = crate::maps_out::write(root);
                return Ok(None);
            }
            Err(err) => {
                if json_path.is_file() {
                    let n = import_json(root, &json_path)?;
                    if n > 0 {
                        let _ = crate::maps_out::write(root);
                        return Ok(None);
                    }
                }
                return Ok(Some(format!("sqlite_present_unread: {err}")));
            }
        }
    }
    if json_path.is_file() {
        let n = import_json(root, &json_path)?;
        if n > 0 {
            let _ = crate::maps_out::write(root);
        }
        return Ok(None);
    }
    if sqlite.is_file() {
        return Ok(Some("sqlite_present_unread".into()));
    }
    Ok(None)
}

fn import_sqlite(root: &Path, db: &Path) -> Result<usize, String> {
    let files = sqlite_lines(db, "SELECT rel_path FROM files;")?;
    let edges = sqlite_lines(db, "SELECT src, dst FROM edges;")?;
    let mut rels: BTreeSet<String> = BTreeSet::new();
    for line in files {
        let rel = line.trim().to_string();
        if rel.is_empty() || rel.starts_with('_') {
            continue;
        }
        rels.insert(rel);
    }
    let mut by_src: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    for line in edges {
        let mut parts = line.split('\t');
        let src = parts.next().unwrap_or("").trim();
        let dst = parts.next().unwrap_or("").trim();
        if src.is_empty() || dst.is_empty() || src.starts_with('_') || dst.starts_with('_') {
            continue;
        }
        rels.insert(src.to_string());
        by_src.entry(src.to_string()).or_default().insert(dst.to_string());
    }
    if rels.is_empty() {
        return Ok(0);
    }
    write_rows(root, &rels, &by_src)?;
    Ok(rels.len())
}

fn sqlite_lines(db: &Path, sql: &str) -> Result<Vec<String>, String> {
    let output = Command::new("sqlite3")
        .args(["-batch", "-separator", "\t", &db.display().to_string(), sql])
        .output()
        .map_err(|err| format!("sqlite3 CLI is not available ({err})"))?;
    if !output.status.success() {
        let err = String::from_utf8_lossy(&output.stderr);
        return Err(format!("sqlite3 exited {}: {err}", output.status));
    }
    Ok(String::from_utf8_lossy(&output.stdout).lines().map(|s| s.to_string()).filter(|s| !s.trim().is_empty()).collect())
}

fn import_json(root: &Path, path: &Path) -> Result<usize, String> {
    let text = fs::read_to_string(path).map_err(|e| e.to_string())?;
    let parsed = jsonutil::parse(&text).map_err(|e| e.to_string())?;
    let obj = parsed.as_object().ok_or_else(|| "import_cache.json is not an object".to_string())?;
    let mut rels: BTreeSet<String> = BTreeSet::new();
    let mut by_src: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    for (key, entry) in obj {
        if key.starts_with('_') {
            continue;
        }
        if entry.as_object().is_none() {
            continue;
        }
        rels.insert(key.clone());
        let mut dsts = BTreeSet::new();
        if let Some(pairs) = entry.get("resolved_pairs").and_then(|v| v.as_array()) {
            for pair in pairs {
                if let Some(dst) = pair.get("resolved").and_then(|v| v.as_str()).or_else(|| pair.as_str()) {
                    if !dst.is_empty() && dst != key {
                        dsts.insert(dst.to_string());
                    }
                }
            }
        }
        if let Some(resolved) = entry.get("resolved").and_then(|v| v.as_array()) {
            for item in resolved {
                if let Some(dst) = item.as_str() {
                    if !dst.is_empty() && dst != key {
                        dsts.insert(dst.to_string());
                    }
                }
            }
        }
        if !dsts.is_empty() {
            by_src.insert(key.clone(), dsts);
        }
    }
    if rels.is_empty() {
        return Ok(0);
    }
    write_rows(root, &rels, &by_src)?;
    Ok(rels.len())
}

fn write_rows(root: &Path, rels: &BTreeSet<String>, by_src: &BTreeMap<String, BTreeSet<String>>) -> Result<(), String> {
    let _lock = crate::project_lock::ProjectLock::acquire(root)?;
    let mut session = Session::open(root)?;
    for rel in rels {
        let dsts = by_src.get(rel).cloned().unwrap_or_default();
        let edge_lines: Vec<String> = dsts.iter().map(|dst| cache::format_edge_line(dst, 1, &[], false, false, false)).collect();
        session.upsert(&FileUpdate {
            rel: rel.clone(),
            mtime_ns: 0,
            size: 0,
            hash: "sha256:legacy".into(),
            imports: Vec::new(),
            dsts,
            edge_lines,
            external: Vec::new(),
            unresolved: Vec::new(),
        });
    }
    session.commit()
}
