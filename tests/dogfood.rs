//! Real container roots are refused. One scoped child copy from each root is mapped.
//! Live August health and cache files are not modified.

use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use wikifier::jsonutil::{parse, Json};
use wikifier::sha256::sha256_hex;
use wikifier::{session_bootstrap, update_maps};

const CONTAINERS: &[(&str, &str, &str)] = &[
    (
        "cloned_sample_projects",
        "/Users/aron/Documents/coding_projects/cloned_sample_projects",
        "/Users/aron/Documents/coding_projects/cloned_sample_projects/redox/src",
    ),
    (
        "Sample_Probatio_Beyond",
        "/Users/aron/Documents/coding_projects/Sample_Probatio_Beyond",
        "/Users/aron/Documents/coding_projects/Sample_Probatio_Beyond/tqdm",
    ),
    (
        "Sample_Probatio_Separate",
        "/Users/aron/Documents/coding_projects/Sample_Probatio_Separate",
        "/Users/aron/Documents/coding_projects/Sample_Probatio_Separate/python",
    ),
    (
        "lang_cobol",
        "/Users/aron/Documents/coding_projects/lang_cobol_sample_projects_for_testing",
        "/Users/aron/Documents/coding_projects/lang_cobol_sample_projects_for_testing/cobol-examples-michelou/examples",
    ),
];

fn fingerprint(path: &Path) -> Option<String> {
    let bytes = fs::read(path).ok()?;
    Some(format!("{}:{}", bytes.len(), sha256_hex(&bytes)))
}

fn watch_files(root: &Path) -> Vec<PathBuf> {
    [
        root.join("file_health.json"),
        root.join("file_health.md"),
        root.join(".wikifier_staging/import_cache.sqlite"),
        root.join(".wikifier_staging/import_cache.json"),
    ]
    .into_iter()
    .filter(|p| p.is_file())
    .collect()
}

fn snapshot(paths: &[PathBuf]) -> Vec<(PathBuf, String)> {
    paths.iter().filter_map(|p| fingerprint(p).map(|h| (p.clone(), h))).collect()
}

fn copy_tree(from: &Path, to: &Path) {
    for ent in fs::read_dir(from).unwrap().flatten() {
        let name = ent.file_name();
        let name = name.to_string_lossy();
        if name == ".git" || name == "node_modules" || name == "target" || name == ".wikifier_staging" || name == "dist" || name == "build" || name == "__pycache__" {
            continue;
        }
        let dest = to.join(ent.file_name());
        if ent.path().is_dir() {
            fs::create_dir_all(&dest).unwrap();
            copy_tree(&ent.path(), &dest);
        } else if ent.path().is_file() {
            fs::copy(ent.path(), dest).unwrap();
        }
    }
}

fn assert_scope_risk(label: &str, value: &Json) {
    assert_eq!(value.get("success").and_then(|s| s.as_bool()), Some(true), "{label} {value}");
    assert_eq!(value.get("map_complete").and_then(|s| s.as_bool()), Some(false), "{label} claimed a complete map: {value}");
    assert_eq!(value.get("readiness").and_then(|s| s.as_str()), Some("map_ok_scope_risk"), "{label} readiness: {value}");
    let scope = value.get("scope").unwrap_or(value);
    let count = scope.get("child_project_count").and_then(|n| match n { Json::Int(i) => Some(*i), _ => None }).unwrap_or(0);
    let container = scope.get("container").and_then(|s| s.as_bool()).unwrap_or(false);
    assert!(container || count >= 3, "{label} did not report a container scope risk: {value}");
    assert_ne!(scope.get("full_tree").and_then(|s| s.as_bool()), Some(true), "{label} full_tree walk: {value}");
}

