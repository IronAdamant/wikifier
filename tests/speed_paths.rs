//! The fast paths must give the answers the slow paths gave: edges from the index,
//! map artifacts kept when the cache did not change, stat-first change checks, and a
//! capped bootstrap file list.

use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use wikifier::api;
use wikifier::cache;
use wikifier::{check_changes, mark_green, read_health, update_maps, Json};

fn scratch(name: &str) -> PathBuf {
    let n = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let dir = std::env::temp_dir().join(format!("wk-speed-{name}-{n}-{}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(dir.join("src/pkg")).unwrap();
    fs::write(dir.join("map_paths.txt"), "src\n").unwrap();
    fs::write(dir.join("monitored_paths.txt"), "src\n").unwrap();
    dir
}

/// `a` and `b` import each other, `c` imports `a` and itself.
fn cyclic_project(name: &str) -> PathBuf {
    let root = scratch(name);
    fs::write(root.join("src/pkg/__init__.py"), "").unwrap();
    fs::write(root.join("src/pkg/a.py"), "from . import b\n").unwrap();
    fs::write(root.join("src/pkg/b.py"), "from . import a\n").unwrap();
    fs::write(
        root.join("src/pkg/c.py"),
        "from . import a\nfrom . import c\n",
    )
    .unwrap();
    let built = update_maps(&root);
    assert_eq!(ok(&built), Some(true), "{built}");
    root
}

fn ok(value: &Json) -> Option<bool> {
    value.get("success").and_then(|v| v.as_bool())
}

fn by_src_edges(root: &Path) -> BTreeSet<(String, String)> {
    let mut out = BTreeSet::new();
    for rel in cache::all_paths(root) {
        for dst in cache::load_dependencies(root, &rel).unwrap() {
            if dst != rel {
                out.insert((rel.clone(), dst));
            }
        }
    }
    out
}

#[test]
fn edges_from_the_index_match_the_by_src_records() {
    let root = cyclic_project("edges");
    let expected = by_src_edges(&root);
    assert!(expected.contains(&("src/pkg/a.py".into(), "src/pkg/b.py".into())));
    assert_eq!(cache::edges(&root), expected);

    // An index written before targets were stored still yields the same edges.
    let index = root.join(".wikifier_staging/wk_cache/index.tsv");
    let old_rows: String = fs::read_to_string(&index)
        .unwrap()
        .lines()
        .map(|line| line.split('\t').take(4).collect::<Vec<_>>().join("\t") + "\n")
        .collect();
    fs::write(&index, old_rows).unwrap();
    assert_eq!(cache::edges(&root), expected);

    let cycles = api::cycles(&root);
    assert_eq!(cycles.get("count"), Some(&Json::Int(1)), "{cycles}");
    assert!(cycles.to_string().contains("break_hint"), "{cycles}");
    let _ = fs::remove_dir_all(root);
}

#[test]
fn a_warm_run_keeps_map_artifacts_until_the_cache_changes() {
    let root = cyclic_project("warm");
    let library = root.join("library.md");
    let marked = format!("{}<!-- kept -->\n", fs::read_to_string(&library).unwrap());
    fs::write(&library, &marked).unwrap();
    let warm = update_maps(&root);
    assert_eq!(warm.get("files_parsed"), Some(&Json::Int(0)), "{warm}");
    assert_eq!(fs::read_to_string(&library).unwrap(), marked);

    // CRLF from a Windows checkout is still recognised as the generated file.
    fs::write(&library, marked.replace('\n', "\r\n")).unwrap();
    update_maps(&root);
    assert!(fs::read_to_string(&library)
        .unwrap()
        .contains("<!-- kept -->"));

    fs::write(root.join("src/pkg/d.py"), "from . import c\n").unwrap();
    update_maps(&root);
    let text = fs::read_to_string(&library).unwrap();
    assert!(!text.contains("<!-- kept -->"), "{text}");
    assert!(text.contains("src/pkg/d.py"), "{text}");

    // The init placeholder or a missing folder card is rebuilt even with no cache change.
    fs::write(
        &library,
        "# Library & Imports Map\n\nRun `wikifier update-maps` to populate.\n",
    )
    .unwrap();
    fs::remove_dir_all(root.join(".wikifier_staging/maps")).unwrap();
    update_maps(&root);
    assert!(fs::read_to_string(&library)
        .unwrap()
        .contains("src/pkg/d.py"));
    assert!(root.join(".wikifier_staging/maps/_root.json").is_file());
    let _ = fs::remove_dir_all(root);
}

fn green(root: &Path, rel: &str) {
    fs::write(root.join(format!("{rel}.wiki.md")), "# a\n\nImports `b`.\n").unwrap();
    let value = mark_green(root, rel, "wiki (speed-1)", false);
    assert_eq!(ok(&value), Some(true), "{value}");
}

fn changes(root: &Path) -> i64 {
    match check_changes(root).get("changes_detected") {
        Some(Json::Int(n)) => *n,
        other => panic!("{other:?}"),
    }
}

#[test]
fn check_changes_trusts_an_unchanged_stat_and_reads_everything_else() {
    let root = cyclic_project("stat");
    let rel = "src/pkg/a.py";
    let path = root.join(rel);
    green(&root, rel);
    assert_eq!(changes(&root), 0);

    // Same size, mtime put back: the stat rule that update-maps also uses says unchanged.
    let mtime = fs::metadata(&path).unwrap().modified().unwrap();
    fs::write(&path, "from . import c\n").unwrap();
    fs::File::options()
        .write(true)
        .open(&path)
        .unwrap()
        .set_modified(mtime)
        .unwrap();
    assert_eq!(changes(&root), 0);

    // A real edit moves the mtime and is caught.
    fs::write(&path, "from . import b\nX = 2\n").unwrap();
    fs::File::options()
        .write(true)
        .open(&path)
        .unwrap()
        .set_modified(mtime + Duration::from_secs(5))
        .unwrap();
    assert_eq!(changes(&root), 1);
    let _ = fs::remove_dir_all(root);
}

#[test]
fn check_changes_reads_the_file_when_the_index_hash_is_not_the_baseline() {
    let root = cyclic_project("baseline");
    let rel = "src/pkg/b.py";
    green(&root, rel);
    // An index hash from an older hashing rule, with the stat still matching.
    let index = root.join(".wikifier_staging/wk_cache/index.tsv");
    let rewritten: String = fs::read_to_string(&index)
        .unwrap()
        .lines()
        .map(|line| {
            let mut cols: Vec<String> = line.split('\t').map(|c| c.to_string()).collect();
            if cols[0] == rel {
                cols[3] = "sha256:0000".into();
            }
            cols.join("\t") + "\n"
        })
        .collect();
    fs::write(&index, rewritten).unwrap();
    assert_eq!(changes(&root), 0);
    let _ = fs::remove_dir_all(root);
}

#[test]
fn seeded_rows_carry_the_file_content_hash() {
    let root = cyclic_project("seed");
    for row in read_health(&root) {
        let bytes = fs::read(root.join(&row.file)).unwrap();
        assert_eq!(
            row.source_hash,
            wikifier::sha256::content_sha256_prefixed(&bytes),
            "{}",
            row.file
        );
    }
    let _ = fs::remove_dir_all(root);
}

#[test]
fn bootstrap_caps_its_file_list() {
    let root = scratch("bootstrap");
    for i in 0..105 {
        fs::write(root.join(format!("src/m{i:03}.py")), "X = 1\n").unwrap();
    }
    update_maps(&root);
    let mut flags = BTreeMap::new();
    let full = api::dispatch("session-bootstrap", &root, &[], &flags);
    assert_eq!(files(&full), 105);
    assert!(full.get("files_total").is_none());
    flags.insert("limit".to_string(), "3".to_string());
    let capped = api::dispatch("session-bootstrap", &root, &[], &flags);
    assert_eq!(files(&capped), 3);
    assert_eq!(capped.get("files_total"), Some(&Json::Int(105)));

    let mcp = |args: Vec<(&str, Json)>| {
        let mut args = args;
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
                    ("name", Json::String("session_bootstrap".into())),
                    ("arguments", Json::obj(args)),
                ]),
            ),
        ]);
        wikifier::mcp::handle_message(&msg)
            .unwrap()
            .get("result")
            .and_then(|r| r.get("structuredContent"))
            .cloned()
            .unwrap()
    };
    let default = mcp(vec![]);
    assert_eq!(files(&default), 100, "{default}");
    assert_eq!(default.get("files_total"), Some(&Json::Int(105)));
    assert_eq!(files(&mcp(vec![("limit", Json::Int(0))])), 105);
    let _ = fs::remove_dir_all(root);
}

