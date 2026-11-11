//! Worktree overlays. A read tool called with `worktree_root` answers for that git
//! worktree: main's maps plus the files that differ in the tree.
//!
//! The overlay lives in main's `.wikifier_staging/overlays/<fnv of the tree path>/`. It is
//! seeded once from a copy of main's `wk_cache`, then refreshed on every call by the same
//! incremental map run `update-maps` uses: size and mtime skip unchanged files, and a file
//! whose bytes still hash to main's row is not re-parsed. Main's cache, health, journal,
//! pending list and mark-green snapshots are never written. Health, pending and
//! `library.md` for the tree are written under the overlay's `state/`; journal entries
//! are dropped. Writers (`record_change`, `mark_green`, ...) refuse a worktree.
//!
//! While a call runs, the tree's path is registered here, and the path helpers below
//! ([`staging`], [`state`], [`state_write`], [`baselines`]) send that root's reads and
//! writes to the overlay. A root that is not registered gets the plain paths it always had.

use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Mutex;
use std::time::Duration;

use crate::jsonutil::Json;

#[derive(Clone, Debug)]
struct Overlay {
    main: PathBuf,
    tree: PathBuf,
    dir: PathBuf,
}

static ACTIVE: AtomicUsize = AtomicUsize::new(0);
static REGISTRY: Mutex<Vec<Overlay>> = Mutex::new(Vec::new());

/// Health and pending are rebuilt from main's on every call, so a mark-green on main shows
/// up in the tree at once. `library.md` is kept: it only changes with the overlay cache.
const STATE_RESET: &[&str] = &["file_health.json", "file_health.md", "pending_updates.md"];

/// Overlays whose worktree.txt never appeared (a seed that died) are pruned after this.
const PARTIAL_SEED_AGE: Duration = Duration::from_secs(3600);

fn find(root: &Path) -> Option<Overlay> {
    if ACTIVE.load(Ordering::Acquire) == 0 {
        return None;
    }
    let guard = REGISTRY.lock().ok()?;
    guard.iter().find(|o| o.tree == root).cloned()
}

/// True while `root` is a worktree being answered from an overlay.
pub(crate) fn is_overlay(root: &Path) -> bool {
    find(root).is_some()
}

/// The `.wikifier_staging` directory for `root`: the overlay directory for a registered
/// worktree, else `root/.wikifier_staging`.
pub(crate) fn staging(root: &Path) -> PathBuf {
    match find(root) {
        Some(o) => o.dir,
        None => root.join(".wikifier_staging"),
    }
}

/// Where to read a root-level state or config file (`file_health.json`, `journal`,
/// `map_paths.txt`, a wiki, ...). For a worktree: the overlay's own copy, then the tree's
/// file, then main's. Main's is returned even when it is missing, so callers see a miss.
pub(crate) fn state(root: &Path, rel: &str) -> PathBuf {
    let Some(o) = find(root) else {
        return root.join(rel);
    };
    let own = o.dir.join("state").join(rel);
    if own.exists() {
        return own;
    }
    let tree = o.tree.join(rel);
    if tree.exists() {
        return tree;
    }
    o.main.join(rel)
}

/// Where to write a root-level state file. For a worktree it is the overlay's `state/`,
/// with the parent directory created.
pub(crate) fn state_write(root: &Path, rel: &str) -> PathBuf {
    let Some(o) = find(root) else {
        return root.join(rel);
    };
    let path = o.dir.join("state").join(rel);
    if let Some(parent) = path.parent() {
        let _ = fs::create_dir_all(parent);
    }
    path
}

/// Mark-green snapshots. A worktree reads main's (its changed lines are measured against
/// the last mark-green on main) and never writes them.
pub(crate) fn baselines(root: &Path) -> PathBuf {
    match find(root) {
        Some(o) => o.main.join(".wikifier_staging").join("baselines"),
        None => root.join(".wikifier_staging").join("baselines"),
    }
}

type Rows = std::collections::HashMap<String, (u128, u64, String)>;

/// Main's map next to the overlay's, for the files the branch did not change. Health and
/// modularity treat such a file as main's: main's health row as it stands, main's line
/// count, and no read of the tree's copy (which on a fresh checkout is slow to read).
pub(crate) struct BaseView {
    main: PathBuf,
    base: Rows,
    over: Rows,
}

