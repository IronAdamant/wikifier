//! `worktree_root`: read tools answer for a git worktree from main's maps plus the
//! files that differ in the tree, and never write main's state.

use std::collections::BTreeMap;
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::{SystemTime, UNIX_EPOCH};

use wikifier::api::{self, dispatch};
use wikifier::jsonutil::{self, Json};

fn scratch(name: &str) -> PathBuf {
    let n = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let dir = std::env::temp_dir().join(format!("wk-wt-{name}-{n}"));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    dir.canonicalize().map(clean).unwrap()
}

fn clean(path: PathBuf) -> PathBuf {
    let text = path.to_string_lossy().to_string();
    match text.strip_prefix(r"\\?\") {
        Some(rest) if !rest.starts_with("UNC") => PathBuf::from(rest),
        _ => path,
    }
}

fn write(root: &Path, rel: &str, text: &str) {
    let path = root.join(rel);
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    fs::write(path, text).unwrap();
}

/// A main checkout with a mapped Rust crate. `core.rs` is imported by `a.rs`, `b.rs`
/// and `lib.rs`. `.git` makes it a git main checkout.
fn main_tree(name: &str) -> PathBuf {
    let base = scratch(name);
    let main = base.join("main");
    fs::create_dir_all(main.join(".git/worktrees/lane")).unwrap();
    write(
        &main,
        "Cargo.toml",
        "[package]\nname = \"demo\"\nversion = \"0.1.0\"\n",
    );
    write(&main, "map_paths.txt", "src\n");
    write(&main, "monitored_paths.txt", "src\n");
    write(
        &main,
        ".wikifier/config",
        "modularity_max_lines=12\nmodularity_max_fan_in=0\n",
    );
    write(
        &main,
        "src/lib.rs",
        "pub mod core;\npub mod a;\npub mod b;\npub mod c;\nuse crate::core::Camera;\n",
    );
    write(&main, "src/core.rs", "pub struct Camera;\n");
    write(
        &main,
        "src/a.rs",
        "use crate::core::Camera;\npub fn a() {}\n",
    );
    write(
        &main,
        "src/b.rs",
        "use crate::core::Camera;\npub fn b() {}\n",
    );
    write(&main, "src/c.rs", "pub fn c() {}\n");
    write(&main, "src/a.rs.wiki.md", "# a\n\n`a`\n");
    let built = api::update_maps(&main);
    assert_eq!(
        built.get("success").and_then(|v| v.as_bool()),
        Some(true),
        "{built}"
    );
    let green = api::mark_green(&main, "src/a.rs", "baseline", true);
    assert_eq!(
        green.get("success").and_then(|v| v.as_bool()),
        Some(true),
        "{green}"
    );
    main
}

/// A linked worktree of `main` the way git lays one out, without running git: a `.git`
/// file naming `main/.git/worktrees/lane`, whose `commondir` is `../..`. Only tracked
/// files are copied (no Wikifier state, as on a repo that gitignores it).
fn linked_tree(main: &Path) -> PathBuf {
    let tree = main.parent().unwrap().join("lane");
    for rel in [
        "Cargo.toml",
        "src/lib.rs",
        "src/core.rs",
        "src/a.rs",
        "src/b.rs",
        "src/c.rs",
    ] {
        write(&tree, rel, &fs::read_to_string(main.join(rel)).unwrap());
    }
    let gitdir = main.join(".git/worktrees/lane");
    fs::write(gitdir.join("commondir"), "../..\n").unwrap();
    fs::write(tree.join(".git"), format!("gitdir: {}\n", gitdir.display())).unwrap();
    tree
}

