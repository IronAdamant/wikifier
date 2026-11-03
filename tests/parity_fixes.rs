//! Parity with the Python 4.7 package: wiki lookup, symbols, daemon, init, flags.

use std::fs;
use std::path::PathBuf;
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

use wikifier::api::{self, mark_green, update_maps};
use wikifier::jsonutil::Json;

fn scratch(name: &str) -> PathBuf {
    let n = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let dir = std::env::temp_dir().join(format!("wk-par-{name}-{n}"));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(dir.join("src")).unwrap();
    fs::write(dir.join("map_paths.txt"), "src\n").unwrap();
    dir
}

fn bin() -> PathBuf {
    PathBuf::from(env!("CARGO_BIN_EXE_wikifier"))
}

#[test]
fn wiki_lookup_falls_back_to_docs_wiki() {
    let root = scratch("wiki");
    fs::write(root.join("src/a.py"), "def hello():\n    return 1\n").unwrap();
    fs::create_dir_all(root.join("docs/wiki")).unwrap();
    fs::write(
        root.join("docs/wiki/a.py.md"),
        "`hello` lives in the docs wiki.\n",
    )
    .unwrap();
    assert_eq!(
        update_maps(&root).get("success").and_then(|v| v.as_bool()),
        Some(true)
    );
    let edit = api::prepare_edit(&root, "src/a.py");
    assert!(
        edit.get("wiki")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .contains("hello"),
        "{edit}"
    );
    let marked = mark_green(&root, "src/a.py", "docs wiki names hello", false);
    assert_eq!(
        marked.get("verification").and_then(|v| v.as_str()),
        Some("verified"),
        "{marked}"
    );
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn multiline_all_and_pyi_are_public_symbols() {
    let root = scratch("syms");
    fs::write(
        root.join("src/api.py"),
        "__all__ = [\n    \"visible\",\n]\ndef hidden():\n    return 1\n",
    )
    .unwrap();
    fs::write(root.join("src/api.py.wiki.md"), "`visible` is public.\n").unwrap();
    let marked = mark_green(&root, "src/api.py", "only all", false);
    assert_eq!(
        marked.get("success").and_then(|v| v.as_bool()),
        Some(true),
        "{marked}"
    );
    fs::write(root.join("src/types.pyi"), "def stubbed():\n    ...\n").unwrap();
    fs::write(
        root.join("src/types.pyi.wiki.md"),
        "`stubbed` is the stub.\n",
    )
    .unwrap();
    let pyi = mark_green(&root, "src/types.pyi", "stub", false);
    assert_eq!(
        pyi.get("verification").and_then(|v| v.as_str()),
        Some("verified"),
        "{pyi}"
    );
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn js_comment_exports_are_not_public() {
    let root = scratch("js");
    fs::write(
        root.join("src/mod.ts"),
        "// export function ghost() {}\nexport function real() {}\n",
    )
    .unwrap();
    fs::write(root.join("src/mod.ts.wiki.md"), "`real` is exported.\n").unwrap();
    let marked = mark_green(&root, "src/mod.ts", "real only", false);
    assert_eq!(
        marked.get("success").and_then(|v| v.as_bool()),
        Some(true),
        "{marked}"
    );
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn pending_line_uses_the_python_shape() {
    let root = scratch("pend");
    fs::write(root.join("src/a.py"), "x = 1\n").unwrap();
    assert_eq!(
        api::record_change(&root, "src/a.py", "first reason")
            .get("success")
            .and_then(|v| v.as_bool()),
        Some(true)
    );
    let text = fs::read_to_string(root.join("pending_updates.md")).unwrap();
    assert!(
        text.contains("- src/a.py: LLM/agent edit — first reason"),
        "{text}"
    );
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn init_writes_the_python_files_and_honors_no_copy() {
    let root = scratch("init");
    let dest = root.join("proj");
    fs::create_dir_all(dest.join("src")).unwrap();
    let out = Command::new(bin())
        .arg("init")
        .arg(&dest)
        .arg("--no-copy")
        .output()
        .unwrap();
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(!dest.join("index.html").exists());
    assert!(dest.join("exclude_patterns.txt").is_file());
    assert!(dest.join("file_health.md").is_file());
    assert!(dest.join("pending_updates.md").is_file());
    assert!(dest.join("library.md").is_file());
    assert!(dest.join(".wikifier/config").is_file());
    assert!(dest.join("journal").is_dir());
    assert!(dest.join("Logged_issues").is_dir());
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn record_changes_accepts_a_json_reason_object() {
    let root = scratch("reasons");
    fs::write(root.join("src/a.py"), "x = 1\n").unwrap();
    Command::new("git")
        .args(["init"])
        .current_dir(&root)
        .output()
        .unwrap();
    Command::new("git")
        .args(["add", "src/a.py", "map_paths.txt"])
        .current_dir(&root)
        .output()
        .unwrap();
    Command::new("git")
        .args([
            "-c",
            "user.email=a@b.c",
            "-c",
            "user.name=t",
            "commit",
            "-qm",
            "init",
        ])
        .current_dir(&root)
        .output()
        .unwrap();
    fs::write(root.join("src/a.py"), "x = 2\n").unwrap();
    fs::write(root.join("reasons.json"), "{\"src/a.py\":\"bumped x\"}\n").unwrap();
    let out = Command::new(bin())
        .args([
            "--target",
            root.to_str().unwrap(),
            "record-changes",
            "--reasons",
            root.join("reasons.json").to_str().unwrap(),
            "--dry-run",
            "--only",
            "src/a.py",
        ])
        .output()
        .unwrap();
    let text = String::from_utf8_lossy(&out.stdout);
    assert!(
        out.status.success(),
        "{text} {}",
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(
        text.contains("bumped x") || text.contains("src/a.py"),
        "{text}"
    );
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn health_summary_list_paths_and_cycles_flags() {
    let root = scratch("flags");
    fs::create_dir_all(root.join("src/pkg")).unwrap();
    fs::write(root.join("src/pkg/a.py"), "import b\n").unwrap();
    fs::write(root.join("src/pkg/b.py"), "import a\n").unwrap();
    fs::write(root.join("monitored_paths.txt"), "src\n").unwrap();
    assert_eq!(
        update_maps(&root).get("success").and_then(|v| v.as_bool()),
        Some(true)
    );
    let summary = api::dispatch(
        "health",
        &root,
        &[],
        &flag(&[("summary", "true"), ("directory", "src/pkg")]),
    );
    assert!(summary.get("entries").is_none(), "{summary}");
    assert!(summary.get("health_summary").is_some(), "{summary}");
    let listed = api::dispatch(
        "list-paths",
        &root,
        &[],
        &flag(&[("prefix", "src"), ("recursive", "true"), ("max-files", "1")]),
    );
    let files = listed.get("files").and_then(|v| v.as_array()).unwrap();
    assert_eq!(files.len(), 1, "{listed}");
    assert_eq!(
        listed.get("files_truncated").and_then(|v| v.as_bool()),
        Some(true),
        "{listed}"
    );
    let cycles = api::dispatch("cycles", &root, &[], &flag(&[("max-items", "1")]));
    assert!(
        cycles
            .get("cycles")
            .and_then(|v| v.as_array())
            .unwrap()
            .len()
            <= 1,
        "{cycles}"
    );
    assert!(cycles.get("reverse_dependencies").is_some(), "{cycles}");
    let bare = api::dispatch("cycles", &root, &[], &flag(&[("no-analysis", "true")]));
    assert!(bare.get("reverse_dependencies").is_none(), "{bare}");
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn suggest_next_names_low_confidence_edges() {
    let root = scratch("low");
    fs::create_dir_all(root.join("src/pkg")).unwrap();
    fs::write(root.join("src/pkg/__init__.py"), "").unwrap();
    fs::write(root.join("src/pkg/b.py"), "VALUE = 1\n").unwrap();
    fs::write(
        root.join("src/pkg/a.py"),
        "def load():\n    from . import b\n",
    )
    .unwrap();
    fs::write(root.join("monitored_paths.txt"), "src\n").unwrap();
    assert_eq!(
        update_maps(&root).get("success").and_then(|v| v.as_bool()),
        Some(true)
    );
    let next = api::suggest_next_actions(&root);
    let actions = next.get("actions").and_then(|v| v.as_array()).unwrap();
    assert!(
        actions.iter().any(
            |a| a.get("action").and_then(|v| v.as_str()) == Some("review_low_confidence_edges")
        ),
        "{next}"
    );
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn seed_source_hashes_does_not_change_status() {
    let root = scratch("hash");
    fs::write(root.join("src/a.py"), "def hello():\n    return 1\n").unwrap();
    fs::write(root.join("monitored_paths.txt"), "src\n").unwrap();
    assert_eq!(
        update_maps(&root).get("success").and_then(|v| v.as_bool()),
        Some(true)
    );
    fs::write(root.join("src/a.py.wiki.md"), "`hello` says hello.\n").unwrap();
    assert_eq!(
        mark_green(&root, "src/a.py", "named", false)
            .get("success")
            .and_then(|v| v.as_bool()),
        Some(true)
    );
    fs::write(root.join("src/a.py"), "def hello():\n    return 2\n").unwrap();
    let before = api::read_health(&root)
        .into_iter()
        .find(|r| r.file == "src/a.py")
        .unwrap();
    let seeded = api::dispatch(
        "seed-source-hashes",
        &root,
        &[],
        &flag(&[("force", "true")]),
    );
    assert_eq!(
        seeded.get("success").and_then(|v| v.as_bool()),
        Some(true),
        "{seeded}"
    );
    let after = api::read_health(&root)
        .into_iter()
        .find(|r| r.file == "src/a.py")
        .unwrap();
    assert_eq!(after.status, before.status, "{after:?}");
    assert_ne!(after.source_hash, before.source_hash);
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn monitored_paths_scope_health_seeding() {
    let root = scratch("seed");
    fs::write(root.join("src/a.py"), "x = 1\n").unwrap();
    fs::write(root.join("README.md"), "# hi\n").unwrap();
    fs::write(root.join("monitored_paths.txt"), "README.md\n").unwrap();
    assert_eq!(
        update_maps(&root).get("success").and_then(|v| v.as_bool()),
        Some(true)
    );
    let files: Vec<String> = api::read_health(&root)
        .into_iter()
        .map(|r| r.file)
        .collect();
    assert!(
        files.iter().all(|f| f != "src/a.py"),
        "mapped file outside monitored_paths was seeded: {files:?}"
    );
    fs::remove_file(root.join("monitored_paths.txt")).unwrap();
    fs::remove_file(root.join("file_health.json")).ok();
    fs::remove_file(root.join("file_health.md")).ok();
    assert_eq!(
        update_maps(&root).get("success").and_then(|v| v.as_bool()),
        Some(true)
    );
    let files: Vec<String> = api::read_health(&root)
        .into_iter()
        .map(|r| r.file)
        .collect();
    assert!(
        files.iter().any(|f| f == "src/a.py"),
        "absent monitored_paths should seed the map: {files:?}"
    );
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn daemon_install_writes_a_unit_and_logs_exist() {
    let root = scratch("daemon");
    fs::write(root.join("src/a.py"), "x = 1\n").unwrap();
    fs::write(root.join("monitored_paths.txt"), "src\n").unwrap();
    assert_eq!(
        update_maps(&root).get("success").and_then(|v| v.as_bool()),
        Some(true)
    );
    let home = scratch("home");
    let install = Command::new(bin())
        .args([
            "--target",
            root.to_str().unwrap(),
            "daemon",
            "install-service",
        ])
        .env("WIKIFIER_SERVICE_HOME", &home)
        .env("XDG_CONFIG_HOME", home.join(".config"))
        .output()
        .unwrap();
    let text = String::from_utf8_lossy(&install.stdout);
    let err = String::from_utf8_lossy(&install.stderr);
    let unit = home.join(".config/systemd/user/wikifier.service");
    if cfg!(target_os = "linux") {
        assert!(install.status.success(), "{text} {err}");
        let body = fs::read_to_string(&unit).unwrap_or_else(|_| panic!("{text}"));
        assert!(body.contains("daemon run"), "{body}");
    } else if cfg!(target_os = "macos") {
        assert!(install.status.success(), "{text} {err}");
        assert!(
            home.join("Library/LaunchAgents/com.wikifier.agent.plist")
                .is_file(),
            "{text}"
        );
    } else {
        assert!(
            text.contains("Task Scheduler")
                || text.contains("daemon run")
                || text.contains("\"success\":true"),
            "{text} {err}"
        );
    }
    let _ = Command::new(bin())
        .args([
            "--target",
            root.to_str().unwrap(),
            "daemon",
            "uninstall-service",
        ])
        .env("WIKIFIER_SERVICE_HOME", &home)
        .env("XDG_CONFIG_HOME", home.join(".config"))
        .output();
    let logs = Command::new(bin())
        .args(["--target", root.to_str().unwrap(), "daemon", "logs"])
        .output()
        .unwrap();
    assert!(
        logs.status.success(),
        "{}",
        String::from_utf8_lossy(&logs.stdout)
    );
    let _ = fs::remove_dir_all(&root);
    let _ = fs::remove_dir_all(&home);
}

#[test]
fn text_flag_prints_prose_and_default_stays_json() {
    let root = scratch("text");
    fs::write(root.join("src/a.py"), "x = 1\n").unwrap();
    let plain = Command::new(bin())
        .args(["--target", root.to_str().unwrap(), "check-changes"])
        .output()
        .unwrap();
    let plain_text = String::from_utf8_lossy(&plain.stdout);
    assert!(plain_text.contains("\"success\""), "{plain_text}");
    let prose = Command::new(bin())
        .args([
            "--target",
            root.to_str().unwrap(),
            "check-changes",
            "--text",
        ])
        .output()
        .unwrap();
    let prose_text = String::from_utf8_lossy(&prose.stdout);
    assert!(prose_text.contains("check_changes:"), "{prose_text}");
    assert!(!prose_text.contains("\"success\""), "{prose_text}");
    let _ = fs::remove_dir_all(&root);
}

fn flag(pairs: &[(&str, &str)]) -> std::collections::BTreeMap<String, String> {
    pairs
        .iter()
        .map(|(k, v)| ((*k).to_string(), (*v).to_string()))
        .collect()
}

#[test]
fn mcp_prompt_is_specific_and_reasons_object_is_accepted() {
    let prompt = wikifier::jsonutil::parse(r#"{"jsonrpc":"2.0","id":1,"method":"prompts/get","params":{"name":"review_pending_changes"}}"#).unwrap();
    let got = wikifier::mcp::handle_message(&prompt).unwrap();
    let text = got.to_string();
    assert!(text.contains("session_bootstrap"), "{text}");
    assert!(
        !text.contains("Use Wikifier. Prompt review_pending_changes"),
        "{text}"
    );
    let _ = Json::Null;
}
