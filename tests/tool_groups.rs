//! WIKIFIER_TOOLS / WIKIFIER_DISABLE, per the suite's tool-group convention. Each case
//! runs the real `wikifier mcp` with its own environment.

use std::collections::BTreeSet;
use std::io::Write;
use std::path::PathBuf;
use std::process::{Command, Output, Stdio};

use wikifier::api::MCP_TOOLS;
use wikifier::jsonutil::{self, Json};
use wikifier::mcp_groups::{group_of, Selection, GROUPS};

fn bin() -> PathBuf {
    PathBuf::from(env!("CARGO_BIN_EXE_wikifier"))
}

/// An empty project directory, so this repository's own AGENTS.md is not read.
fn project(name: &str) -> PathBuf {
    let n = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let dir = std::env::temp_dir().join(format!("wk-groups-{name}-{n}-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

/// Send `lines` to `wikifier mcp` with `env` set (and both switches cleared otherwise).
fn mcp(env: &[(&str, &str)], lines: &[&str]) -> Output {
    mcp_in(&project("env"), env, lines)
}

fn server(dir: &std::path::Path, env: &[(&str, &str)]) -> Command {
    let mut cmd = Command::new(bin());
    cmd.arg("mcp")
        .current_dir(dir)
        .env_remove("WIKIFIER_PROJECT_ROOT")
        .env_remove("WIKIFIER_TOOLS")
        .env_remove("WIKIFIER_DISABLE")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    for (key, value) in env {
        cmd.env(key, value);
    }
    cmd
}

/// Run `wikifier mcp` in `dir` (its project root) and send `lines`.
fn mcp_in(dir: &std::path::Path, env: &[(&str, &str)], lines: &[&str]) -> Output {
    let mut cmd = server(dir, env);
    let mut child = cmd.spawn().unwrap();
    {
        let mut stdin = child.stdin.take().unwrap();
        for line in lines {
            // A server that refused its switches has already exited (exit 2); writing to
            // it then fails with a broken pipe on Unix, and the exit status is what counts.
            if writeln!(stdin, "{line}").is_err() {
                break;
            }
        }
    }
    child.wait_with_output().unwrap()
}

const LIST: &str = r#"{"jsonrpc":"2.0","id":1,"method":"tools/list"}"#;
const INIT: &str = r#"{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}"#;

fn replies(out: &Output) -> Vec<Json> {
    String::from_utf8_lossy(&out.stdout)
        .lines()
        .map(|line| jsonutil::parse(line).unwrap())
        .collect()
}

fn listed(env: &[(&str, &str)]) -> Vec<String> {
    let out = mcp(env, &[LIST]);
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    replies(&out)[0]
        .get("result")
        .and_then(|r| r.get("tools"))
        .and_then(|t| t.as_array())
        .unwrap()
        .iter()
        .map(|tool| {
            tool.get("name")
                .and_then(|n| n.as_str())
                .unwrap()
                .to_string()
        })
        .collect()
}

fn tools_in(groups: &[&str]) -> Vec<String> {
    MCP_TOOLS
        .iter()
        .filter(|tool| groups.contains(&group_of(tool).unwrap()))
        .map(|tool| tool.to_string())
        .collect()
}

#[test]
fn every_tool_is_in_exactly_one_group() {
    let mut seen = BTreeSet::new();
    for (_, tools) in GROUPS {
        for tool in *tools {
            assert!(MCP_TOOLS.contains(tool), "{tool} is not an MCP tool");
            assert!(seen.insert(*tool), "{tool} is in two groups");
        }
    }
    assert_eq!(seen.len(), MCP_TOOLS.len());
}

#[test]
fn the_default_listing_is_unchanged() {
    let out = mcp(&[], &[INIT, LIST]);
    let lines: Vec<String> = String::from_utf8_lossy(&out.stdout)
        .lines()
        .map(|l| l.to_string())
        .collect();
    let expected = Json::obj(vec![
        ("jsonrpc", Json::String("2.0".into())),
        ("id", Json::Int(1)),
        (
            "result",
            Json::obj(vec![(
                "tools",
                Json::Array(
                    MCP_TOOLS
                        .iter()
                        .map(|n| wikifier::mcp::tool_schema(n))
                        .collect(),
                ),
            )]),
        ),
    ]);
    assert_eq!(lines[1], expected.to_string());
    assert!(!lines[0].contains("instructions"), "{}", lines[0]);
    // An empty variable is the same as an unset one.
    assert_eq!(
        listed(&[("WIKIFIER_TOOLS", " "), ("WIKIFIER_DISABLE", "")]).len(),
        MCP_TOOLS.len()
    );
}

#[test]
fn tools_and_disable_filter_by_group_and_by_tool_name() {
    assert_eq!(
        listed(&[("WIKIFIER_TOOLS", " Core , NOTES ")]),
        tools_in(&["core", "notes"])
    );
    let mut core_and_cycles = tools_in(&["core"]);
    core_and_cycles.push("get_cycles".into());
    let core_and_cycles: BTreeSet<String> = core_and_cycles.into_iter().collect();
    let got: BTreeSet<String> = listed(&[("WIKIFIER_TOOLS", "get_cycles")])
        .into_iter()
        .collect();
    assert_eq!(got, core_and_cycles);
    assert_eq!(
        listed(&[("WIKIFIER_DISABLE", "map,cycles,status")]),
        tools_in(&["core", "notes", "health"])
    );
    let without = listed(&[("WIKIFIER_DISABLE", "journal")]);
    assert_eq!(without.len(), MCP_TOOLS.len() - 1);
    assert!(!without.contains(&"journal".to_string()));
    // _DISABLE applies after _TOOLS.
    let both = listed(&[("WIKIFIER_TOOLS", "all"), ("WIKIFIER_DISABLE", "notes")]);
    assert_eq!(
        both,
        tools_in(&["core", "health", "map", "cycles", "status"])
    );
}

#[test]
fn a_disabled_tool_answers_with_the_switch_to_change() {
    let call = |name: &str| {
        format!(
            r#"{{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{{"name":"{name}","arguments":{{}}}}}}"#
        )
    };
    let error_of = |env: &[(&str, &str)], name: &str| {
        let reply = &replies(&mcp(env, &[&call(name)]))[0];
        let result = reply.get("result").unwrap();
        assert_eq!(result.get("isError"), Some(&Json::Bool(true)), "{reply}");
        result
            .get("structuredContent")
            .and_then(|v| v.get("error"))
            .and_then(|v| v.as_str())
            .unwrap()
            .to_string()
    };
    assert_eq!(
        error_of(&[("WIKIFIER_DISABLE", "notes")], "record_change"),
        r#"tool "record_change" is disabled (group "notes") by WIKIFIER_DISABLE; remove "notes" from it to enable"#
    );
    assert_eq!(
        error_of(&[("WIKIFIER_TOOLS", "core")], "get_cycles"),
        r#"tool "get_cycles" is disabled (group "cycles") by WIKIFIER_TOOLS; add "cycles" to it to enable"#
    );
}

#[test]
fn an_unknown_name_stops_the_server_with_exit_code_2() {
    let out = mcp(&[("WIKIFIER_DISABLE", "lokcs")], &[LIST]);
    assert_eq!(out.status.code(), Some(2));
    assert!(out.stdout.is_empty());
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert_eq!(stderr.lines().count(), 1, "{stderr}");
    assert!(
        stderr.starts_with(
            r#"WIKIFIER_DISABLE: unknown group "lokcs"; groups: core, notes, health, map, cycles, status; tools: check_changes,"#
        ),
        "{stderr}"
    );
    let out = mcp(&[("WIKIFIER_TOOLS", "core,mpa")], &[LIST]);
    assert_eq!(out.status.code(), Some(2));
    assert!(
        String::from_utf8_lossy(&out.stderr).starts_with(r#"WIKIFIER_TOOLS: unknown group "mpa""#)
    );
    // `all` is only an allowlist word.
    assert_eq!(
        mcp(&[("WIKIFIER_DISABLE", "all")], &[LIST]).status.code(),
        Some(2)
    );
}

#[test]
fn core_cannot_be_disabled() {
    for name in ["core", "Session_Bootstrap", "notes, update_maps"] {
        let out = mcp(&[("WIKIFIER_DISABLE", name)], &[LIST]);
        assert_eq!(out.status.code(), Some(2), "{name}");
        assert!(out.stdout.is_empty());
        let stderr = String::from_utf8_lossy(&out.stderr);
        assert_eq!(stderr.lines().count(), 1, "{stderr}");
        assert!(
            stderr.starts_with("WIKIFIER_DISABLE: \"")
                && stderr.contains("\" cannot be disabled, group \"core\" is always on; groups: core, notes, health, map, cycles, status"),
            "{stderr}"
        );
    }
    // An allowlist without core still keeps core.
    assert_eq!(listed(&[("WIKIFIER_TOOLS", "cycles")]), {
        let mut tools = tools_in(&["core", "cycles"]);
        tools.sort_by_key(|t| MCP_TOOLS.iter().position(|m| m == t));
        tools
    });
}

#[test]
fn default_initialize_and_tools_list_match_the_last_release() {
    // The same two requests the fixture was recorded with, from the 5.1.0 release binary.
    let list = r#"{"jsonrpc":"2.0","id":2,"method":"tools/list"}"#;
    let out = mcp(&[], &[INIT, list]);
    let golden = golden();
    assert_eq!(String::from_utf8_lossy(&out.stdout), golden);
}

#[test]
fn initialize_and_list_core_tools_name_the_active_groups() {
    let call = r#"{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"list_core_tools","arguments":{"project_root":"."}}}"#;
    let out = mcp(&[("WIKIFIER_DISABLE", "map,cycles")], &[INIT, call]);
    let got = replies(&out);
    let line = "Wikifier tool groups on: core, notes, health, status; off: map, cycles. Change them with a \"wikifier: tools ...\" or \"wikifier: disable ...\" line in the agent-tools block of AGENTS.md (WIKIFIER_TOOLS / WIKIFIER_DISABLE override it).";
    assert_eq!(
        got[0]
            .get("result")
            .and_then(|r| r.get("instructions"))
            .and_then(|v| v.as_str()),
        Some(line)
    );
    let listed = got[1]
        .get("result")
        .and_then(|r| r.get("structuredContent"))
        .unwrap();
    assert_eq!(listed.get("groups").and_then(|v| v.as_str()), Some(line));
    let tools = listed.get("tools").and_then(|v| v.as_array()).unwrap();
    assert_eq!(tools.len(), MCP_TOOLS.len() - 4);
    assert!(!tools.iter().any(|t| t.as_str() == Some("get_cycles")));
}

#[test]
fn the_cli_ignores_the_switches() {
    let out = Command::new(bin())
        .arg("list-core-tools")
        .env("WIKIFIER_TOOLS", "core")
        .output()
        .unwrap();
    assert!(out.status.success());
    let text = String::from_utf8_lossy(&out.stdout);
    assert!(
        text.contains("get_cycles") && !text.contains("\"groups\""),
        "{text}"
    );
    // Selection itself: the parse used by the server.
    assert!(Selection::parse(None, None).unwrap().allows("get_cycles"));
    assert!(!Selection::parse(Some("core"), None)
        .unwrap()
        .allows("get_cycles"));
}

fn write_agents(dir: &std::path::Path, block: &str) {
    let text = format!(
        "# Agents\n\nNotes for agents.\n\n```agent-tools\n{block}\n```\n\n```agent-tools\nwikifier: disable notes\n```\n"
    );
    std::fs::write(dir.join("AGENTS.md"), text).unwrap();
}

fn names_of(reply: &Json) -> Vec<String> {
    reply
        .get("result")
        .and_then(|r| r.get("tools"))
        .and_then(|t| t.as_array())
        .unwrap()
        .iter()
        .map(|tool| {
            tool.get("name")
                .and_then(|n| n.as_str())
                .unwrap()
                .to_string()
        })
        .collect()
}

fn instructions_of(reply: &Json) -> String {
    reply
        .get("result")
        .and_then(|r| r.get("instructions"))
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string()
}

#[test]
fn the_agents_md_block_chooses_the_groups() {
    let dir = project("block");
    // Only the first agent-tools block counts; other tools' lines and comments are skipped.
    write_agents(
        &dir,
        "# one agent works here\ntrammel: disable locks, notes\nwikifier: disable map cycles\nchisel: tools core",
    );
    let got = replies(&mcp_in(&dir, &[], &[INIT, LIST]));
    let init = got[0].get("result").unwrap();
    assert_eq!(
        init.get("capabilities")
            .and_then(|c| c.get("tools"))
            .and_then(|t| t.get("listChanged")),
        Some(&Json::Bool(true))
    );
    assert!(instructions_of(&got[0])
        .starts_with("Wikifier tool groups on: core, notes, health, status; off: map, cycles."));
    assert_eq!(
        names_of(&got[1]),
        tools_in(&["core", "notes", "health", "status"])
    );

    let call = r#"{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"get_cycles","arguments":{}}}"#;
    let refused = &replies(&mcp_in(&dir, &[], &[call]))[0];
    assert_eq!(
        refused
            .get("result")
            .and_then(|r| r.get("structuredContent"))
            .and_then(|v| v.get("error"))
            .and_then(|v| v.as_str()),
        Some(
            r#"tool "get_cycles" is disabled (group "cycles") by AGENTS.md agent-tools; remove "cycles" from the "wikifier: disable" line to enable"#
        )
    );
}

#[test]
fn the_environment_wins_per_key() {
    let dir = project("precedence");
    write_agents(
        &dir,
        "wikifier: tools core, notes, cycles\nwikifier: disable cycles",
    );
    // WIKIFIER_DISABLE replaces the block's disable line; its tools line still applies.
    let got = replies(&mcp_in(&dir, &[("WIKIFIER_DISABLE", "notes")], &[LIST]));
    assert_eq!(names_of(&got[0]), tools_in(&["core", "cycles"]));
    // WIKIFIER_TOOLS replaces the tools line; the block's disable line still applies.
    let got = replies(&mcp_in(&dir, &[("WIKIFIER_TOOLS", "all")], &[LIST]));
    assert_eq!(
        names_of(&got[0]),
        tools_in(&["core", "notes", "health", "map", "status"])
    );
}

#[test]
fn block_mistakes_are_warnings_not_failures() {
    let dir = project("warn");
    write_agents(
        &dir,
        "wikifier: disable lokcs\nwikifier: tools core, health\nwikifier: color blue",
    );
    let out = mcp_in(&dir, &[], &[INIT, LIST]);
    assert!(out.status.success());
    let got = replies(&out);
    let text = instructions_of(&got[0]);
    let lines: Vec<&str> = text.lines().collect();
    assert_eq!(lines.len(), 3, "{text}");
    assert_eq!(
        lines[0],
        r#"AGENTS.md agent-tools: unknown key "color" for wikifier; write "wikifier: tools <groups>" or "wikifier: disable <groups>""#
    );
    assert_eq!(
        lines[1],
        r#"AGENTS.md agent-tools: unknown group "lokcs" for wikifier; groups: core, notes, health, map, cycles, status"#
    );
    assert!(lines[2].starts_with("Wikifier tool groups on: core, health;"));
    // The bad disable line is ignored; the good tools line still applies.
    assert_eq!(names_of(&got[1]), tools_in(&["core", "health"]));

    write_agents(&dir, "wikifier: disable core");
    let got = replies(&mcp_in(&dir, &[], &[INIT, LIST]));
    assert!(instructions_of(&got[0]).starts_with(
        r#"AGENTS.md agent-tools: "core" cannot be disabled for wikifier, group "core" is always on; groups:"#
    ));
    assert_eq!(names_of(&got[1]).len(), MCP_TOOLS.len());
}

#[test]
fn no_block_leaves_every_reply_as_before() {
    let dir = project("noblock");
    let list = r#"{"jsonrpc":"2.0","id":2,"method":"tools/list"}"#;
    let bare = mcp_in(&dir, &[], &[INIT, list]).stdout;
    std::fs::write(
        dir.join("AGENTS.md"),
        "# Agents\n\n```text\nwikifier: disable notes\n```\n\n````markdown\n```agent-tools\nwikifier: disable notes\n```\n````\n",
    )
    .unwrap();
    assert_eq!(mcp_in(&dir, &[], &[INIT, list]).stdout, bare);
    let golden = golden();
    assert_eq!(String::from_utf8_lossy(&bare), golden);
}

#[test]
fn editing_the_block_mid_session_sends_list_changed() {
    use std::io::{BufRead, BufReader};
    let dir = project("live");
    write_agents(&dir, "wikifier: disable map");
    let mut child = server(&dir, &[]).spawn().unwrap();
    let mut stdin = child.stdin.take().unwrap();
    let mut stdout = BufReader::new(child.stdout.take().unwrap());
    let mut send = |line: &str| {
        writeln!(stdin, "{line}").unwrap();
        stdin.flush().unwrap();
    };
    let mut recv = || {
        let mut line = String::new();
        stdout.read_line(&mut line).unwrap();
        jsonutil::parse(line.trim()).unwrap()
    };
    send(INIT);
    recv();
    send(LIST);
    assert_eq!(names_of(&recv()).len(), MCP_TOOLS.len() - 3);

    write_agents(&dir, "wikifier: disable map, cycles, status");
    send(LIST);
    let notice = recv();
    assert_eq!(
        notice.get("method").and_then(|m| m.as_str()),
        Some("notifications/tools/list_changed"),
        "{notice}"
    );
    assert!(notice.get("id").is_none());
    assert_eq!(names_of(&recv()), tools_in(&["core", "notes", "health"]));

    // A change that leaves the tool list as it is sends no notification.
    write_agents(
        &dir,
        "wikifier: disable status, map , cycles   # same groups",
    );
    send(LIST);
    let reply = recv();
    assert_eq!(reply.get("id"), Some(&Json::Int(1)), "{reply}");
    drop(stdin);
    child.wait().unwrap();
}

#[test]
fn the_parser_reads_only_the_first_agent_tools_fence() {
    use wikifier::mcp_groups::AgentTools;
    let parsed = AgentTools::parse(
        "````markdown\n```agent-tools\nwikifier: disable notes\n```\n````\n\n~~~agent-tools\nWikifier: tools core, health\nwikifier: disable cycles # off\nwikifier: disable status\n~~~\n```agent-tools\nwikifier: disable map\n```\n",
    );
    assert!(parsed.found);
    assert_eq!(parsed.tools.as_deref(), Some("core,health"));
    assert_eq!(parsed.disable.as_deref(), Some("cycles,status"));
    assert!(parsed.warnings.is_empty());
    assert_eq!(AgentTools::parse("no block here"), AgentTools::default());
}

/// What 5.1.0 answered to `initialize` and `tools/list`, with this version's number and the
/// one field the convention adds to every server: `capabilities.tools.listChanged`.
fn golden() -> String {
    std::fs::read_to_string(
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/mcp_default_5.1.0.jsonl"),
    )
    .unwrap()
    .replace("\r\n", "\n")
    .replace(
        r#""version":"5.1.0""#,
        &format!(r#""version":"{}""#, env!("CARGO_PKG_VERSION")),
    )
    .replacen(r#""tools":{}"#, r#""tools":{"listChanged":true}"#, 1)
}

/// This repository dogfoods its own MCP server. Its AGENTS.md documents the block, and those
/// examples must switch nothing: the repo keeps every tool.
#[test]
fn this_repos_agents_md_examples_switch_nothing() {
    use wikifier::mcp_groups::AgentTools;
    let here = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let text = std::fs::read_to_string(here.join("AGENTS.md")).unwrap();
    assert!(text.contains("wikifier: disable map, cycles, status"));
    let parsed = AgentTools::parse(&text);
    assert!(!parsed.found, "{parsed:?}");
    assert_eq!(parsed.tools, None);
    assert_eq!(parsed.disable, None);
    let got = replies(&mcp_in(&here, &[], &[INIT, LIST]));
    assert_eq!(instructions_of(&got[0]), "");
    assert_eq!(names_of(&got[1]).len(), MCP_TOOLS.len());
    // The convention's own example shape, a block inside a markdown fence, is text too.
    let nested =
        AgentTools::parse("````markdown\n```agent-tools\nwikifier: disable notes\n```\n````\n");
    assert_eq!(nested, AgentTools::default());
}