/// The branch: `c.rs` and a new `d.rs` start importing `core.rs`, `a.rs` stops, `b.rs`
/// is deleted, and `c.rs` grows past the 12-line modularity limit.
fn edit_branch(tree: &Path) {
    write(
        tree,
        "src/lib.rs",
        "pub mod core;\npub mod a;\npub mod c;\npub mod d;\nuse crate::core::Camera;\n",
    );
    write(tree, "src/a.rs", "pub fn a() {}\npub fn a2() {}\n");
    fs::remove_file(tree.join("src/b.rs")).unwrap();
    let mut long = String::from("use crate::core::Camera;\n");
    for i in 0..20 {
        long.push_str(&format!("pub fn c{i}() {{}}\n"));
    }
    write(tree, "src/c.rs", &long);
    write(
        tree,
        "src/d.rs",
        "use crate::core;\npub fn d() { let _ = core::Camera; }\n",
    );
}

fn flags(pairs: &[(&str, &str)]) -> BTreeMap<String, String> {
    pairs
        .iter()
        .map(|(k, v)| (k.to_string(), v.to_string()))
        .collect()
}

fn strings(value: &Json, key: &str) -> Vec<String> {
    let mut out: Vec<String> = value
        .get(key)
        .and_then(|v| v.as_array())
        .unwrap_or_else(|| panic!("no {key} in {value}"))
        .iter()
        .filter_map(|v| v.as_str().map(str::to_string))
        .collect();
    out.sort();
    out
}

fn success(value: &Json) -> bool {
    value.get("success").and_then(|v| v.as_bool()) == Some(true)
}

/// Every file under `dir` with its bytes, for "main was not written" checks.
fn snapshot(dir: &Path) -> BTreeMap<String, Vec<u8>> {
    let mut out = BTreeMap::new();
    let mut stack = vec![dir.to_path_buf()];
    while let Some(next) = stack.pop() {
        let Ok(entries) = fs::read_dir(&next) else {
            continue;
        };
        for entry in entries.flatten() {
            let path = entry.path();
            let name = entry.file_name().to_string_lossy().to_string();
            if name == "overlays" || name == ".lock" || name == "wk.lock" {
                continue;
            }
            if path.is_dir() {
                stack.push(path);
            } else {
                out.insert(
                    path.strip_prefix(dir).unwrap().display().to_string(),
                    fs::read(&path).unwrap(),
                );
            }
        }
    }
    out
}

fn main_state(main: &Path) -> BTreeMap<String, Vec<u8>> {
    let mut all = snapshot(&main.join(".wikifier_staging"));
    for rel in [
        "file_health.json",
        "file_health.md",
        "pending_updates.md",
        "library.md",
    ] {
        if let Ok(bytes) = fs::read(main.join(rel)) {
            all.insert(rel.into(), bytes);
        }
    }
    all.extend(snapshot(&main.join("journal")));
    all
}

#[test]
fn dependents_follow_the_worktree_and_main_is_untouched() {
    let main = main_tree("deps");
    let tree = linked_tree(&main);
    edit_branch(&tree);
    let before = main_state(&main);
    let wt = tree.display().to_string();

    let plain = dispatch(
        "get_dependents",
        &main,
        &["src/core.rs".into()],
        &flags(&[]),
    );
    assert_eq!(
        strings(&plain, "dependents"),
        ["src/a.rs", "src/b.rs", "src/lib.rs"],
        "{plain}"
    );
    assert!(plain.get("worktree").is_none(), "{plain}");

    let over = dispatch(
        "get_dependents",
        &main,
        &["src/core.rs".into()],
        &flags(&[("worktree_root", &wt)]),
    );
    assert!(success(&over), "{over}");
    assert_eq!(
        strings(&over, "dependents"),
        ["src/c.rs", "src/d.rs", "src/lib.rs"],
        "{over}"
    );
    assert_eq!(
        over.get("worktree").and_then(|v| v.as_str()),
        Some(wt.as_str())
    );
    // lib.rs, a.rs, c.rs changed; d.rs added; b.rs deleted.
    assert_eq!(over.get("overlay_files"), Some(&Json::Int(5)), "{over}");

    // The plain call is unchanged afterwards, and main's cache, health, journal, pending
    // list, library and snapshots are byte-for-byte what they were.
    let again = dispatch(
        "get_dependents",
        &main,
        &["src/core.rs".into()],
        &flags(&[]),
    );
    assert_eq!(again.to_string(), plain.to_string());
    assert_eq!(main_state(&main), before);
    // Nothing was written into the worktree either.
    assert!(!tree.join(".wikifier_staging").exists());
    assert!(!tree.join("file_health.json").exists());
    assert!(!tree.join("journal").exists());

    let deps = dispatch(
        "get_dependencies",
        &main,
        &["src/d.rs".into()],
        &flags(&[("worktree", &wt)]),
    );
    assert!(success(&deps), "{deps}");
    let gone = dispatch(
        "get_dependencies",
        &main,
        &["src/b.rs".into()],
        &flags(&[("worktree", &wt)]),
    );
    assert_eq!(
        gone.get("error_type").and_then(|v| v.as_str()),
        Some("FileNotFound"),
        "{gone}"
    );
}

