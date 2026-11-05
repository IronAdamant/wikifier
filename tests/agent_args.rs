//! Arguments as agents actually send them: Windows separators, absolute paths, a guessed
//! argument name, a file that is not there. Each must hit the right row or fail with a next step.

use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use wikifier::api;
use wikifier::{load_dependents, prepare_edit, read_health, record_change, update_maps, Json};

fn scratch(name: &str) -> PathBuf {
    let n = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let dir = std::env::temp_dir().join(format!("wk-args-{name}-{n}-{}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    dir
}

fn mapped_project(name: &str) -> PathBuf {
    let root = scratch(name);
    fs::create_dir_all(root.join("src")).unwrap();
    fs::write(root.join("map_paths.txt"), "src\n").unwrap();
    fs::write(root.join("src/a.py"), "def hello():\n    return 1\n").unwrap();
    fs::write(root.join("src/b.py"), "from a import hello\n").unwrap();
    let built = update_maps(&root);
    assert_eq!(
        built.get("success").and_then(|v| v.as_bool()),
        Some(true),
        "{built}"
    );
    root
}

fn field<'a>(value: &'a Json, key: &str) -> &'a str {
    value.get(key).and_then(|v| v.as_str()).unwrap_or("")
}

fn mcp_call(root: &Path, name: &str, mut args: Vec<(&str, Json)>) -> Json {
    args.push((
        "project_root",
        Json::String(root.to_string_lossy().into_owned()),
    ));
    let msg = Json::obj(vec![
        ("jsonrpc", Json::String("2.0".into())),
        ("id", Json::Int(7)),
        ("method", Json::String("tools/call".into())),
        (
            "params",
            Json::obj(vec![
                ("name", Json::String(name.into())),
                ("arguments", Json::obj(args)),
            ]),
        ),
    ]);
    let reply = wikifier::mcp::handle_message(&msg).expect("tools/call has an id");
    reply
        .get("result")
        .and_then(|r| r.get("structuredContent"))
        .cloned()
        .unwrap_or_else(|| panic!("no structuredContent: {reply}"))
}

#[test]
fn backslash_and_absolute_file_args_hit_the_mapped_row() {
    let root = mapped_project("sep");
    let recorded = record_change(&root, "src\\a.py", "windows separator (args-1)");
    assert_eq!(field(&recorded, "file"), "src/a.py", "{recorded}");
    let rows: Vec<_> = read_health(&root)
        .into_iter()
        .filter(|row| row.file.ends_with("a.py"))
        .collect();
    assert_eq!(rows.len(), 1, "a second health row appeared: {rows:?}");
    assert_eq!(rows[0].file, "src/a.py");
    assert_eq!(rows[0].reason, "windows separator (args-1)");

    let absolute = root.join("src").join("a.py");
    for arg in [absolute.to_string_lossy().into_owned(), "./src/a.py".into()] {
        let report = prepare_edit(&root, &arg);
        assert_eq!(field(&report, "file"), "src/a.py", "{arg}: {report}");
        assert!(report.to_string().contains("src/b.py"), "{arg}: {report}");
    }
    let importers = load_dependents(&root, "src\\a.py");
    assert!(importers.to_string().contains("src/b.py"), "{importers}");
    let _ = fs::remove_dir_all(root);
}

#[test]
fn lookups_on_a_missing_file_fail_with_a_next_step() {
    let root = mapped_project("missing");
    for value in [
        prepare_edit(&root, "src/nope.py"),
        load_dependents(&root, "src/nope.py"),
        api::dependency_report(&root, "src/nope.py", false),
        api::dispatch(
            "get_file_wiki",
            &root,
            &["src/nope.py".into()],
            &BTreeMap::new(),
        ),
    ] {
        assert_eq!(
            value.get("success").and_then(|v| v.as_bool()),
            Some(false),
            "{value}"
        );
        assert_eq!(field(&value, "error_type"), "FileNotFound", "{value}");
        assert!(field(&value, "error").contains("list_paths"), "{value}");
    }
    let empty = api::dependency_report(&root, "", false);
    assert_eq!(field(&empty, "error_type"), "ValueError", "{empty}");
    let _ = fs::remove_dir_all(root);
}

#[test]
fn mcp_names_the_argument_an_agent_left_out() {
    let root = mapped_project("mcpargs");
    let guessed = mcp_call(
        &root,
        "prepare_edit",
        vec![("file_path", Json::String("src/a.py".into()))],
    );
    assert_eq!(
        field(&guessed, "error_type"),
        "InvalidArguments",
        "{guessed}"
    );
    let text = field(&guessed, "error");
    assert!(text.contains("needs file"), "{text}");
    assert!(text.contains("Received: file_path, project_root"), "{text}");

    let no_reason = mcp_call(
        &root,
        "record_change",
        vec![("file", Json::String("src/a.py".into()))],
    );
    assert!(
        field(&no_reason, "error").contains("needs reason"),
        "{no_reason}"
    );
    assert!(
        wikifier::read_journal(&root, None).is_empty(),
        "a rejected call still wrote the journal"
    );

    let alias = mcp_call(
        &root,
        "search_journal",
        vec![("text", Json::String("anything".into()))],
    );
    assert_eq!(
        alias.get("success").and_then(|v| v.as_bool()),
        Some(true),
        "{alias}"
    );
    let _ = fs::remove_dir_all(root);
}

