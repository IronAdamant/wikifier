//! Smaller 5.5.0 fixes: the parser stamp that re-parses a cache from an older parser,
//! the config reader that stopped at a line without `=`, and the MCP deadline cap.

use std::fs;
use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};

use wikifier::api::{self, dispatch};
use wikifier::jsonutil::Json;

fn scratch(name: &str) -> PathBuf {
    let n = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let dir = std::env::temp_dir().join(format!("wk-m5-{name}-{n}"));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(dir.join("src")).unwrap();
    fs::write(dir.join("map_paths.txt"), "src\n").unwrap();
    dir
}

fn int(value: &Json, key: &str) -> i64 {
    match value.get(key) {
        Some(Json::Int(n)) => *n,
        other => panic!("{key} = {other:?} in {value}"),
    }
}

#[test]
fn a_cache_from_an_older_parser_re_parses_its_rust_files_once() {
    let root = scratch("stamp");
    fs::write(
        root.join("Cargo.toml"),
        "[package]\nname = \"s\"\nversion = \"0.1.0\"\n",
    )
    .unwrap();
    fs::write(root.join("src/lib.rs"), "pub mod sight;\npub mod studio;\n").unwrap();
    fs::write(root.join("src/sight.rs"), "pub const SCHEMA: u8 = 1;\n").unwrap();
    fs::write(
        root.join("src/studio.rs"),
        "use super::*;\npub fn f() -> u8 { sight::SCHEMA }\n",
    )
    .unwrap();
    fs::write(root.join("src/helper.py"), "X = 1\n").unwrap();
    let first = api::update_maps(&root);
    assert_eq!(int(&first, "files_parsed"), 4, "{first}");
    let stamp = root.join(".wikifier_staging/wk_cache/parser");
    let current = fs::read(&stamp).unwrap();
    assert!(!current.is_empty());
    assert_eq!(int(&api::update_maps(&root), "files_parsed"), 0);

    // A 5.4.0 cache has no stamp: its Rust files (not the Python one) parse once more.
    fs::remove_file(&stamp).unwrap();
    let upgraded = api::update_maps(&root);
    assert_eq!(int(&upgraded, "files_parsed"), 3, "{upgraded}");
    assert_eq!(fs::read(&stamp).unwrap(), current);
    assert_eq!(int(&api::update_maps(&root), "files_parsed"), 0);
    let deps = api::load_dependents(&root, "src/sight.rs");
    let list: Vec<&str> = deps
        .get("dependents")
        .and_then(|v| v.as_array())
        .unwrap()
        .iter()
        .filter_map(|v| v.as_str())
        .collect();
    assert_eq!(list, ["src/lib.rs", "src/studio.rs"], "{deps}");

    // A capped run that leaves files unparsed does not write the stamp yet.
    fs::write(&stamp, "older\n").unwrap();
    let capped = dispatch(
        "update-maps",
        &root,
        &[],
        &[("max-files".to_string(), "1".to_string())]
            .into_iter()
            .collect(),
    );
    assert_eq!(int(&capped, "files_remaining_dirty"), 2, "{capped}");
    assert_eq!(fs::read(&stamp).unwrap(), b"older\n");
}

#[test]
fn a_config_line_without_equals_does_not_hide_later_keys() {
    let root = scratch("config");
    fs::create_dir_all(root.join(".wikifier")).unwrap();
    fs::write(
        root.join(".wikifier/config"),
        "project_root=/x\nnote written by hand\nmodularity_max_lines=2\n",
    )
    .unwrap();
    fs::write(root.join("src/a.py"), "A = 1\nB = 2\nC = 3\n").unwrap();
    api::update_maps(&root);
    let health = api::health(&root);
    let modularity = health.get("modularity").unwrap();
    assert_eq!(int(modularity, "max_lines"), 2, "{health}");
    assert_eq!(int(modularity, "alert_count"), 1, "{health}");
}

#[test]
fn an_mcp_deadline_is_capped_at_ten_minutes() {
    use wikifier::mcp::{deadline_s, MAX_TIMEOUT_S};
    assert_eq!(MAX_TIMEOUT_S, 600);
    assert_eq!(deadline_s(None, None), 60);
    assert_eq!(deadline_s(Some(90), Some("5")), 90);
    assert_eq!(deadline_s(None, Some("120")), 120);
    assert_eq!(deadline_s(Some(7200), None), 600);
    assert_eq!(deadline_s(None, Some("3600")), 600);
    assert_eq!(deadline_s(None, Some("junk")), 60);
}

