//! Fewer files in the project root and fewer calls per session:
//! - `init` keeps a new project's state under `.wikifier/` (the contained layout) and keeps
//!   an existing project's root layout; in a git repo it adds a marked `.gitignore` block.
//! - `record-change` puts a new or changed source file in the map (no `update-maps` step).
//! - `record_changes` skips other tools' state directories without asking for reasons.
//! - `health` and `check_changes` say in one line when there is nothing to report.

use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

use wikifier::api::{self, dispatch};
use wikifier::jsonutil::Json;

fn scratch(name: &str) -> PathBuf {
    let n = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let dir = std::env::temp_dir().join(format!("wk-layout-{name}-{n}"));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    dir.canonicalize().unwrap()
}

fn write(root: &Path, rel: &str, text: &str) {
    let path = root.join(rel);
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    fs::write(path, text).unwrap();
}

fn flags(pairs: &[(&str, &str)]) -> BTreeMap<String, String> {
    pairs
        .iter()
        .map(|(k, v)| ((*k).to_string(), (*v).to_string()))
        .collect()
}

fn success(value: &Json) -> bool {
    value.get("success").and_then(|v| v.as_bool()) == Some(true)
}

fn text(value: &Json, key: &str) -> String {
    value
        .get(key)
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string()
}

fn strings(value: &Json, key: &str) -> Vec<String> {
    value
        .get(key)
        .and_then(|v| v.as_array())
        .map(|items| {
            items
                .iter()
                .filter_map(|v| v.as_str().map(str::to_string))
                .collect()
        })
        .unwrap_or_default()
}

fn git(root: &Path, args: &[&str]) -> String {
    let out = Command::new("git")
        .args(["-c", "user.email=a@b.c", "-c", "user.name=t"])
        .args(args)
        .current_dir(root)
        .output()
        .unwrap();
    String::from_utf8_lossy(&out.stdout).to_string()
}

fn has_git() -> bool {
    Command::new("git").arg("--version").output().is_ok()
}

/// Top-level names in `root`, sorted, without `.git`.
fn top_level(root: &Path) -> Vec<String> {
    let mut names: Vec<String> = fs::read_dir(root)
        .unwrap()
        .flatten()
        .map(|e| e.file_name().to_string_lossy().to_string())
        .filter(|n| n != ".git")
        .collect();
    names.sort();
    names
}

fn init(root: &Path, pairs: &[(&str, &str)]) -> Json {
    dispatch("init", root, &[], &flags(pairs))
}

