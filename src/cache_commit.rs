//! One cache commit per run: edit the index in memory, then publish it.
//! `by_src` is written before `by_dst`. `generation` is written last.
//! A crash leaves `commit.pending` so the next open rebuilds `by_dst` from `by_src`.

use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::fs::{self, OpenOptions};
use std::io::{ErrorKind, Write};
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use crate::cache::{self, FileUpdate};

#[derive(Clone, Debug)]
struct Row {
    rel: String,
    mtime_ns: u128,
    size: u64,
    hash: String,
    dsts: BTreeSet<String>,
}

pub struct Consistency {
    pub consistent: bool,
    pub incomplete: bool,
    pub mismatches: Vec<String>,
}

pub(crate) struct LockGuard {
    path: PathBuf,
}

impl Drop for LockGuard {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.path);
    }
}

impl LockGuard {
    pub(crate) fn acquire(root: &Path) -> Result<Self, String> {
        let dir = cache::cache_root(root);
        fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
        let path = dir.join("wk.lock");
        let deadline = Instant::now() + Duration::from_secs(30);
        loop {
            match OpenOptions::new().write(true).create_new(true).open(&path) {
                Ok(mut file) => {
                    let stamp = SystemTime::now()
                        .duration_since(UNIX_EPOCH)
                        .map(|d| d.as_secs())
                        .unwrap_or(0);
                    writeln!(file, "{}\n{stamp}", std::process::id()).map_err(|e| e.to_string())?;
                    file.sync_all().map_err(|e| e.to_string())?;
                    return Ok(LockGuard { path });
                }
                Err(err) if err.kind() == ErrorKind::AlreadyExists => {
                    if try_steal(&path) {
                        continue;
                    }
                    if Instant::now() >= deadline {
                        let text = fs::read_to_string(&path).unwrap_or_default();
                        let pid = text.lines().next().unwrap_or("?").trim();
                        return Err(format!(
                            "cache locked by pid {pid}; another wikifier run holds {} — wait for it to finish, or remove the lock if that process is gone",
                            path.display()
                        ));
                    }
                    std::thread::sleep(Duration::from_millis(50));
                }
                Err(err) => return Err(format!("failed to lock cache: {err}")),
            }
        }
    }
}

fn try_steal(path: &Path) -> bool {
    let text = match fs::read_to_string(path) {
        Ok(text) => text,
        Err(_) => return false,
    };
    let pid: i32 = text
        .lines()
        .next()
        .unwrap_or("0")
        .trim()
        .parse()
        .unwrap_or(0);
    let stale = if pid > 0 {
        !crate::proc::pid_alive(pid)
    } else {
        fs::metadata(path)
            .ok()
            .and_then(|meta| meta.modified().ok())
            .and_then(|t| t.elapsed().ok())
            .map(|age| age.as_secs() >= 5)
            .unwrap_or(true)
    };
    if !stale {
        return false;
    }
    if fs::read_to_string(path).unwrap_or_default() != text {
        return false;
    }
    fs::remove_file(path).is_ok()
}

pub struct Session {
    root: PathBuf,
    rows: BTreeMap<String, Row>,
    rev: BTreeMap<String, BTreeSet<String>>,
    dirty_src: BTreeMap<String, Vec<String>>,
    dirty_dst: BTreeSet<String>,
    payloads: BTreeMap<String, String>,
    notes: BTreeMap<String, Option<String>>,
    barrels: Vec<(String, Vec<String>)>,
    removed: BTreeSet<String>,
    rewrite_index: bool,
    sizes: Sizes,
    reparse: BTreeSet<String>,
    _lock: LockGuard,
}