#[test]
fn health_and_modularity_describe_the_branch() {
    let main = main_tree("health");
    let tree = linked_tree(&main);
    edit_branch(&tree);
    let wt = tree.display().to_string();

    let main_health = dispatch("health", &main, &[], &flags(&[]));
    let main_mod = main_health.get("modularity").unwrap();
    assert_eq!(
        main_mod.get("alert_count"),
        Some(&Json::Int(0)),
        "{main_health}"
    );

    let health = dispatch("health", &main, &[], &flags(&[("worktree_root", &wt)]));
    assert!(success(&health), "{health}");
    let modularity = health.get("modularity").unwrap();
    let fresh = modularity
        .get("new_in_worktree")
        .and_then(|v| v.as_array())
        .unwrap_or_else(|| panic!("{health}"));
    assert_eq!(fresh.len(), 1, "{health}");
    assert_eq!(
        fresh[0].get("file").and_then(|v| v.as_str()),
        Some("src/c.rs")
    );
    assert_eq!(
        fresh[0].get("kind").and_then(|v| v.as_str()),
        Some("line_count")
    );
    assert_eq!(fresh[0].get("value"), Some(&Json::Int(21)));

    // a.rs was marked green on main and changed in the branch: Yellow, with the lines.
    let entries = health.get("entries").and_then(|v| v.as_array()).unwrap();
    let row = |file: &str| {
        entries
            .iter()
            .find(|e| e.get("file").and_then(|v| v.as_str()) == Some(file))
            .unwrap_or_else(|| panic!("no {file} in {health}"))
            .clone()
    };
    let a = row("src/a.rs");
    assert!(
        a.get("status")
            .and_then(|v| v.as_str())
            .unwrap()
            .contains("Yellow"),
        "{a}"
    );
    assert!(a.get("changed_lines").is_some(), "{a}");
    let b = row("src/b.rs");
    assert!(
        b.get("status")
            .and_then(|v| v.as_str())
            .unwrap()
            .contains("Red"),
        "{b}"
    );
    let d = row("src/d.rs");
    assert_eq!(
        d.get("reason").and_then(|v| v.as_str()),
        Some("Initial stub")
    );

    // Main still says a.rs is Green.
    let main_entries = main_health
        .get("entries")
        .and_then(|v| v.as_array())
        .unwrap();
    let main_a = main_entries
        .iter()
        .find(|e| e.get("file").and_then(|v| v.as_str()) == Some("src/a.rs"))
        .unwrap();
    assert!(main_a
        .get("status")
        .and_then(|v| v.as_str())
        .unwrap()
        .contains("Green"));

    let bootstrap = dispatch(
        "session_bootstrap",
        &main,
        &[],
        &flags(&[("worktree_root", &wt)]),
    );
    assert!(success(&bootstrap), "{bootstrap}");
    assert!(bootstrap
        .get("actions")
        .and_then(|v| v.as_array())
        .unwrap()
        .iter()
        .any(
            |a| a.get("action").and_then(|v| v.as_str()) == Some("review_modularity")
                && a.get("file").and_then(|v| v.as_str()) == Some("src/c.rs")
        ));

    let changes = dispatch(
        "check_changes",
        &main,
        &[],
        &flags(&[("worktree_root", &wt)]),
    );
    // Everything the branch changed or deleted against main's recorded hashes; the new
    // d.rs is an Initial stub, not a change.
    assert_eq!(
        strings(&changes, "files"),
        ["src/a.rs", "src/b.rs", "src/c.rs", "src/lib.rs"],
        "{changes}"
    );
    assert_eq!(
        changes.get("modularity_alerts"),
        Some(&Json::Int(1)),
        "{changes}"
    );
}

