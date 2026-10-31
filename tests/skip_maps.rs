//! Stat pre-check: unchanged files are not read. Size+mtime collisions are visible to validate
//! and repaired by `update-maps --full`.

use std::collections::BTreeMap;
use std::fs::{self, File};
use std::path::PathBuf;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use wikifier::api::{dispatch, validate};
use wikifier::jsonutil::Json;
use wikifier::{load_dependencies, update_maps};

fn scratch(name: &str) -> PathBuf {
    let n = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
    let dir = std::env::temp_dir().join(format!("wk-skip-{name}-{n}-{}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(dir.join("src/pkg")).unwrap();
    fs::write(dir.join("map_paths.txt"), "src\n").unwrap();
    dir
}

fn int_field(value: &Json, key: &str) -> i64 {
    match value.get(key) {
        Some(Json::Int(n)) => *n,
        _ => panic!("{key} missing in {value}"),
    }
}

fn strings(value: &Json, key: &str) -> Vec<String> {
    value.get(key).and_then(|v| v.as_array()).unwrap_or(&[]).iter().filter_map(|v| v.as_str().map(|s| s.to_string())).collect()
}

fn has_dep(value: &Json, key: &str, needle: &str) -> bool {
    value.get(key).and_then(|v| v.as_array()).unwrap_or(&[]).iter().any(|item| {
        item.as_str() == Some(needle) || item.get("path").and_then(|p| p.as_str()) == Some(needle)
    })
}

#[test]
fn stat_skip_covers_unchanged_content_mtime_delete_and_new() {
    let root = scratch("life");
    fs::write(root.join("src/pkg/__init__.py"), "").unwrap();
    fs::write(root.join("src/pkg/a.py"), "from . import b\nVALUE = 1\n").unwrap();
    fs::write(root.join("src/pkg/b.py"), "VALUE = 2\n").unwrap();

    let cold = update_maps(&root);
    assert_eq!(cold.get("success").and_then(|s| s.as_bool()), Some(true), "{cold}");
    let n = int_field(&cold, "parseable_files");
    assert_eq!(int_field(&cold, "files_parsed"), n, "cold run should parse every file: {cold}");
    assert_eq!(int_field(&cold, "files_skipped"), 0, "{cold}");
    assert!(!cold.get("edges").and_then(|v| v.as_array()).unwrap().is_empty(), "default output still lists edges: {cold}");
    let deps = load_dependencies(&root, "src/pkg/a.py");
    assert!(has_dep(&deps, "internal", "src/pkg/b.py"), "{deps}");

    let warm = update_maps(&root);
    assert_eq!(int_field(&warm, "files_parsed"), 0, "{warm}");
    assert_eq!(int_field(&warm, "files_hashed"), 0, "unchanged files were read: {warm}");
    assert_eq!(int_field(&warm, "files_skipped"), n, "{warm}");
    assert!(has_dep(&load_dependencies(&root, "src/pkg/a.py"), "internal", "src/pkg/b.py"));

    fs::write(root.join("src/pkg/a.py"), "from . import b\nVALUE = 1\n\ndef extra():\n    return 3\n").unwrap();
    let edited = update_maps(&root);
    assert!(int_field(&edited, "files_parsed") >= 1, "{edited}");
    assert!(int_field(&edited, "files_skipped") >= 1, "untouched files were parsed: {edited}");
    assert!(has_dep(&load_dependencies(&root, "src/pkg/a.py"), "internal", "src/pkg/b.py"), "{edited}");

    let b = root.join("src/pkg/b.py");
    let later = SystemTime::now() + Duration::from_secs(30);
    File::options().write(true).open(&b).unwrap().set_modified(later).unwrap();
    let touched = update_maps(&root);
    assert_eq!(int_field(&touched, "files_parsed"), 0, "mtime-only change was reparsed: {touched}");
    assert!(int_field(&touched, "files_hashed") >= 1, "mtime-only change skipped the hash: {touched}");
    assert!(has_dep(&load_dependencies(&root, "src/pkg/a.py"), "internal", "src/pkg/b.py"));
    let settled = update_maps(&root);
    assert_eq!(int_field(&settled, "files_hashed"), 0, "stored mtime was not refreshed: {settled}");
    assert_eq!(int_field(&settled, "files_skipped"), n, "{settled}");

    fs::remove_file(&b).unwrap();
    let deleted = update_maps(&root);
    assert_eq!(deleted.get("success").and_then(|s| s.as_bool()), Some(true), "{deleted}");
    let paths = wikifier::cache::all_paths(&root);
    assert!(!paths.iter().any(|p| p == "src/pkg/b.py"), "{paths:?}");
    assert!(!has_dep(&load_dependencies(&root, "src/pkg/a.py"), "internal", "src/pkg/b.py"), "dangling edge kept");

    fs::write(root.join("src/pkg/c.py"), "VALUE = 4\n").unwrap();
    let added = update_maps(&root);
    assert!(int_field(&added, "files_parsed") >= 1, "{added}");
    assert!(wikifier::cache::all_paths(&root).iter().any(|p| p == "src/pkg/c.py"), "{added}");
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn same_size_and_mtime_is_caught_by_validate_and_full_rehash() {
    let root = scratch("stealth");
    fs::write(root.join("src/a.py"), "VALUE = 1\n").unwrap();
    assert_eq!(update_maps(&root).get("success").and_then(|s| s.as_bool()), Some(true));
    let path = root.join("src/a.py");
    let mtime = fs::metadata(&path).unwrap().modified().unwrap();
    fs::write(&path, "VALUE = 9\n").unwrap();
    File::options().write(true).open(&path).unwrap().set_modified(mtime).unwrap();
    assert_eq!(fs::metadata(&path).unwrap().modified().unwrap(), mtime, "this platform did not preserve mtime");

    let skipped = update_maps(&root);
    assert_eq!(int_field(&skipped, "files_parsed"), 0, "stat hit reparsed a same-size same-mtime edit: {skipped}");
    assert_eq!(int_field(&skipped, "files_hashed"), 0, "{skipped}");
    let report = validate(&root);
    assert_eq!(report.get("success").and_then(|s| s.as_bool()), Some(false), "{report}");
    assert_eq!(report.get("error_type").and_then(|s| s.as_str()), Some("StaleMap"), "{report}");
    assert!(strings(&report, "content_drift").iter().any(|p| p == "src/a.py"), "{report}");

    let mut flags = BTreeMap::new();
    flags.insert("full".into(), "true".into());
    let repaired = dispatch("update-maps", &root, &[], &flags);
    assert_eq!(repaired.get("success").and_then(|s| s.as_bool()), Some(true), "{repaired}");
    assert_eq!(repaired.get("rehash").and_then(|s| s.as_bool()), Some(true), "{repaired}");
    assert!(int_field(&repaired, "files_parsed") >= 1, "{repaired}");
    let clean = validate(&root);
    assert_eq!(clean.get("success").and_then(|s| s.as_bool()), Some(true), "{clean}");
    assert!(strings(&clean, "content_drift").is_empty(), "{clean}");
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn quiet_omits_the_edge_list_without_dropping_the_count() {
    let root = scratch("quiet");
    fs::write(root.join("src/pkg/__init__.py"), "").unwrap();
    fs::write(root.join("src/pkg/a.py"), "from . import b\n").unwrap();
    fs::write(root.join("src/pkg/b.py"), "VALUE = 1\n").unwrap();
    let loud = update_maps(&root);
    let loud_edges = strings(&loud, "edges");
    assert!(!loud_edges.is_empty() || int_field(&loud, "edges_persisted") >= 0);
    assert!(!loud.get("edges").and_then(|v| v.as_array()).unwrap().is_empty(), "{loud}");
    let persisted = int_field(&loud, "edges_persisted");
    assert!(persisted >= 1, "{loud}");

    let mut flags = BTreeMap::new();
    flags.insert("quiet".into(), "true".into());
    let quiet = dispatch("update-maps", &root, &[], &flags);
    assert_eq!(quiet.get("success").and_then(|s| s.as_bool()), Some(true), "{quiet}");
    assert_eq!(quiet.get("edges_omitted").and_then(|s| s.as_bool()), Some(true), "{quiet}");
    assert!(quiet.get("edges").and_then(|v| v.as_array()).unwrap().is_empty(), "{quiet}");
    assert_eq!(int_field(&quiet, "edges_persisted"), persisted, "{quiet}");
    assert_eq!(int_field(&quiet, "files_parsed"), 0, "{quiet}");
    let _ = fs::remove_dir_all(&root);
}