impl Session {
    pub fn open(root: &Path) -> Result<Self, String> {
        let lock = LockGuard::acquire(root)?;
        migrate_legacy(root)?;
        if cache::commit_pending_path(root).is_file() {
            rebuild_locked(root)?;
        }
        let (rows, rewrite_index) = load_rows(root);
        let mut rev: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
        for (rel, row) in &rows {
            for dst in &row.dsts {
                rev.entry(dst.clone()).or_default().insert(rel.clone());
            }
        }
        let check = check_entries(root, &rows, &rev);
        let rewrite_index = rewrite_index
            || check.rewrite
            || !check.reparse.is_empty()
            || !check.stale_dsts.is_empty();
        Ok(Session {
            root: root.to_path_buf(),
            rows,
            rev,
            dirty_src: BTreeMap::new(),
            dirty_dst: check.stale_dsts,
            payloads: BTreeMap::new(),
            notes: BTreeMap::new(),
            barrels: Vec::new(),
            removed: BTreeSet::new(),
            rewrite_index,
            sizes: check.sizes,
            reparse: check.reparse,
            _lock: lock,
        })
    }

    pub fn known(&self, rel: &str) -> Option<(u128, u64, String)> {
        self.rows
            .get(rel)
            .map(|row| (row.mtime_ns, row.size, row.hash.clone()))
    }

    pub fn dsts_of(&self, rel: &str) -> BTreeSet<String> {
        self.rows
            .get(rel)
            .map(|row| row.dsts.clone())
            .unwrap_or_default()
    }

    /// Record a new size or mtime when the bytes still match the stored hash.
    pub fn note_stat(&mut self, rel: &str, mtime_ns: u128, size: u64) {
        let Some(row) = self.rows.get_mut(rel) else {
            return;
        };
        if row.mtime_ns == mtime_ns && row.size == size {
            return;
        }
        row.mtime_ns = mtime_ns;
        row.size = size;
        self.rewrite_index = true;
    }

    pub fn rels(&self) -> Vec<String> {
        self.rows.keys().cloned().collect()
    }

    pub fn upsert(&mut self, upd: &FileUpdate) {
        self.removed.remove(&upd.rel);
        let old = self
            .rows
            .get(&upd.rel)
            .map(|row| row.dsts.clone())
            .unwrap_or_default();
        for gone in old.difference(&upd.dsts) {
            if let Some(set) = self.rev.get_mut(gone) {
                set.remove(&upd.rel);
            }
            self.dirty_dst.insert(gone.clone());
        }
        for added in upd.dsts.difference(&old) {
            self.rev
                .entry(added.clone())
                .or_default()
                .insert(upd.rel.clone());
            self.dirty_dst.insert(added.clone());
        }
        let mut src_lines = if upd.edge_lines.is_empty() {
            upd.dsts.iter().cloned().collect::<Vec<_>>()
        } else {
            upd.edge_lines.clone()
        };
        src_lines.sort();
        src_lines.dedup();
        self.dirty_src.insert(upd.rel.clone(), src_lines);
        let payload = format!(
            "{{\"rel\":{},\"sha256\":{},\"imports\":{},\"resolved\":{}}}",
            crate::jsonutil::Json::String(upd.rel.clone()),
            crate::jsonutil::Json::String(upd.hash.clone()),
            crate::jsonutil::Json::Array(
                upd.imports
                    .iter()
                    .cloned()
                    .map(crate::jsonutil::Json::String)
                    .collect()
            ),
            crate::jsonutil::Json::Array(
                upd.dsts
                    .iter()
                    .cloned()
                    .map(crate::jsonutil::Json::String)
                    .collect()
            ),
        );
        self.payloads.insert(upd.rel.clone(), payload);
        let mut notes = String::new();
        for name in &upd.external {
            notes.push_str(&format!("E\t{name}\n"));
        }
        for (raw, line, reason) in &upd.unresolved {
            notes.push_str(&format!("U\t{raw}\t{line}\t{reason}\n"));
        }
        self.notes.insert(
            upd.rel.clone(),
            if notes.is_empty() { None } else { Some(notes) },
        );
        self.rows.insert(
            upd.rel.clone(),
            Row {
                rel: upd.rel.clone(),
                mtime_ns: upd.mtime_ns,
                size: upd.size,
                hash: upd.hash.clone(),
                dsts: upd.dsts.clone(),
            },
        );
        self.rewrite_index = true;
    }

