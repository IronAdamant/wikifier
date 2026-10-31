//! The shipped binary is the entry point: version, two stable bootstraps, MCP tool names.

use std::io::{Read, Write};
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
fn mcp_lists_contract_tools() {
    let mut child = Command::new(bin())
        .arg("mcp")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .unwrap();
    let mut stdin = child.stdin.take().unwrap();
    let req = r#"{"jsonrpc":"2.0","id":1,"method":"tools/list"}"#;
    write!(stdin, "Content-Length: {}\r\n\r\n{req}", req.len()).unwrap();
    drop(stdin);
    let mut stdout = child.stdout.take().unwrap();
    let mut buf = String::new();
    stdout.read_to_string(&mut buf).unwrap();
    let _ = child.wait();
    for name in wikifier::api::MCP_TOOLS {
        assert!(buf.contains(&format!("\"name\":\"{name}\"")), "missing tool {name}\n{buf}");
    }
    assert!(buf.contains("\"success\":") || buf.contains("tools"), "{buf}");
}
