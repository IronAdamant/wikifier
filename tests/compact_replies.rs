//! MCP replies that grow with the repository are compact by default: counts plus the
//! first `limit` items, with `full: true` for everything. The CLI is unchanged.

use std::fs;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use wikifier::jsonutil::Json;

/// 70 modules import `core.py`; 7 two-file cycles and one 12-file cycle; `os` imports
/// give diagnostics notes. Then a recorded change makes one row an actionable Yellow.
fn big_project() -> PathBuf {
    let n = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let root = std::env::temp_dir().join(format!("wk-compact-{n}-{}", std::process::id()));
    let pkg = root.join("src/pkg");
    fs::create_dir_all(pkg.join("sub")).unwrap();
    fs::write(root.join("map_paths.txt"), "src\n").unwrap();
    fs::write(pkg.join("__init__.py"), "").unwrap();
    fs::write(pkg.join("core.py"), "import os\n").unwrap();
    for i in 0..70 {
        let dir = if i % 2 == 0 { "" } else { "sub/" };
        let dots = if i % 2 == 0 { "." } else { ".." };
        fs::write(
            pkg.join(format!("{dir}m{i:02}.py")),
            format!("import os\nfrom {dots} import core\n"),
        )
        .unwrap();
    }
    fs::write(pkg.join("sub/__init__.py"), "").unwrap();
    for i in 0..7 {
        fs::write(
            pkg.join(format!("pa{i}.py")),
            format!("from . import pb{i}\n"),
        )
        .unwrap();
        fs::write(
            pkg.join(format!("pb{i}.py")),
            format!("from . import pa{i}\n"),
        )
        .unwrap();
    }
    for i in 0..12 {
        let next = (i + 1) % 12;
        fs::write(
            pkg.join(format!("r{i:02}.py")),
            format!("from . import r{next:02}\n"),
        )
        .unwrap();
    }
    let built = wikifier::update_maps(&root);
    assert_eq!(
        built.get("success").and_then(|v| v.as_bool()),
        Some(true),
        "{built}"
    );
    let recorded = wikifier::record_change(&root, "src/pkg/sub/m69.py", "changed (compact-1)");
    assert_eq!(
        recorded.get("success").and_then(|v| v.as_bool()),
        Some(true)
    );
    root
}

fn call(root: &Path, name: &str, mut args: Vec<(&str, Json)>) -> Json {
    args.push((
        "project_root",
        Json::String(root.to_string_lossy().into_owned()),
    ));
    let msg = Json::obj(vec![
        ("jsonrpc", Json::String("2.0".into())),
        ("id", Json::Int(1)),
        ("method", Json::String("tools/call".into())),
        (
            "params",
            Json::obj(vec![
                ("name", Json::String(name.into())),
                ("arguments", Json::obj(args)),
            ]),
        ),
    ]);
    let reply = wikifier::mcp::handle_message(&msg).unwrap();
    let result = reply.get("result").unwrap();
    assert_eq!(result.get("isError"), Some(&Json::Bool(false)), "{reply}");
    result.get("structuredContent").cloned().unwrap()
}

fn len(value: &Json, key: &str) -> usize {
    value
        .get(key)
        .and_then(|v| v.as_array())
        .map(|a| a.len())
        .unwrap_or_else(|| panic!("no {key} in {value}"))
}

fn int(value: &Json, key: &str) -> i64 {
    match value.get(key) {
        Some(Json::Int(n)) => *n,
        other => panic!("{key}: {other:?}"),
    }
}

