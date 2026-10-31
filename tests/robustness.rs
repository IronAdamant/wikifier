//! UTF-8, long cache names, crash repair, and concurrent commits.

use std::collections::BTreeSet;
use std::fs;
use std::path::PathBuf;
use std::thread;
use std::time::{SystemTime, UNIX_EPOCH};

use wikifier::cache::{self, by_src_path, check_consistency, commit_pending_path, payload_bytes, payload_path, rebuild, FileUpdate, Session};
use wikifier::jsonutil::Json;
use wikifier::{load_dependencies, load_dependents, mark_green, update_maps};

fn scratch(name: &str) -> PathBuf {
    let n = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
    let dir = std::env::temp_dir().join(format!("wk-robust-{name}-{n}-{}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(dir.join("src/pkg")).unwrap();
    fs::write(dir.join("map_paths.txt"), "src\n").unwrap();
    dir
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
fn non_ascii_and_non_utf8_files_do_not_abort_the_map() {
    let root = scratch("utf8");
    fs::write(root.join("src/pkg/__init__.py"), "").unwrap();
    let mut python = String::new();
    for _ in 0..40 {
        python.push_str("café = \"🐍漢字\"\n");
    }
    python.push_str("from . import b\n");
    fs::write(root.join("src/pkg/a.py"), python).unwrap();
    fs::write(root.join("src/pkg/b.py"), "VALUE = 1\n").unwrap();
    fs::write(root.join("src/pkg/bad.py"), b"from . import b\n\xff\n").unwrap();
    fs::write(root.join("src/app.ts"), "import { add } from \"./math\";\nconst café = \"🐍漢字\";\n").unwrap();
    fs::write(root.join("src/math.ts"), "export const add = (n: number) => n;\n").unwrap();

    let mapped = update_maps(&root);
    assert_eq!(mapped.get("success").and_then(|s| s.as_bool()), Some(true), "{mapped}");
    let warnings = strings(&mapped, "warnings");
    assert!(warnings.iter().any(|w| w.contains("src/pkg/bad.py") && w.contains("UTF-8")), "{warnings:?}");
    assert!(warnings.iter().all(|w| !w.contains("src/pkg/a.py")), "valid non-ASCII file warned: {warnings:?}");

    let deps = load_dependencies(&root, "src/pkg/a.py");
    assert!(has_dep(&deps, "internal", "src/pkg/b.py"), "{deps}");
    let bad = load_dependencies(&root, "src/pkg/bad.py");
    assert!(has_dep(&bad, "internal", "src/pkg/b.py"), "lossy UTF-8 dropped the import: {bad}");
    let ts = load_dependencies(&root, "src/app.ts");
    assert!(has_dep(&ts, "internal", "src/math.ts"), "{ts}");

    let marked = mark_green(&root, "src/pkg/bad.py", "", false);
    let marked_warnings = strings(&marked, "warnings");
    assert!(marked_warnings.iter().any(|w| w.contains("UTF-8")), "{marked}");
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn hashed_cache_names_round_trip_long_paths() {
    let mut rel = String::from("src");
    for i in 0..6 {
        rel.push('/');
        rel.push_str(&"n".repeat(50));
        rel.push_str(&i.to_string());
    }
    rel.push_str("/mod.py");
    assert!(rel.len() > 255, "path is only {} bytes", rel.len());

    let root = scratch("long");
    let mut session = Session::open(&root).unwrap();
    session.upsert(&FileUpdate {
        rel: rel.clone(),
        mtime_ns: 1,
        size: 4,
        hash: "sha256:long".into(),
        imports: Vec::new(),
        dsts: BTreeSet::new(),
        edge_lines: Vec::new(),
        external: Vec::new(),
        unresolved: Vec::new(),
    });
    session.commit().unwrap();

    let stored = payload_path(&root, &rel);
    let name = stored.file_name().unwrap().to_string_lossy();
    assert!(name.len() < 32, "cache file name is still the raw path: {name}");
    let payload = String::from_utf8(payload_bytes(&root, &rel).expect("payload")).unwrap();
    assert!(payload.contains(&rel), "{payload}");
    let edges = fs::read_to_string(by_src_path(&root, &rel)).unwrap();
    assert!(edges.starts_with(&format!("@\t{rel}\n")), "{edges}");
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn crash_window_mismatch_is_detected_and_rebuilt() {
    let root = scratch("crash");
    fs::write(root.join("src/pkg/__init__.py"), "").unwrap();
    fs::write(root.join("src/pkg/a.py"), "from . import b\n").unwrap();
    fs::write(root.join("src/pkg/b.py"), "VALUE = 1\n").unwrap();
    fs::write(root.join("src/pkg/d.py"), "VALUE = 2\n").unwrap();
    let mapped = update_maps(&root);
    assert_eq!(mapped.get("success").and_then(|s| s.as_bool()), Some(true), "{mapped}");
    let before_b = load_dependents(&root, "src/pkg/b.py");
    assert!(has_dep(&before_b, "dependents", "src/pkg/a.py"), "{before_b}");

    fs::write(by_src_path(&root, "src/pkg/a.py"), "@\tsrc/pkg/a.py\nsrc/pkg/d.py\t1\t\n").unwrap();
    fs::write(commit_pending_path(&root), "99\n").unwrap();

    let stale_d = load_dependents(&root, "src/pkg/d.py");
    assert!(!has_dep(&stale_d, "dependents", "src/pkg/a.py"), "reverse index updated despite the crash: {stale_d}");
    let stale_b = load_dependents(&root, "src/pkg/b.py");
    assert!(has_dep(&stale_b, "dependents", "src/pkg/a.py"), "forward crash should leave the old reverse edge: {stale_b}");

    let report = wikifier::api::validate(&root);
    assert_eq!(report.get("success").and_then(|s| s.as_bool()), Some(false), "{report}");
    assert_eq!(report.get("cache_consistent").and_then(|s| s.as_bool()), Some(false), "{report}");
    assert!(!strings(&report, "cache_mismatches").is_empty(), "{report}");

    rebuild(&root).unwrap();
    let fixed_d = load_dependents(&root, "src/pkg/d.py");
    assert!(has_dep(&fixed_d, "dependents", "src/pkg/a.py"), "{fixed_d}");
    let fixed_b = load_dependents(&root, "src/pkg/b.py");
    assert!(!has_dep(&fixed_b, "dependents", "src/pkg/a.py"), "{fixed_b}");
    let deps = load_dependencies(&root, "src/pkg/a.py");
    assert!(has_dep(&deps, "internal", "src/pkg/d.py"), "{deps}");
    let again = wikifier::api::validate(&root);
    assert_eq!(again.get("cache_consistent").and_then(|s| s.as_bool()), Some(true), "{again}");
    assert_eq!(again.get("success").and_then(|s| s.as_bool()), Some(true), "{again}");
    assert!(!commit_pending_path(&root).is_file(), "pending marker survived rebuild");
    let _ = check_consistency(&root);
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn parallel_updates_do_not_corrupt_the_cache() {
    let root = scratch("parallel");
    for i in 0..12 {
        fs::write(root.join(format!("src/f{i}.py")), format!("VALUE = {i}\n")).unwrap();
    }
    let mut handles = Vec::new();
    for _ in 0..3 {
        let root = root.clone();
        handles.push(thread::spawn(move || update_maps(&root)));
    }
    let results: Vec<_> = handles.into_iter().map(|handle| handle.join().expect("thread")).collect();
    for result in &results {
        assert_eq!(result.get("success").and_then(|s| s.as_bool()), Some(true), "{result}");
    }
    let paths = cache::all_paths(&root);
    assert_eq!(paths.len(), 12, "{paths:?}");
    let check = check_consistency(&root);
    assert!(check.consistent, "{:?}", check.mismatches);
    assert!(!check.incomplete, "commit.pending left behind");
    let _ = fs::remove_dir_all(&root);
}