fn modularity_actions(value: &Json) -> Vec<(String, String)> {
    value
        .get("actions")
        .and_then(|v| v.as_array())
        .unwrap()
        .iter()
        .filter(|a| a.get("action").and_then(|v| v.as_str()) == Some("review_modularity"))
        .map(|a| {
            (
                a.get("file").and_then(|v| v.as_str()).unwrap().to_string(),
                a.get("kind").and_then(|v| v.as_str()).unwrap().to_string(),
            )
        })
        .collect()
}

#[test]
fn a_crate_root_does_not_raise_a_fan_in_alert() {
    let root = scratch("fanin");
    fs::create_dir_all(root.join(".wikifier")).unwrap();
    fs::write(root.join(".wikifier/config"), "modularity_max_fan_in=2\n").unwrap();
    fs::write(
        root.join("Cargo.toml"),
        "[package]\nname = \"hub\"\nversion = \"0.1.0\"\n",
    )
    .unwrap();
    let mut lib = String::from("pub mod types;\n");
    for name in ["a", "b", "c"] {
        lib.push_str(&format!("pub mod {name};\n"));
        fs::write(
            root.join(format!("src/{name}.rs")),
            "use crate::types::T;\nuse hub::T as U;\n",
        )
        .unwrap();
    }
    fs::write(root.join("src/lib.rs"), lib).unwrap();
    fs::write(root.join("src/types.rs"), "pub struct T;\n").unwrap();
    api::update_maps(&root);
    let found = modularity_actions(&api::suggest_next_actions(&root));
    assert!(
        found.contains(&("src/types.rs".into(), "fan_in".into())),
        "{found:?}"
    );
    assert!(
        !found.iter().any(|(file, _)| file == "src/lib.rs"),
        "lib.rs is every `use hub::` import's target: {found:?}"
    );
}

#[test]
fn alerts_are_ranked_capped_and_changed_files_come_first() {
    let root = scratch("cap");
    fs::create_dir_all(root.join(".wikifier")).unwrap();
    fs::write(
        root.join(".wikifier/config"),
        "modularity_max_lines=10\nmodularity_max_fan_in=0\n",
    )
    .unwrap();
    for i in 0..15 {
        let body = "x = 1\n".repeat(11 + i * 2);
        fs::write(root.join(format!("src/m{i:02}.py")), body).unwrap();
    }
    api::update_maps(&root);
    // m00 is the smallest alert (11 lines); after mark-green and an edit it is a changed file.
    let green = api::mark_green(&root, "src/m00.py", "baseline", true);
    assert_eq!(
        green.get("success").and_then(|v| v.as_bool()),
        Some(true),
        "{green}"
    );
    fs::write(root.join("src/m00.py"), "y = 2\n".repeat(12)).unwrap();
    api::check_changes(&root);

    let next = api::suggest_next_actions(&root);
    let found = modularity_actions(&next);
    assert_eq!(found.len(), 10, "{found:?}");
    assert_eq!(
        found[0].0, "src/m00.py",
        "the changed file leads: {found:?}"
    );
    assert_eq!(found[1].0, "src/m14.py", "then the worst: {found:?}");
    let summary = next.get("modularity").unwrap();
    assert_eq!(int(summary, "alert_count"), 15);
    assert_eq!(int(summary, "alerts_listed"), 10);
    assert_eq!(int(summary.get("by_kind").unwrap(), "line_count"), 15);
    let first = &summary.get("alerts").and_then(|v| v.as_array()).unwrap()[0];
    assert!(
        first.get("reason").is_none(),
        "summary alerts stay short: {first}"
    );

    let all = dispatch(
        "suggest-next",
        &root,
        &[],
        &[("full".to_string(), "true".to_string())]
            .into_iter()
            .collect(),
    );
    assert_eq!(modularity_actions(&all).len(), 15);
    let health = dispatch(
        "health",
        &root,
        &[],
        &[("summary".to_string(), "true".to_string())]
            .into_iter()
            .collect(),
    );
    assert_eq!(
        int(health.get("modularity").unwrap(), "alerts_listed"),
        10,
        "{health}"
    );
}