    pub fn remove(&mut self, rel: &str) {
        let importers: Vec<String> = self
            .rev
            .get(rel)
            .cloned()
            .unwrap_or_default()
            .into_iter()
            .filter(|src| src != rel && self.rows.contains_key(src))
            .collect();
        for src in importers {
            self.strip_dst(&src, rel);
        }
        if let Some(row) = self.rows.remove(rel) {
            for dst in row.dsts {
                if let Some(set) = self.rev.get_mut(&dst) {
                    set.remove(rel);
                }
                self.dirty_dst.insert(dst);
            }
        }
        self.rev.remove(rel);
        self.dirty_src.remove(rel);
        self.payloads.remove(rel);
        self.notes.remove(rel);
        self.removed.insert(rel.to_string());
        self.rewrite_index = true;
    }

    fn strip_dst(&mut self, src: &str, dst: &str) {
        if let Some(row) = self.rows.get_mut(src) {
            row.dsts.remove(dst);
        }
        if let Some(set) = self.rev.get_mut(dst) {
            set.remove(src);
        }
        let mut lines = self
            .dirty_src
            .get(src)
            .cloned()
            .unwrap_or_else(|| cache::content_lines(&cache::by_src_path(&self.root, src)));
        lines.retain(|line| cache::dst_of(line) != dst);
        self.dirty_src.insert(src.to_string(), lines);
        self.dirty_dst.insert(dst.to_string());
        self.rewrite_index = true;
    }

    pub fn stage_barrel(&mut self, rel: &str, dsts: &[String]) {
        self.barrels.push((rel.to_string(), dsts.to_vec()));
    }

    /// True when [`Session::commit`] would write anything.
    pub fn has_changes(&self) -> bool {
        self.rewrite_index || !self.barrels.is_empty()
    }

    /// True when `rel`'s cache files failed the open check, so it must be parsed again
    /// even though its size and mtime are unchanged.
    pub fn needs_parse(&self, rel: &str) -> bool {
        self.reparse.contains(rel)
    }