fn files(value: &Json) -> usize {
    value
        .get("files")
        .and_then(|v| v.as_array())
        .map(|a| a.len())
        .unwrap_or_else(|| panic!("{value}"))
}

/// Every cache file except the generation counter, by path under `wk_cache`.
fn cache_snapshot(root: &Path) -> BTreeMap<String, Vec<u8>> {
    fn walk(dir: &Path, base: &Path, out: &mut BTreeMap<String, Vec<u8>>) {
        for ent in fs::read_dir(dir).unwrap().flatten() {
            let path = ent.path();
            if path.is_dir() {
                walk(&path, base, out);
            } else {
                let rel = path
                    .strip_prefix(base)
                    .unwrap()
                    .to_string_lossy()
                    .replace('\\', "/");
                if rel != "generation" {
                    out.insert(rel, fs::read(&path).unwrap());
                }
            }
        }
    }
    let base = root.join(".wikifier_staging/wk_cache");
    let mut out = BTreeMap::new();
    walk(&base, &base, &mut out);
    out
}

fn answers(root: &Path) -> Vec<String> {
    ["src/pkg/a.py", "src/pkg/b.py", "src/pkg/c.py"]
        .iter()
        .flat_map(|rel| {
            [
                api::dependency_report(root, rel, true).to_string(),
                wikifier::load_dependents(root, rel).to_string(),
            ]
        })
        .chain([api::cycles(root).to_string()])
        .collect()
}