impl BaseView {
    /// True when `rel` in the tree holds the bytes main's map hashed: the overlay row
    /// still matches the file's size and mtime, and its hash is main's row hash.
    pub(crate) fn unchanged(&self, root: &Path, rel: &str) -> bool {
        let (Some(over), Some(base)) = (self.over.get(rel), self.base.get(rel)) else {
            return false;
        };
        over.2 == base.2
            && over.2.starts_with("sha256:")
            && crate::cache::stat_ns(&root.join(rel)) == Some((over.0, over.1))
    }

    /// Main's copy of `rel`.
    pub(crate) fn main_path(&self, rel: &str) -> PathBuf {
        self.main.join(rel)
    }

    pub(crate) fn main(&self) -> &Path {
        &self.main
    }
}

/// `Some` while `root` is a worktree being answered from an overlay.
pub(crate) fn base_view(root: &Path) -> Option<BaseView> {
    let overlay = find(root)?;
    Some(BaseView {
        base: crate::cache::index_by_path(&overlay.main),
        over: crate::cache::index_by_path(root),
        main: overlay.main,
    })
}

struct Registration {
    tree: PathBuf,
}

impl Registration {
    fn new(overlay: Overlay) -> Self {
        let tree = overlay.tree.clone();
        if let Ok(mut guard) = REGISTRY.lock() {
            guard.push(overlay);
            ACTIVE.fetch_add(1, Ordering::AcqRel);
        }
        Registration { tree }
    }
}

impl Drop for Registration {
    fn drop(&mut self) {
        if let Ok(mut guard) = REGISTRY.lock() {
            if let Some(i) = guard.iter().position(|o| o.tree == self.tree) {
                guard.remove(i);
                ACTIVE.fetch_sub(1, Ordering::AcqRel);
            }
        }
    }
}

/// What one dispatch should run against.
pub(crate) enum Target {
    Main,
    Tree { main: PathBuf, tree: PathBuf },
    Fail(Json),
}

fn fail(error_type: &str, error: String) -> Json {
    Json::obj(vec![
        ("success", Json::Bool(false)),
        ("error", Json::String(error)),
        ("error_type", Json::String(error_type.into())),
    ])
}

/// `worktree` / `worktree_root` in `flags` (CLI `--worktree`, MCP `worktree_root`) picks a
/// tree. Without it, a root that is a linked git worktree with no Wikifier state of its
/// own, whose main checkout has that state, is answered as that worktree, so a server
/// started inside a worktree (or a `project_root` pointing at one) gets the tree's answer
/// instead of an empty map. Every other root runs as it always did.
pub(crate) fn target(root: &Path, name: &str, flags: &BTreeMap<String, String>) -> Target {
    let raw = ["worktree", "worktree_root", "worktree-root"]
        .iter()
        .find_map(|key| flags.get(*key))
        .map(|s| s.trim().to_string());
    match raw {
        Some(raw) if raw.is_empty() => Target::Main,
        Some(raw) if raw == "true" => Target::Fail(fail(
            "WorktreeError",
            "--worktree needs a path: pass the absolute path of your git worktree.".into(),
        )),
        Some(raw) => match validate(root, &raw) {
            Ok(Some(tree)) => Target::Tree {
                main: clean(root.canonicalize().unwrap_or_else(|_| root.to_path_buf())),
                tree,
            },
            Ok(None) => Target::Main,
            Err(err) => Target::Fail(fail("WorktreeError", err)),
        },
        None => match auto(root, name) {
            Some((main, tree)) => Target::Tree { main, tree },
            None => Target::Main,
        },
    }
}

