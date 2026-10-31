//! Fixture edges must match the Python 4.7 tool, which is the CPython-ast oracle.

use std::collections::BTreeSet;
use std::fs;
use std::path::Path;
use std::process::Command;

use wikifier::jsonutil::{parse, Json};
use wikifier::{mapped_edges, update_maps};

#[test]
fn accuracy_fixtures_match_python_oracle() {
    let repo = Path::new(env!("CARGO_MANIFEST_DIR"));
    let script = r#"
import json, sys, tempfile
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from tests.accuracy_fixtures import FIXTURES, materialize, measure
from wikifier import import_cache as ic
out = []
for name, fx in FIXTURES.items():
    root = Path(tempfile.mkdtemp(prefix="wkfix-"))
    materialize(root, fx)
    result = measure(root, fx)
    cache = ic.load_cache(root)
    found = []
    for src, entry in cache.items():
        if not isinstance(src, str) or src.startswith("_") or not isinstance(entry, dict):
            continue
        for pair in entry.get("resolved_pairs") or []:
            dst = pair.get("resolved")
            if dst and dst != src:
                found.append([src, dst])
    expected = [[a, b] for a, b in sorted(fx["edges"])]
    out.append({
        "name": name,
        "root": str(root),
        "expected": expected,
        "python": sorted(found),
        "precision": result["precision"],
        "recall": result["recall"],
    })
print(json.dumps(out))
"#;
    let output = Command::new("python3")
        .arg("-c")
        .arg(script)
        .arg(repo)
        .output()
        .expect("python3");
    assert!(
        output.status.success(),
        "python oracle failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    let text = String::from_utf8(output.stdout).unwrap();
    let fixtures = parse(&text).expect("oracle json");
    for fx in fixtures.as_array().unwrap() {
        let name = fx.get("name").and_then(|n| n.as_str()).unwrap();
        let root = Path::new(fx.get("root").and_then(|n| n.as_str()).unwrap());
        let python = edge_set(fx.get("python").unwrap());
        let expected = edge_set(fx.get("expected").unwrap());
        assert_eq!(python, expected, "{name}: python oracle drifted from accuracy_fixtures");
        let built = update_maps(root);
        assert_eq!(
            built.get("success").and_then(|s| s.as_bool()),
            Some(true),
            "{name}: {built}"
        );
        let rust = mapped_edges(root);
        if rust != python {
            let missed: Vec<_> = python.difference(&rust).cloned().collect();
            let extra: Vec<_> = rust.difference(&python).cloned().collect();
            panic!("{name}: rust edges diverged\nmissed {missed:?}\nextra {extra:?}");
        }
        let _ = fs::remove_dir_all(root);
    }
}

fn edge_set(value: &Json) -> BTreeSet<(String, String)> {
    let mut out = BTreeSet::new();
    for item in value.as_array().unwrap() {
        let pair = item.as_array().unwrap();
        out.insert((
            pair[0].as_str().unwrap().to_string(),
            pair[1].as_str().unwrap().to_string(),
        ));
    }
    out
}

#[test]
fn each_parsed_language_emits_a_local_edge() {
    let root = std::env::temp_dir().join(format!("wk-langs-{}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(root.join("src")).unwrap();
    fs::write(root.join("map_paths.txt"), "src\n").unwrap();
    fs::write(root.join("src/a.py"), "import b\n").unwrap();
    fs::write(root.join("src/b.py"), "x = 1\n").unwrap();
    fs::write(root.join("src/app.js"), "import { n } from './lib';\n").unwrap();
    fs::write(root.join("src/lib.js"), "export const n = 1;\n").unwrap();
    fs::write(root.join("src/main.rs"), "mod helper;\n").unwrap();
    fs::write(root.join("src/helper.rs"), "pub fn h() {}\n").unwrap();
    fs::write(root.join("src/a.go"), "package p\nimport \"./b\"\n").unwrap();
    fs::write(root.join("src/b.go"), "package b\n").unwrap();
    fs::write(root.join("src/a.c"), "#include \"b.h\"\n").unwrap();
    fs::write(root.join("src/b.h"), "#pragma once\n").unwrap();
    fs::write(root.join("src/A.java"), "import demo.B;\nclass A {}\n").unwrap();
    fs::write(root.join("src/B.java"), "package demo;\npublic class B {}\n").unwrap();
    fs::write(root.join("src/A.cs"), "using Demo;\nclass A {}\n").unwrap();
    fs::write(root.join("src/Demo.cs"), "class Demo {}\n").unwrap();
    let built = update_maps(&root);
    assert_eq!(built.get("success").and_then(|s| s.as_bool()), Some(true), "{built}");
    let edges = mapped_edges(&root);
    for (src, dst) in [
        ("src/a.py", "src/b.py"),
        ("src/app.js", "src/lib.js"),
        ("src/main.rs", "src/helper.rs"),
        ("src/a.go", "src/b.go"),
        ("src/a.c", "src/b.h"),
        ("src/A.java", "src/B.java"),
        ("src/A.cs", "src/Demo.cs"),
    ] {
        assert!(edges.contains(&(src.into(), dst.into())), "missing {src} -> {dst} in {edges:?}");
    }
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn unknown_suffixes_emit_no_edges() {
    let root = std::env::temp_dir().join(format!("wk-unk-{}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(root.join("src")).unwrap();
    fs::write(root.join("map_paths.txt"), "src\n").unwrap();
    fs::write(root.join("monitored_paths.txt"), "src\n").unwrap();
    fs::write(root.join("src/hello.cbl"), "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. HELLO.\n").unwrap();
    fs::write(root.join("src/hello.cob"), "       PROCEDURE DIVISION.\n").unwrap();
    fs::write(root.join("src/hello.cpy"), "       COPY HELLO.\n").unwrap();
    fs::write(root.join("src/hello.swift"), "import Foundation\n").unwrap();
    fs::write(root.join("src/hello.s"), "mov x0, #0\n").unwrap();
    fs::write(root.join("src/real.py"), "def hi():\n    return 1\n").unwrap();
    let built = update_maps(&root);
    assert_eq!(built.get("success").and_then(|s| s.as_bool()), Some(true), "{built}");
    let edges = mapped_edges(&root);
    assert!(edges.is_empty(), "{edges:?}");
    let files = built.get("parseable_files").and_then(|n| match n { Json::Int(i) => Some(*i), _ => None });
    assert_eq!(files, Some(1), "only real.py is parseable, got {built}");
    let _ = fs::remove_dir_all(&root);
}
