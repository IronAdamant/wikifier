//! The shipped binary is the entry point: version, two stable bootstraps, MCP tool names.

use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::time::{SystemTime, UNIX_EPOCH};

fn bin() -> PathBuf {
    PathBuf::from(env!("CARGO_BIN_EXE_wikifier"))
}

fn project() -> PathBuf {
    let n = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
    let root = std::env::temp_dir().join(format!("wk-cli-{n}"));
    std::fs::create_dir_all(root.join("src")).unwrap();
    std::fs::write(root.join("map_paths.txt"), "src\n").unwrap();
    std::fs::write(root.join("monitored_paths.txt"), "src\n").unwrap();
    std::fs::write(root.join("src/a.py"), "def hello():\n    return 1\n").unwrap();
    std::fs::write(root.join("src/b.py"), "from .a import hello\n").unwrap();
    // b.py is not in a package (no __init__). Still a mapped file.
    root
}

#[test]
fn version_matches_package() {
    let out = Command::new(bin()).arg("--version").output().unwrap();
    assert!(out.status.success());
    assert_eq!(String::from_utf8_lossy(&out.stdout).trim(), format!("wikifier {}", env!("CARGO_PKG_VERSION")));
}

#[test]
fn two_bootstraps_agree() {
    let root = project();
    let run = || {
        let out = Command::new(bin())
            .args(["--target", root.to_str().unwrap(), "session-bootstrap"])
            .output()
            .unwrap();
        assert!(out.status.success(), "stderr {}", String::from_utf8_lossy(&out.stderr));
        String::from_utf8(out.stdout).unwrap()
    };
    let first = run();
    let second = run();
    assert_eq!(first, second, "bootstrap was not stable across two runs");
    assert!(first.contains("\"success\":true"), "{first}");
    assert!(first.contains("\"readiness\":"), "{first}");
    assert!(first.contains("\"health_summary\":"), "{first}");
    assert!(first.contains("\"actions\":"), "{first}");
    assert!(first.contains("src/a.py"), "{first}");
    let _ = std::fs::remove_dir_all(root);
}

#[test]
fn mcp_stdio_is_newline_delimited_json() {
    let root = project();
    let mut child = Command::new(bin())
        .arg("mcp")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    let mut stdin = child.stdin.take().unwrap();
    let stdout = child.stdout.take().unwrap();
    let mut lines = BufReader::new(stdout);
    let mut send = |payload: &str| {
        writeln!(stdin, "{payload}").unwrap();
        stdin.flush().unwrap();
    };
    let mut recv = || {
        let mut line = String::new();
        lines.read_line(&mut line).unwrap();
        assert!(!line.to_ascii_lowercase().contains("content-length"), "{line}");
        assert!(line.ends_with('\n'), "reply was not one JSON line: {line:?}");
        parse_line(&line)
    };

    send(r#"{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}"#);
    let init = recv();
    assert_eq!(init.get("id").and_then(|v| match v { wikifier::Json::Int(n) => Some(*n), _ => None }), Some(1), "{init}");
    assert_eq!(init.get("result").and_then(|v| v.get("protocolVersion")).and_then(|v| v.as_str()), Some("2024-11-05"), "{init}");

    send(r#"{"jsonrpc":"2.0","id":2,"method":"tools/list"}"#);
    let listed = recv();
    let tools = listed.get("result").and_then(|v| v.get("tools")).and_then(|v| v.as_array()).unwrap_or_else(|| panic!("{listed}"));
    assert_eq!(tools.len(), wikifier::api::MCP_TOOLS.len());
    for tool in tools {
        let name = tool.get("name").and_then(|v| v.as_str()).unwrap_or("");
        let description = tool.get("description").and_then(|v| v.as_str()).unwrap_or("");
        assert!(description.len() > 40, "{name} description {description}");
        assert!(!description.starts_with("Wikifier "), "{name} still has a placeholder description");
        let required = tool.get("inputSchema").and_then(|v| v.get("required")).and_then(|v| v.as_array()).unwrap_or_else(|| panic!("{name} schema {tool}"));
        assert!(required.iter().any(|v| v.as_str() == Some("project_root")), "{name} required {required:?}");
    }

    let root_text = root.to_str().unwrap().replace('\\', "\\\\").replace('"', "\\\"");
    send(&format!(
        r#"{{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{{"name":"get_current_project_root","arguments":{{"project_root":"{root_text}"}}}}}}"#
    ));
    let called = recv();
    let text = called.to_string();
    assert!(text.contains("\"success\":true"), "{called}");
    assert!(text.contains(&root.file_name().unwrap().to_string_lossy().to_string()), "{called}");
    drop(stdin);
    let status = child.wait().unwrap();
    assert!(status.success(), "mcp exit {status}");
    let _ = std::fs::remove_dir_all(root);
}

fn parse_line(line: &str) -> wikifier::Json {
    wikifier::jsonutil::parse(line.trim()).unwrap_or_else(|err| panic!("stdio json {err}: {line}"))
}