#[test]
fn writers_refuse_a_worktree_and_leave_main_alone() {
    let main = main_tree("writers");
    let tree = linked_tree(&main);
    edit_branch(&tree);
    let before = main_state(&main);
    let wt = tree.display().to_string();
    for (name, positional) in [
        (
            "record_change",
            vec!["src/a.rs".to_string(), "why".to_string()],
        ),
        (
            "mark_green",
            vec!["src/a.rs".to_string(), "why".to_string()],
        ),
        (
            "record_deletion",
            vec!["src/b.rs".to_string(), "gone".to_string()],
        ),
        ("record_changes", vec![]),
        ("heal_stubs", vec![]),
    ] {
        let value = dispatch(name, &main, &positional, &flags(&[("worktree_root", &wt)]));
        assert_eq!(
            value.get("error_type").and_then(|v| v.as_str()),
            Some("WorktreeReadOnly"),
            "{name}: {value}"
        );
        let error = value.get("error").and_then(|v| v.as_str()).unwrap();
        assert!(error.contains("main") && error.contains(name), "{error}");
    }
    assert_eq!(main_state(&main), before);

    // update_maps with a worktree refreshes only the overlay.
    let maps = dispatch("update_maps", &main, &[], &flags(&[("worktree_root", &wt)]));
    assert!(success(&maps), "{maps}");
    assert_eq!(main_state(&main), before);
}

#[test]
fn a_bad_worktree_root_is_a_one_line_error() {
    let main = main_tree("bad");
    let missing = main.parent().unwrap().join("nowhere");
    let checks = [
        (missing.display().to_string(), "does not exist"),
        ("relative/path".to_string(), "absolute"),
    ];
    for (raw, needle) in checks {
        let value = dispatch(
            "get_dependents",
            &main,
            &["src/core.rs".into()],
            &flags(&[("worktree_root", &raw)]),
        );
        assert_eq!(
            value.get("error_type").and_then(|v| v.as_str()),
            Some("WorktreeError"),
            "{value}"
        );
        let error = value.get("error").and_then(|v| v.as_str()).unwrap();
        assert!(error.contains(needle) && !error.contains('\n'), "{error}");
    }
    // A separate clone has its own .git directory: not a checkout of this project.
    let clone = main.parent().unwrap().join("clone");
    fs::create_dir_all(clone.join(".git")).unwrap();
    let value = dispatch(
        "get_dependents",
        &main,
        &["src/core.rs".into()],
        &flags(&[("worktree_root", &clone.display().to_string())]),
    );
    let error = value.get("error").and_then(|v| v.as_str()).unwrap_or("");
    assert!(error.contains("not a checkout"), "{value}");
    // A plain directory is not a git checkout of a git main.
    let plain = main.parent().unwrap().join("plain");
    fs::create_dir_all(&plain).unwrap();
    let value = dispatch(
        "get_dependents",
        &main,
        &["src/core.rs".into()],
        &flags(&[("worktree_root", &plain.display().to_string())]),
    );
    let error = value.get("error").and_then(|v| v.as_str()).unwrap_or("");
    assert!(error.contains("no .git"), "{value}");
    // worktree_root equal to main is a plain main call.
    let same = dispatch(
        "get_dependents",
        &main,
        &["src/core.rs".into()],
        &flags(&[("worktree_root", &main.display().to_string())]),
    );
    let plain_call = dispatch(
        "get_dependents",
        &main,
        &["src/core.rs".into()],
        &flags(&[]),
    );
    assert_eq!(same.to_string(), plain_call.to_string());
}