#[test]
fn init_puts_a_new_projects_state_under_dot_wikifier() {
    let root = scratch("contained");
    write(&root, "pkg/__init__.py", "");
    write(&root, "pkg/a.py", "x = 1\n");
    let value = init(&root, &[]);
    assert!(success(&value), "{value}");
    assert_eq!(text(&value, "layout"), "contained");
    assert_eq!(text(&value, "state_dir"), ".wikifier");
    // The root gets the state directory and nothing else.
    assert_eq!(top_level(&root), [".wikifier", "pkg"]);
    let state = root.join(".wikifier");
    for file in [
        "layout",
        "config",
        "marker",
        "map_paths.txt",
        "monitored_paths.txt",
        "exclude_patterns.txt",
        "file_health.md",
        "pending_updates.md",
        "library.md",
        "index.html",
    ] {
        assert!(state.join(file).is_file(), "missing .wikifier/{file}");
    }
    for dir in ["journal", "Logged_issues", "staging"] {
        assert!(state.join(dir).is_dir(), "missing .wikifier/{dir}");
    }
    assert!(strings(&value, "created").contains(&".wikifier/file_health.md".to_string()));

    // Every command reads and writes there: map, record, health, journal.
    assert!(success(&api::update_maps(&root)));
    let rec = api::record_change(&root, "pkg/a.py", "bump");
    assert!(success(&rec), "{rec}");
    assert!(state.join("file_health.json").is_file());
    assert!(fs::read_to_string(state.join("pending_updates.md"))
        .unwrap()
        .contains("pkg/a.py"));
    assert!(fs::read_to_string(state.join("library.md"))
        .unwrap()
        .contains("pkg/a.py"));
    assert!(state.join("staging/wk_cache").is_dir());
    assert_eq!(api::read_journal(&root, None).len(), 1);
    let health = api::health(&root);
    assert!(
        health
            .get("entries")
            .and_then(|v| v.as_array())
            .map(|a| a.len())
            >= Some(1),
        "{health}"
    );
    assert_eq!(top_level(&root), [".wikifier", "pkg"], "root stayed clean");

    // A second init keeps everything and cannot switch layouts.
    let again = init(&root, &[]);
    assert!(success(&again), "{again}");
    assert_eq!(strings(&again, "created"), Vec::<String>::new());
    let switch = init(&root, &[("layout", "root")]);
    assert!(!success(&switch), "{switch}");
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn an_existing_root_layout_project_keeps_its_files_where_they_are() {
    let root = scratch("existing");
    write(&root, "src/a.py", "x = 1\n");
    // What a pre-5.7 init left behind.
    write(&root, "map_paths.txt", "src/\n");
    write(&root, "file_health.md", "# Documentation Health Matrix\n\n| File | Status | Last Updated | Reason / Intent |\n|------|--------|--------------|-----------------|\n");
    let value = init(&root, &[]);
    assert!(success(&value), "{value}");
    assert_eq!(text(&value, "layout"), "root");
    assert!(root.join("library.md").is_file());
    assert!(root.join("pending_updates.md").is_file());
    assert!(root.join("journal").is_dir());
    assert!(root.join(".wikifier_staging").is_dir());
    assert!(!root.join(".wikifier/layout").exists());
    assert!(!root.join(".wikifier/library.md").exists());
    let rec = api::record_change(&root, "src/a.py", "bump");
    assert!(success(&rec), "{rec}");
    assert!(root.join("file_health.json").is_file());
    assert!(root.join(".wikifier_staging/wk_cache").is_dir());
    assert!(!root.join(".wikifier/staging").exists());
    // init does not move files, so asking for the contained layout is refused.
    let switch = init(&root, &[("layout", "contained")]);
    assert!(!success(&switch), "{switch}");
    assert!(text(&switch, "error").contains("does not move"), "{switch}");
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn init_layout_root_still_gives_a_new_project_the_old_layout() {
    let root = scratch("asked-root");
    write(&root, "src/a.py", "x = 1\n");
    let value = init(&root, &[("layout", "root")]);
    assert!(success(&value), "{value}");
    assert_eq!(text(&value, "layout"), "root");
    assert!(root.join("map_paths.txt").is_file());
    assert!(root.join("index.html").is_file());
    let bad = init(&scratch("bad-layout"), &[("layout", "sideways")]);
    assert!(!success(&bad), "{bad}");
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn init_adds_one_marked_gitignore_block_for_untracked_state() {
    if !has_git() {
        return;
    }
    // Contained: one line covers everything.
    let root = scratch("gi-contained");
    git(&root, &["init", "-q"]);
    write(&root, ".gitignore", "*.pyc\n");
    write(&root, "src/a.py", "x = 1\n");
    let value = init(&root, &[]);
    assert!(success(&value), "{value}");
    let ignore = fs::read_to_string(root.join(".gitignore")).unwrap();
    assert!(ignore.starts_with("*.pyc\n"), "{ignore}");
    assert!(ignore.contains("# >>> wikifier state"), "{ignore}");
    assert!(ignore.contains("\n/.wikifier/\n"), "{ignore}");
    let status = git(&root, &["status", "--porcelain", "--untracked-files=all"]);
    assert!(!status.contains(".wikifier"), "{status}");
    // Re-running init leaves the block alone.
    let again = init(&root, &[]);
    assert_eq!(
        again.get("gitignore"),
        Some(&Json::String("block_present".into()))
    );
    assert_eq!(fs::read_to_string(root.join(".gitignore")).unwrap(), ignore);
    let _ = fs::remove_dir_all(&root);

    // Root layout: only the files git neither tracks nor ignores yet.
    let root = scratch("gi-root");
    git(&root, &["init", "-q"]);
    write(&root, "src/a.py", "x = 1\n");
    write(&root, "map_paths.txt", "src/\n");
    write(&root, ".gitignore", "/library.md\n");
    git(&root, &["add", "map_paths.txt", "src/a.py"]);
    let value = init(&root, &[]);
    assert!(success(&value), "{value}");
    let added = value
        .get("gitignore")
        .map(|g| strings(g, "added"))
        .unwrap_or_default();
    assert!(added.contains(&"/file_health.md".to_string()), "{value}");
    assert!(added.contains(&"/journal/".to_string()), "{value}");
    assert!(
        added.contains(&"/.wikifier_staging/".to_string()),
        "{value}"
    );
    assert!(
        !added.contains(&"/map_paths.txt".to_string()),
        "tracked: {value}"
    );
    assert!(
        !added.contains(&"/library.md".to_string()),
        "already ignored: {value}"
    );
    let status = git(&root, &["status", "--porcelain", "--untracked-files=all"]);
    for name in [
        "file_health.md",
        "pending_updates.md",
        "index.html",
        ".wikifier",
    ] {
        assert!(!status.contains(name), "{name} still untracked: {status}");
    }
    let _ = fs::remove_dir_all(&root);

    // Opt out, and outside git.
    let root = scratch("gi-off");
    git(&root, &["init", "-q"]);
    let off = init(&root, &[("no-gitignore", "true")]);
    assert_eq!(off.get("gitignore"), Some(&Json::String("skipped".into())));
    assert!(!root.join(".gitignore").exists());
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn record_change_puts_a_new_file_in_the_map() {
    let root = scratch("record-map");
    write(&root, "pkg/__init__.py", "");
    write(&root, "pkg/b.py", "x = 1\n");
    assert!(success(&init(&root, &[])));
    assert!(success(&api::update_maps(&root)));

    // A new file that imports b.py: the record alone adds it and its edge.
    write(&root, "pkg/a.py", "from pkg import b\n");
    let rec = api::record_change(&root, "pkg/a.py", "new module");
    assert!(success(&rec), "{rec}");
    assert_eq!(text(&rec, "map"), "added", "{rec}");
    let deps = api::load_dependents(&root, "pkg/b.py");
    assert_eq!(strings(&deps, "dependents"), ["pkg/a.py"], "{deps}");
    assert!(fs::read_to_string(root.join(".wikifier/library.md"))
        .unwrap()
        .contains("pkg/a.py"));

    // Recording it again without an edit parses nothing.
    let same = api::record_change(&root, "pkg/a.py", "again, no edit");
    assert_eq!(text(&same, "map"), "unchanged", "{same}");

    // A changed import is picked up too.
    write(&root, "pkg/c.py", "y = 2\n");
    write(&root, "pkg/a.py", "from pkg import c\n");
    let upd = api::record_change(&root, "pkg/a.py", "switch to c");
    assert_eq!(text(&upd, "map"), "updated", "{upd}");
    assert_eq!(
        strings(&api::load_dependents(&root, "pkg/c.py"), "dependents"),
        ["pkg/a.py"]
    );
    assert!(strings(&api::load_dependents(&root, "pkg/b.py"), "dependents").is_empty());

    // Not a source, or outside the map scope: recorded, map untouched.
    write(&root, "README.md", "# r\n");
    let doc = api::record_change(&root, "README.md", "docs");
    assert!(success(&doc), "{doc}");
    assert_eq!(text(&doc, "map"), "out_of_scope", "{doc}");
    write(&root, "scripts/tool.py", "z = 3\n");
    let outside = api::record_change(&root, "scripts/tool.py", "helper");
    assert_eq!(text(&outside, "map"), "out_of_scope", "{outside}");
    assert!(!wikifier::cache::all_paths(&root).contains(&"scripts/tool.py".to_string()));

    // --no-map leaves the map alone.
    write(&root, "pkg/d.py", "from pkg import b\n");
    let skipped = dispatch(
        "record-change",
        &root,
        &["pkg/d.py".into(), "later".into()],
        &flags(&[("no-map", "true")]),
    );
    assert!(success(&skipped), "{skipped}");
    assert!(skipped.get("map").is_none(), "{skipped}");
    assert!(!wikifier::cache::all_paths(&root).contains(&"pkg/d.py".to_string()));
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn record_change_on_a_fresh_init_maps_without_update_maps() {
    // The A/B hooks ran init, then record-change per edit, and update-maps only at stop.
    let root = scratch("fresh-map");
    write(&root, "lib/core.py", "x = 1\n");
    assert!(success(&init(&root, &[])));
    write(&root, "lib/api.py", "from lib import core\n");
    let rec = api::record_change(&root, "lib/api.py", "edited by agent");
    assert_eq!(text(&rec, "map"), "added", "{rec}");
    assert_eq!(
        strings(&api::load_dependents(&root, "lib/core.py"), "dependents"),
        ["lib/api.py"]
    );
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn record_changes_skips_other_tools_state_and_maps_new_files() {
    if !has_git() {
        return;
    }
    let root = scratch("batch");
    git(&root, &["init", "-q"]);
    write(&root, "pkg/__init__.py", "");
    write(&root, "pkg/b.py", "x = 1\n");
    assert!(success(&init(&root, &[("no-gitignore", "true")])));
    assert!(success(&api::update_maps(&root)));
    git(&root, &["add", "pkg"]);
    git(&root, &["commit", "-qm", "seed"]);
    write(&root, "pkg/a.py", "from pkg import b\n");
    for rel in [
        ".trammel/plans/p1.json",
        ".swarmnotes/storage/api.md",
        ".claude/settings.json",
        ".stele-context/db.json",
        ".coordinationhub/state.json",
        ".chisel/cache.json",
        ".probatio/run.json",
    ] {
        write(&root, rel, "{}\n");
    }
    let value = api::record_changes(&root, &["pkg/a.py=new module".to_string()], None);
    assert!(success(&value), "{value}");
    assert_eq!(strings(&value, "files"), ["pkg/a.py"], "{value}");
    let skipped = strings(&value, "skipped_tool_state");
    for dir in [
        ".trammel",
        ".swarmnotes",
        ".claude",
        ".stele-context",
        ".chisel",
        ".probatio",
    ] {
        assert!(
            skipped.iter().any(|p| p.starts_with(dir)),
            "{dir} not skipped: {value}"
        );
    }
    // Wikifier's own `.wikifier/` is neither asked about nor listed as another tool's.
    assert!(
        !skipped.iter().any(|p| p.starts_with(".wikifier")),
        "{value}"
    );
    assert_eq!(strings(&value, "mapped"), ["pkg/a.py"], "{value}");
    assert_eq!(
        strings(&api::load_dependents(&root, "pkg/b.py"), "dependents"),
        ["pkg/a.py"]
    );
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn health_and_check_changes_say_so_when_there_is_nothing_to_report() {
    let root = scratch("quiet");
    write(&root, "pkg/a.py", "x = 1\n");
    assert!(success(&init(&root, &[])));
    let health = api::health(&root);
    assert!(
        text(&health, "note").starts_with("Nothing to report"),
        "{health}"
    );
    let summary = dispatch("health", &root, &[], &flags(&[("summary", "true")]));
    assert!(
        text(&summary, "note").starts_with("Nothing to report"),
        "{summary}"
    );
    let checked = api::check_changes(&root);
    assert!(
        text(&checked, "note").starts_with("Nothing to report"),
        "{checked}"
    );

    // Once there is work, the note goes away.
    assert!(success(&api::record_change(&root, "pkg/a.py", "bump")));
    let health = api::health(&root);
    assert!(health.get("note").is_none(), "{health}");
    let _ = fs::remove_dir_all(&root);
}

/// A linked worktree of a contained-layout main reads main's map and state from
/// `.wikifier/` (which a worktree checkout does not have: it is gitignored).
#[test]
fn a_worktree_of_a_contained_main_answers_from_mains_state() {
    let base = scratch("wt");
    let main = base.join("main");
    fs::create_dir_all(main.join(".git/worktrees/lane")).unwrap();
    write(&main, "pkg/__init__.py", "");
    write(&main, "pkg/core.py", "x = 1\n");
    write(&main, "pkg/a.py", "from pkg import core\n");
    assert!(success(&init(&main, &[("no-gitignore", "true")])));
    assert!(success(&api::update_maps(&main)));
    let tree = base.join("lane");
    for rel in ["pkg/__init__.py", "pkg/core.py", "pkg/a.py"] {
        write(&tree, rel, &fs::read_to_string(main.join(rel)).unwrap());
    }
    write(&tree, "pkg/b.py", "from pkg import core\n");
    let gitdir = main.join(".git/worktrees/lane");
    fs::write(gitdir.join("commondir"), "../..\n").unwrap();
    fs::write(tree.join(".git"), format!("gitdir: {}\n", gitdir.display())).unwrap();
    let over = dispatch(
        "get_dependents",
        &main,
        &["pkg/core.py".into()],
        &flags(&[("worktree_root", &tree.display().to_string())]),
    );
    assert!(success(&over), "{over}");
    assert_eq!(
        strings(&over, "dependents"),
        ["pkg/a.py", "pkg/b.py"],
        "{over}"
    );
    assert!(main.join(".wikifier/staging/overlays").is_dir());
    assert!(!main.join(".wikifier_staging").exists());
    assert!(!tree.join(".wikifier_staging").exists());
    let _ = fs::remove_dir_all(&base);
}
