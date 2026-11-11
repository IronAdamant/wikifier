//! Modularity alerts and changed-line ranges.
//!
//! Alerts are derived from the files and the last dependency map. They are not
//! a rewrite and they do not change health status. Line ranges compare a file
//! with the snapshot saved at mark-green so an agent can review the lines that
//! drifted. This is not a linter.

use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::fs;
use std::path::{Path, PathBuf};

use crate::jsonutil::Json;

#[derive(Clone)]
pub(crate) struct Alert {
    pub file: String,
    pub kind: &'static str,
    pub value: u64,
    pub threshold: u64,
}

/// Alerts listed in a reply unless `full` asks for all of them. `alert_count` and
/// `by_kind` always give the totals. On Specula the whole list was 215 alerts and 59 KB.
pub(crate) const LISTED: usize = 10;

impl Alert {
    /// How far past its limit the file is: 2.0 is twice the threshold. Lists rank by it.
    pub(crate) fn severity(&self) -> f64 {
        self.value as f64 / self.threshold.max(1) as f64
    }

    pub(crate) fn key(&self) -> String {
        format!("{}\t{}", self.file, self.kind)
    }

    pub(crate) fn reason(&self) -> String {
        match self.kind {
            "line_count" => format!(
                "{} has {} lines, over the modularity limit of {}. Alert only; the file was not split.",
                self.file, self.value, self.threshold
            ),
            _ => format!(
                "{} has {} dependents, over the fan-in limit of {}. Alert only; the file was not split.",
                self.file, self.value, self.threshold
            ),
        }
    }
}

pub(crate) fn alerts(root: &Path, directory: Option<&str>) -> Vec<Alert> {
    let (mut found, _) = compute(root, &read_state(root).line_cache);
    if let Some(dir) = directory
        .map(|d| d.trim_matches('/'))
        .filter(|d| !d.is_empty())
    {
        found.retain(|alert| alert.file == dir || alert.file.starts_with(&format!("{dir}/")));
    }
    found
}

/// Recompute alerts, journal a crossing the first time it appears, and write
/// `.wikifier_staging/modularity.json` for every agent that shares this root.
pub(crate) fn refresh(root: &Path) -> Vec<Alert> {
    let mut state = read_state(root);
    let (found, cache) = compute(root, &state.line_cache);
    let live: BTreeSet<String> = found.iter().map(Alert::key).collect();
    state.journaled.retain(|key| live.contains(key));
    for alert in &found {
        if state.journaled.insert(alert.key()) {
            let _ =
                crate::artifacts::append_journal(root, "modularity", &alert.file, &alert.reason());
        }
    }
    state.line_cache = cache;
    state.alerts = found.clone();
    let _ = write_state(root, &state);
    found
}

pub(crate) fn save_baseline(root: &Path, rel: &str) {
    // A worktree reads main's snapshots and never replaces them.
    if crate::worktree::is_overlay(root) {
        return;
    }
    let Ok(bytes) = fs::read(root.join(rel)) else {
        return;
    };
    let path = baseline_path(root, rel);
    let _ = crate::cache::atomic_write(&path, &normalize_newlines(&bytes));
}

pub(crate) fn ensure_baseline(root: &Path, rel: &str) {
    if baseline_path(root, rel).is_file() {
        return;
    }
    save_baseline(root, rel);
}

/// `Some` when a mark-green snapshot exists (ranges may be empty). `None` when
/// there is nothing to diff against.
pub(crate) fn ranges_since_baseline(root: &Path, rel: &str) -> Option<Vec<(u32, u32)>> {
    let path = baseline_path(root, rel);
    let before = fs::read(&path).ok()?;
    let after = fs::read(root.join(rel)).unwrap_or_default();
    Some(changed_line_ranges(&before, &normalize_newlines(&after)))
}

pub(crate) fn whole_file_range(root: &Path, rel: &str) -> Vec<(u32, u32)> {
    let Ok(bytes) = fs::read(root.join(rel)) else {
        return Vec::new();
    };
    let n = physical_lines(&bytes);
    if n == 0 {
        Vec::new()
    } else {
        vec![(1, n as u32)]
    }
}