#[test]
fn a_root_that_is_a_bare_worktree_is_answered_as_one() {
    let main = main_tree("auto");
    let tree = linked_tree(&main);
    edit_branch(&tree);
    // Before 5.5.0 this answered success with an empty dependents list.
    let value = dispatch(
        "get_dependents",
        &tree,
        &["src/core.rs".into()],
        &flags(&[]),
    );
    assert!(success(&value), "{value}");
    assert_eq!(
        strings(&value, "dependents"),
        ["src/c.rs", "src/d.rs", "src/lib.rs"],
        "{value}"
    );
    assert!(value.get("worktree").is_some(), "{value}");
    let refused = dispatch(
        "record_change",
        &tree,
        &["src/a.rs".into(), "why".into()],
        &flags(&[]),
    );
    assert_eq!(
        refused.get("error_type").and_then(|v| v.as_str()),
        Some("WorktreeReadOnly"),
        "{refused}"
    );
    assert!(!tree.join("file_health.json").exists());
}

#[test]
fn a_main_without_git_accepts_a_copy_of_the_tree() {
    let base = scratch("copy");
    let main = base.join("main");
    write(&main, "map_paths.txt", "src\n");
    write(&main, "src/lib.rs", "pub mod core;\n");
    write(&main, "src/core.rs", "pub struct Camera;\n");
    assert!(success(&api::update_maps(&main)));
    let copy = base.join("copy");
    write(&copy, "src/lib.rs", "pub mod core;\npub mod e;\n");
    write(&copy, "src/core.rs", "pub struct Camera;\n");
    write(&copy, "src/e.rs", "use crate::core::Camera;\n");
    let value = dispatch(
        "get_dependents",
        &main,
        &["src/core.rs".into()],
        &flags(&[("worktree_root", &copy.display().to_string())]),
    );
    assert_eq!(
        strings(&value, "dependents"),
        ["src/e.rs", "src/lib.rs"],
        "{value}"
    );
    assert_eq!(value.get("overlay_files"), Some(&Json::Int(2)), "{value}");
}

#[test]
fn overlays_of_removed_worktrees_are_pruned() {
    let main = main_tree("prune");
    let tree = linked_tree(&main);
    let wt = tree.display().to_string();
    let first = dispatch(
        "health",
        &main,
        &[],
        &flags(&[("worktree_root", &wt), ("summary", "true")]),
    );
    assert!(success(&first), "{first}");
    let overlays = main.join(".wikifier_staging/overlays");
    assert_eq!(fs::read_dir(&overlays).unwrap().count(), 1);
    fs::remove_dir_all(&tree).unwrap();
    let other = main.parent().unwrap().join("lane2");
    write(&other, "src/lib.rs", "pub mod core;\n");
    write(&other, "src/core.rs", "pub struct Camera;\n");
    let gitdir = main.join(".git/worktrees/lane2");
    fs::create_dir_all(&gitdir).unwrap();
    fs::write(gitdir.join("commondir"), "../..\n").unwrap();
    fs::write(
        other.join(".git"),
        format!("gitdir: {}\n", gitdir.display()),
    )
    .unwrap();
    let second = dispatch(
        "health",
        &main,
        &[],
        &flags(&[
            ("worktree_root", &other.display().to_string()),
            ("summary", "true"),
        ]),
    );
    assert!(success(&second), "{second}");
    let left: Vec<String> = fs::read_dir(&overlays)
        .unwrap()
        .flatten()
        .map(|e| fs::read_to_string(e.path().join("worktree.txt")).unwrap())
        .collect();
    assert_eq!(left.len(), 1, "{left:?}");
    assert!(
        left[0].starts_with(&other.display().to_string()),
        "{left:?}"
    );
}

