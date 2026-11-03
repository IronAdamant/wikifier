//! The agent-facing contract that the early Rust port left thin.

use std::fs;
use std::path::PathBuf;
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

use wikifier::api::{self, dependency_report, load_dependencies, mark_green, read_health, read_journal, record_deletion, update_maps, update_maps_run, MapRun};
use wikifier::jsonutil::{self, Json};
use wikifier::mcp;

fn scratch(name: &str) -> PathBuf {
    let n = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
    let dir = std::env::temp_dir().join(format!("wk-v07-{name}-{n}"));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(dir.join("src")).unwrap();
    fs::write(dir.join("map_paths.txt"), "src\n").unwrap();
    fs::write(dir.join("monitored_paths.txt"), "src\n").unwrap();
    dir
}

fn int_field(value: &Json, key: &str) -> i64 {
    match value.get(key) {
        Some(Json::Int(n)) => *n,
        _ => panic!("missing int {key} in {value}"),
    }
}

#[test]
fn update_maps_writes_library_and_folder_cards() {
    let root = scratch("maps");
    fs::write(root.join("src/a.py"), "from . import b\n").unwrap();
    fs::write(root.join("src/b.py"), "VALUE = 1\n").unwrap();
    fs::write(root.join("src/__init__.py"), "").unwrap();
    let mapped = update_maps(&root);
    assert_eq!(mapped.get("success").and_then(|s| s.as_bool()), Some(true), "{mapped}");
    assert_eq!(mapped.get("map_complete").and_then(|s| s.as_bool()), Some(true), "{mapped}");
    let library = fs::read_to_string(root.join("library.md")).unwrap();
    assert!(library.contains("src/a.py"), "{library}");
    assert!(library.contains("```mermaid"), "{library}");
    assert!(library.contains("## File Tree"), "{library}");
    assert!(library.contains("src/a.py"), "{library}");
    let card = fs::read_to_string(root.join(".wikifier_staging/maps/_root.json")).unwrap();
    assert!(card.contains("src/"), "{card}");
    let src_card = fs::read_to_string(root.join(".wikifier_staging/maps/src/_index.json")).unwrap();
    assert!(src_card.contains("src/a.py"), "{src_card}");
    let status = fs::read_to_string(root.join(".wikifier_staging/incremental_status.json")).unwrap();
    assert!(status.contains("map_complete"), "{status}");
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn directory_max_files_and_stream_are_honored() {
    let root = scratch("budget");
    fs::create_dir_all(root.join("other")).unwrap();
    fs::write(root.join("src/a.py"), "x = 1\n").unwrap();
    fs::write(root.join("src/b.py"), "y = 2\n").unwrap();
    fs::write(root.join("other/c.py"), "z = 3\n").unwrap();
    let missing = update_maps_run(&root, &MapRun {
        full: false,
        quiet: true,
        directory: Some("missing".into()),
        max_files: None,
        stream: false,
    });
    assert_eq!(missing.get("error_type").and_then(|s| s.as_str()), Some("ScopeError"), "{missing}");

    let budget = update_maps_run(&root, &MapRun {
        full: false,
        quiet: false,
        directory: Some("src".into()),
        max_files: Some(1),
        stream: true,
    });
    assert_eq!(budget.get("success").and_then(|s| s.as_bool()), Some(true), "{budget}");
    assert_eq!(budget.get("map_complete").and_then(|s| s.as_bool()), Some(false), "{budget}");
    assert!(int_field(&budget, "files_remaining_dirty") >= 1, "{budget}");
    assert!(int_field(&budget, "files_parsed") <= 1, "{budget}");
    let paths = wikifier::cache::all_paths(&root);
    assert!(paths.iter().all(|p| p.starts_with("src/")), "directory leaked: {paths:?}");

    let rest = update_maps_run(&root, &MapRun {
        full: false,
        quiet: true,
        directory: Some("src".into()),
        max_files: Some(10),
        stream: false,
    });
    assert_eq!(rest.get("map_complete").and_then(|s| s.as_bool()), Some(true), "{rest}");
    assert_eq!(int_field(&rest, "files_remaining_dirty"), 0, "{rest}");
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn record_deletion_marks_red_and_drops_the_graph() {
    let root = scratch("del");
    fs::write(root.join("src/a.py"), "from . import b\n").unwrap();
    fs::write(root.join("src/b.py"), "VALUE = 1\n").unwrap();
    fs::write(root.join("src/__init__.py"), "").unwrap();
    assert_eq!(update_maps(&root).get("success").and_then(|s| s.as_bool()), Some(true));
    fs::write(root.join("pending_updates.md"), "# Pending Updates\n\n- src/b.py — old\n").unwrap();
    fs::remove_file(root.join("src/b.py")).unwrap();
    let deleted = record_deletion(&root, "src/b.py", "removed the helper");
    assert_eq!(deleted.get("success").and_then(|s| s.as_bool()), Some(true), "{deleted}");
    assert_eq!(deleted.get("removed_from_graph").and_then(|s| s.as_bool()), Some(true), "{deleted}");
    let row = read_health(&root).into_iter().find(|r| r.file == "src/b.py").unwrap();
    assert!(row.status.contains("Red"), "{:?}", row.status);
    let deps = load_dependencies(&root, "src/a.py");
    let internal = deps.get("internal").and_then(|v| v.as_array()).unwrap();
    assert!(internal.iter().all(|e| e.get("path").and_then(|p| p.as_str()) != Some("src/b.py")), "{deps}");
    let pending = fs::read_to_string(root.join("pending_updates.md")).unwrap();
    assert!(!pending.contains("src/b.py"), "{pending}");
    let again = record_deletion(&root, "src/b.py", "removed the helper");
    assert_eq!(again.get("duplicate_skipped").and_then(|s| s.as_bool()), Some(true), "{again}");
    let journal = read_journal(&root, None);
    assert_eq!(journal.iter().filter(|e| e.action == "record-deletion" && e.file == "src/b.py").count(), 1);
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn record_changes_matches_globs_deletions_and_green() {
    let root = scratch("batch");
    fs::write(root.join("src/a.py"), "def hello():\n    return 1\n").unwrap();
    fs::write(root.join("src/b.py"), "VALUE = 1\n").unwrap();
    fs::write(root.join("src/a.py.wiki.md"), "hello is the greeting\n").unwrap();
    Command::new("git").args(["init"]).current_dir(&root).output().unwrap();
    Command::new("git").args(["add", "-A"]).current_dir(&root).output().unwrap();
    Command::new("git").args(["-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-m", "init"]).current_dir(&root).output().unwrap();
    fs::write(root.join("src/a.py"), "def hello():\n    return 2\n").unwrap();
    fs::remove_file(root.join("src/b.py")).unwrap();
    let dry = api::record_changes_opts(&root, &["src/*.py=touched the package".into()], None, &[], None, false, true);
    assert_eq!(dry.get("success").and_then(|s| s.as_bool()), Some(true), "{dry}");
    assert!(int_field(&dry, "recorded") >= 2, "{dry}");
    assert!(read_journal(&root, None).is_empty(), "dry-run wrote a journal");

    let recorded = api::record_changes_opts(&root, &["src/=touched the package".into()], None, &["src/a.py".into()], None, true, false);
    assert_eq!(recorded.get("success").and_then(|s| s.as_bool()), Some(true), "{recorded}");
    let files = recorded.get("files").and_then(|v| v.as_array()).unwrap();
    assert!(files.iter().any(|v| v.as_str() == Some("src/a.py")), "{recorded}");
    assert!(files.iter().all(|v| v.as_str() != Some("src/b.py")), "only filter leaked: {recorded}");
    let failed = recorded.get("verification_failed").and_then(|v| v.as_array()).unwrap();
    assert!(failed.is_empty(), "{recorded}");
    let row = read_health(&root).into_iter().find(|r| r.file == "src/a.py").unwrap();
    assert!(row.status.contains("Green"), "{:?}", row.status);
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn full_dependencies_carry_confidence_and_cycles_have_a_break_hint() {
    let root = scratch("intel");
    fs::write(root.join("src/a.py"), "import b\n").unwrap();
    fs::write(root.join("src/b.py"), "import a\n").unwrap();
    assert_eq!(update_maps(&root).get("success").and_then(|s| s.as_bool()), Some(true));
    let full = dependency_report(&root, "src/a.py", true);
    assert_eq!(full.get("detail").and_then(|s| s.as_str()), Some("full"), "{full}");
    let edge = full.get("imports").and_then(|v| v.as_array()).unwrap().iter().find(|e| e.get("path").and_then(|p| p.as_str()) == Some("src/b.py")).unwrap();
    assert!(edge.get("confidence").is_some(), "{edge}");
    assert!(edge.get("conditional").is_some() && edge.get("via_barrel").is_some(), "{edge}");
    let report = api::cycles(&root);
    let cycle = report.get("cycles").and_then(|v| v.as_array()).unwrap();
    assert!(!cycle.is_empty(), "{report}");
    assert!(cycle[0].get("break_hint").is_some(), "{report}");
    let barrels = api::barrel_reports(&root);
    assert_eq!(barrels.get("success").and_then(|s| s.as_bool()), Some(true), "{barrels}");
    assert!(barrels.get("barrels").and_then(|v| v.as_array()).is_some(), "{barrels}");
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn wiki_check_covers_js_exports_removed_symbols_and_an_unchanged_wiki() {
    let root = scratch("wiki");
    fs::write(root.join("src/mod.ts"), "export function hello() { return 1 }\n").unwrap();
    fs::write(root.join("src/mod.ts.wiki.md"), "no exports named here\n").unwrap();
    let refused = mark_green(&root, "src/mod.ts", "", false);
    assert_eq!(refused.get("error_type").and_then(|s| s.as_str()), Some("WikiVerificationError"), "{refused}");
    let issues = refused.get("issues").and_then(|v| v.as_array()).unwrap();
    assert!(issues.iter().any(|v| v.as_str().unwrap_or("").contains("undocumented_new_symbols")), "{refused}");

    fs::write(root.join("src/mod.ts.wiki.md"), "`hello` is the greeting\n").unwrap();
    let marked = mark_green(&root, "src/mod.ts", "wiki names hello", false);
    assert_eq!(marked.get("success").and_then(|s| s.as_bool()), Some(true), "{marked}");

    let wiki = fs::read_to_string(root.join("src/mod.ts.wiki.md")).unwrap();
    fs::write(root.join("src/mod.ts"), "export function goodbye() { return 1 }\n").unwrap();
    fs::write(root.join("src/mod.ts.wiki.md"), &wiki).unwrap();
    let stale = mark_green(&root, "src/mod.ts", "same wiki", false);
    assert_eq!(stale.get("error_type").and_then(|s| s.as_str()), Some("WikiVerificationError"), "{stale}");
    let text = stale.to_string();
    assert!(text.contains("wiki_mentions_removed_symbols"), "{stale}");
    assert!(text.contains("wiki_not_updated_for_api_change"), "{stale}");
    let summary = api::health(&root).get("health_summary").cloned().unwrap();
    assert!(summary.get("green_breakdown").is_some(), "{summary}");
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn legacy_json_cache_is_readable_before_a_remap() {
    let root = scratch("legacy");
    fs::create_dir_all(root.join(".wikifier_staging")).unwrap();
    fs::write(root.join("src/a.py"), "x = 1\n").unwrap();
    fs::write(
        root.join(".wikifier_staging/import_cache.json"),
        r#"{"src/a.py":{"resolved_pairs":[{"resolved":"src/b.py"}]},"src/b.py":{"resolved_pairs":[]}}"#,
    ).unwrap();
    let deps = load_dependencies(&root, "src/a.py");
    assert_eq!(deps.get("success").and_then(|s| s.as_bool()), Some(true), "{deps}");
    let internal = deps.get("internal").and_then(|v| v.as_array()).unwrap();
    assert!(internal.iter().any(|e| e.get("path").and_then(|p| p.as_str()) == Some("src/b.py")), "{deps}");
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn init_keeps_existing_path_lists_and_copies_the_dashboard() {
    let root = scratch("init");
    fs::write(root.join("map_paths.txt"), "pkg\n").unwrap();
    fs::write(root.join("monitored_paths.txt"), "README.md\n").unwrap();
    let value = api::dispatch("init", &root, &[], &std::collections::BTreeMap::new());
    assert_eq!(value.get("success").and_then(|s| s.as_bool()), Some(true), "{value}");
    assert_eq!(fs::read_to_string(root.join("map_paths.txt")).unwrap().trim(), "pkg");
    assert_eq!(fs::read_to_string(root.join("monitored_paths.txt")).unwrap().trim(), "README.md");
    assert!(root.join("index.html").is_file(), "init did not copy index.html");
    assert!(root.join(".wikifier").is_dir());
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn mcp_reports_tool_errors_and_reads_resources() {
    let root = scratch("mcp");
    let root_text = root.to_str().unwrap().replace('\\', "\\\\").replace('"', "\\\"");
    let call = format!(
        r#"{{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{{"name":"record_change","arguments":{{"project_root":"{root_text}","file":"src/missing.py","reason":"gone"}}}}}}"#
    );
    let msg = jsonutil::parse(&call).unwrap();
    let resp = mcp::handle_message(&msg).unwrap();
    let result = resp.get("result").unwrap();
    assert_eq!(result.get("isError").and_then(|s| s.as_bool()), Some(true), "{resp}");
    let read = jsonutil::parse(&format!(
        r#"{{"jsonrpc":"2.0","id":2,"method":"resources/read","params":{{"uri":"wikifier://health","project_root":"{root_text}"}}}}"#
    )).unwrap();
    let resource = mcp::handle_message(&read).unwrap();
    assert!(resource.get("result").and_then(|v| v.get("contents")).is_some(), "{resource}");
    let prompt = jsonutil::parse(r#"{"jsonrpc":"2.0","id":3,"method":"prompts/get","params":{"name":"review_pending_changes"}}"#).unwrap();
    let got = mcp::handle_message(&prompt).unwrap();
    assert!(got.get("result").and_then(|v| v.get("messages")).is_some(), "{got}");
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn prune_keeps_monitored_files_outside_the_map_roots() {
    let root = scratch("prune");
    fs::write(root.join("README.md"), "# hi\n").unwrap();
    fs::write(root.join("monitored_paths.txt"), "README.md\n").unwrap();
    fs::write(root.join("src/a.py"), "x = 1\n").unwrap();
    fs::create_dir_all(root.join("other")).unwrap();
    fs::write(root.join("other/gone.py"), "z = 1\n").unwrap();
    let mapped = update_maps(&root);
    assert_eq!(mapped.get("success").and_then(|s| s.as_bool()), Some(true), "{mapped}");
    let readme = api::record_change(&root, "README.md", "watch the readme");
    assert_eq!(readme.get("success").and_then(|s| s.as_bool()), Some(true), "{readme}");
    let other = api::record_change(&root, "other/gone.py", "outside the map");
    assert_eq!(other.get("success").and_then(|s| s.as_bool()), Some(true), "{other}");
    let pruned = api::prune_health(&root);
    assert_eq!(pruned.get("success").and_then(|s| s.as_bool()), Some(true), "{pruned}");
    assert!(int_field(&pruned, "changed") >= 1, "{pruned}");
    let files: Vec<String> = read_health(&root).into_iter().map(|row| row.file).collect();
    assert!(files.iter().any(|file| file == "README.md"), "{files:?}");
    assert!(files.iter().any(|file| file == "src/a.py"), "{files:?}");
    assert!(files.iter().all(|file| file != "other/gone.py"), "{files:?}");
    let pending = api::prune_pending(&root);
    assert_eq!(pending.get("success").and_then(|s| s.as_bool()), Some(true), "{pending}");
    let pending_text = fs::read_to_string(root.join("pending_updates.md")).unwrap_or_default();
    assert!(pending_text.contains("README.md"), "{pending_text}");
    assert!(!pending_text.contains("other/gone.py"), "{pending_text}");
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn serve_loop_serves_the_dashboard_files_and_shuts_down() {
    let root = scratch("serve-dash");
    fs::write(root.join("file_health.json"), r#"{"entries":{"src/a.py":{"status":"green"}}}"#).unwrap();
    fs::write(root.join("library.md"), "# map\n").unwrap();
    let server_root = root.clone();
    let handle = std::thread::spawn(move || api::serve_loop(&server_root, 0));
    let port_file = root.join(".wikifier_staging/serve.port");
    let port = (0..50).find_map(|_| {
        std::thread::sleep(std::time::Duration::from_millis(20));
        fs::read_to_string(&port_file).ok().and_then(|text| text.trim().parse::<u16>().ok())
    }).expect("serve did not publish a port");
    let health = http_exchange(port, "GET /file_health.json HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n");
    assert!(health.contains("200"), "{health}");
    assert!(health.contains("src/a.py"), "{health}");
    let status = http_exchange(port, "GET /__wikifier/status HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n");
    assert!(status.contains("wikifier_serve"), "{status}");
    let library = http_exchange(port, "GET /library.md HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n");
    assert!(library.contains("# map"), "{library}");
    let stopped = http_exchange(port, "POST /__wikifier/shutdown HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\nContent-Length: 0\r\n\r\n");
    assert!(stopped.contains("ok"), "{stopped}");
    let finished = handle.join().expect("serve thread");
    assert_eq!(finished.get("success").and_then(|flag| flag.as_bool()), Some(true), "{finished}");
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn heal_stubs_dry_run_leaves_initial_stubs() {
    use std::collections::BTreeMap;
    let root = scratch("heal-dry");
    fs::write(root.join("src/a.py"), "def alpha():\n    return 1\n").unwrap();
    let mapped = update_maps(&root);
    assert_eq!(mapped.get("success").and_then(|flag| flag.as_bool()), Some(true), "{mapped}");
    fs::write(root.join("src/a.py.wiki.md"), "This wiki is long enough to heal the alpha stub.\n").unwrap();
    let mut flags = BTreeMap::new();
    flags.insert("dry-run".into(), "true".into());
    let dry = api::dispatch("heal-stubs", &root, &[], &flags);
    assert_eq!(dry.get("success").and_then(|flag| flag.as_bool()), Some(true), "{dry}");
    assert_eq!(dry.get("dry_run").and_then(|flag| flag.as_bool()), Some(true), "{dry}");
    assert!(int_field(&dry, "healed_count") >= 1, "{dry}");
    assert_eq!(int_field(&dry, "changed"), 0, "{dry}");
    let during = read_health(&root);
    assert!(during.iter().any(|row| row.file == "src/a.py" && row.reason == "Initial stub"), "{during:?}");
    let wet = api::dispatch("heal-stubs", &root, &[], &BTreeMap::new());
    assert!(int_field(&wet, "changed") >= 1, "{wet}");
    let after = read_health(&root);
    assert!(after.iter().any(|row| row.file == "src/a.py" && row.reason == "healed stub"), "{after:?}");
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn init_positional_directory_is_the_project_root() {
    let root = scratch("init-pos");
    let dest = root.join("proj");
    fs::create_dir_all(dest.join("src")).unwrap();
    let out = Command::new(env!("CARGO_BIN_EXE_wikifier")).arg("init").arg(&dest).output().unwrap();
    assert!(out.status.success(), "{}", String::from_utf8_lossy(&out.stderr));
    let seeded = fs::read_to_string(dest.join("map_paths.txt")).unwrap_or_default();
    assert!(seeded.contains("src"), "{seeded}");
    assert!(dest.join(".wikifier/marker").is_file());
    assert!(dest.join("index.html").is_file());
    assert_eq!(fs::read_to_string(root.join("map_paths.txt")).unwrap(), "src\n");
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn search_journal_file_flag_keeps_one_path() {
    use std::collections::BTreeMap;
    let root = scratch("search");
    fs::write(root.join("src/a.py"), "x = 1\n").unwrap();
    fs::write(root.join("src/b.py"), "y = 2\n").unwrap();
    assert_eq!(api::record_change(&root, "src/a.py", "alpha reason").get("success").and_then(|flag| flag.as_bool()), Some(true));
    assert_eq!(api::record_change(&root, "src/b.py", "beta reason").get("success").and_then(|flag| flag.as_bool()), Some(true));
    let mut flags = BTreeMap::new();
    flags.insert("file".into(), "src/a.py".into());
    let found = api::dispatch("search-journal", &root, &[], &flags);
    let Json::Array(entries) = found.get("entries").unwrap() else { panic!("{found}") };
    assert_eq!(entries.len(), 1, "{found}");
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn verify_wikis_prefix_checks_one_file() {
    use std::collections::BTreeMap;
    let root = scratch("verify-prefix");
    fs::write(root.join("src/a.py"), "def alpha():\n    return 1\n").unwrap();
    fs::write(root.join("src/b.py"), "def beta():\n    return 2\n").unwrap();
    let mapped = update_maps(&root);
    assert_eq!(mapped.get("success").and_then(|flag| flag.as_bool()), Some(true), "{mapped}");
    fs::write(root.join("src/a.py.wiki.md"), "alpha is the public function.\n").unwrap();
    fs::write(root.join("src/b.py.wiki.md"), "beta is the public function.\n").unwrap();
    let marked_a = mark_green(&root, "src/a.py", "wiki names alpha", false);
    let marked_b = mark_green(&root, "src/b.py", "wiki names beta", false);
    assert_eq!(marked_a.get("success").and_then(|flag| flag.as_bool()), Some(true), "{marked_a}");
    assert_eq!(marked_b.get("success").and_then(|flag| flag.as_bool()), Some(true), "{marked_b}");
    let checked = api::dispatch("verify-wikis", &root, &["src/a.py".into()], &BTreeMap::new());
    assert_eq!(checked.get("success").and_then(|flag| flag.as_bool()), Some(true), "{checked}");
    assert_eq!(int_field(&checked, "checked"), 1, "{checked}");
    let _ = fs::remove_dir_all(&root);
}

fn http_exchange(port: u16, request: &str) -> String {
    use std::io::{Read, Write};
    let mut stream = std::net::TcpStream::connect(("127.0.0.1", port)).unwrap();
    stream.write_all(request.as_bytes()).unwrap();
    let mut buf = String::new();
    stream.read_to_string(&mut buf).unwrap();
    buf
}
