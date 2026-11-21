//! Where a project's Wikifier state lives.
//!
//! Two layouts:
//! - `root` (every project set up before this layout existed, and any project without
//!   `.wikifier/layout`): health, pending list, library, journal, scope lists and
//!   `index.html` sit in the project root, the cache in `.wikifier_staging/`.
//! - `contained` (what `init` writes for a new project): the same files under `.wikifier/`,
//!   the cache in `.wikifier/staging/`. The project root gets nothing but `.wikifier/` and the
//!   per-file `*.wiki.md` notes, which stay beside their sources in both layouts.
//!
//! The layout is the file `.wikifier/layout`: its first line `contained` selects the
//! contained layout. Nothing else is detected at run time, so a project that already has its
//! files in the root keeps working unchanged. `init` picks the layout once (see
//! [`init_choice`]).
//!
//! [`ensure_gitignore`] is the marked `.gitignore` block `init` adds in a git work tree.

use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use crate::jsonutil::Json;

/// The state directory in the contained layout. It exists in both layouts: `init` keeps
/// `.wikifier/config` and the version marker there.
pub(crate) const STATE_DIR: &str = ".wikifier";
/// The layout file, relative to the project root.
pub(crate) const LAYOUT_FILE: &str = ".wikifier/layout";
/// The cache and lock directory of the root layout.
pub(crate) const ROOT_STAGING: &str = ".wikifier_staging";
/// The cache and lock directory of the contained layout.
pub(crate) const CONTAINED_STAGING: &str = ".wikifier/staging";

/// Top-level names that move under `.wikifier/` in the contained layout.
pub(crate) const RELOCATED: &[&str] = &[
    "file_health.json",
    "file_health.md",
    "library.md",
    "pending_updates.md",
    "map_paths.txt",
    "monitored_paths.txt",
    "exclude_patterns.txt",
    "journal",
    "Logged_issues",
    "index.html",
];

/// Root-layout files that show a project already has Wikifier state in its root. A bare
/// `.wikifier_staging/` (a cache from a command run before `init`) does not count.
const ROOT_MARKERS: &[&str] = &[
    "file_health.json",
    "file_health.md",
    "library.md",
    "pending_updates.md",
    "map_paths.txt",
    "monitored_paths.txt",
    "journal",
];

/// The layout file is read at most once a second per root. Many path lookups run per
/// command (the cache path is built per file), and a layout only changes when `init` runs.
const TTL: Duration = Duration::from_secs(1);

static SEEN: Mutex<Option<HashMap<PathBuf, (bool, Instant)>>> = Mutex::new(None);

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum Layout {
    Root,
    Contained,
}

impl Layout {
    pub(crate) fn name(self) -> &'static str {
        match self {
            Layout::Root => "root",
            Layout::Contained => "contained",
        }
    }

    pub(crate) fn parse(text: &str) -> Option<Layout> {
        match text.trim() {
            "root" => Some(Layout::Root),
            "contained" => Some(Layout::Contained),
            _ => None,
        }
    }
}

/// True when `root` uses the contained layout.
pub(crate) fn contained(root: &Path) -> bool {
    let now = Instant::now();
    if let Ok(guard) = SEEN.lock() {
        if let Some((value, at)) = guard.as_ref().and_then(|m| m.get(root)) {
            if now.duration_since(*at) < TTL {
                return *value;
            }
        }
    }
    let value = read_layout(root) == Some(Layout::Contained);
    if let Ok(mut guard) = SEEN.lock() {
        guard
            .get_or_insert_with(HashMap::new)
            .insert(root.to_path_buf(), (value, now));
    }
    value
}

/// The layout `root` uses now.
pub(crate) fn of(root: &Path) -> Layout {
    if contained(root) {
        Layout::Contained
    } else {
        Layout::Root
    }
}

fn read_layout(root: &Path) -> Option<Layout> {
    let text = fs::read_to_string(root.join(LAYOUT_FILE)).ok()?;
    text.lines()
        .map(str::trim)
        .find(|line| !line.is_empty() && !line.starts_with('#'))
        .and_then(Layout::parse)
}

/// Forget the cached answer for `root` (after `init` wrote the layout file).
pub(crate) fn forget(root: &Path) {
    if let Ok(mut guard) = SEEN.lock() {
        if let Some(map) = guard.as_mut() {
            map.remove(root);
        }
    }
}

fn first_component(rel: &str) -> &str {
    rel.split('/').next().unwrap_or(rel)
}

/// True when `rel`'s first component is a file or directory the contained layout moves.
pub(crate) fn is_relocated(rel: &str) -> bool {
    RELOCATED.contains(&first_component(rel))
}

