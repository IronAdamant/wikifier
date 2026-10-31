//! Per-file payloads plus src and dst edge indexes.
//! A run loads the index once, edits it in memory, and commits once.
//! Lookups read one index file, not every payload.
//! Cache file names are FNV-1a hashes so long relative paths fit on disk.
//! The original path is stored in the payload JSON and as the `@` header of edge files.

use std::collections::BTreeSet;
use std::fs::{self, OpenOptions};
#[cfg(not(windows))]
use std::fs::File;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

use crate::scope::rel_of;

pub use crate::cache_commit::{check_consistency, rebuild, Consistency, Session};

static TEMP_SEQ: AtomicU64 = AtomicU64::new(0);

pub(crate) const STORE_KINDS: &[(&str, &str)] = &[
    ("payload", "json"),
    ("by_src", "edges"),
    ("by_dst", "edges"),
    ("notes", "txt"),
    ("barrels", "json"),
];

pub(crate) fn cache_root(root: &Path) -> PathBuf {
    root.join(".wikifier_staging").join("wk_cache")
}

/// Stable FNV-1a 64. `std::hash` is keyed per process, so it cannot name cache files.
pub(crate) fn fnv1a64(data: &[u8]) -> u64 {
    let mut hash = 0xcbf29ce484222325u64;
    for byte in data {
        hash ^= u64::from(*byte);
        hash = hash.wrapping_mul(0x0000_0100_0000_01b3);
    }
    hash
}

pub(crate) fn enc(rel: &str) -> String {
    format!("{:016x}", fnv1a64(rel.as_bytes()))
}

pub(crate) fn legacy_enc(rel: &str) -> String {
    rel.replace('%', "%25").replace('/', "%2F")
}

pub(crate) fn store_file(root: &Path, sub: &str, rel: &str, ext: &str) -> PathBuf {
    cache_root(root).join(sub).join(format!("{}.{}", enc(rel), ext))
}

pub(crate) fn legacy_file(root: &Path, sub: &str, rel: &str, ext: &str) -> PathBuf {
    cache_root(root).join(sub).join(format!("{}.{}", legacy_enc(rel), ext))
}

fn read_file(root: &Path, sub: &str, rel: &str, ext: &str) -> PathBuf {
    let hashed = store_file(root, sub, rel, ext);
    if hashed.is_file() {
        return hashed;
    }
    let legacy = legacy_file(root, sub, rel, ext);
    if legacy.is_file() {
        return legacy;
    }
    hashed
}

pub fn payload_path(root: &Path, rel: &str) -> PathBuf {
    read_file(root, "payload", rel, "json")
}

pub fn by_src_path(root: &Path, rel: &str) -> PathBuf {
    read_file(root, "by_src", rel, "edges")
}

pub(crate) fn index_file(root: &Path) -> PathBuf {
    cache_root(root).join("index.tsv")
}

pub(crate) fn paths_file(root: &Path) -> PathBuf {
    cache_root(root).join("paths.txt")
}

pub fn commit_pending_path(root: &Path) -> PathBuf {
    cache_root(root).join("commit.pending")
}

pub(crate) fn generation_path(root: &Path) -> PathBuf {
    cache_root(root).join("generation")
}

pub(crate) fn names_marker(root: &Path) -> PathBuf {
    cache_root(root).join("names-v2")
}

pub(crate) fn atomic_write(path: &Path, bytes: &[u8]) -> Result<(), String> {
    let parent = path.parent().unwrap_or(Path::new("."));
    fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    let seq = TEMP_SEQ.fetch_add(1, Ordering::Relaxed);
    let file_name = path.file_name().and_then(|s| s.to_str()).unwrap_or("cache");
    let tmp = parent.join(format!(".{file_name}.{}.{seq}.tmp", std::process::id()));
    let write_result = (|| {
        let mut file = OpenOptions::new().write(true).create_new(true).open(&tmp).map_err(|e| e.to_string())?;
        file.write_all(bytes).map_err(|e| e.to_string())?;
        file.sync_all().map_err(|e| e.to_string())?;
        Ok(())
    })();
    if let Err(err) = write_result {
        let _ = fs::remove_file(&tmp);
        return Err(err);
    }
    if let Err(err) = replace_file(&tmp, path) {
        let _ = fs::remove_file(&tmp);
        return Err(err);
    }
    fsync_dir(parent);
    Ok(())
}