/// `Ok(None)` when the tree is main itself.
fn validate(main: &Path, raw: &str) -> Result<Option<PathBuf>, String> {
    let given = PathBuf::from(raw);
    if !given.is_absolute() {
        return Err(format!(
            "worktree_root must be an absolute path, got {raw}. Pass the full path of your git worktree."
        ));
    }
    if !given.is_dir() {
        return Err(format!(
            "worktree_root does not exist: {raw}. Pass the absolute path of your git worktree (git worktree list shows them), or omit it to query main."
        ));
    }
    let tree = clean(given.canonicalize().map_err(|e| format!("{raw}: {e}"))?);
    let main_real = clean(main.canonicalize().unwrap_or_else(|_| main.to_path_buf()));
    if tree == main_real {
        return Ok(None);
    }
    match (git_common_dir(&main_real), git_common_dir(&tree)) {
        (Some(base), Some(other)) if base == other => Ok(Some(tree)),
        (Some(base), Some(other)) => Err(format!(
            "worktree_root {} is not a checkout of {}: its git common dir is {}, main's is {}. Pass a worktree made with git -C <main> worktree add, or omit worktree_root.",
            tree.display(),
            main_real.display(),
            other.display(),
            base.display()
        )),
        (Some(_), None) => Err(format!(
            "worktree_root {} has no .git, so it is not a worktree of {}. Pass the worktree's top-level directory (git rev-parse --show-toplevel).",
            tree.display(),
            main_real.display()
        )),
        // Main is not a git checkout: any other directory is a copy of the project.
        (None, _) => Ok(Some(tree)),
    }
}

fn auto(root: &Path, name: &str) -> Option<(PathBuf, PathBuf)> {
    if name == "init" || !root.join(".git").is_file() || has_state(root) {
        return None;
    }
    let tree = clean(root.canonicalize().ok()?);
    let common = git_common_dir(&tree)?;
    if common.file_name()?.to_str()? != ".git" {
        return None;
    }
    let main = common.parent()?.to_path_buf();
    if main == tree || !has_state(&main) {
        return None;
    }
    Some((main, tree))
}

fn has_state(dir: &Path) -> bool {
    dir.join(".wikifier_staging").join("wk_cache").is_dir()
        || dir.join("map_paths.txt").is_file()
        || dir.join("file_health.json").is_file()
}

/// The git common dir of a checkout: `.git` itself for a main checkout, the `commondir`
/// of the `gitdir:` a linked worktree's `.git` file names. Read from files, no `git` call.
fn git_common_dir(dir: &Path) -> Option<PathBuf> {
    let dot = dir.join(".git");
    if dot.is_dir() {
        return dot.canonicalize().ok().map(clean);
    }
    let text = fs::read_to_string(&dot).ok()?;
    let gitdir = text
        .lines()
        .find_map(|l| l.trim().strip_prefix("gitdir:"))?;
    let gitdir = dir.join(gitdir.trim());
    let common = match fs::read_to_string(gitdir.join("commondir")) {
        Ok(rel) => gitdir.join(rel.trim()),
        Err(_) => gitdir,
    };
    common.canonicalize().ok().map(clean)
}

/// `\\?\D:\x` from `canonicalize` on Windows is `D:\x` in replies and comparisons.
fn clean(path: PathBuf) -> PathBuf {
    let text = path.to_string_lossy();
    if let Some(rest) = text.strip_prefix(r"\\?\") {
        if !rest.starts_with("UNC\\") {
            return PathBuf::from(rest);
        }
    }
    path
}

/// Commands that write main's state or run a long-lived loop. They refuse a worktree.
fn refuses(name: &str) -> bool {
    matches!(
        name,
        "record-change"
            | "record_change"
            | "record-changes"
            | "record_changes"
            | "record-deletion"
            | "record_deletion"
            | "mark-green"
            | "mark_green"
            | "heal-stubs"
            | "heal_stubs"
            | "seed-health"
            | "seed-source-hashes"
            | "seed_source_content_hashes"
            | "prune-pending"
            | "prune-health"
            | "prune-barrels"
            | "prune-brc"
            | "gc-barrels"
            | "init"
            | "monitor"
            | "serve"
            | "daemon"
    )
}

