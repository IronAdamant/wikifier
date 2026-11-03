//! Behaviour the review found untested: MCP deadline, check-changes cap,
//! sqlite cache import, and actionable low-confidence edges.

use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use wikifier::cache::indexed_rows;
use wikifier::jsonutil::{parse, Json};
use wikifier::mcp;
use wikifier::{load_dependencies, session_bootstrap, update_maps};

fn scratch(name: &str) -> PathBuf {
    let n = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
    let dir = std::env::temp_dir().join(format!("wk-gap-{name}-{n}"));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(dir.join("src")).unwrap();
    std::fs::write(dir.join("map_paths.txt"), "src\n").unwrap();
    std::fs::write(dir.join("monitored_paths.txt"), "src\n").unwrap();
    dir
}

fn json_text(value: &Json) -> String {
    value.to_string()
}

fn mcp_call(bin: &str, deadline: Option<&str>, body: &str) -> (Json, Duration) {
    let mut cmd = Command::new(bin);
    cmd.arg("mcp").stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::null());
    match deadline {
        Some(value) => {
            cmd.env("WIKIFIER_MCP_DEADLINE_S", value);
        }
        None => {
            cmd.env_remove("WIKIFIER_MCP_DEADLINE_S");
        }
    }
    let mut child = cmd.spawn().unwrap();
    let mut stdin = child.stdin.take().unwrap();
    let stdout = child.stdout.take().unwrap();
    let started = Instant::now();
    writeln!(stdin, "{body}").unwrap();
    let mut line = String::new();
    BufReader::new(stdout).read_line(&mut line).unwrap();
    let elapsed = started.elapsed();
    let _ = child.kill();
    let _ = child.wait();
    let parsed = parse(line.trim()).unwrap_or_else(|err| panic!("mcp json {err}: {line}"));
    (parsed, elapsed)
}

fn tool_body(root: &std::path::Path, name: &str) -> String {
    let root_text = root.to_str().unwrap().replace('\\', "\\\\").replace('"', "\\\"");
    format!(
        r#"{{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{{"name":"{name}","arguments":{{"project_root":"{root_text}"}}}}}}"#
    )
}

fn structured(message: &Json) -> &Json {
    message.get("result").and_then(|result| result.get("structuredContent")).unwrap_or_else(|| panic!("no structured content in {message}"))
}

