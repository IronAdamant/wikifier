//! Cache lookups must not need every payload. One-file updates must not rewrite the others.
//! Health and journal files in the Python 4.7 shape are readable without a migration rewrite.

use std::fs;
use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};

use wikifier::cache::payload_bytes;
use wikifier::{load_dependencies, load_dependents, list_paths, read_health, read_journal, record_change, update_maps};

fn scratch(name: &str) -> PathBuf {
    let nanos = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
    let dir = std::env::temp_dir().join(format!("wk-{name}-{nanos}"));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(dir.join("src")).unwrap();
    dir
}

#[test]
fn one_file_update_does_not_rewrite_other_payloads_and_lookups_skip_them() {
    let root = scratch("cache");
    fs::create_dir_all(root.join("src/pkg")).unwrap();
    fs::write(root.join("map_paths.txt"), "src\n").unwrap();
    fs::write(root.join("src/pkg/__init__.py"), "").unwrap();
    fs::write(root.join("src/pkg/a.py"), "from . import b\n").unwrap();
    fs::write(root.join("src/pkg/b.py"), "VALUE = 1\n").unwrap();
    fs::write(root.join("map_paths.txt"), "src\n").unwrap();

    let first = update_maps(&root);
    assert_eq!(first.get("success").and_then(|s| s.as_bool()), Some(true), "{first}");

    let b_before = payload_bytes(&root, "src/pkg/b.py").expect("b payload");
    let a_before = payload_bytes(&root, "src/pkg/a.py").expect("a payload");
    fs::write(root.join("src/pkg/a.py"), "from . import b\n\ndef extra():\n    return 2\n").unwrap();
    // mtime may not move on some filesystems within the same nanosecond; bump by rewriting after a stat
    let _ = fs::File::open(root.join("src/pkg/a.py")).unwrap();

    let second = update_maps(&root);
    assert_eq!(second.get("success").and_then(|s| s.as_bool()), Some(true), "{second}");
    let b_after = payload_bytes(&root, "src/pkg/b.py").unwrap();
    let a_after = payload_bytes(&root, "src/pkg/a.py").unwrap();
    assert_eq!(b_before, b_after, "untouched file payload was rewritten");
    assert_ne!(a_before, a_after, "changed file payload should change");

    // Corrupt every other payload. Src lookup and dst lookup read indexes only.
    fs::write(wikifier::cache::payload_path(&root, "src/pkg/b.py"), b"NOT JSON").unwrap();
    let deps = load_dependencies(&root, "src/pkg/a.py");
    assert_eq!(deps.get("success").and_then(|s| s.as_bool()), Some(true), "{deps}");
    let internal = deps.get("internal").and_then(|v| v.as_array()).unwrap();
    assert!(internal.iter().any(|v| v.get("path").and_then(|p| p.as_str()) == Some("src/pkg/b.py")), "{deps}");
    assert!(deps.get("external").and_then(|v| v.as_array()).is_some(), "{deps}");
    assert!(deps.get("needs_review").and_then(|v| v.as_array()).is_some(), "{deps}");

    fs::write(wikifier::cache::payload_path(&root, "src/pkg/a.py"), b"NOT JSON").unwrap();
    let importers = load_dependents(&root, "src/pkg/b.py");
    assert_eq!(importers.get("success").and_then(|s| s.as_bool()), Some(true), "{importers}");
    let dep_list = importers.get("dependents").and_then(|v| v.as_array()).unwrap();
    assert!(dep_list.iter().any(|v| v.as_str() == Some("src/pkg/a.py")), "{importers}");

    let listed = list_paths(&root, "src/pkg");
    assert_eq!(listed.get("success").and_then(|s| s.as_bool()), Some(true), "{listed}");
    let count = listed.get("file_count").and_then(|n| match n { wikifier::Json::Int(i) => Some(*i), _ => None });
    assert!(count.unwrap_or(0) >= 2, "{listed}");
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn reads_python_47_health_and_journal_without_rewriting_them() {
    let root = scratch("art");
    let health = r#"{
  "version": 2,
  "last_updated": "2026-10-01 18:48:10",
  "entries": {
    "src/app.py": {
      "status": "🟢 Green",
      "last_updated": "2026-10-01 18:46:22",
      "reason": "kept",
      "source_content_hash": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    }
  }
}"#;
    fs::write(root.join("file_health.json"), health).unwrap();
    let md = "# Documentation Health Matrix\n\n| File | Status | Last Updated | Reason / Intent |\n|------|--------|--------------|-----------------|\n| src/app.py | 🟢 Green | 2026-10-01 18:46:22 | kept |\n";
    fs::write(root.join("file_health.md"), md).unwrap();
    fs::create_dir_all(root.join("journal/2026/10")).unwrap();
    let journal = "## [2026-10-01 18:02:17] record-change\n**File:** src/app.py\n**Reason:** content changed since last mark-green\n\n";
    fs::write(root.join("journal/2026/10/01.md"), journal).unwrap();
    fs::write(root.join("pending_updates.md"), "# Pending Updates\n\n(no pending items — run check-changes after making edits)\n").unwrap();
    let health_before = fs::read(root.join("file_health.json")).unwrap();
    let journal_before = fs::read(root.join("journal/2026/10/01.md")).unwrap();
    let md_before = fs::read(root.join("file_health.md")).unwrap();

    let rows = read_health(&root);
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].file, "src/app.py");
    assert!(rows[0].source_hash.starts_with("sha256:"), "{}", rows[0].source_hash);
    assert!(rows[0].status.contains("Green"));

    let entries = read_journal(&root, Some("2026-10-01"));
    assert_eq!(entries.len(), 1);
    assert_eq!(entries[0].file, "src/app.py");
    assert_eq!(entries[0].action, "record-change");
    assert!(entries[0].reason.contains("mark-green"));

    assert_eq!(fs::read(root.join("file_health.json")).unwrap(), health_before);
    assert_eq!(fs::read(root.join("journal/2026/10/01.md")).unwrap(), journal_before);
    assert_eq!(fs::read(root.join("file_health.md")).unwrap(), md_before);

    // A later record_change appends a journal entry and must not be required to migrate the old row's hash.
    fs::write(root.join("src/app.py"), "print(1)\n").unwrap();
    let rec = record_change(&root, "src/app.py", "touch the copy only");
    assert_eq!(rec.get("success").and_then(|s| s.as_bool()), Some(true), "{rec}");
    let entries = read_journal(&root, None);
    assert!(entries.iter().any(|e| e.reason == "touch the copy only"));
    let rows = read_health(&root);
    let old = rows.iter().find(|r| r.file == "src/app.py").unwrap();
    assert!(old.status.contains("Yellow") || old.reason.contains("touch"));
    let _ = fs::remove_dir_all(&root);
}
