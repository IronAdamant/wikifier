//! One rule for every count cap (`limit`, `max_items`, `max_files`), CLI and MCP:
//! absent = the tool's default, 0 = no cap (the same as MCP `full: true`), N = at most N.
//! 5.3.0 read 0 three ways: "all" in session_bootstrap, "the default" in the compact
//! tools, and "nothing" in health, journal, cycles, verify_wikis and the CLI.

use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

use wikifier::jsonutil::{self, Json};

/// 70 modules import core.py, 8 import cycles, 3 Green files whose wiki misses a new name,
/// 3 recorded changes,
/// `os` imports for diagnostics notes, and 121 mapped files in all.
fn project() -> PathBuf {
    let n = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let root = std::env::temp_dir().join(format!("wk-limit-{n}-{}", std::process::id()));
    let pkg = root.join("src/pkg");
    fs::create_dir_all(&pkg).unwrap();
    fs::write(root.join("map_paths.txt"), "src\n").unwrap();
    fs::write(pkg.join("__init__.py"), "").unwrap();
    fs::write(pkg.join("core.py"), "import os\n").unwrap();
    for i in 0..70 {
        fs::write(
            pkg.join(format!("m{i:02}.py")),
            "import os\nfrom . import core\n",
        )
        .unwrap();
    }
    for i in 0..8 {
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
    for i in 0..30 {
        fs::write(pkg.join(format!("x{i:02}.py")), "VALUE = 1\n").unwrap();
    }
    for i in 0..3 {
        fs::write(pkg.join(format!("g{i}.py")), "def one():\n    return 1\n").unwrap();
    }
    assert_eq!(ok(&wikifier::update_maps(&root)), Some(true));
    for i in 0..3 {
        let rel = format!("src/pkg/g{i}.py");
        fs::write(
            root.join(format!("{rel}.wiki.md")),
            "# g\n\n- `one()` returns 1.\n",
        )
        .unwrap();
        assert_eq!(
            ok(&wikifier::mark_green(&root, &rel, "wiki (limit-1)", false)),
            Some(true)
        );
        // A new public name the wiki does not mention: verify_wikis now fails this file.
        fs::write(
            root.join(&rel),
            "def one():\n    return 1\n\ndef two():\n    return 2\n",
        )
        .unwrap();
        // Three other files carry recorded changes: journal entries and next actions.
        let other = format!("src/pkg/x{i:02}.py");
        let why = format!("changed x{i:02} (limit-1)");
        assert_eq!(
            ok(&wikifier::record_change(&root, &other, &why)),
            Some(true)
        );
    }
    root
}

fn ok(value: &Json) -> Option<bool> {
    value.get("success").and_then(|v| v.as_bool())
}

fn mcp(root: &Path, name: &str, extra: &[(&str, Json)]) -> Json {
    let mut args: Vec<(&str, Json)> = extra.to_vec();
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
    // verify_wikis reports failing wikis as an error result; its list is still the subject.
    if name != "verify_wikis" {
        assert_eq!(
            result.get("isError"),
            Some(&Json::Bool(false)),
            "{name}: {reply}"
        );
    }
    result.get("structuredContent").cloned().unwrap()
}

fn count(value: &Json, key: &str) -> usize {
    value
        .get(key)
        .and_then(|v| v.as_array())
        .map(|a| a.len())
        .unwrap_or_else(|| panic!("no {key} in {value}"))
}

/// (tool, extra args, the list the cap applies to, MCP default when absent, total).
type Case = (
    &'static str,
    Vec<(&'static str, Json)>,
    &'static str,
    usize,
    usize,
);

fn cases() -> Vec<Case> {
    let core = || vec![("file", Json::String("src/pkg/core.py".into()))];
    vec![
        ("session_bootstrap", vec![], "files", 100, 121),
        ("get_project_status", vec![], "files", 100, 121),
        ("health", vec![], "entries", 10, 121),
        ("get_cycles", vec![], "cycles", 5, 8),
        ("get_dependents", core(), "dependents", 50, 70),
        ("prepare_edit", core(), "dependents", 25, 70),
        ("get_resolution_diagnostics", vec![], "notes", 20, 71),
        ("verify_wikis", vec![], "failed", 3, 3),
        ("suggest_next_actions", vec![], "actions", 3, 3),
        ("journal", vec![], "entries", 3, 3),
        (
            "search_journal",
            vec![("query", Json::String("limit-1".into()))],
            "entries",
            3,
            3,
        ),
    ]
}

#[test]
fn every_mcp_cap_reads_absent_zero_and_one_the_same_way() {
    let root = project();
    for (tool, args, key, default, total) in cases() {
        let with = |cap: Option<i64>| {
            let mut extra = args.clone();
            if let Some(n) = cap {
                extra.push(("limit", Json::Int(n)));
            }
            mcp(&root, tool, &extra)
        };
        assert_eq!(count(&with(None), key), default, "{tool}: limit absent");
        let all = with(Some(0));
        assert_eq!(count(&all, key), total, "{tool}: limit 0 is no cap");
        assert_eq!(count(&with(Some(1)), key), 1, "{tool}: limit 1");
        if wikifier::mcp_compact::default_limit(tool).is_some() {
            let mut extra = args.clone();
            extra.push(("full", Json::Bool(true)));
            assert_eq!(mcp(&root, tool, &extra), all, "{tool}: limit 0 equals full");
        }
    }
    // max_items is get_cycles' name for the same cap.
    for (cap, want) in [(0, 8), (1, 1)] {
        let value = mcp(&root, "get_cycles", &[("max_items", Json::Int(cap))]);
        assert_eq!(count(&value, "cycles"), want, "max_items {cap}");
    }
    // max_files caps list_paths the same way; unset lists every file.
    let list = |cap: Option<i64>| {
        let mut extra = vec![
            ("prefix", Json::String("src/pkg".into())),
            ("depth", Json::Int(0)),
        ];
        if let Some(n) = cap {
            extra.push(("max_files", Json::Int(n)));
        }
        count(&mcp(&root, "list_paths", &extra), "files")
    };
    assert_eq!(list(None), 121);
    assert_eq!(list(Some(0)), 121);
    assert_eq!(list(Some(1)), 1);
    let _ = fs::remove_dir_all(root);
}

#[test]
fn every_cli_cap_reads_absent_zero_and_one_the_same_way() {
    let root = project();
    let run = |args: &[&str]| {
        let out = Command::new(env!("CARGO_BIN_EXE_wikifier"))
            .arg("--target")
            .arg(&root)
            .args(args)
            .output()
            .unwrap();
        jsonutil::parse(String::from_utf8_lossy(&out.stdout).trim()).unwrap()
    };
    let cli: [(&[&str], &str, &str, usize); 8] = [
        (&["session-bootstrap"], "--limit", "files", 121),
        (&["health"], "--limit", "entries", 121),
        (&["journal"], "--limit", "entries", 3),
        (&["search-journal", "limit-1"], "--limit", "entries", 3),
        (&["verify-wikis"], "--limit", "failed", 3),
        (&["suggest-next"], "--limit", "actions", 3),
        (&["cycles"], "--max-items", "cycles", 8),
        (
            &["list-paths", "src/pkg", "--depth", "0"],
            "--max-files",
            "files",
            121,
        ),
    ];
    for (base, flag, key, total) in cli {
        assert_eq!(count(&run(base), key), total, "{base:?} absent");
        let with = |n: &str| {
            let mut args = base.to_vec();
            args.extend([flag, n]);
            count(&run(&args), key)
        };
        assert_eq!(with("0"), total, "{base:?} {flag} 0");
        assert_eq!(with("1"), 1, "{base:?} {flag} 1");
    }
    let _ = fs::remove_dir_all(root);
}

#[test]
fn the_shared_parser() {
    use wikifier::api::Cap;
    assert_eq!(Cap::parse(None), Cap::Default);
    assert_eq!(Cap::parse(Some("0")), Cap::All);
    assert_eq!(Cap::parse(Some(" 7 ")), Cap::First(7));
    assert_eq!(Cap::parse(Some("-1")), Cap::Default);
    assert_eq!(Cap::parse(Some("ten")), Cap::Default);
    assert_eq!(Cap::All.max(), None);
    assert_eq!(Cap::First(3).max(), Some(3));
}