pub(crate) fn lines_json(ranges: &[(u32, u32)]) -> Json {
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

pub(crate) fn format_ranges(ranges: &[(u32, u32)]) -> String {
    ranges
        .iter()
        .map(|(start, end)| {
            if start == end {
                format!("{start}")
            } else {
                format!("{start}-{end}")
            }
        })
        .collect::<Vec<_>>()
        .join(", ")
}

pub(crate) fn line_count(root: &Path, rel: &str) -> u64 {
    fs::read(root.join(rel))
        .map(|bytes| physical_lines(&bytes))
        .unwrap_or(0)
}

/// Inclusive 1-based ranges in `after` that differ from `before`. A pure
/// deletion is the surviving line beside the gap. Identical inputs are empty.
pub(crate) fn changed_line_ranges(before: &[u8], after: &[u8]) -> Vec<(u32, u32)> {
    let before = normalize_newlines(before);
    let after = normalize_newlines(after);
    if before == after {
        return Vec::new();
    }
    let old = split_lines(&before);
    let new = split_lines(&after);
    let mut ranges = Vec::new();
    diff_window(&old, &new, 0, new.len(), 0, &mut ranges);
    coalesce(&mut ranges);
    if ranges.is_empty() && !new.is_empty() {
        let last = new.len() as u32;
        ranges.push((last, last));
    }
    ranges
}

fn compute(
    root: &Path,
    cache: &HashMap<String, LineRec>,
) -> (Vec<Alert>, HashMap<String, LineRec>) {
    let thresholds = crate::project_config::thresholds(root);
    let mut fan_in: HashMap<String, u64> = HashMap::new();
    for (_src, dst) in crate::cache::edges(root) {
        *fan_in.entry(dst).or_default() += 1;
    }
    let mut next_cache = HashMap::new();
    let mut found = Vec::new();
    // A worktree counts the lines of a file it did not change in main's copy, with main's
    // line cache, instead of reading its own copy.
    let base_view = crate::worktree::base_view(root);
    let main_cache = base_view
        .as_ref()
        .map(|view| read_state(view.main()).line_cache)
        .unwrap_or_default();
    for rel in crate::cache::all_paths(root) {
        let from_main = base_view
            .as_ref()
            .filter(|view| view.unchanged(root, &rel))
            .map(|view| view.main_path(&rel));
        let (path, prior) = match from_main {
            Some(main_path) => (main_path, main_cache.get(&rel)),
            None => (root.join(&rel), cache.get(&rel)),
        };
        if !path.is_file() {
            continue;
        }
        let Some((lines, rec)) = cached_lines(&path, prior) else {
            continue;
        };
        next_cache.insert(rel.clone(), rec);
        if thresholds.max_lines > 0 && lines > thresholds.max_lines {
            found.push(Alert {
                file: rel.clone(),
                kind: "line_count",
                value: lines,
                threshold: thresholds.max_lines,
            });
        }
        let inbound = fan_in.get(&rel).copied().unwrap_or(0);
        if thresholds.max_fan_in > 0 && inbound > thresholds.max_fan_in && !entry_point(&rel) {
            found.push(Alert {
                file: rel,
                kind: "fan_in",
                value: inbound,
                threshold: thresholds.max_fan_in,
            });
        }
    }
    found.sort_by(|a, b| {
        b.severity()
            .total_cmp(&a.severity())
            .then(a.file.cmp(&b.file))
            .then(a.kind.cmp(b.kind))
    });
    (found, next_cache)
}

/// Files every importer of a package resolves to: a crate root (`use my_crate::X` points
/// at `lib.rs`), a Python package `__init__.py`, a JS/TS `index` barrel. Their fan-in is
/// the package's, so a fan-in alert on them is noise (Specula: `specula-core/src/lib.rs`
/// with 242 dependents). Their line count still alerts.
fn entry_point(rel: &str) -> bool {
    let name = rel.rsplit('/').next().unwrap_or(rel);
    matches!(
        name,
        "lib.rs"
            | "main.rs"
            | "__init__.py"
            | "index.ts"
            | "index.tsx"
            | "index.js"
            | "index.jsx"
            | "index.mjs"
            | "index.cjs"
            | "index.mts"
            | "index.cts"
    )
}

struct LineRec {
    size: u64,
    mtime_ns: String,
    lines: u64,
}

fn cached_lines(path: &Path, prior: Option<&LineRec>) -> Option<(u64, LineRec)> {
    let meta = fs::metadata(path).ok()?;
    let size = meta.len();
    let mtime_ns = meta
        .modified()
        .ok()?
        .duration_since(std::time::UNIX_EPOCH)
        .ok()?
        .as_nanos()
        .to_string();
    if let Some(prior) = prior {
        if prior.size == size && prior.mtime_ns == mtime_ns {
            return Some((
                prior.lines,
                LineRec {
                    size,
                    mtime_ns,
                    lines: prior.lines,
                },
            ));
        }
    }
    let bytes = fs::read(path).ok()?;
    let lines = physical_lines(&bytes);
    Some((
        lines,
        LineRec {
            size,
            mtime_ns,
            lines,
        },
    ))
}

fn physical_lines(bytes: &[u8]) -> u64 {
    if bytes.is_empty() {
        return 0;
    }
    let mut n = 0u64;
    for byte in bytes {
        if *byte == b'\n' {
            n += 1;
        }
    }
    if !bytes.ends_with(b"\n") {
        n += 1;
    }
    n
}

struct Snap {
    line_cache: HashMap<String, LineRec>,
    journaled: BTreeSet<String>,
    alerts: Vec<Alert>,
}

fn read_state(root: &Path) -> Snap {
    let mut snap = Snap {
        line_cache: HashMap::new(),
        journaled: BTreeSet::new(),
        alerts: Vec::new(),
    };
    let Ok(text) = fs::read_to_string(snapshot_path(root)) else {
        return snap;
    };
    let Ok(json) = crate::jsonutil::parse(&text) else {
        return snap;
    };
    if let Some(Json::Array(items)) = json.get("journaled") {
        for item in items {
            if let Some(key) = item.as_str() {
                snap.journaled.insert(key.to_string());
            }
        }
    }
    if let Some(Json::Object(map)) = json.get("line_cache") {
        for (file, rec) in map {
            let Some(size) = rec.get("size").and_then(json_u64) else {
                continue;
            };
            let Some(lines) = rec.get("lines").and_then(json_u64) else {
                continue;
            };
            let Some(mtime_ns) = rec.get("mtime_ns").and_then(|v| v.as_str()) else {
                continue;
            };
            snap.line_cache.insert(
                file.clone(),
                LineRec {
                    size,
                    mtime_ns: mtime_ns.to_string(),
                    lines,
                },
            );
        }
    }
    snap
}

fn write_state(root: &Path, state: &Snap) -> Result<(), String> {
    let thresholds = crate::project_config::thresholds(root);
    let cache = Json::from_pairs(
        state
            .line_cache
            .iter()
            .map(|(file, rec)| {
                (
                    file.clone(),
                    Json::obj(vec![
                        ("size", Json::Int(rec.size as i64)),
                        ("mtime_ns", Json::String(rec.mtime_ns.clone())),
                        ("lines", Json::Int(rec.lines as i64)),
                    ]),
                )
            })
            .collect(),
    );
    let body = Json::obj(vec![
        ("max_lines", Json::Int(thresholds.max_lines as i64)),
        ("max_fan_in", Json::Int(thresholds.max_fan_in as i64)),
        (
            "journaled",
            Json::Array(state.journaled.iter().cloned().map(Json::String).collect()),
        ),
        ("line_cache", cache),
        (
            "alerts",
            Json::Array(state.alerts.iter().map(alert_json).collect()),
        ),
    ]);
    crate::cache::atomic_write(&snapshot_path(root), body.to_string().as_bytes())
}

fn alert_json(alert: &Alert) -> Json {
    Json::obj(vec![
        ("file", Json::String(alert.file.clone())),
        ("kind", Json::String(alert.kind.into())),
        ("value", Json::Int(alert.value as i64)),
        ("threshold", Json::Int(alert.threshold as i64)),
        ("reason", Json::String(alert.reason())),
    ])
}

pub(crate) fn snapshot_path(root: &Path) -> PathBuf {
    crate::worktree::staging(root).join("modularity.json")
}

fn baseline_path(root: &Path, rel: &str) -> PathBuf {
    crate::worktree::baselines(root).join(format!("{}.txt", crate::cache::enc(rel)))
}

fn json_u64(value: &Json) -> Option<u64> {
    match value {
        Json::Int(n) if *n >= 0 => Some(*n as u64),
        _ => None,
    }
}

fn normalize_newlines(bytes: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'\r' && bytes.get(i + 1) == Some(&b'\n') {
            i += 1;
            continue;
        }
        out.push(bytes[i]);
        i += 1;
    }
    out
}