/// `rel` (a root-level state name such as `file_health.md` or `journal/2026/11/21.md`)
/// under `base`, placed by `contained`.
pub(crate) fn join(base: &Path, contained: bool, rel: &str) -> PathBuf {
    if contained && is_relocated(rel) {
        base.join(STATE_DIR).join(rel)
    } else {
        base.join(rel)
    }
}

/// Where `rel` lives in `root`. Names that the layout does not move (wikis, `.wikifier/config`,
/// sources) come back as `root/rel`.
pub(crate) fn path(root: &Path, rel: &str) -> PathBuf {
    if !is_relocated(rel) {
        return root.join(rel);
    }
    join(root, contained(root), rel)
}

/// `rel` as the project sees it: `.wikifier/file_health.md` in the contained layout, else
/// `file_health.md`. For messages and replies.
pub(crate) fn display(root: &Path, rel: &str) -> String {
    if is_relocated(rel) && contained(root) {
        format!("{STATE_DIR}/{rel}")
    } else {
        rel.to_string()
    }
}

/// The cache, lock and daemon directory for `root`.
pub(crate) fn staging(root: &Path) -> PathBuf {
    staging_for(root, contained(root))
}

pub(crate) fn staging_for(root: &Path, contained: bool) -> PathBuf {
    if contained {
        root.join(CONTAINED_STAGING)
    } else {
        root.join(ROOT_STAGING)
    }
}

/// True when `root` already keeps Wikifier files in its root (an existing project).
pub(crate) fn has_root_state(root: &Path) -> bool {
    ROOT_MARKERS.iter().any(|name| root.join(name).exists())
}

/// What `init` should use. An explicit `requested` layout wins for a project with no state
/// yet. A project that already has root-layout files keeps the root layout: asking it for the
/// contained layout is an error, because `init` does not move files.
pub(crate) fn init_choice(root: &Path, requested: Option<Layout>) -> Result<Layout, String> {
    if let Some(current) = read_layout(root) {
        return match requested {
            Some(want) if want != current => Err(format!(
                "this project already uses the {} layout ({LAYOUT_FILE}); init does not move files",
                current.name()
            )),
            _ => Ok(current),
        };
    }
    if has_root_state(root) {
        return match requested {
            Some(Layout::Contained) => Err(
                "this project already keeps Wikifier files in its root (file_health.md, map_paths.txt, ...); \
                 init does not move them. Run init without --layout to keep the root layout"
                    .to_string(),
            ),
            _ => Ok(Layout::Root),
        };
    }
    Ok(requested.unwrap_or(Layout::Contained))
}

/// Write `.wikifier/layout` for the contained layout. The root layout writes no file, so a
/// project set up by an older `init` and one set up by this one look the same.
pub(crate) fn write_layout(root: &Path, layout: Layout) -> Result<bool, String> {
    let path = root.join(LAYOUT_FILE);
    let result = if layout == Layout::Contained && !path.is_file() {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).map_err(|e| e.to_string())?;
        }
        fs::write(
            &path,
            "contained\n\
             # Wikifier keeps its state (health, pending, library, journal, scope lists, cache)\n\
             # in this directory. Removing this file points Wikifier back at the project root.\n",
        )
        .map_err(|e| e.to_string())?;
        Ok(true)
    } else {
        Ok(false)
    };
    forget(root);
    result
}

/// What `init` may add to `.gitignore`, as `.gitignore` lines (anchored to the project).
fn gitignore_candidates(root: &Path, dashboard: &str) -> Vec<String> {
    if contained(root) {
        return vec!["/.wikifier/".to_string()];
    }
    let mut out = vec!["/.wikifier/".to_string(), "/.wikifier_staging/".to_string()];
    for name in RELOCATED {
        let path = root.join(name);
        if !path.exists() {
            continue;
        }
        // A root index.html is ignored only when it is the dashboard init wrote.
        if *name == "index.html"
            && fs::read_to_string(&path)
                .map(|t| t != dashboard)
                .unwrap_or(true)
        {
            continue;
        }
        if path.is_dir() {
            out.push(format!("/{name}/"));
        } else {
            out.push(format!("/{name}"));
        }
    }
    out
}

const GITIGNORE_BEGIN: &str = "# >>> wikifier state (added by `wikifier init`)";
const GITIGNORE_END: &str = "# <<< wikifier state";

