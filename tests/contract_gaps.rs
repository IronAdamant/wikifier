//! Contract holes the verification panel caught: health drift, real commands, readiness, deps.

use std::fs;
use std::path::PathBuf;
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

use wikifier::api::{check_changes, cycles, load_dependencies, mark_green, read_health, read_journal, record_changes, serve_once, session_bootstrap, update_maps, validate, verify_wikis};
use wikifier::jsonutil::Json;

fn scratch(name: &str) -> PathBuf {
    let n = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
    let dir = std::env::temp_dir().join(format!("wk-gap-{name}-{n}"));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(dir.join("src")).unwrap();
    fs::write(dir.join("map_paths.txt"), "src\n").unwrap();
    fs::write(dir.join("monitored_paths.txt"), "src\n").unwrap();
    dir
}

fn int_field(v: &Json, key: &str) -> i64 {
    match v.get(key) {
        Some(Json::Int(n)) => *n,
        _ => panic!("missing int {key} in {v}"),
    }
}

#[test]
fn check_changes_yellows_green_from_health_baseline_and_update_maps_keeps_it() {
    let root = scratch("dirty");
    fs::write(root.join("src/a.py"), "def hello():\n    return 1\n").unwrap();
    assert_eq!(update_maps(&root).get("success").and_then(|s| s.as_bool()), Some(true));
    let marked = mark_green(&root, "src/a.py", "wiki matches", false);
    assert_eq!(marked.get("success").and_then(|s| s.as_bool()), Some(true), "{marked}");
    fs::write(root.join("src/a.py"), "def hello():\n    return 2\n").unwrap();
    let dirty = check_changes(&root);
    assert_eq!(dirty.get("success").and_then(|s| s.as_bool()), Some(true), "{dirty}");
    assert!(int_field(&dirty, "dirty_total") >= 1, "{dirty}");
    let row = read_health(&root).into_iter().find(|r| r.file == "src/a.py").unwrap();
    assert!(row.status.contains("Yellow"), "health stayed {:?}", row.status);
    assert!(row.reason.contains("content changed"));
    let journal = read_journal(&root, None);
    assert!(journal.iter().any(|e| e.file == "src/a.py" && e.reason.contains("content changed")), "{journal:?}");
    let pending = fs::read_to_string(root.join("pending_updates.md")).unwrap_or_default();
    assert!(pending.contains("src/a.py"), "{pending}");
    assert_eq!(update_maps(&root).get("success").and_then(|s| s.as_bool()), Some(true));
    let row = read_health(&root).into_iter().find(|r| r.file == "src/a.py").unwrap();
    assert!(row.status.contains("Yellow"), "update_maps cleared yellow: {}", row.status);
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn readiness_blocks_without_health_and_refuses_reds() {
    let root = scratch("ready");
    fs::write(root.join("src/a.py"), "x = 1\n").unwrap();
    let blocked = session_bootstrap(&root);
    // bootstrap builds the map and seeds health, so a fresh tree becomes ready or wiki-work, not a lie.
    let ready = blocked.get("readiness").and_then(|s| s.as_str()).unwrap_or("");
    assert_ne!(ready, "", "{blocked}");
    // Strip the health file and ask again without a map rebuild.
    fs::remove_file(root.join("file_health.json")).ok();
    fs::remove_file(root.join("file_health.md")).ok();
    let again = wikifier::health(&root);
    assert_eq!(int_field(again.get("health_summary").unwrap(), "total"), 0);
    let status = wikifier::api::dispatch("autonomous-status", &root, &[], &std::collections::BTreeMap::new());
    assert_eq!(status.get("readiness").and_then(|s| s.as_str()), Some("blocked"), "{status}");

    fs::write(root.join("file_health.json"), r#"{"version":2,"entries":{"src/a.py":{"status":"🔴 Red","last_updated":"2026-10-01 00:00:00","reason":"missing","source_content_hash":"sha256:abc"}}}"#).unwrap();
    let red = session_bootstrap(&root);
    assert_eq!(red.get("readiness").and_then(|s| s.as_str()), Some("not_ready"), "{red}");
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn dependencies_are_compact_and_force_overrides_wiki_check() {
    let root = scratch("deps");
    fs::write(root.join("src/a.py"), "import os\nfrom . import b\n\ndef hello():\n    return 1\n").unwrap();
    fs::write(root.join("src/__init__.py"), "").unwrap();
    fs::write(root.join("src/b.py"), "VALUE = 1\n").unwrap();
    assert_eq!(update_maps(&root).get("success").and_then(|s| s.as_bool()), Some(true));
    let deps = load_dependencies(&root, "src/a.py");
    assert_eq!(deps.get("success").and_then(|s| s.as_bool()), Some(true), "{deps}");
    let internal = deps.get("internal").and_then(|v| v.as_array()).unwrap();
    assert!(internal.iter().any(|e| e.get("path").and_then(|p| p.as_str()) == Some("src/b.py")), "{deps}");
    assert!(internal.iter().all(|e| e.get("line").is_some() && e.get("names").is_some()), "{deps}");
    let external = deps.get("external").and_then(|v| v.as_array()).unwrap();
    assert!(external.iter().any(|e| e.as_str() == Some("os")), "{deps}");
    assert!(deps.get("needs_review").and_then(|v| v.as_array()).is_some());

    fs::write(root.join("src/a.py.wiki.md"), "mentions nothing useful\n").unwrap();
    let refused = mark_green(&root, "src/a.py", "", false);
    assert_eq!(refused.get("error_type").and_then(|s| s.as_str()), Some("WikiVerificationError"), "{refused}");
    let forced = mark_green(&root, "src/a.py", "wiki is still accurate", true);
    assert_eq!(forced.get("success").and_then(|s| s.as_bool()), Some(true), "{forced}");
    assert_eq!(forced.get("verification").and_then(|s| s.as_str()), Some("forced"), "{forced}");
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn cycles_record_changes_validate_and_verify_are_not_canned() {
    let root = scratch("cmds");
    fs::write(root.join("src/a.py"), "import b\n").unwrap();
    fs::write(root.join("src/b.py"), "import a\n").unwrap();
    assert_eq!(update_maps(&root).get("success").and_then(|s| s.as_bool()), Some(true));
    let report = cycles(&root);
    assert_eq!(report.get("success").and_then(|s| s.as_bool()), Some(true), "{report}");
    assert!(int_field(&report, "count") >= 1, "{report}");

    fs::write(root.join("src/c.py"), "import missing_local_thing\n").unwrap();
    let missing = validate(&root);
    let list = missing.get("missing").and_then(|v| v.as_array()).unwrap();
    assert!(list.iter().any(|v| v.as_str() == Some("src/c.py")), "{missing}");

    fs::write(root.join("src/a.py.wiki.md"), "no symbols here\n").unwrap();
    let _ = mark_green(&root, "src/a.py", "force", true);
    // a.py public surface may be empty so verify can pass; give it a function the wiki misses.
    fs::write(root.join("src/a.py"), "import b\n\ndef added():\n    return 1\n").unwrap();
    let _ = mark_green(&root, "src/a.py", "force the new symbol", true);
    let checked = verify_wikis(&root);
    assert!(int_field(&checked, "checked") >= 1, "{checked}");
    assert_eq!(checked.get("success").and_then(|s| s.as_bool()), Some(false), "{checked}");

    let no_git = record_changes(&root, &[], None);
    assert_eq!(no_git.get("error_type").and_then(|s| s.as_str()), Some("GitUnavailableError"), "{no_git}");
    Command::new("git").args(["init"]).current_dir(&root).output().unwrap();
    Command::new("git").args(["add", "-A"]).current_dir(&root).output().unwrap();
    Command::new("git").args(["-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-m", "init"]).current_dir(&root).output().unwrap();
    fs::write(root.join("src/a.py"), "import b\n\ndef added():\n    return 2\n").unwrap();
    let recorded = record_changes(&root, &["src/a.py=edited the cycle".into()], None);
    assert_eq!(recorded.get("success").and_then(|s| s.as_bool()), Some(true), "{recorded}");
    assert!(int_field(&recorded, "recorded") >= 1, "{recorded}");
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn stale_wikis_prune_barrels_and_metrics_do_real_work() {
    let root = scratch("hygiene");
    fs::write(root.join("src/index.ts"), "export * from './math';\n").unwrap();
    fs::write(root.join("src/math.ts"), "export const add = (n: number) => n;\n").unwrap();
    fs::write(root.join("src/a.py"), "def hello():\n    return 1\n").unwrap();
    let mapped = update_maps(&root);
    assert_eq!(mapped.get("success").and_then(|s| s.as_bool()), Some(true), "{mapped}");
    let barrel_dir = root.join(".wikifier_staging/wk_cache/barrels");
    let barrels: Vec<_> = fs::read_dir(&barrel_dir).unwrap().flatten().map(|e| e.path()).collect();
    assert!(!barrels.is_empty(), "update_maps did not write a barrel record");

    let flags = std::collections::BTreeMap::new();
    let snap = wikifier::api::dispatch("metrics-snapshot", &root, &[], &flags);
    assert_eq!(snap.get("success").and_then(|s| s.as_bool()), Some(true), "{snap}");
    assert_eq!(snap.get("appended").and_then(|s| s.as_bool()), Some(true), "{snap}");
    let latest = fs::read_to_string(root.join(".wikifier_staging/metrics_latest.json")).unwrap();
    assert!(latest.contains("\"total\":"), "{latest}");
    let hist1 = fs::read_to_string(root.join(".wikifier_staging/metrics_history.jsonl")).unwrap();
    assert_eq!(hist1.lines().filter(|l| !l.is_empty()).count(), 1, "{hist1}");
    let snap2 = wikifier::api::dispatch("metrics-snapshot", &root, &[], &flags);
    assert_eq!(snap2.get("success").and_then(|s| s.as_bool()), Some(true), "{snap2}");
    let hist2 = fs::read_to_string(root.join(".wikifier_staging/metrics_history.jsonl")).unwrap();
    assert_eq!(hist2.lines().filter(|l| !l.is_empty()).count(), 2, "{hist2}");

    fs::write(root.join("src/a.py.wiki.md"), "hello returns 1\n").unwrap();
    let marked = mark_green(&root, "src/a.py", "wiki names hello", false);
    assert_eq!(marked.get("success").and_then(|s| s.as_bool()), Some(true), "{marked}");
    let before = wikifier::api::dispatch("stale-wikis", &root, &[], &flags);
    let before_files = before.get("files").and_then(|v| v.as_array()).unwrap();
    assert!(before_files.iter().all(|f| f.as_str() != Some("src/a.py")), "{before}");
    fs::write(root.join("src/a.py"), "def hello():\n    return 2\n").unwrap();
    let dirty = check_changes(&root);
    assert!(int_field(&dirty, "dirty_total") >= 1, "{dirty}");
    let after = wikifier::api::dispatch("stale-wikis", &root, &[], &flags);
    let after_files = after.get("files").and_then(|v| v.as_array()).unwrap();
    assert!(after_files.iter().any(|f| f.as_str() == Some("src/a.py")), "{after}");
    assert!(int_field(&after, "count") >= 1, "{after}");

    fs::remove_file(root.join("src/math.ts")).unwrap();
    let pruned = wikifier::api::dispatch("prune-barrels", &root, &[], &flags);
    assert_eq!(pruned.get("success").and_then(|s| s.as_bool()), Some(true), "{pruned}");
    assert!(int_field(&pruned, "pruned") >= 1, "{pruned}");
    let left: Vec<_> = fs::read_dir(&barrel_dir).unwrap().flatten().collect();
    assert!(left.is_empty(), "barrel cache files were not removed");
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn serve_binds_and_daemon_starts() {
    let root = scratch("serve");
    fs::write(root.join("src/a.py"), "x = 1\n").unwrap();
    let _ = update_maps(&root);
    let served = serve_once(&root);
    assert_eq!(served.get("success").and_then(|s| s.as_bool()), Some(true), "{served}");
    assert_eq!(served.get("bound").and_then(|s| s.as_bool()), Some(true), "{served}");
    assert_eq!(served.get("served").and_then(|s| s.as_bool()), Some(true), "{served}");
    assert!(int_field(&served, "port") > 0, "{served}");

    let bin = env!("CARGO_BIN_EXE_wikifier");
    let start = Command::new(bin).args(["--target", root.to_str().unwrap(), "daemon", "start"]).output().unwrap();
    assert!(start.status.success(), "{}", String::from_utf8_lossy(&start.stderr));
    let start_json = wikifier::jsonutil::parse(&String::from_utf8(start.stdout.clone()).unwrap()).unwrap();
    assert_eq!(start_json.get("running").and_then(|s| s.as_bool()), Some(true), "{start_json}");
    let status = Command::new(bin).args(["--target", root.to_str().unwrap(), "daemon", "status"]).output().unwrap();
    let status_json = wikifier::jsonutil::parse(&String::from_utf8(status.stdout).unwrap()).unwrap();
    assert_eq!(status_json.get("running").and_then(|s| s.as_bool()), Some(true), "{status_json}");
    let stop = Command::new(bin).args(["--target", root.to_str().unwrap(), "daemon", "stop"]).output().unwrap();
    assert!(stop.status.success(), "{}", String::from_utf8_lossy(&stop.stderr));
    let _ = fs::remove_dir_all(&root);
}