#[test]
fn containers_are_refused_and_scoped_children_map() {
    let mut watched = Vec::new();
    for (_, container, child) in CONTAINERS {
        assert!(Path::new(container).is_dir(), "missing {container}");
        assert!(Path::new(child).is_dir(), "missing {child}");
        watched.extend(watch_files(Path::new(container)));
        watched.extend(watch_files(Path::new(child)));
    }
    let before = snapshot(&watched);

    let bin = env!("CARGO_BIN_EXE_wikifier");
    for (label, container, child) in CONTAINERS {
        let boot = Command::new(bin).args(["--target", container, "session-bootstrap"]).output().unwrap();
        assert!(boot.status.success(), "{label} bootstrap status {:?} {}", boot.status, String::from_utf8_lossy(&boot.stderr));
        let boot_json = parse(&String::from_utf8(boot.stdout.clone()).unwrap()).unwrap_or_else(|e| panic!("{label} bootstrap json {e}: {}", String::from_utf8_lossy(&boot.stdout)));
        assert_scope_risk(label, &boot_json);

        let maps = Command::new(bin).args(["--target", container, "update-maps"]).output().unwrap();
        assert!(maps.status.success(), "{label} update-maps {:?}", maps.status);
        let maps_json = parse(&String::from_utf8(maps.stdout.clone()).unwrap()).unwrap();
        assert_scope_risk(&format!("{label} update-maps"), &maps_json);
        assert_eq!(maps_json.get("parseable_files").and_then(|n| match n { Json::Int(i) => Some(*i), _ => None }), Some(0), "{label} walked files: {maps_json}");

        let copy = std::env::temp_dir().join(format!("wk-dog-{label}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&copy);
        fs::create_dir_all(copy.join("pkg")).unwrap();
        copy_tree(Path::new(child), &copy.join("pkg"));
        fs::write(copy.join("map_paths.txt"), "pkg\n").unwrap();
        fs::write(copy.join("monitored_paths.txt"), "pkg\n").unwrap();
        fs::create_dir_all(copy.join("decoy")).unwrap();
        fs::write(copy.join("decoy/skip.py"), "import os\n").unwrap();
        fs::write(copy.join("decoy/skip.cbl"), "IDENTIFICATION DIVISION.\n").unwrap();

        let child_boot = session_bootstrap(&copy);
        assert_eq!(child_boot.get("success").and_then(|s| s.as_bool()), Some(true), "{label} child bootstrap {child_boot}");
        assert_ne!(child_boot.get("readiness").and_then(|s| s.as_str()), Some("map_ok_scope_risk"), "{label} child treated as container");

        let child_maps = update_maps(&copy);
        assert_eq!(child_maps.get("success").and_then(|s| s.as_bool()), Some(true), "{label} child maps {child_maps}");
        let n = child_maps.get("parseable_files").and_then(|v| match v { Json::Int(i) => Some(*i), _ => None }).unwrap();
        let edges = child_maps.get("edges").and_then(|e| e.as_array()).unwrap_or(&[]);
        for edge in edges {
            let dst = edge.get("dst").and_then(|d| d.as_str()).unwrap_or("");
            let src = edge.get("src").and_then(|d| d.as_str()).unwrap_or("");
            for bad in [".cbl", ".cob", ".cpy", ".swift", ".s"] {
                assert!(!src.ends_with(bad) && !dst.ends_with(bad), "{label} unsupported edge {src} -> {dst}");
            }
            assert!(!src.starts_with("decoy/") && !dst.starts_with("decoy/"), "{label} escaped scope {src} -> {dst}");
        }
        let _ = child_boot.get("files");
        let again = session_bootstrap(&copy);
        let files = again.get("files").and_then(|f| f.as_array()).unwrap();
        assert!(files.iter().all(|f| f.as_str().unwrap_or("").starts_with("pkg/")), "{label} files left scope: {again}");
        if *label == "lang_cobol" {
            assert_eq!(n, 0, "cobol sample must not be parsed as source: {child_maps}");
            assert!(edges.is_empty(), "{edges:?}");
        } else {
            assert!(n > 0, "{label} parsed nothing: {child_maps}");
        }
        let _ = (files, child_boot);
        let _ = fs::remove_dir_all(&copy);
    }

    let after = snapshot(&watched);
    assert_eq!(before, after, "live health or cache bytes changed");
}