#[test]
fn the_cli_takes_worktree() {
    let main = main_tree("cli");
    let tree = linked_tree(&main);
    edit_branch(&tree);
    let out = Command::new(env!("CARGO_BIN_EXE_wikifier"))
        .args([
            "--target",
            &main.display().to_string(),
            "dependents",
            "src/core.rs",
        ])
        .args(["--worktree", &tree.display().to_string()])
        .output()
        .unwrap();
    let value = jsonutil::parse(String::from_utf8_lossy(&out.stdout).trim()).unwrap();
    assert_eq!(
        strings(&value, "dependents"),
        ["src/c.rs", "src/d.rs", "src/lib.rs"],
        "{value}"
    );
}

fn mcp(lines: &[String]) -> Vec<Json> {
    let mut child = Command::new(env!("CARGO_BIN_EXE_wikifier"))
        .arg("mcp")
        .env_remove("WIKIFIER_TOOLS")
        .env_remove("WIKIFIER_DISABLE")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .unwrap();
    {
        let stdin = child.stdin.as_mut().unwrap();
        for line in lines {
            writeln!(stdin, "{line}").unwrap();
        }
    }
    let out = child.wait_with_output().unwrap();
    String::from_utf8_lossy(&out.stdout)
        .lines()
        .filter(|l| l.contains("\"id\""))
        .map(|l| jsonutil::parse(l).unwrap())
        .collect()
}

#[test]
fn mcp_read_tools_take_worktree_root_and_writers_do_not_list_it() {
    let main = main_tree("mcp");
    let tree = linked_tree(&main);
    edit_branch(&tree);
    let call = Json::obj(vec![
        ("jsonrpc", Json::String("2.0".into())),
        ("id", Json::Int(2)),
        ("method", Json::String("tools/call".into())),
        (
            "params",
            Json::obj(vec![
                ("name", Json::String("get_dependents".into())),
                (
                    "arguments",
                    Json::obj(vec![
                        ("project_root", Json::String(main.display().to_string())),
                        ("file", Json::String("src/core.rs".into())),
                        ("worktree_root", Json::String(tree.display().to_string())),
                    ]),
                ),
            ]),
        ),
    ]);
    let list = r#"{"jsonrpc":"2.0","id":1,"method":"tools/list"}"#.to_string();
    let got = mcp(&[list, call.to_string()]);
    let tools = got[0]
        .get("result")
        .and_then(|r| r.get("tools"))
        .and_then(|t| t.as_array())
        .unwrap();
    let props = |name: &str| {
        tools
            .iter()
            .find(|t| t.get("name").and_then(|v| v.as_str()) == Some(name))
            .and_then(|t| t.get("inputSchema"))
            .and_then(|s| s.get("properties"))
            .cloned()
            .unwrap()
    };
    for name in [
        "get_dependents",
        "get_cycles",
        "why_file",
        "health",
        "check_changes",
        "prepare_edit",
    ] {
        assert!(props(name).get("worktree_root").is_some(), "{name}");
    }
    for name in ["record_change", "mark_green", "record_changes"] {
        assert!(props(name).get("worktree_root").is_none(), "{name}");
    }
    let reply = got[1]
        .get("result")
        .and_then(|r| r.get("structuredContent"))
        .cloned()
        .unwrap();
    assert_eq!(
        strings(&reply, "dependents"),
        ["src/c.rs", "src/d.rs", "src/lib.rs"],
        "{reply}"
    );
    assert_eq!(reply.get("overlay_files"), Some(&Json::Int(5)), "{reply}");
}