#[test]
fn mcp_deadline_stops_a_blocking_call_and_lets_a_fast_call_finish() {
    let root = scratch("deadline");
    std::fs::write(root.join("src/a.py"), "x = 1\n").unwrap();
    let bin = env!("CARGO_BIN_EXE_wikifier");

    let (fast, fast_elapsed) = mcp_call(bin, Some("1"), &tool_body(&root, "health"));
    let fast_body = structured(&fast);
    assert_eq!(fast_body.get("success").and_then(|flag| flag.as_bool()), Some(true), "{fast}");
    assert!(fast_elapsed < Duration::from_secs(1), "health took {fast_elapsed:?}");

    let (slow, slow_elapsed) = mcp_call(bin, Some("1"), &tool_body(&root, "monitor"));
    let slow_body = structured(&slow);
    assert_eq!(slow_body.get("success").and_then(|flag| flag.as_bool()), Some(false), "{slow}");
    assert_eq!(slow_body.get("error_type").and_then(|flag| flag.as_str()), Some("DeadlineExceeded"), "{slow}");
    assert_eq!(slow_body.get("timed_out").and_then(|flag| flag.as_bool()), Some(true), "{slow}");
    assert_eq!(slow_body.get("may_still_complete").and_then(|flag| flag.as_bool()), Some(true), "{slow}");
    assert!(slow_body.get("error").and_then(|flag| flag.as_str()).unwrap_or("").contains("WIKIFIER_MCP_DEADLINE_S") || slow_body.to_string().contains("deadline"), "{slow}");
    assert!(slow_elapsed >= Duration::from_millis(700), "deadline 1 returned in {slow_elapsed:?}");
    assert!(slow_elapsed < Duration::from_secs(8), "deadline 1 hung for {slow_elapsed:?}");
    assert_eq!(fast.get("result").and_then(|result| result.get("isError")).and_then(|flag| flag.as_bool()), Some(false), "{fast}");
    assert_eq!(slow.get("result").and_then(|result| result.get("isError")).and_then(|flag| flag.as_bool()), Some(true), "{slow}");

    let (zero, zero_elapsed) = mcp_call(bin, Some("0"), &tool_body(&root, "monitor"));
    let zero_body = structured(&zero);
    assert_eq!(zero_body.get("timed_out").and_then(|flag| flag.as_bool()), Some(true), "{zero}");
    assert!(zero_elapsed >= Duration::from_millis(700), "deadline 0 was not raised to 1s ({zero_elapsed:?})");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn check_changes_cap_stops_the_pass_and_names_the_env_var() {
    let root = scratch("cap");
    for name in ["a.py", "b.py", "c.py"] {
        std::fs::write(root.join("src").join(name), format!("{name} = 1\n")).unwrap();
    }
    let mapped = update_maps(&root);
    assert_eq!(mapped.get("success").and_then(|flag| flag.as_bool()), Some(true), "{mapped}");
    let bin = env!("CARGO_BIN_EXE_wikifier");

    let capped = Command::new(bin)
        .args(["--target", root.to_str().unwrap(), "check-changes"])
        .env("WIKIFIER_CHECK_CHANGES_MAX", "1")
        .output()
        .unwrap();
    let capped_json = parse(&String::from_utf8(capped.stdout.clone()).unwrap()).unwrap_or_else(|err| panic!("{err}: {}", String::from_utf8_lossy(&capped.stdout)));
    assert_eq!(capped_json.get("success").and_then(|flag| flag.as_bool()), Some(true), "{capped_json}");
    assert_eq!(capped_json.get("truncated").and_then(|flag| flag.as_bool()), Some(true), "{capped_json}");
    assert!(json_text(&capped_json).contains("WIKIFIER_CHECK_CHANGES_MAX"), "{capped_json}");
    assert!(json_text(&capped_json).contains("stopped at 1 files"), "{capped_json}");

    let open = Command::new(bin)
        .args(["--target", root.to_str().unwrap(), "check-changes"])
        .env("WIKIFIER_CHECK_CHANGES_MAX", "50")
        .output()
        .unwrap();
    let open_json = parse(&String::from_utf8(open.stdout).unwrap()).unwrap();
    assert_eq!(open_json.get("truncated"), None, "{open_json}");

    let ignored = Command::new(bin)
        .args(["--target", root.to_str().unwrap(), "check-changes"])
        .env("WIKIFIER_CHECK_CHANGES_MAX", "nope")
        .output()
        .unwrap();
    let ignored_json = parse(&String::from_utf8(ignored.stdout).unwrap()).unwrap();
    assert_eq!(ignored_json.get("truncated"), None, "a non-numeric cap must stay at the default: {ignored_json}");
    let _ = std::fs::remove_dir_all(&root);
}

fn sqlite3_available() -> bool {
    Command::new("sqlite3").arg("-version").output().map(|out| out.status.success()).unwrap_or(false)
}

#[test]
fn sqlite_import_fills_an_empty_cache_and_reports_an_unreadable_file() {
    let broken = scratch("sqlite-bad");
    std::fs::create_dir_all(broken.join(".wikifier_staging")).unwrap();
    std::fs::write(broken.join(".wikifier_staging/import_cache.sqlite"), b"not a sqlite database").unwrap();
    std::fs::write(broken.join("src/a.py"), "x = 1\n").unwrap();
    let boot = session_bootstrap(&broken);
    assert_eq!(boot.get("success").and_then(|flag| flag.as_bool()), Some(true), "{boot}");
    let warnings = json_text(boot.get("warnings").unwrap_or(&Json::Null));
    assert!(warnings.contains("sqlite_present_unread"), "{boot}");
    let _ = std::fs::remove_dir_all(&broken);
    if !sqlite3_available() {
        eprintln!("sqlite3 CLI is not on PATH; the import assertions run where the CLI is installed");
        return;
    }

    let root = scratch("sqlite");
    std::fs::create_dir_all(root.join(".wikifier_staging")).unwrap();
    std::fs::write(root.join("src/a.py"), "x = 1\n").unwrap();
    std::fs::write(root.join("src/b.py"), "y = 2\n").unwrap();
    let db = root.join(".wikifier_staging/import_cache.sqlite");
    let created = Command::new("sqlite3")
        .arg(&db)
        .arg("CREATE TABLE files (rel_path TEXT); CREATE TABLE edges (src TEXT, dst TEXT); INSERT INTO files VALUES ('src/a.py'); INSERT INTO files VALUES ('src/b.py'); INSERT INTO edges VALUES ('src/a.py', 'src/b.py');")
        .status()
        .unwrap_or_else(|err| panic!("sqlite3 CLI is required for this test: {err}"));
    assert!(created.success(), "sqlite3 could not create the cache");

    let deps = load_dependencies(&root, "src/a.py");
    assert_eq!(deps.get("success").and_then(|flag| flag.as_bool()), Some(true), "{deps}");
    let internal = deps.get("internal").and_then(|item| item.as_array()).unwrap_or(&[]);
    assert!(internal.iter().any(|edge| edge.get("path").and_then(|path| path.as_str()) == Some("src/b.py")), "{deps}");
    let rows = indexed_rows(&root);
    assert!(rows.iter().any(|row| row.0 == "src/a.py" && row.3 == "sha256:legacy" && row.1 == 0), "{rows:?}");

    let extra = Command::new("sqlite3")
        .arg(&db)
        .arg("INSERT INTO edges VALUES ('src/a.py', 'src/c.py');")
        .status()
        .unwrap();
    assert!(extra.success());
    let again = load_dependencies(&root, "src/a.py");
    let paths: Vec<_> = again.get("internal").and_then(|item| item.as_array()).unwrap_or(&[]).iter().filter_map(|edge| edge.get("path").and_then(|path| path.as_str())).collect();
    assert_eq!(paths, ["src/b.py"], "a filled cache must ignore a later sqlite file: {again}");

    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn actionable_low_conf_edges_keep_conditional_and_drop_dynamic() {
    let root = scratch("low");
    std::fs::create_dir_all(root.join("src/pkg")).unwrap();
    std::fs::write(root.join("src/pkg/__init__.py"), "").unwrap();
    std::fs::write(root.join("src/pkg/b.py"), "VALUE = 1\n").unwrap();
    std::fs::write(root.join("src/pkg/c.py"), "VALUE = 2\n").unwrap();
    std::fs::write(root.join("src/pkg/d.py"), "VALUE = 3\n").unwrap();
    std::fs::write(
        root.join("src/pkg/a.py"),
        "from . import b\n\ndef load():\n    from . import c\n    import importlib\n    return importlib.import_module('pkg.d')\n",
    ).unwrap();
    let mapped = update_maps(&root);
    assert_eq!(mapped.get("success").and_then(|flag| flag.as_bool()), Some(true), "{mapped}");

    let root_text = root.to_str().unwrap().replace('\\', "\\\\").replace('"', "\\\"");
    let raw = format!(
        r#"{{"jsonrpc":"2.0","id":7,"method":"tools/call","params":{{"name":"get_resolution_diagnostics","arguments":{{"project_root":"{root_text}"}}}}}}"#
    );
    let message = mcp::handle_message(&parse(&raw).unwrap()).unwrap();
    let body = structured(&message);
    assert_eq!(body.get("success").and_then(|flag| flag.as_bool()), Some(true), "{body}");
    let low = body.get("actionable_low_conf_edges").and_then(|item| item.as_array()).unwrap_or(&[]);
    assert!(low.iter().any(|edge| {
        edge.get("file").and_then(|value| value.as_str()) == Some("src/pkg/a.py")
            && edge.get("path").and_then(|value| value.as_str()) == Some("src/pkg/c.py")
            && edge.get("reason").and_then(|value| value.as_str()) == Some("conditional_guard")
            && matches!(edge.get("confidence"), Some(Json::Float(n)) if (*n - 0.55).abs() < 0.001)
    }), "{body}");
    assert!(low.iter().all(|edge| edge.get("path").and_then(|value| value.as_str()) != Some("src/pkg/b.py")), "static edge was treated as low confidence: {body}");
    assert!(low.iter().all(|edge| edge.get("reason").and_then(|value| value.as_str()) != Some("dynamic_literal")), "dynamic edges are noise, not actionable: {body}");
    let counts = body.get("reason_code_counts").unwrap_or(&Json::Null);
    assert!(counts.get("conditional_guard").is_some(), "{counts}");
    assert!(counts.get("dynamic_literal").is_some(), "{counts}");
    let _ = std::fs::remove_dir_all(&root);
}