    pub fn commit(mut self) -> Result<(), String> {
        if !self.has_changes() {
            return Ok(());
        }
        let mut sizes = std::mem::take(&mut self.sizes);
        let gen = read_generation(&self.root).saturating_add(1);
        cache::atomic_write(
            &cache::commit_pending_path(&self.root),
            format!("{gen}\n").as_bytes(),
        )?;
        // by_dst is keyed by the importer's target. Dropping a file removes its
        // forward edges above; the reverse file for this path stays until importers change.
        for rel in &self.removed {
            for kind in ["by_src", "payload", "notes"] {
                sizes.remove(&(kind.to_string(), rel.clone()));
            }
            for (sub, ext) in [
                ("payload", "json"),
                ("by_src", "edges"),
                ("notes", "txt"),
                ("barrels", "json"),
            ] {
                let _ = fs::remove_file(cache::store_file(&self.root, sub, rel, ext));
                let _ = fs::remove_file(cache::legacy_file(&self.root, sub, rel, ext));
            }
        }
        // Forward files (by_src, payload, notes, barrels) are written and flushed as one
        // batch before any by_dst file, so a crash between them is repaired from by_src.
        let mut forward: Vec<(PathBuf, Vec<u8>)> = Vec::new();
        for (rel, lines) in &self.dirty_src {
            if self.removed.contains(rel) {
                continue;
            }
            let body = if lines.is_empty() {
                String::new()
            } else {
                format!("{}\n", lines.join("\n"))
            };
            let bytes = cache::labeled(rel, &body);
            sizes.insert(("by_src".into(), rel.clone()), bytes.len() as u64);
            forward.push((cache::store_file(&self.root, "by_src", rel, "edges"), bytes));
        }
        for (rel, payload) in &self.payloads {
            sizes.insert(("payload".into(), rel.clone()), payload.len() as u64);
            forward.push((
                cache::store_file(&self.root, "payload", rel, "json"),
                payload.as_bytes().to_vec(),
            ));
        }
        for (rel, notes) in &self.notes {
            let path = cache::store_file(&self.root, "notes", rel, "txt");
            match notes {
                Some(body) => {
                    let bytes = cache::labeled(rel, body);
                    sizes.insert(("notes".into(), rel.clone()), bytes.len() as u64);
                    forward.push((path, bytes));
                }
                None => {
                    sizes.remove(&("notes".to_string(), rel.clone()));
                    let _ = fs::remove_file(&path);
                }
            }
        }
        // A file staged twice keeps its last record, as the serial writes did.
        let barrels: BTreeMap<&String, &Vec<String>> =
            self.barrels.iter().map(|(rel, dsts)| (rel, dsts)).collect();
        for (rel, dsts) in barrels {
            let body = crate::jsonutil::Json::obj(vec![
                ("src", crate::jsonutil::Json::String(rel.clone())),
                (
                    "dsts",
                    crate::jsonutil::Json::Array(
                        dsts.iter()
                            .cloned()
                            .map(crate::jsonutil::Json::String)
                            .collect(),
                    ),
                ),
            ]);
            forward.push((
                cache::store_file(&self.root, "barrels", rel, "json"),
                body.to_string().into_bytes(),
            ));
        }
        cache::write_derived_all(&forward)?;
        let mut reverse: Vec<(PathBuf, Vec<u8>)> = Vec::new();
        for dst in &self.dirty_dst {
            let path = cache::store_file(&self.root, "by_dst", dst, "edges");
            let srcs = self.rev.get(dst).cloned().unwrap_or_default();
            if srcs.is_empty() {
                sizes.remove(&("by_dst".to_string(), dst.clone()));
                let _ = fs::remove_file(&path);
            } else {
                let lines: Vec<String> = srcs.iter().cloned().collect();
                let body = format!("{}\n", lines.join("\n"));
                let bytes = cache::labeled(dst, &body);
                sizes.insert(("by_dst".into(), dst.clone()), bytes.len() as u64);
                reverse.push((path, bytes));
            }
        }
        cache::write_derived_all(&reverse)?;
        save_index(&self.root, &self.rows)?;
        save_sizes(&self.root, &sizes)?;
        cache::atomic_write(
            &cache::generation_path(&self.root),
            format!("{gen}\n").as_bytes(),
        )?;
        let _ = fs::remove_file(cache::commit_pending_path(&self.root));
        cache::atomic_write(&cache::names_marker(&self.root), b"fnv1a64\n")?;
        Ok(())
    }
}

/// Kinds of cache file `Session::open` checks before trusting a row: sub-directory and
/// extension. Barrel records are auxiliary and are not checked.
const CHECKED: &[(&str, &str)] = &[
    ("by_src", "edges"),
    ("payload", "json"),
    ("notes", "txt"),
    ("by_dst", "edges"),
];

/// Byte length of each checked cache file, keyed by kind and path.
type Sizes = BTreeMap<(String, String), u64>;

fn sizes_path(root: &Path) -> PathBuf {
    cache::cache_root(root).join("sizes.tsv")
}

/// The recorded sizes, or `None` when the file is missing or any line is malformed.
fn read_sizes(root: &Path) -> Option<Sizes> {
    let text = fs::read_to_string(sizes_path(root)).ok()?;
    let mut out = Sizes::new();
    for line in text.lines() {
        let mut parts = line.splitn(3, '\t');
        let (Some(kind), Some(len), Some(rel)) = (parts.next(), parts.next(), parts.next()) else {
            return None;
        };
        if rel.is_empty() || !CHECKED.iter().any(|(k, _)| *k == kind) {
            return None;
        }
        out.insert((kind.to_string(), rel.to_string()), len.parse().ok()?);
    }
    Some(out)
}