#[test]
fn health_lists_the_most_actionable_entries_first() {
    let root = big_project();
    let compact = call(&root, "health", vec![]);
    assert_eq!(len(&compact, "entries"), 10);
    let total = int(&compact, "entries_total") as usize;
    assert!(total > 90, "{total}");
    let first = &compact.get("entries").unwrap().as_array().unwrap()[0];
    assert_eq!(
        first.get("file").and_then(|v| v.as_str()),
        Some("src/pkg/sub/m69.py")
    );
    assert!(first.get("source_content_hash").is_none(), "{first}");
    assert!(compact.get("health_summary").is_some());

    assert_eq!(
        len(
            &call(&root, "health", vec![("limit", Json::Int(3))]),
            "entries"
        ),
        3
    );
    let full = call(&root, "health", vec![("full", Json::Bool(true))]);
    assert_eq!(len(&full, "entries"), total);
    assert!(full.get("entries_total").is_none());
    let row = &full.get("entries").unwrap().as_array().unwrap()[0];
    assert!(row.get("source_content_hash").is_some(), "{row}");
    let _ = fs::remove_dir_all(root);
}

#[test]
fn dependents_are_capped_with_a_directory_summary() {
    let root = big_project();
    let core = vec![("file", Json::String("src/pkg/core.py".into()))];
    let compact = call(&root, "get_dependents", core.clone());
    assert_eq!(len(&compact, "dependents"), 50);
    assert_eq!(int(&compact, "dependents_total"), 70);
    let dirs = compact
        .get("dependent_dirs")
        .and_then(|v| v.as_array())
        .unwrap();
    let counted: i64 = dirs.iter().map(|d| int(d, "n")).sum();
    assert_eq!(counted, 70);

    let mut full_args = core.clone();
    full_args.push(("full", Json::Bool(true)));
    let full = call(&root, "get_dependents", full_args);
    assert_eq!(len(&full, "dependents"), 70);
    assert!(full.get("dependents_total").is_none());

    let prep = call(&root, "prepare_edit", core.clone());
    assert_eq!(len(&prep, "dependents"), 25);
    assert_eq!(int(&prep, "dependents_total"), 70);
    let mut limit_args = core;
    limit_args.push(("limit", Json::Int(5)));
    assert_eq!(
        len(&call(&root, "get_dependents", limit_args), "dependents"),
        5
    );

    // A file with few dependents is untouched.
    let small = call(
        &root,
        "get_dependents",
        vec![("file", Json::String("src/pkg/pa0.py".into()))],
    );
    assert_eq!(len(&small, "dependents"), 1);
    assert!(small.get("dependents_total").is_none());
    let _ = fs::remove_dir_all(root);
}

#[test]
fn cycles_and_diagnostics_are_capped() {
    let root = big_project();
    let compact = call(&root, "get_cycles", vec![]);
    assert_eq!(int(&compact, "count"), 8);
    assert_eq!(len(&compact, "cycles"), 5);
    for cycle in compact.get("cycles").unwrap().as_array().unwrap() {
        assert!(len(cycle, "files") <= 10, "{cycle}");
        if int(cycle, "size") > 10 {
            assert_eq!(cycle.get("files_truncated"), Some(&Json::Bool(true)));
        }
    }
    let full = call(&root, "get_cycles", vec![("full", Json::Bool(true))]);
    assert_eq!(len(&full, "cycles"), 8);
    let big = full
        .get("cycles")
        .unwrap()
        .as_array()
        .unwrap()
        .iter()
        .find(|c| int(c, "size") == 12)
        .cloned()
        .unwrap();
    assert_eq!(len(&big, "files"), 12);

    let notes = call(&root, "get_resolution_diagnostics", vec![]);
    assert_eq!(len(&notes, "notes"), 20);
    assert!(int(&notes, "notes_total") > 70);
    let all = call(
        &root,
        "get_resolution_diagnostics",
        vec![("full", Json::Bool(true))],
    );
    assert_eq!(len(&all, "notes") as i64, int(&notes, "notes_total"));
    let _ = fs::remove_dir_all(root);
}

#[test]
fn the_cli_keeps_full_output() {
    let root = big_project();
    let out = std::process::Command::new(env!("CARGO_BIN_EXE_wikifier"))
        .arg("--target")
        .arg(&root)
        .args(["dependents", "src/pkg/core.py"])
        .output()
        .unwrap();
    let value = wikifier::jsonutil::parse(String::from_utf8_lossy(&out.stdout).trim()).unwrap();
    assert_eq!(len(&value, "dependents"), 70);
    let _ = fs::remove_dir_all(root);
}
