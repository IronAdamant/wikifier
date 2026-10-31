//! Per-file payloads plus src and dst edge indexes.
//! A one-file update rewrites that file's payload and the edge lists it touches.
//! Lookups read one index file, not every payload.

use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};

use crate::scope::rel_of;

fn cache_root(root: &Path) -> PathBuf {
    root.join(".wikifier_staging").join("wk_cache")
}

fn enc(rel: &str) -> String {
    rel.replace('%', "%25").replace('/', "%2F")
}

pub fn payload_path(root: &Path, rel: &str) -> PathBuf {
    cache_root(root).join("payload").join(format!("{}.json", enc(rel)))
}

fn by_src_path(root: &Path, rel: &str) -> PathBuf {
    cache_root(root).join("by_src").join(format!("{}.edges", enc(rel)))
}

fn by_dst_path(root: &Path, rel: &str) -> PathBuf {
    cache_root(root).join("by_dst").join(format!("{}.edges", enc(rel)))
}

fn paths_file(root: &Path) -> PathBuf {
    cache_root(root).join("paths.txt")
}

fn index_file(root: &Path) -> PathBuf {
    cache_root(root).join("index.tsv")
}

fn atomic_write(path: &Path, bytes: &[u8]) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let tmp = path.with_extension("tmp");
    fs::write(&tmp, bytes).map_err(|e| e.to_string())?;
    fs::rename(&tmp, path).map_err(|e| e.to_string())?;
    Ok(())
}

fn read_lines(path: &Path) -> Vec<String> {
    fs::read_to_string(path)
        .unwrap_or_default()
        .lines()
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .collect()
}

fn dst_of(line: &str) -> String {
    line.split('\t').next().unwrap_or("").trim().to_string()
}

pub fn load_dependencies(root: &Path, rel: &str) -> Result<Vec<String>, String> {
    // Index only. A corrupt sibling payload must not matter.
    let mut dsts: Vec<String> = read_lines(&by_src_path(root, rel)).into_iter().map(|l| dst_of(&l)).filter(|s| !s.is_empty()).collect();
    dsts.sort();
    dsts.dedup();
    Ok(dsts)
}

#[derive(Clone, Debug)]
pub struct InternalEdge {
    pub path: String,
    pub line: i64,
    pub names: Vec<String>,
}

#[derive(Clone, Debug)]
pub struct DependencyView {
    pub internal: Vec<InternalEdge>,
    pub external: Vec<String>,
    pub unresolved: Vec<(String, i64)>,
}

fn notes_path(root: &Path, rel: &str) -> PathBuf {
    cache_root(root).join("notes").join(format!("{}.txt", enc(rel)))
}

pub fn load_dependency_view(root: &Path, rel: &str) -> Result<DependencyView, String> {
    let mut internal = Vec::new();
    for line in read_lines(&by_src_path(root, rel)) {
        let mut parts = line.split('\t');
        let path = parts.next().unwrap_or("").trim().to_string();
        if path.is_empty() {
            continue;
        }
        let line_no = parts.next().unwrap_or("0").parse().unwrap_or(0);
        let names = parts.next().unwrap_or("").split(',').filter(|s| !s.is_empty()).map(|s| s.to_string()).collect();
        internal.push(InternalEdge { path, line: line_no, names });
    }
    let mut external = Vec::new();
    let mut unresolved = Vec::new();
    for line in read_lines(&notes_path(root, rel)) {
        let mut parts = line.split('\t');
        match parts.next().unwrap_or("") {
            "E" => {
                let name = parts.next().unwrap_or("").to_string();
                if !name.is_empty() {
                    external.push(name);
                }
            }
            "U" => {
                let raw = parts.next().unwrap_or("").to_string();
                let line_no = parts.next().unwrap_or("0").parse().unwrap_or(0);
                if !raw.is_empty() {
                    unresolved.push((raw, line_no));
                }
            }
            _ => {}
        }
    }
    external.sort();
    external.dedup();
    Ok(DependencyView { internal, external, unresolved })
}

pub fn load_dependents(root: &Path, rel: &str) -> Result<Vec<String>, String> {
    let mut srcs = read_lines(&by_dst_path(root, rel));
    srcs.sort();
    srcs.dedup();
    Ok(srcs)
}