fn git_lines(root: &Path, args: &[&str]) -> Option<Vec<String>> {
    let out = std::process::Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .stdin(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .output()
        .ok()?;
    // check-ignore exits 1 when nothing is ignored; its stdout is still the answer.
    if !out.status.success() && out.status.code() != Some(1) {
        return None;
    }
    Some(
        String::from_utf8_lossy(&out.stdout)
            .lines()
            .map(|l| l.trim().to_string())
            .filter(|l| !l.is_empty())
            .collect(),
    )
}

/// Add a marked block to `root/.gitignore` for Wikifier's files that git neither tracks nor
/// ignores. Nothing happens outside a git work tree, when the block is already there, or
/// when every file is covered. Tracked files are left alone: ignoring them would only hide
/// later additions. `dashboard` is the `index.html` init writes.
pub(crate) fn ensure_gitignore(root: &Path, dashboard: &str) -> Json {
    let inside = git_lines(root, &["rev-parse", "--is-inside-work-tree"]);
    if inside
        .as_deref()
        .and_then(|l| l.first())
        .map(String::as_str)
        != Some("true")
    {
        return Json::String("not_a_git_repo".into());
    }
    let path = root.join(".gitignore");
    let existing = fs::read_to_string(&path).unwrap_or_default();
    if existing.lines().any(|l| l.trim() == GITIGNORE_BEGIN) {
        return Json::String("block_present".into());
    }
    let candidates = gitignore_candidates(root, dashboard);
    let bare: Vec<String> = candidates
        .iter()
        .map(|c| c.trim_start_matches('/').to_string())
        .collect();
    let mut args = vec!["ls-files", "--"];
    args.extend(bare.iter().map(|s| s.trim_end_matches('/')));
    let tracked = git_lines(root, &args).unwrap_or_default();
    let mut args = vec!["check-ignore", "--"];
    args.extend(bare.iter().map(String::as_str));
    let ignored = git_lines(root, &args).unwrap_or_default();
    let wanted: Vec<&String> = candidates
        .iter()
        .zip(bare.iter())
        .filter(|(_, b)| {
            let plain = b.trim_end_matches('/');
            let is_tracked = tracked
                .iter()
                .any(|t| t == plain || t.starts_with(&format!("{plain}/")));
            let is_ignored = ignored.iter().any(|i| i.trim_end_matches('/') == plain);
            !is_tracked && !is_ignored
        })
        .map(|(c, _)| c)
        .collect();
    if wanted.is_empty() {
        return Json::String("already_ignored".into());
    }
    let mut text = existing.clone();
    if !text.is_empty() && !text.ends_with('\n') {
        text.push('\n');
    }
    if !text.is_empty() {
        text.push('\n');
    }
    text.push_str(GITIGNORE_BEGIN);
    text.push('\n');
    for line in &wanted {
        text.push_str(line);
        text.push('\n');
    }
    text.push_str(GITIGNORE_END);
    text.push('\n');
    if fs::write(&path, text).is_err() {
        return Json::String("write_failed".into());
    }
    Json::obj(vec![
        (
            "added",
            Json::Array(wanted.into_iter().cloned().map(Json::String).collect()),
        ),
        ("file", Json::String(".gitignore".into())),
    ])
}

#[cfg(test)]
mod tests {
    use super::*;

    fn scratch(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "wk_layout_{name}_{}_{:?}",
            std::process::id(),
            std::thread::current().id()
        ));
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn without_a_layout_file_every_name_stays_in_the_root() {
        let root = scratch("plain");
        assert!(!contained(&root));
        assert_eq!(path(&root, "file_health.md"), root.join("file_health.md"));
        assert_eq!(staging(&root), root.join(".wikifier_staging"));
        assert_eq!(display(&root, "library.md"), "library.md");
    }

    #[test]
    fn the_contained_layout_moves_state_but_not_wikis_or_config() {
        let root = scratch("contained");
        write_layout(&root, Layout::Contained).unwrap();
        assert!(contained(&root));
        assert_eq!(
            path(&root, "journal/2026/11/21.md"),
            root.join(".wikifier/journal/2026/11/21.md")
        );
        assert_eq!(path(&root, "index.html"), root.join(".wikifier/index.html"));
        assert_eq!(
            path(&root, "src/a.rs.wiki.md"),
            root.join("src/a.rs.wiki.md")
        );
        assert_eq!(
            path(&root, ".wikifier/config"),
            root.join(".wikifier/config")
        );
        assert_eq!(staging(&root), root.join(".wikifier/staging"));
        assert_eq!(display(&root, "library.md"), ".wikifier/library.md");
    }

    #[test]
    fn init_keeps_an_existing_root_layout() {
        let root = scratch("existing");
        fs::write(root.join("file_health.md"), "# x\n").unwrap();
        assert_eq!(init_choice(&root, None).unwrap(), Layout::Root);
        assert!(init_choice(&root, Some(Layout::Contained)).is_err());
        let fresh = scratch("fresh");
        assert_eq!(init_choice(&fresh, None).unwrap(), Layout::Contained);
        assert_eq!(
            init_choice(&fresh, Some(Layout::Root)).unwrap(),
            Layout::Root
        );
        // A cache left by a command run before init does not make a project "existing".
        fs::create_dir_all(fresh.join(".wikifier_staging")).unwrap();
        assert_eq!(init_choice(&fresh, None).unwrap(), Layout::Contained);
    }
}