fn save_sizes(root: &Path, sizes: &Sizes) -> Result<(), String> {
    let mut body = String::new();
    for ((kind, rel), len) in sizes {
        body.push_str(&format!("{kind}\t{len}\t{rel}\n"));
    }
    cache::atomic_write(&sizes_path(root), body.as_bytes())
}

/// File name to byte length for one cache directory, from a single listing.
fn listed_sizes(dir: &Path) -> HashMap<String, u64> {
    let Ok(entries) = fs::read_dir(dir) else {
        return HashMap::new();
    };
    entries
        .flatten()
        .filter_map(|ent| {
            let len = ent.metadata().ok()?.len();
            Some((ent.file_name().to_string_lossy().into_owned(), len))
        })
        .collect()
}

/// What `Session::open` found wrong with the cache files.
struct EntryCheck {
    sizes: Sizes,
    reparse: BTreeSet<String>,
    stale_dsts: BTreeSet<String>,
    rewrite: bool,
}

/// Compare every checked cache file with its recorded size (one directory listing per
/// kind). A file with no recorded size is read and its content checked once. A missing,
/// resized, or malformed file is a miss: its source is parsed again, or its `by_dst`
/// record is rewritten from the index. This is what lets the cache skip fsync.
fn check_entries(
    root: &Path,
    rows: &BTreeMap<String, Row>,
    rev: &BTreeMap<String, BTreeSet<String>>,
) -> EntryCheck {
    let recorded = read_sizes(root);
    let mut check = EntryCheck {
        sizes: Sizes::new(),
        reparse: BTreeSet::new(),
        stale_dsts: BTreeSet::new(),
        rewrite: recorded.is_none(),
    };
    let recorded = recorded.unwrap_or_default();
    let listed: HashMap<&str, HashMap<String, u64>> = CHECKED
        .iter()
        .map(|(kind, _)| (*kind, listed_sizes(&cache::cache_root(root).join(kind))))
        .collect();
    let mut verify = |kind: &str, ext: &str, rel: &str, required: bool| -> bool {
        let name = format!("{}.{ext}", cache::enc(rel));
        let actual = listed.get(kind).and_then(|dir| dir.get(&name)).copied();
        let key = (kind.to_string(), rel.to_string());
        if let Some(len) = recorded.get(&key) {
            if actual == Some(*len) {
                check.sizes.insert(key, *len);
                return true;
            }
            return false;
        }
        let Some(len) = actual else {
            return !required;
        };
        let path = cache::store_file(root, kind, rel, ext);
        let bytes = fs::read(&path).unwrap_or_default();
        let ok = match kind {
            "by_src" => cache::labeled_lines(&bytes, rel).is_some_and(|lines| {
                let dsts: BTreeSet<String> = lines.iter().map(|l| cache::dst_of(l)).collect();
                rows.get(rel).is_some_and(|row| row.dsts == dsts)
            }),
            "notes" => cache::labeled_lines(&bytes, rel).is_some_and(|lines| {
                lines
                    .iter()
                    .all(|l| l.starts_with("E\t") || l.starts_with("U\t"))
            }),
            "payload" => std::str::from_utf8(&bytes)
                .ok()
                .and_then(|text| crate::jsonutil::parse(text).ok())
                .is_some_and(|json| json.get("rel").and_then(|v| v.as_str()) == Some(rel)),
            _ => cache::labeled_lines(&bytes, rel).is_some_and(|lines| {
                let srcs: BTreeSet<String> = lines.into_iter().collect();
                rev.get(rel).is_some_and(|want| *want == srcs)
            }),
        };
        if ok {
            check.sizes.insert(key, len);
            check.rewrite = true;
        }
        ok
    };
    let mut reparse = BTreeSet::new();
    for rel in rows.keys() {
        let src_ok = verify("by_src", "edges", rel, true);
        let payload_ok = verify("payload", "json", rel, false);
        let notes_ok = verify("notes", "txt", rel, false);
        if !(src_ok && payload_ok && notes_ok) {
            reparse.insert(rel.clone());
        }
    }
    let mut stale = BTreeSet::new();
    for (dst, srcs) in rev {
        if !srcs.is_empty() && !verify("by_dst", "edges", dst, true) {
            stale.insert(dst.clone());
        }
    }
    check.reparse = reparse;
    check.stale_dsts = stale;
    check
}