/// Run `name` for `tree`, answered from main's maps plus the tree's changed files.
pub(crate) fn run(
    name: &str,
    main: &Path,
    tree: &Path,
    positional: &[String],
    flags: &BTreeMap<String, String>,
) -> Json {
    if refuses(name) {
        return fail(
            "WorktreeReadOnly",
            format!(
                "{name} writes Wikifier state, which lives only on main ({}); it does not take a worktree ({}). Run it on main after the branch merges. Read tools take worktree_root.",
                main.display(),
                tree.display()
            ),
        );
    }
    let active = match prepare(main, tree, needs_health(name)) {
        Ok(active) => active,
        Err(err) => return fail("WorktreeError", err),
    };
    let mut flags = flags.clone();
    for key in ["worktree", "worktree_root", "worktree-root"] {
        flags.remove(key);
    }
    let mut value = crate::api::dispatch_main(name, tree, positional, &flags);
    if value.as_object().is_some() {
        if let Some(mut modularity) = value.get("modularity").cloned() {
            let directory = flags.get("directory").map(|s| s.as_str());
            modularity.insert("new_in_worktree", new_alerts(main, tree, directory));
            value.insert("modularity", modularity);
        }
        value.insert("worktree", Json::String(tree.display().to_string()));
        value.insert("overlay_files", Json::Int(active.overlay_files as i64));
    }
    drop(active);
    value
}

/// Modularity alerts in the tree that main does not have: what this branch made
/// non-modular.
fn new_alerts(main: &Path, tree: &Path, directory: Option<&str>) -> Json {
    let base: BTreeSet<String> = crate::drift::alerts(main, directory)
        .iter()
        .map(|a| a.key())
        .collect();
    Json::Array(
        crate::drift::alerts(tree, directory)
            .into_iter()
            .filter(|a| !base.contains(&a.key()))
            .map(|a| {
                Json::obj(vec![
                    ("file", Json::String(a.file.clone())),
                    ("kind", Json::String(a.kind.into())),
                    ("value", Json::Int(a.value as i64)),
                    ("threshold", Json::Int(a.threshold as i64)),
                ])
            })
            .collect(),
    )
}

struct Active {
    // Field order is drop order: release the overlay lock, then unregister the tree.
    _lock: crate::project_lock::ProjectLock,
    _registration: Registration,
    overlay_files: usize,
}

fn overlays_dir(main: &Path) -> PathBuf {
    main.join(".wikifier_staging").join("overlays")
}

/// The overlay directory for `tree` under `main`. Stable across runs and processes.
pub(crate) fn overlay_dir(main: &Path, tree: &Path) -> PathBuf {
    overlays_dir(main).join(crate::cache::enc(&tree.to_string_lossy()))
}

/// Lookups that read only the map skip the health pass, so `get_dependents` on a worktree
/// costs a stat walk, not a hash of every drifted file.
fn needs_health(name: &str) -> bool {
    !matches!(
        name,
        "get_dependents"
            | "dependents"
            | "importers"
            | "get_dependencies"
            | "dependencies"
            | "deps"
            | "get_cycles"
            | "cycles"
            | "list_paths"
            | "list-paths"
            | "why_file"
            | "why-file"
            | "why"
            | "search_journal"
            | "search-journal"
            | "journal"
            | "get_file_wiki"
            | "get_resolution_diagnostics"
            | "get_barrel_reports"
            | "get_incremental_status"
            | "get_current_project_root"
            | "update_maps"
            | "update-maps"
            | "cache-status"
            | "cache"
            | "rebuild-cache"
            | "rebuild_cache"
    )
}

fn prepare(main: &Path, tree: &Path, health: bool) -> Result<Active, String> {
    let dir = overlay_dir(main, tree);
    prune(&overlays_dir(main), &dir);
    if !dir.join("worktree.txt").is_file() {
        seed(main, tree, &dir)?;
    }
    let registration = Registration::new(Overlay {
        main: main.to_path_buf(),
        tree: tree.to_path_buf(),
        dir: dir.clone(),
    });
    let lock = crate::project_lock::ProjectLock::acquire(tree)?;
    for name in STATE_RESET {
        let _ = fs::remove_file(dir.join("state").join(name));
    }
    adopt_unchanged(main, tree);
    let maps = crate::api::update_maps_run(
        tree,
        &crate::api::MapRun {
            full: false,
            quiet: true,
            directory: None,
            max_files: None,
            stream: false,
        },
    );
    if maps.get("success").and_then(|v| v.as_bool()) != Some(true) {
        let err = maps
            .get("error")
            .and_then(|v| v.as_str())
            .unwrap_or("map refresh failed")
            .to_string();
        return Err(format!("could not map worktree {}: {err}", tree.display()));
    }
    if health {
        let _ = crate::api::check_changes(tree);
    }
    let overlay_files = differing_files(main, tree);
    Ok(Active {
        _lock: lock,
        _registration: registration,
        overlay_files,
    })
}