fn record_of(root: &Path, kind: &str, contains: &str) -> PathBuf {
    let dir = root.join(".wikifier_staging/wk_cache").join(kind);
    fs::read_dir(&dir)
        .unwrap()
        .flatten()
        .map(|ent| ent.path())
        .find(|path| String::from_utf8_lossy(&fs::read(path).unwrap()).contains(contains))
        .unwrap_or_else(|| panic!("no {kind} record mentioning {contains}"))
}

#[test]
fn corrupt_and_truncated_cache_files_are_rebuilt_identically() {
    let root = cyclic_project("heal");
    assert!(root.join(".wikifier_staging/wk_cache/sizes.tsv").is_file());
    let before = cache_snapshot(&root);
    let answered = answers(&root);

    // Garbage of another length in a forward record, and a truncated reverse record.
    let by_src = record_of(&root, "by_src", "@\tsrc/pkg/a.py\n");
    fs::write(&by_src, b"\0\0garbage").unwrap();
    let by_dst = record_of(&root, "by_dst", "@\tsrc/pkg/a.py\n");
    let bytes = fs::read(&by_dst).unwrap();
    fs::write(&by_dst, &bytes[..bytes.len() / 2]).unwrap();

    // Lookups treat a bad record as a miss and answer from index.tsv.
    assert_eq!(
        cache::load_dependencies(&root, "src/pkg/a.py").unwrap(),
        vec!["src/pkg/b.py".to_string()]
    );
    let importers = cache::load_dependents(&root, "src/pkg/a.py").unwrap();
    assert_eq!(
        importers,
        vec!["src/pkg/b.py".to_string(), "src/pkg/c.py".to_string()]
    );

    let healed = update_maps(&root);
    assert_eq!(healed.get("files_parsed"), Some(&Json::Int(1)), "{healed}");
    assert_eq!(cache_snapshot(&root), before);
    assert_eq!(answers(&root), answered);

    // Same-size damage is caught by content once the recorded sizes are gone too.
    let notes_free = record_of(&root, "by_src", "@\tsrc/pkg/b.py\n");
    let len = fs::read(&notes_free).unwrap().len();
    fs::write(&notes_free, vec![0u8; len]).unwrap();
    fs::remove_file(root.join(".wikifier_staging/wk_cache/sizes.tsv")).unwrap();
    update_maps(&root);
    assert_eq!(cache_snapshot(&root), before);
    assert_eq!(answers(&root), answered);
    let _ = fs::remove_dir_all(root);
}

/// Health, journal, and pending stay durable: each write replaces the whole file through a
/// synced temp file, and no temp file is left beside it.
#[test]
fn user_state_is_replaced_whole_and_leaves_no_temp_files() {
    let root = cyclic_project("durable");
    let recorded = wikifier::record_change(&root, "src/pkg/a.py", "durable write (speed-2)");
    assert_eq!(ok(&recorded), Some(true), "{recorded}");
    let pending = fs::read_to_string(root.join("pending_updates.md")).unwrap();
    assert!(
        pending.contains("- src/pkg/a.py: durable write (speed-2)"),
        "{pending}"
    );
    assert!(read_health(&root)
        .iter()
        .any(|row| row.file == "src/pkg/a.py" && row.reason == "durable write (speed-2)"));
    let journal = wikifier::read_journal(&root, None);
    assert!(journal
        .iter()
        .any(|e| e.reason == "durable write (speed-2)"));
    let mut dirs = vec![root.clone()];
    while let Some(dir) = dirs.pop() {
        for ent in fs::read_dir(&dir).unwrap().flatten() {
            let path = ent.path();
            if path.is_dir() {
                dirs.push(path);
            } else {
                assert!(
                    !path.to_string_lossy().ends_with(".tmp"),
                    "left behind: {}",
                    path.display()
                );
            }
        }
    }
    wikifier::artifacts::write_durable(&root.join("pending_updates.md"), b"# Pending Updates\n")
        .unwrap();
    assert_eq!(
        fs::read_to_string(root.join("pending_updates.md")).unwrap(),
        "# Pending Updates\n"
    );
    let _ = fs::remove_dir_all(root);
}