fn read_generation(root: &Path) -> u64 {
    fs::read_to_string(cache::generation_path(root))
        .ok()
        .and_then(|text| text.trim().parse().ok())
        .unwrap_or(0)
}

fn join_dsts(dsts: &BTreeSet<String>) -> String {
    let mut out = String::new();
    for (i, dst) in dsts.iter().enumerate() {
        if i > 0 {
            out.push('\u{1e}');
        }
        out.push_str(dst);
    }
    out
}

fn parse_dsts(raw: &str) -> BTreeSet<String> {
    raw.split('\u{1e}')
        .filter(|s| !s.is_empty())
        .map(|s| s.to_string())
        .collect()
}

fn index_record_lines(root: &Path) -> Vec<String> {
    fs::read_to_string(cache::index_file(root))
        .unwrap_or_default()
        .lines()
        .map(|line| line.trim_end_matches('\r').trim_start().to_string())
        .filter(|line| !line.is_empty())
        .collect()
}

/// Each indexed file with its resolved targets, or `None` for a row from before targets
/// were stored in the index.
pub(crate) fn index_targets(root: &Path) -> Vec<(String, Option<BTreeSet<String>>)> {
    index_record_lines(root)
        .into_iter()
        .filter_map(|line| {
            let mut parts = line.split('\t');
            let rel = parts.next().unwrap_or("").to_string();
            if rel.is_empty() {
                return None;
            }
            Some((rel, parts.nth(3).map(parse_dsts)))
        })
        .collect()
}

fn load_rows(root: &Path) -> (BTreeMap<String, Row>, bool) {
    let mut map = BTreeMap::new();
    let mut upgrade = false;
    for line in index_record_lines(root) {
        let mut parts = line.split('\t');
        let rel = parts.next().unwrap_or("").to_string();
        if rel.is_empty() {
            continue;
        }
        let mtime_ns = parts.next().unwrap_or("0").parse().unwrap_or(0);
        let size = parts.next().unwrap_or("0").parse().unwrap_or(0);
        let hash = parts.next().unwrap_or("").to_string();
        let dsts = match parts.next() {
            Some(raw) => parse_dsts(raw),
            None => {
                upgrade = true;
                cache::load_dependencies(root, &rel)
                    .unwrap_or_default()
                    .into_iter()
                    .collect()
            }
        };
        map.insert(
            rel.clone(),
            Row {
                rel,
                mtime_ns,
                size,
                hash,
                dsts,
            },
        );
    }
    (map, upgrade)
}

fn save_index(root: &Path, rows: &BTreeMap<String, Row>) -> Result<(), String> {
    let mut body = String::new();
    let mut paths = String::new();
    for row in rows.values() {
        body.push_str(&format!(
            "{}\t{}\t{}\t{}\t{}\n",
            row.rel,
            row.mtime_ns,
            row.size,
            row.hash,
            join_dsts(&row.dsts)
        ));
        paths.push_str(&row.rel);
        paths.push('\n');
    }
    cache::atomic_write(&cache::index_file(root), body.as_bytes())?;
    cache::atomic_write(&cache::paths_file(root), paths.as_bytes())?;
    Ok(())
}

fn index_rels(root: &Path) -> Vec<String> {
    cache::read_lines(&cache::index_file(root))
        .into_iter()
        .filter_map(|line| {
            let rel = line.split('\t').next().unwrap_or("").trim().to_string();
            if rel.is_empty() {
                None
            } else {
                Some(rel)
            }
        })
        .collect()
}