/// Copy main's cache under main's project lock, so a concurrent `update-maps` on main
/// cannot hand the overlay a half-written generation. `worktree.txt` is written last: it
/// marks a finished seed and names the tree for pruning.
fn seed(main: &Path, tree: &Path, dir: &Path) -> Result<(), String> {
    let _main_lock = crate::project_lock::ProjectLock::acquire(main)?;
    if dir.join("worktree.txt").is_file() {
        return Ok(());
    }
    if dir.exists() {
        fs::remove_dir_all(dir).map_err(|e| format!("reset overlay {}: {e}", dir.display()))?;
    }
    fs::create_dir_all(dir).map_err(|e| format!("create overlay {}: {e}", dir.display()))?;
    let staging = main.join(".wikifier_staging");
    let cache = staging.join("wk_cache");
    if cache.is_dir() {
        copy_tree(&cache, &dir.join("wk_cache"))?;
    }
    let low_conf = staging.join("low_conf.tsv");
    if low_conf.is_file() {
        fs::copy(&low_conf, dir.join("low_conf.tsv")).map_err(|e| e.to_string())?;
    }
    fs::write(
        dir.join("worktree.txt"),
        format!("{}\n{}\n", tree.display(), main.display()),
    )
    .map_err(|e| e.to_string())
}

/// Copy a cache directory: hard links where the file system allows, else copies. Its
/// files are small and many (about 2,200 on Specula), so the work runs on several threads.
fn copy_tree(from: &Path, to: &Path) -> Result<(), String> {
    let mut pairs = Vec::new();
    list_tree(from, to, &mut pairs)?;
    let threads = std::thread::available_parallelism()
        .map(|n| n.get())
        .unwrap_or(1)
        .clamp(1, 8);
    let chunk = pairs.len().div_ceil(threads).max(1);
    std::thread::scope(|scope| {
        let workers: Vec<_> = pairs
            .chunks(chunk)
            .map(|part| {
                scope.spawn(move || {
                    part.iter().try_for_each(|(src, dst)| {
                        // Every cache write replaces a file by rename and never edits one
                        // in place, so a hard link is a safe copy: a later write by either
                        // side swaps in a new file and leaves the other side's alone.
                        fs::hard_link(src, dst)
                            .or_else(|_| fs::copy(src, dst).map(|_| ()))
                            .map_err(|e| format!("{}: {e}", src.display()))
                    })
                })
            })
            .collect();
        workers.into_iter().try_for_each(|worker| {
            worker
                .join()
                .unwrap_or_else(|_| Err("overlay copy thread panicked".to_string()))
        })
    })
}

/// Create the directories under `to` and list the files to copy, skipping locks and
/// half-written temp files.
fn list_tree(from: &Path, to: &Path, out: &mut Vec<(PathBuf, PathBuf)>) -> Result<(), String> {
    fs::create_dir_all(to).map_err(|e| e.to_string())?;
    for entry in fs::read_dir(from).map_err(|e| e.to_string())?.flatten() {
        let name = entry.file_name();
        let text = name.to_string_lossy();
        if text == "wk.lock" || text.ends_with(".tmp") {
            continue;
        }
        let path = entry.path();
        let dest = to.join(&name);
        if path.is_dir() {
            list_tree(&path, &dest, out)?;
        } else {
            out.push((path, dest));
        }
    }
    Ok(())
}