pub(crate) fn write_labeled(path: &Path, rel: &str, body: &str) -> Result<(), String> {
    let mut text = format!("@\t{rel}\n");
    text.push_str(body);
    if !text.ends_with('\n') {
        text.push('\n');
    }
    atomic_write(path, text.as_bytes())
}

fn replace_file(from: &Path, to: &Path) -> Result<(), String> {
    #[cfg(windows)]
    {
        replace_file_windows(from, to)
    }
    #[cfg(not(windows))]
    {
        fs::rename(from, to).map_err(|e| format!("rename {} -> {}: {e}", from.display(), to.display()))
    }
}

#[cfg(windows)]
fn replace_file_windows(from: &Path, to: &Path) -> Result<(), String> {
    use std::os::windows::ffi::OsStrExt;
    const MOVEFILE_REPLACE_EXISTING: u32 = 0x1;
    const MOVEFILE_WRITE_THROUGH: u32 = 0x8;
    #[link(name = "kernel32")]
    extern "system" {
        fn MoveFileExW(existing: *const u16, new: *const u16, flags: u32) -> i32;
    }
    fn wide(path: &Path) -> Vec<u16> {
        let mut encoded: Vec<u16> = path.as_os_str().encode_wide().collect();
        encoded.push(0);
        encoded
    }
    let src = wide(from);
    let dst = wide(to);
    let ok = unsafe { MoveFileExW(src.as_ptr(), dst.as_ptr(), MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH) };
    if ok == 0 {
        Err(format!("rename {} -> {}: {}", from.display(), to.display(), std::io::Error::last_os_error()))
    } else {
        Ok(())
    }
}

fn fsync_dir(path: &Path) {
    #[cfg(not(windows))]
    {
        if let Ok(file) = File::open(path) {
            let _ = file.sync_all();
        }
    }
    #[cfg(windows)]
    {
        fsync_dir_windows(path);
    }
}

#[cfg(windows)]
fn fsync_dir_windows(path: &Path) {
    use std::os::windows::ffi::OsStrExt;
    const GENERIC_WRITE: u32 = 0x4000_0000;
    const FILE_SHARE_READ: u32 = 0x1;
    const FILE_SHARE_WRITE: u32 = 0x2;
    const OPEN_EXISTING: u32 = 3;
    const FILE_FLAG_BACKUP_SEMANTICS: u32 = 0x0200_0000;
    #[link(name = "kernel32")]
    extern "system" {
        fn CreateFileW(
            name: *const u16,
            access: u32,
            share: u32,
            security: *mut core::ffi::c_void,
            disposition: u32,
            flags: u32,
            template: *mut core::ffi::c_void,
        ) -> *mut core::ffi::c_void;
        fn FlushFileBuffers(handle: *mut core::ffi::c_void) -> i32;
        fn CloseHandle(handle: *mut core::ffi::c_void) -> i32;
    }
    let mut wide: Vec<u16> = path.as_os_str().encode_wide().collect();
    wide.push(0);
    unsafe {
        let handle = CreateFileW(
            wide.as_ptr(),
            GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            std::ptr::null_mut(),
            OPEN_EXISTING,
            FILE_FLAG_BACKUP_SEMANTICS,
            std::ptr::null_mut(),
        );
        if handle.is_null() || handle == (-1isize as *mut core::ffi::c_void) {
            return;
        }
        FlushFileBuffers(handle);
        CloseHandle(handle);
    }
}