pub fn list_prefix(root: &Path, prefix: &str) -> Result<Vec<String>, String> {
    let pref = prefix.trim_matches('/');
    let mut out = Vec::new();
    for line in read_lines(&paths_file(root)) {
        if pref.is_empty() || line == pref || line.starts_with(&(pref.to_string() + "/")) {
            out.push(line);
        }
    }
    Ok(out)
}

pub fn all_paths(root: &Path) -> Vec<String> {
    read_lines(&paths_file(root))
}

#[derive(Clone, Debug)]
struct Row {
    rel: String,
    mtime_ns: u128,
    size: u64,
    hash: String,
    dsts: BTreeSet<String>,
}

fn load_index(root: &Path) -> BTreeMap<String, Row> {
    let mut map = BTreeMap::new();
    for line in read_lines(&index_file(root)) {
        let mut parts = line.split('\t');
        let rel = parts.next().unwrap_or("").to_string();
        if rel.is_empty() {
            continue;
        }
        let mtime_ns = parts.next().unwrap_or("0").parse().unwrap_or(0);
        let size = parts.next().unwrap_or("0").parse().unwrap_or(0);
        let hash = parts.next().unwrap_or("").to_string();
        let dsts = load_dependencies(root, &rel).unwrap_or_default().into_iter().collect();
        map.insert(rel.clone(), Row { rel, mtime_ns, size, hash, dsts });
    }
    map
}

fn save_index(root: &Path, rows: &BTreeMap<String, Row>) -> Result<(), String> {
    let mut body = String::new();
    let mut paths = String::new();
    for (rel, row) in rows {
        body.push_str(&format!("{rel}\t{}\t{}\t{}\n", row.mtime_ns, row.size, row.hash));
        paths.push_str(rel);
        paths.push('\n');
    }
    atomic_write(&index_file(root), body.as_bytes())?;
    atomic_write(&paths_file(root), paths.as_bytes())?;
    Ok(())
}

fn rewrite_dst(root: &Path, dst: &str, src: &str, add: bool) -> Result<(), String> {
    let path = by_dst_path(root, dst);
    let mut lines = read_lines(&path);
    lines.retain(|s| s != src);
    if add {
        lines.push(src.to_string());
    }
    lines.sort();
    lines.dedup();
    if lines.is_empty() {
        let _ = fs::remove_file(&path);
        return Ok(());
    }
    atomic_write(&path, lines.join("\n").as_bytes())?;
    Ok(())
}

pub struct FileUpdate {
    pub rel: String,
    pub mtime_ns: u128,
    pub size: u64,
    pub hash: String,
    pub imports: Vec<String>,
    pub dsts: BTreeSet<String>,
    pub edge_lines: Vec<String>,
    pub external: Vec<String>,
    pub unresolved: Vec<(String, i64)>,
}

/// Write one file's payload and patch only its src index and the dst indexes that changed.
pub fn upsert_file(root: &Path, upd: &FileUpdate) -> Result<(), String> {
    let mut rows = load_index(root);
    let old_dsts = rows.get(&upd.rel).map(|r| r.dsts.clone()).unwrap_or_default();
    let payload = format!(
        "{{\"rel\":{},\"sha256\":{},\"imports\":{},\"resolved\":{}}}",
        crate::jsonutil::Json::String(upd.rel.clone()),
        crate::jsonutil::Json::String(upd.hash.clone()),
        crate::jsonutil::Json::Array(upd.imports.iter().cloned().map(crate::jsonutil::Json::String).collect()),
        crate::jsonutil::Json::Array(upd.dsts.iter().cloned().map(crate::jsonutil::Json::String).collect()),
    );
    atomic_write(&payload_path(root, &upd.rel), payload.as_bytes())?;
    let mut src_lines = if upd.edge_lines.is_empty() {
        upd.dsts.iter().cloned().collect::<Vec<_>>()
    } else {
        upd.edge_lines.clone()
    };
    src_lines.sort();
    src_lines.dedup();
    atomic_write(&by_src_path(root, &upd.rel), src_lines.join("\n").as_bytes())?;
    let mut notes = String::new();
    for name in &upd.external {
        notes.push_str(&format!("E\t{name}\n"));
    }
    for (raw, line) in &upd.unresolved {
        notes.push_str(&format!("U\t{raw}\t{line}\n"));
    }
    if notes.is_empty() {
        let _ = fs::remove_file(notes_path(root, &upd.rel));
    } else {
        atomic_write(&notes_path(root, &upd.rel), notes.as_bytes())?;
    }
    for gone in old_dsts.difference(&upd.dsts) {
        rewrite_dst(root, gone, &upd.rel, false)?;
    }
    for added in upd.dsts.difference(&old_dsts) {
        rewrite_dst(root, added, &upd.rel, true)?;
    }
    rows.insert(
        upd.rel.clone(),
        Row {
            rel: upd.rel.clone(),
            mtime_ns: upd.mtime_ns,
            size: upd.size,
            hash: upd.hash.clone(),
            dsts: upd.dsts.clone(),
        },
    );
    save_index(root, &rows)
}