/// Give overlay rows the tree's size and mtime when git proves the tree's file holds the
/// bytes main's map hashed, so the map run skips them by stat instead of reading them.
/// The proof: main's file still has the size and mtime of main's map row (so its bytes
/// are what the map hashed) and of main's git index entry, the tree's file has the size
/// and mtime of the tree's git index entry, and both entries name the same blob. A fresh
/// `git worktree add` gives every file a new mtime; without this the first call read the
/// whole tree. Returns how many rows were adopted. Without a readable git index on both
/// sides this does nothing and the map run hashes, as before.
fn adopt_unchanged(main: &Path, tree: &Path) -> usize {
    let rows = crate::cache::index_by_path(tree);
    let candidates: Vec<(String, u128, u64)> = rows
        .into_iter()
        .filter_map(|(rel, (mtime, size, hash))| {
            if !hash.starts_with("sha256:") {
                return None;
            }
            let stat = crate::cache::stat_ns(&tree.join(&rel))?;
            (stat != (mtime, size)).then_some((rel, mtime, size))
        })
        .collect();
    if candidates.is_empty() {
        return 0;
    }
    let (Some(main_index), Some(tree_index)) = (
        crate::git_index::GitIndex::read(main),
        crate::git_index::GitIndex::read(tree),
    ) else {
        return 0;
    };
    let mut adopted = Vec::new();
    for (rel, mtime, size) in candidates {
        let main_path = main.join(&rel);
        if crate::cache::stat_ns(&main_path) != Some((mtime, size)) {
            continue;
        }
        let tree_path = tree.join(&rel);
        let (Some(base), Some(ours)) = (
            main_index.blob_if_fresh(&rel, &main_path),
            tree_index.blob_if_fresh(&rel, &tree_path),
        ) else {
            continue;
        };
        if base != ours {
            continue;
        }
        if let Some((tree_mtime, tree_size)) = crate::cache::stat_ns(&tree_path) {
            adopted.push((rel, tree_mtime, tree_size));
        }
    }
    if adopted.is_empty() {
        return 0;
    }
    let Ok(mut session) = crate::cache::Session::open(tree) else {
        return 0;
    };
    for (rel, mtime, size) in &adopted {
        session.note_stat(rel, *mtime, *size);
    }
    if session.commit().is_err() {
        return 0;
    }
    adopted.len()
}

/// Drop overlays whose worktree is gone, and seeds that never finished.
fn prune(overlays: &Path, keep: &Path) {
    let Ok(entries) = fs::read_dir(overlays) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path == keep || !path.is_dir() {
            continue;
        }
        let stale = match fs::read_to_string(path.join("worktree.txt")) {
            Ok(text) => text
                .lines()
                .next()
                .map(|tree| tree.trim().is_empty() || !Path::new(tree.trim()).is_dir())
                .unwrap_or(true),
            Err(_) => entry
                .metadata()
                .and_then(|m| m.modified())
                .ok()
                .and_then(|t| t.elapsed().ok())
                .is_some_and(|age| age >= PARTIAL_SEED_AGE),
        };
        if stale {
            let _ = fs::remove_dir_all(&path);
        }
    }
}

/// Files whose indexed content differs between main's map and the overlay: added,
/// changed, or deleted in the tree.
fn differing_files(main: &Path, tree: &Path) -> usize {
    let base = crate::cache::index_by_path(main);
    let over = crate::cache::index_by_path(tree);
    let changed = over
        .iter()
        .filter(|(rel, row)| base.get(*rel).is_none_or(|b| b.2 != row.2))
        .count();
    let deleted = base.keys().filter(|rel| !over.contains_key(*rel)).count();
    changed + deleted
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn clean_strips_the_verbatim_prefix_of_a_drive_path_only() {
        assert_eq!(
            clean(PathBuf::from(r"\\?\D:\a\b")),
            PathBuf::from(r"D:\a\b")
        );
        assert_eq!(
            clean(PathBuf::from(r"\\?\UNC\srv\share")),
            PathBuf::from(r"\\?\UNC\srv\share")
        );
        assert_eq!(clean(PathBuf::from("/tmp/x")), PathBuf::from("/tmp/x"));
    }

    #[test]
    fn writers_refuse_and_readers_do_not() {
        for name in [
            "record_change",
            "mark-green",
            "record_changes",
            "init",
            "daemon",
        ] {
            assert!(refuses(name), "{name}");
        }
        for name in [
            "get_dependents",
            "health",
            "check_changes",
            "update_maps",
            "why_file",
        ] {
            assert!(!refuses(name), "{name}");
        }
    }

    #[test]
    fn unregistered_roots_keep_their_plain_paths() {
        let root = Path::new("/no/such/root");
        assert_eq!(staging(root), root.join(".wikifier_staging"));
        assert_eq!(
            state(root, "file_health.json"),
            root.join("file_health.json")
        );
        assert!(!is_overlay(root));
    }
}
