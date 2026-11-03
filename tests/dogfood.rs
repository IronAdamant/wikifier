//! Container roots are refused. A scoped child is mapped. Unsupported suffixes are not edges.
//! The fixture is created in a temp directory so CI does not depend on a developer machine path.

use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use wikifier::jsonutil::{parse, Json};
use wikifier::{prepare_edit, session_bootstrap, update_maps};

fn temp_root(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("wk-dog-{name}-{}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    dir
}

fn write_child(dir: &Path) {
    fs::create_dir_all(dir.join(".git")).unwrap();
}

fn assert_scope_risk(label: &str, value: &Json) {
    assert_eq!(
        value.get("success").and_then(|s| s.as_bool()),
        Some(true),
        "{label} {value}"
    );
    assert_eq!(
        value.get("map_complete").and_then(|s| s.as_bool()),
        Some(false),
        "{label} claimed a complete map: {value}"
    );
    assert_eq!(
        value.get("readiness").and_then(|s| s.as_str()),
        Some("map_ok_scope_risk"),
        "{label} readiness: {value}"
    );
    let scope = value.get("scope").unwrap_or(value);
    let count = scope
        .get("child_project_count")
        .and_then(|n| match n {
            Json::Int(i) => Some(*i),
            _ => None,
        })
        .unwrap_or(0);
    let container = scope
        .get("container")
        .and_then(|s| s.as_bool())
        .unwrap_or(false);
    assert!(
        container || count >= 3,
        "{label} did not report a container scope risk: {value}"
    );
    assert_ne!(
        scope.get("full_tree").and_then(|s| s.as_bool()),
        Some(true),
        "{label} full_tree walk: {value}"
    );
}

#[test]
fn containers_are_refused_and_scoped_children_map() {
    let container = temp_root("container");
    for name in ["alpha", "beta", "gamma"] {
        write_child(&container.join(name));
    }
    fs::create_dir_all(container.join("alpha/src/pkg")).unwrap();
    fs::write(container.join("alpha/src/pkg/__init__.py"), "").unwrap();
    fs::write(container.join("alpha/src/pkg/a.py"), "from . import b\n").unwrap();
    fs::write(container.join("alpha/src/pkg/b.py"), "VALUE = 1\n").unwrap();
    fs::write(
        container.join("alpha/src/pkg/skip.cbl"),
        "IDENTIFICATION DIVISION.\n",
    )
    .unwrap();
    fs::write(container.join("beta/lib.py"), "VALUE = 1\n").unwrap();
    fs::write(container.join("gamma/main.py"), "VALUE = 1\n").unwrap();
    write_child(&container.join("cobol"));
    fs::create_dir_all(container.join("cobol/examples")).unwrap();
    fs::write(
        container.join("cobol/examples/hello.cbl"),
        "IDENTIFICATION DIVISION.\n",
    )
    .unwrap();

    let bin = env!("CARGO_BIN_EXE_wikifier");
    let boot = Command::new(bin)
        .args(["--target", container.to_str().unwrap(), "session-bootstrap"])
        .output()
        .unwrap();
    assert!(
        boot.status.success(),
        "bootstrap status {:?} {}",
        boot.status,
        String::from_utf8_lossy(&boot.stderr)
    );
    let boot_json = parse(&String::from_utf8(boot.stdout.clone()).unwrap()).unwrap_or_else(|err| {
        panic!(
            "bootstrap json {err}: {}",
            String::from_utf8_lossy(&boot.stdout)
        )
    });
    assert_scope_risk("container", &boot_json);

    let maps = Command::new(bin)
        .args(["--target", container.to_str().unwrap(), "update-maps"])
        .output()
        .unwrap();
    assert!(maps.status.success(), "update-maps {:?}", maps.status);
    let maps_json = parse(&String::from_utf8(maps.stdout.clone()).unwrap()).unwrap();
    assert_scope_risk("container update-maps", &maps_json);
    assert_eq!(
        maps_json.get("parseable_files").and_then(|n| match n {
            Json::Int(i) => Some(*i),
            _ => None,
        }),
        Some(0),
        "walked files: {maps_json}"
    );

    let copy = temp_root("scoped");
    fs::create_dir_all(copy.join("pkg")).unwrap();
    for name in ["__init__.py", "a.py", "b.py", "skip.cbl"] {
        fs::copy(
            container.join("alpha/src/pkg").join(name),
            copy.join("pkg").join(name),
        )
        .unwrap();
    }
    fs::write(copy.join("map_paths.txt"), "pkg\n").unwrap();
    fs::write(copy.join("monitored_paths.txt"), "pkg\n").unwrap();
    fs::create_dir_all(copy.join("decoy")).unwrap();
    fs::write(copy.join("decoy/skip.py"), "import os\n").unwrap();
    fs::write(copy.join("decoy/skip.cbl"), "IDENTIFICATION DIVISION.\n").unwrap();

    let child_boot = session_bootstrap(&copy);
    assert_eq!(
        child_boot.get("success").and_then(|s| s.as_bool()),
        Some(true),
        "child bootstrap {child_boot}"
    );
    assert_ne!(
        child_boot.get("readiness").and_then(|s| s.as_str()),
        Some("map_ok_scope_risk"),
        "child treated as container"
    );

    let child_maps = update_maps(&copy);
    assert_eq!(
        child_maps.get("success").and_then(|s| s.as_bool()),
        Some(true),
        "child maps {child_maps}"
    );
    let n = child_maps
        .get("parseable_files")
        .and_then(|v| match v {
            Json::Int(i) => Some(*i),
            _ => None,
        })
        .unwrap();
    assert!(n > 0, "parsed nothing: {child_maps}");
    let edges = child_maps
        .get("edges")
        .and_then(|e| e.as_array())
        .unwrap_or(&[]);
    assert!(
        edges
            .iter()
            .any(|edge| edge.get("dst").and_then(|d| d.as_str()) == Some("pkg/b.py")),
        "{child_maps}"
    );
    for edge in edges {
        let dst = edge.get("dst").and_then(|d| d.as_str()).unwrap_or("");
        let src = edge.get("src").and_then(|d| d.as_str()).unwrap_or("");
        for bad in [".cbl", ".cob", ".cpy", ".swift", ".s"] {
            assert!(
                !src.ends_with(bad) && !dst.ends_with(bad),
                "unsupported edge {src} -> {dst}"
            );
        }
        assert!(
            !src.starts_with("decoy/") && !dst.starts_with("decoy/"),
            "escaped scope {src} -> {dst}"
        );
    }
    let again = session_bootstrap(&copy);
    let files = again.get("files").and_then(|f| f.as_array()).unwrap();
    assert!(
        files
            .iter()
            .all(|f| f.as_str().unwrap_or("").starts_with("pkg/")),
        "files left scope: {again}"
    );

    let cobol = temp_root("cobol");
    fs::create_dir_all(cobol.join("examples")).unwrap();
    fs::copy(
        container.join("cobol/examples/hello.cbl"),
        cobol.join("examples/hello.cbl"),
    )
    .unwrap();
    fs::write(cobol.join("map_paths.txt"), "examples\n").unwrap();
    fs::write(cobol.join("monitored_paths.txt"), "examples\n").unwrap();
    let cobol_maps = update_maps(&cobol);
    assert_eq!(
        cobol_maps.get("success").and_then(|s| s.as_bool()),
        Some(true),
        "{cobol_maps}"
    );
    assert_eq!(
        cobol_maps.get("parseable_files").and_then(|n| match n {
            Json::Int(i) => Some(*i),
            _ => None,
        }),
        Some(0),
        "{cobol_maps}"
    );
    assert!(cobol_maps
        .get("edges")
        .and_then(|e| e.as_array())
        .unwrap_or(&[])
        .is_empty());

    let _ = fs::remove_dir_all(&container);
    let _ = fs::remove_dir_all(&copy);
    let _ = fs::remove_dir_all(&cobol);
}

fn copy_tree(from: &Path, to: &Path) {
    fs::create_dir_all(to).unwrap();
    for entry in fs::read_dir(from).unwrap() {
        let entry = entry.unwrap();
        let target = to.join(entry.file_name());
        if entry.path().is_dir() {
            copy_tree(&entry.path(), &target);
        } else {
            fs::copy(entry.path(), target).unwrap();
        }
    }
}

fn string_list(value: &Json, key: &str) -> Vec<String> {
    value
        .get(key)
        .and_then(|item| item.as_array())
        .unwrap_or(&[])
        .iter()
        .filter_map(|item| item.as_str().map(|text| text.to_string()))
        .collect()
}

#[test]
fn prepare_edit_on_this_repo_lists_api_dependents() {
    let live = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let root = temp_root("self-api");
    fs::copy(live.join("Cargo.toml"), root.join("Cargo.toml")).unwrap();
    fs::copy(live.join("map_paths.txt"), root.join("map_paths.txt")).unwrap();
    copy_tree(&live.join("src"), &root.join("src"));
    copy_tree(&live.join("tests"), &root.join("tests"));

    let built = update_maps(&root);
    assert_eq!(
        built.get("success").and_then(|s| s.as_bool()),
        Some(true),
        "{built}"
    );
    assert_eq!(
        built.get("map_complete").and_then(|s| s.as_bool()),
        Some(true),
        "{built}"
    );

    let prep = prepare_edit(&root, "src/api.rs");
    assert_eq!(
        prep.get("success").and_then(|s| s.as_bool()),
        Some(true),
        "{prep}"
    );
    let mut dependents = string_list(&prep, "dependents");
    dependents.sort();
    let expected = vec![
        "src/lib.rs",
        "src/main.rs",
        "src/mcp.rs",
        "tests/cli_surface.rs",
        "tests/contract_gaps.rs",
        "tests/parity_fixes.rs",
        "tests/protocol_v07.rs",
        "tests/robustness.rs",
        "tests/skip_maps.rs",
    ];
    assert_eq!(dependents, expected, "prepare-edit src/api.rs dependents");

    let main = prepare_edit(&root, "src/main.rs");
    assert!(
        main.get("dependencies")
            .and_then(|item| item.as_array())
            .is_some_and(|rows| !rows.is_empty()),
        "{main}"
    );
    let main_deps: Vec<String> = main
        .get("dependencies")
        .and_then(|item| item.as_array())
        .unwrap_or(&[])
        .iter()
        .filter_map(|item| {
            item.get("path")
                .and_then(|path| path.as_str())
                .map(|text| text.to_string())
        })
        .collect();
    assert!(
        main_deps.iter().any(|path| path == "src/api.rs"),
        "main.rs dependencies: {main_deps:?}"
    );
    assert!(
        main_deps.iter().any(|path| path == "src/timeutil.rs"),
        "main.rs dependencies: {main_deps:?}"
    );
    let _ = fs::remove_dir_all(&root);
}