fn split_lines(bytes: &[u8]) -> Vec<String> {
    String::from_utf8_lossy(bytes)
        .lines()
        .map(|line| line.to_string())
        .collect()
}

/// Unique shared lines split a window. Without one, the whole new window is a
/// single range. Depth is capped so a large file cannot recurse without bound.
fn diff_window(
    old: &[String],
    new: &[String],
    new_base: usize,
    new_len: usize,
    depth: u32,
    out: &mut Vec<(u32, u32)>,
) {
    if old.is_empty() && new.is_empty() {
        return;
    }
    if depth > 64 {
        push_window(new, new_base, new_len, out);
        return;
    }
    if old.is_empty() {
        push_window(new, new_base, new_len, out);
        return;
    }
    if new.is_empty() {
        push_deletion(new_base, new_len, out);
        return;
    }
    let mut start = 0;
    while start < old.len() && start < new.len() && old[start] == new[start] {
        start += 1;
    }
    let mut old_end = old.len();
    let mut new_end = new.len();
    while old_end > start && new_end > start && old[old_end - 1] == new[new_end - 1] {
        old_end -= 1;
        new_end -= 1;
    }
    let old_mid = &old[start..old_end];
    let new_mid = &new[start..new_end];
    let mid_base = new_base + start;
    if old_mid.is_empty() && new_mid.is_empty() {
        return;
    }
    if let Some((old_at, new_at)) = first_anchor(old_mid, new_mid) {
        diff_window(
            &old_mid[..old_at],
            &new_mid[..new_at],
            mid_base,
            new_len,
            depth + 1,
            out,
        );
        diff_window(
            &old_mid[old_at + 1..],
            &new_mid[new_at + 1..],
            mid_base + new_at + 1,
            new_len,
            depth + 1,
            out,
        );
        return;
    }
    if new_mid.is_empty() {
        push_deletion(mid_base, new_len, out);
    } else {
        push_window(new_mid, mid_base, new_len, out);
    }
}