pub fn remove_file(root: &Path, rel: &str) -> Result<(), String> {
    let mut rows = load_index(root);
    if let Some(row) = rows.remove(rel) {
        for dst in &row.dsts {
            rewrite_dst(root, dst, rel, false)?;
        }
    }
    let _ = fs::remove_file(payload_path(root, rel));
    let _ = fs::remove_file(by_src_path(root, rel));
    save_index(root, &rows)
}

pub fn indexed_rows(root: &Path) -> Vec<(String, u128, u64, String)> {
    load_index(root)
        .into_values()
        .map(|r| (r.rel, r.mtime_ns, r.size, r.hash))
        .collect()
}

pub fn payload_bytes(root: &Path, rel: &str) -> Option<Vec<u8>> {
    fs::read(payload_path(root, rel)).ok()
}

pub fn stat_ns(path: &Path) -> Option<(u128, u64)> {
    let meta = fs::metadata(path).ok()?;
    let mtime = meta.modified().ok()?.duration_since(std::time::UNIX_EPOCH).ok()?.as_nanos();
    Some((mtime, meta.len()))
}

pub fn edges(root: &Path) -> BTreeSet<(String, String)> {
    let mut out = BTreeSet::new();
    for rel in all_paths(root) {
        if let Ok(dsts) = load_dependencies(root, &rel) {
            for dst in dsts {
                if dst != rel {
                    out.insert((rel.clone(), dst));
                }
            }
        }
    }
    out
}

pub fn rel_string(root: &Path, path: &Path) -> String {
    rel_of(root, path)
}

fn barrel_path(root: &Path, rel: &str) -> PathBuf {
    cache_root(root).join("barrels").join(format!("{}.json", enc(rel)))
}

pub fn write_barrel_record(root: &Path, rel: &str, dsts: &[String]) -> Result<(), String> {
    let body = crate::jsonutil::Json::obj(vec![
        ("src", crate::jsonutil::Json::String(rel.to_string())),
        ("dsts", crate::jsonutil::Json::Array(dsts.iter().cloned().map(crate::jsonutil::Json::String).collect())),
    ]);
    atomic_write(&barrel_path(root, rel), body.to_string().as_bytes())
}

pub fn prune_barrel_files(root: &Path, max_age_days: f64, dry_run: bool) -> Result<usize, String> {
    let dir = cache_root(root).join("barrels");
    let entries = match fs::read_dir(&dir) {
        Ok(e) => e,
        Err(_) => return Ok(0),
    };
    let now = std::time::SystemTime::now();
    let max_age = std::time::Duration::from_secs((max_age_days.max(0.0) * 86400.0) as u64);
    let mut pruned = 0usize;
    for ent in entries.flatten() {
        let path = ent.path();
        if !path.is_file() {
            continue;
        }
        let text = fs::read_to_string(&path).unwrap_or_default();
        let parsed = crate::jsonutil::parse(&text).ok();
        let src = parsed.as_ref().and_then(|v| v.get("src")).and_then(|s| s.as_str()).unwrap_or("");
        let dsts: Vec<String> = parsed.as_ref()
            .and_then(|v| v.get("dsts"))
            .and_then(|v| v.as_array())
            .map(|a| a.iter().filter_map(|x| x.as_str().map(|s| s.to_string())).collect())
            .unwrap_or_default();
        let dangling = src.is_empty()
            || !root.join(src).is_file()
            || dsts.iter().any(|d| !root.join(d).is_file());
        let aged = ent.metadata().ok().and_then(|m| m.modified().ok()).and_then(|t| now.duration_since(t).ok()).map(|age| age > max_age).unwrap_or(false);
        if dangling || aged {
            pruned += 1;
            if !dry_run {
                let _ = fs::remove_file(&path);
            }
        }
    }
    Ok(pruned)
}