fn migrate_legacy(root: &Path) -> Result<(), String> {
    let root_dir = cache::cache_root(root);
    if cache::names_marker(root).is_file() || !root_dir.is_dir() {
        return Ok(());
    }
    for sub in ["payload", "by_src", "by_dst", "notes", "barrels"] {
        let dir = root_dir.join(sub);
        let Ok(entries) = fs::read_dir(&dir) else {
            continue;
        };
        for ent in entries.flatten() {
            let name = ent.file_name().to_string_lossy().to_string();
            if !name.contains('%') {
                continue;
            }
            let (stem, ext) = name.rsplit_once('.').unwrap_or((&name, "bin"));
            let rel = percent_decode(stem);
            let dest = cache::store_file(root, sub, &rel, ext);
            if !dest.exists() {
                let _ = fs::rename(ent.path(), dest);
            }
        }
    }
    let mut rels = index_rels(root);
    for line in cache::read_lines(&cache::index_file(root)) {
        if let Some(raw) = line.split('\t').nth(4) {
            rels.extend(parse_dsts(raw));
        }
    }
    for rel in rels {
        for (sub, ext) in cache::STORE_KINDS {
            let legacy = cache::legacy_file(root, sub, &rel, ext);
            let hashed = cache::store_file(root, sub, &rel, ext);
            if legacy.is_file() && legacy != hashed && !hashed.exists() {
                let _ = fs::rename(&legacy, &hashed);
            }
        }
    }
    cache::atomic_write(&cache::names_marker(root), b"fnv1a64\n")
}

fn percent_decode(text: &str) -> String {
    let bytes = text.as_bytes();
    let mut out = Vec::new();
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%' && i + 2 < bytes.len() {
            if let Ok(value) = u8::from_str_radix(&text[i + 1..i + 3], 16) {
                out.push(value);
                i += 3;
                continue;
            }
        }
        out.push(bytes[i]);
        i += 1;
    }
    String::from_utf8_lossy(&out).into_owned()
}

fn hash_to_rel(root: &Path) -> HashMap<String, String> {
    let mut map = HashMap::new();
    for rel in index_rels(root) {
        map.insert(cache::enc(&rel), rel.clone());
        map.insert(cache::legacy_enc(&rel), rel);
    }
    map
}

fn file_header(path: &Path) -> Option<String> {
    let text = fs::read_to_string(path).ok()?;
    text.lines()
        .next()
        .and_then(|line| line.trim().strip_prefix("@\t").map(|s| s.to_string()))
}

fn read_edge_dir(
    dir: &Path,
    names: &HashMap<String, String>,
    orphans: &mut Vec<String>,
) -> BTreeMap<String, BTreeSet<String>> {
    let mut out = BTreeMap::new();
    let Ok(entries) = fs::read_dir(dir) else {
        return out;
    };
    for ent in entries.flatten() {
        let path = ent.path();
        if path.extension().and_then(|ext| ext.to_str()) != Some("edges") {
            continue;
        }
        let stem = path
            .file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or("")
            .to_string();
        let rel = file_header(&path).or_else(|| names.get(&stem).cloned());
        let Some(rel) = rel else {
            orphans.push(format!("edge file {} has no stored path", path.display()));
            continue;
        };
        let dsts = cache::content_lines(&path)
            .into_iter()
            .map(|line| cache::dst_of(&line))
            .filter(|s| !s.is_empty())
            .collect();
        out.insert(rel, dsts);
    }
    out
}