fn push_window(lines: &[String], base: usize, _new_len: usize, out: &mut Vec<(u32, u32)>) {
    if lines.is_empty() {
        return;
    }
    let start = (base + 1) as u32;
    let end = (base + lines.len()) as u32;
    out.push((start, end));
}

fn push_deletion(new_base: usize, new_len: usize, out: &mut Vec<(u32, u32)>) {
    if new_len == 0 {
        return;
    }
    let line = if new_base == 0 {
        1
    } else if new_base >= new_len {
        new_len
    } else {
        new_base + 1
    };
    let line = line as u32;
    out.push((line, line));
}

fn first_anchor(old: &[String], new: &[String]) -> Option<(usize, usize)> {
    let mut old_counts: BTreeMap<&str, usize> = BTreeMap::new();
    let mut new_counts: BTreeMap<&str, usize> = BTreeMap::new();
    for line in old {
        *old_counts.entry(line).or_default() += 1;
    }
    for line in new {
        *new_counts.entry(line).or_default() += 1;
    }
    for (new_at, line) in new.iter().enumerate() {
        if new_counts.get(line.as_str()) == Some(&1) && old_counts.get(line.as_str()) == Some(&1) {
            let old_at = old.iter().position(|item| item == line)?;
            return Some((old_at, new_at));
        }
    }
    None
}

fn coalesce(ranges: &mut Vec<(u32, u32)>) {
    if ranges.is_empty() {
        return;
    }
    ranges.sort_by(|a, b| a.0.cmp(&b.0).then(a.1.cmp(&b.1)));
    let mut out = vec![ranges[0]];
    for (start, end) in ranges.iter().skip(1).copied() {
        let last = out.last_mut().unwrap();
        if start <= last.1.saturating_add(1) {
            last.1 = last.1.max(end);
        } else {
            out.push((start, end));
        }
    }
    *ranges = out;
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn two_hunks_stay_apart() {
        let before = b"def alpha():\n    return 1\n\ndef beta():\n    return 2\n";
        let after = b"def alpha():\n    return 9\n\ndef beta():\n    return 2\n    return 3\n";
        assert_eq!(changed_line_ranges(before, after), vec![(2, 2), (6, 6)]);
    }

    #[test]
    fn deletion_points_at_the_surviving_neighbour() {
        let before = b"a\nb\nc\n";
        let after = b"a\nc\n";
        assert_eq!(changed_line_ranges(before, after), vec![(2, 2)]);
    }
}