#[test]
fn mcp_update_maps_leaves_out_the_edge_list_unless_asked() {
    let root = mapped_project("edges");
    let lean = mcp_call(&root, "update_maps", vec![("full", Json::Bool(true))]);
    assert_eq!(
        lean.get("success").and_then(|v| v.as_bool()),
        Some(true),
        "{lean}"
    );
    assert_eq!(
        lean.get("edges_omitted").and_then(|v| v.as_bool()),
        Some(true),
        "{lean}"
    );
    assert_eq!(lean.get("edges_persisted"), Some(&Json::Int(1)), "{lean}");
    assert_eq!(
        lean.get("edges")
            .and_then(|v| v.as_array())
            .map(|a| a.len()),
        Some(0)
    );

    let full = mcp_call(
        &root,
        "update_maps",
        vec![("full", Json::Bool(true)), ("edges", Json::Bool(true))],
    );
    assert_eq!(
        full.get("edges")
            .and_then(|v| v.as_array())
            .map(|a| a.len()),
        Some(1),
        "{full}"
    );
    let _ = fs::remove_dir_all(root);
}

#[test]
fn init_maps_the_directories_that_hold_source() {
    let init = |root: &Path| {
        let value = api::dispatch("init", root, &[], &BTreeMap::new());
        assert_eq!(
            value.get("success").and_then(|v| v.as_bool()),
            Some(true),
            "{value}"
        );
        let text = fs::read_to_string(root.join("map_paths.txt")).unwrap();
        text.lines()
            .filter(|line| !line.starts_with('#') && !line.trim().is_empty())
            .map(|line| line.to_string())
            .collect::<Vec<_>>()
    };

    let workspace = scratch("workspace");
    fs::create_dir_all(workspace.join("crates/core/src")).unwrap();
    fs::write(workspace.join("crates/core/src/lib.rs"), "pub fn f() {}\n").unwrap();
    fs::create_dir_all(workspace.join("tests")).unwrap();
    fs::write(workspace.join("tests/it.rs"), "#[test]\nfn t() {}\n").unwrap();
    fs::create_dir_all(workspace.join("docs")).unwrap();
    fs::write(workspace.join("docs/guide.md"), "# guide\n").unwrap();
    fs::create_dir_all(workspace.join("target/debug")).unwrap();
    fs::write(workspace.join("target/debug/build.rs"), "fn main() {}\n").unwrap();
    assert_eq!(init(&workspace), ["crates/", "tests/"]);
    let built = update_maps(&workspace);
    assert_eq!(
        built.get("success").and_then(|v| v.as_bool()),
        Some(true),
        "{built}"
    );
    let _ = fs::remove_dir_all(workspace);

    let classic = scratch("classic");
    fs::create_dir_all(classic.join("src")).unwrap();
    fs::create_dir_all(classic.join("lib")).unwrap();
    fs::write(classic.join("lib/x.py"), "x = 1\n").unwrap();
    assert_eq!(init(&classic), ["src/"]);
    let _ = fs::remove_dir_all(classic);

    let empty = scratch("empty");
    assert_eq!(init(&empty), ["src/"]);
    let _ = fs::remove_dir_all(empty);
}

#[test]
fn mcp_health_honors_limit_and_summary() {
    let root = mapped_project("health");
    let capped = mcp_call(&root, "health", vec![("limit", Json::Int(1))]);
    assert_eq!(
        capped
            .get("entries")
            .and_then(|v| v.as_array())
            .map(|a| a.len()),
        Some(1),
        "{capped}"
    );
    assert_eq!(capped.get("entries_total"), Some(&Json::Int(2)), "{capped}");

    let counts = mcp_call(&root, "health", vec![("summary", Json::Bool(true))]);
    assert!(counts.get("entries").is_none(), "{counts}");
    assert!(counts.get("health_summary").is_some(), "{counts}");
    let _ = fs::remove_dir_all(root);
}

/// A Windows checkout with `core.autocrlf` turns LF into CRLF. That is not an edit, so a
/// Green file must stay clean.
#[test]
fn crlf_checkout_of_a_green_file_is_not_a_change() {
    let root = mapped_project("crlf");
    fs::write(
        root.join("src/a.py.wiki.md"),
        "# a.py\n\n- `hello()` returns 1.\n",
    )
    .unwrap();
    let green = wikifier::mark_green(&root, "src/a.py", "wiki written (args-2)", false);
    assert_eq!(
        green.get("success").and_then(|v| v.as_bool()),
        Some(true),
        "{green}"
    );
    let lf = fs::read(root.join("src/a.py")).unwrap();
    let mut crlf = Vec::new();
    for byte in lf {
        if byte == b'\n' {
            crlf.push(b'\r');
        }
        crlf.push(byte);
    }
    fs::write(root.join("src/a.py"), crlf).unwrap();
    let checked = wikifier::check_changes(&root);
    assert_eq!(
        checked.get("changes_detected"),
        Some(&Json::Int(0)),
        "{checked}"
    );
    let row = read_health(&root)
        .into_iter()
        .find(|row| row.file == "src/a.py")
        .unwrap();
    assert!(row.status.contains("Green"), "{row:?}");
    let _ = fs::remove_dir_all(root);
}