pub fn check_consistency(root: &Path) -> Consistency {
    let incomplete = cache::commit_pending_path(root).is_file();
    let mut mismatches = Vec::new();
    if incomplete {
        mismatches.push("commit.pending is set; the last cache commit did not finish".into());
    }
    if !cache::cache_root(root).is_dir() {
        return Consistency {
            consistent: mismatches.is_empty(),
            incomplete,
            mismatches,
        };
    }
    let names = hash_to_rel(root);
    let mut orphans = Vec::new();
    let forward = read_edge_dir(
        &cache::cache_root(root).join("by_src"),
        &names,
        &mut orphans,
    );
    let reverse = read_edge_dir(
        &cache::cache_root(root).join("by_dst"),
        &names,
        &mut orphans,
    );
    mismatches.append(&mut orphans);
    let mut expected: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    for (src, dsts) in &forward {
        for dst in dsts {
            expected.entry(dst.clone()).or_default().insert(src.clone());
        }
    }
    let mut keys: BTreeSet<String> = expected.keys().cloned().collect();
    keys.extend(reverse.keys().cloned());
    for dst in keys {
        let want = expected.get(&dst).cloned().unwrap_or_default();
        let got = reverse.get(&dst).cloned().unwrap_or_default();
        for src in want.difference(&got) {
            mismatches.push(format!("by_dst {dst} missing importer {src}"));
        }
        for src in got.difference(&want) {
            mismatches.push(format!("by_dst {dst} lists extra importer {src}"));
        }
    }
    let (rows, _) = load_rows(root);
    for (rel, row) in &rows {
        let got = forward.get(rel).cloned().unwrap_or_default();
        if got != row.dsts {
            mismatches.push(format!("index dsts for {rel} disagree with by_src"));
        }
    }
    for rel in forward.keys() {
        if !rows.contains_key(rel) {
            mismatches.push(format!("by_src {rel} is not in the index"));
        }
    }
    Consistency {
        consistent: mismatches.is_empty(),
        incomplete,
        mismatches,
    }
}

pub fn rebuild(root: &Path) -> Result<(), String> {
    let _lock = LockGuard::acquire(root)?;
    migrate_legacy(root)?;
    rebuild_locked(root)
}

fn rebuild_locked(root: &Path) -> Result<(), String> {
    // by_dst is rewritten from scratch; the next open re-reads every file for its size.
    let _ = fs::remove_file(sizes_path(root));
    let (old, _) = load_rows(root);
    let names = hash_to_rel(root);
    let mut orphans = Vec::new();
    let forward = read_edge_dir(
        &cache::cache_root(root).join("by_src"),
        &names,
        &mut orphans,
    );
    if !orphans.is_empty() {
        return Err(orphans.join("; "));
    }
    let dst_dir = cache::cache_root(root).join("by_dst");
    if let Ok(entries) = fs::read_dir(&dst_dir) {
        for ent in entries.flatten() {
            if ent.path().extension().and_then(|ext| ext.to_str()) == Some("edges") {
                let _ = fs::remove_file(ent.path());
            }
        }
    }
    let mut rev: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    for (src, dsts) in &forward {
        for dst in dsts {
            rev.entry(dst.clone()).or_default().insert(src.clone());
        }
    }
    let reverse: Vec<(PathBuf, Vec<u8>)> = rev
        .iter()
        .map(|(dst, srcs)| {
            let lines: Vec<String> = srcs.iter().cloned().collect();
            let body = format!("{}\n", lines.join("\n"));
            (
                cache::store_file(root, "by_dst", dst, "edges"),
                cache::labeled(dst, &body),
            )
        })
        .collect();
    cache::write_derived_all(&reverse)?;
    let mut rows = BTreeMap::new();
    for (rel, dsts) in &forward {
        let prev = old.get(rel);
        rows.insert(
            rel.clone(),
            Row {
                rel: rel.clone(),
                mtime_ns: prev.map(|row| row.mtime_ns).unwrap_or(0),
                size: prev.map(|row| row.size).unwrap_or(0),
                hash: prev.map(|row| row.hash.clone()).unwrap_or_default(),
                dsts: dsts.clone(),
            },
        );
    }
    save_index(root, &rows)?;
    let gen = read_generation(root).saturating_add(1);
    cache::atomic_write(&cache::generation_path(root), format!("{gen}\n").as_bytes())?;
    let _ = fs::remove_file(cache::commit_pending_path(root));
    cache::atomic_write(&cache::names_marker(root), b"fnv1a64\n")?;
    Ok(())
}