pub(crate) fn read_lines(path: &Path) -> Vec<String> {
    fs::read_to_string(path).unwrap_or_default().lines().map(|s| s.trim().to_string()).filter(|s| !s.is_empty()).collect()
}

pub(crate) fn content_lines(path: &Path) -> Vec<String> {
    read_lines(path).into_iter().filter(|line| !line.starts_with("@\t")).collect()
}

pub(crate) fn dst_of(line: &str) -> String {
    line.split('\t').next().unwrap_or("").trim().to_string()
}

pub fn load_dependencies(root: &Path, rel: &str) -> Result<Vec<String>, String> {
    let mut dsts: Vec<String> = content_lines(&by_src_path(root, rel)).into_iter().map(|line| dst_of(&line)).filter(|s| !s.is_empty()).collect();
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
    read_file(root, "notes", rel, "txt")
}

pub fn load_dependency_view(root: &Path, rel: &str) -> Result<DependencyView, String> {
    let mut internal = Vec::new();
    for line in content_lines(&by_src_path(root, rel)) {
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
    let mut srcs = content_lines(&read_file(root, "by_dst", rel, "edges"));
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

/// Write one file. Prefer [`Session`] when updating many files in one run.
pub fn upsert_file(root: &Path, upd: &FileUpdate) -> Result<(), String> {
    let mut session = Session::open(root)?;
    session.upsert(upd);
    session.commit()
}

pub fn remove_file(root: &Path, rel: &str) -> Result<(), String> {
    let mut session = Session::open(root)?;
    session.remove(rel);
    session.commit()
}

pub fn indexed_rows(root: &Path) -> Vec<(String, u128, u64, String)> {
    read_lines(&index_file(root))
        .into_iter()
        .filter_map(|line| {
            let mut parts = line.split('\t');
            let rel = parts.next().unwrap_or("").to_string();
            if rel.is_empty() {
                return None;
            }
            let mtime_ns = parts.next().unwrap_or("0").parse().unwrap_or(0);
            let size = parts.next().unwrap_or("0").parse().unwrap_or(0);
            let hash = parts.next().unwrap_or("").to_string();
            Some((rel, mtime_ns, size, hash))
        })
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

pub fn write_barrel_record(root: &Path, rel: &str, dsts: &[String]) -> Result<(), String> {
    let _lock = crate::cache_commit::LockGuard::acquire(root)?;
    let body = crate::jsonutil::Json::obj(vec![
        ("src", crate::jsonutil::Json::String(rel.to_string())),
        ("dsts", crate::jsonutil::Json::Array(dsts.iter().cloned().map(crate::jsonutil::Json::String).collect())),
    ]);
    atomic_write(&store_file(root, "barrels", rel, "json"), body.to_string().as_bytes())
}

pub fn prune_barrel_files(root: &Path, max_age_days: f64, dry_run: bool) -> Result<usize, String> {
    let _lock = crate::cache_commit::LockGuard::acquire(root)?;
    let dir = cache_root(root).join("barrels");
    let entries = match fs::read_dir(&dir) {
        Ok(entries) => entries,
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
        let dsts: Vec<String> = parsed
            .as_ref()
            .and_then(|v| v.get("dsts"))
            .and_then(|v| v.as_array())
            .map(|items| items.iter().filter_map(|item| item.as_str().map(|s| s.to_string())).collect())
            .unwrap_or_default();
        let dangling = src.is_empty() || !root.join(src).is_file() || dsts.iter().any(|dst| !root.join(dst).is_file());
        let aged = ent
            .metadata()
            .ok()
            .and_then(|meta| meta.modified().ok())
            .and_then(|t| now.duration_since(t).ok())
            .map(|age| age > max_age)
            .unwrap_or(false);
        if dangling || aged {
            pruned += 1;
            if !dry_run {
                let _ = fs::remove_file(&path);
            }
        }
    }
    Ok(pruned)
}
