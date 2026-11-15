//! 5.6.0: a Rust path that ends at a module's `use` items is followed to the file that
//! defines the name (`via_barrel`), across workspace crates, through `pub use` names,
//! aliases, globs, chains of modules, and `pub(crate) use` inside one crate. A glob import
//! of a crate root links the names the file uses. The edge to the root file stays.

use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use wikifier::api::{self, dispatch};
use wikifier::jsonutil::Json;

fn scratch(name: &str) -> PathBuf {
    let n = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let dir = std::env::temp_dir().join(format!("wk-rx-{name}-{n}"));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    dir.canonicalize().map(clean).unwrap()
}

fn clean(path: PathBuf) -> PathBuf {
    let text = path.to_string_lossy().to_string();
    match text.strip_prefix(r"\\?\") {
        Some(rest) if !rest.starts_with("UNC") => PathBuf::from(rest),
        _ => path,
    }
}

fn write(root: &Path, rel: &str, text: &str) {
    let path = root.join(rel);
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    fs::write(path, text).unwrap();
}

fn package(root: &Path, dir: &str, name: &str) {
    write(
        root,
        &format!("{dir}/Cargo.toml"),
        &format!("[package]\nname = \"{name}\"\nversion = \"0.1.0\"\nedition = \"2021\"\n"),
    );
}

fn map(root: &Path) -> Json {
    let built = api::update_maps(root);
    assert_eq!(
        built.get("success").and_then(|v| v.as_bool()),
        Some(true),
        "{built}"
    );
    built
}

fn int(value: &Json, key: &str) -> i64 {
    match value.get(key) {
        Some(Json::Int(n)) => *n,
        other => panic!("{key} = {other:?} in {value}"),
    }
}

fn flags(pairs: &[(&str, &str)]) -> BTreeMap<String, String> {
    pairs
        .iter()
        .map(|(k, v)| (k.to_string(), v.to_string()))
        .collect()
}

fn strings(value: &Json, key: &str) -> Vec<String> {
    let mut out: Vec<String> = value
        .get(key)
        .and_then(|v| v.as_array())
        .unwrap_or_else(|| panic!("no {key} in {value}"))
        .iter()
        .filter_map(|v| v.as_str().map(str::to_string))
        .collect();
    out.sort();
    out
}

fn dependents(root: &Path, rel: &str) -> Vec<String> {
    strings(&api::load_dependents(root, rel), "dependents")
}

/// `path -> via_barrel` for one file's internal edges.
fn dependencies(root: &Path, rel: &str) -> BTreeMap<String, bool> {
    let reply = api::load_dependencies(root, rel);
    reply
        .get("internal")
        .and_then(|v| v.as_array())
        .unwrap_or_else(|| panic!("no internal in {reply}"))
        .iter()
        .map(|edge| {
            (
                edge.get("path")
                    .and_then(|v| v.as_str())
                    .unwrap()
                    .to_string(),
                edge.get("via_barrel").and_then(|v| v.as_bool()).unwrap(),
            )
        })
        .collect()
}

const INPUT: &str = "crates/sp-input/src/input.rs";
const LIB: &str = "crates/sp-input/src/lib.rs";
const RECORD: &str = "crates/sp-input/src/record.rs";
const FORMS: &str = "crates/sp-input/src/forms.rs";
const HIDDEN: &str = "crates/sp-input/src/hidden.rs";
const DEEPEST: &str = "crates/sp-input/src/deep/one/two.rs";
const USER: &str = "crates/sp-input/src/user.rs";

/// A workspace whose `sp-input` crate re-exports in every form the scan follows (and a few
/// it does not), and one app crate per way of importing it.
fn workspace(name: &str) -> PathBuf {
    let root = scratch(name);
    write(&root, "map_paths.txt", "crates\n");
    write(
        &root,
        "Cargo.toml",
        "[workspace]\nmembers = [\"crates/*\"]\nresolver = \"2\"\n",
    );
    package(&root, "crates/sp-input", "sp-input");
    let src = "crates/sp-input/src";
    write(
        &root,
        LIB,
        "pub mod input;\nmod record;\nmod forms;\nmod hidden;\nmod deep;\nmod user;\nmod gen;\n\
         mod cfg_a;\nmod cfg_b;\n#[path = \"elsewhere.rs\"]\nmod pathmod;\n\
         pub use input::Input;\npub use record::*;\npub use forms::{Alpha, Beta as Gamma};\n\
         pub use deep::Deepest;\npub(crate) use forms::Internal;\nuse hidden::Private;\n\
         pub use std::fmt::Debug;\npub use gen::Made;\npub use pathmod::FromPath;\n\
         #[cfg(unix)]\npub use cfg_a::Pick;\n#[cfg(not(unix))]\npub use cfg_b::Pick;\n\
         pub mod inline {\n    pub use crate::forms::Alpha as InlineAlpha;\n}\n",
    );
    write(
        &root,
        INPUT,
        "pub struct Input { pub n: u32 }\nimpl Input { pub fn new() -> Self { Input { n: 0 } } }\n",
    );
    write(
        &root,
        RECORD,
        "use crate::input::Input;\npub struct Record;\npub fn record(_: &Input) -> Record { Record }\nfn helper() {}\n",
    );
    write(
        &root,
        FORMS,
        "pub struct Alpha;\npub struct Beta;\npub(crate) struct Internal;\n",
    );
    write(&root, HIDDEN, "pub struct Private;\n");
    write(
        &root,
        &format!("{src}/deep.rs"),
        "mod one;\npub use one::Deepest;\n",
    );
    write(
        &root,
        &format!("{src}/deep/one.rs"),
        "mod two;\npub use two::*;\n",
    );
    write(&root, DEEPEST, "pub struct Deepest;\n");
    write(
        &root,
        USER,
        "use crate::Internal;\nuse crate::Private;\npub fn f(_: Internal, _: Private) {}\n",
    );
    write(
        &root,
        &format!("{src}/gen.rs"),
        "macro_rules! make { ($n:ident) => { pub struct $n; } }\nmake!(Made);\n",
    );
    write(
        &root,
        &format!("{src}/elsewhere.rs"),
        "pub struct FromPath;\n",
    );
    write(&root, &format!("{src}/cfg_a.rs"), "pub struct Pick;\n");
    write(&root, &format!("{src}/cfg_b.rs"), "pub struct Pick;\n");
    let apps = [
        // A name the crate root re-exports.
        (
            "app",
            "use sp_input::Input;\nfn main() { let _ = Input::new(); }\n",
        ),
        // A glob import of the crate root, then bare uses of what it brings in.
        (
            "app2",
            "use sp_input::*;\nfn main() { let i = Input::new(); let _r: Record = record(&i); }\n",
        ),
        // The full module path, which 5.5.0 already followed.
        (
            "app3",
            "use sp_input::input::Input;\nfn main() { let _ = Input { n: 0 }; }\n",
        ),
        // A chain of re-exports: lib.rs -> deep.rs -> deep/one.rs -> glob -> deep/one/two.rs.
        (
            "app4",
            "use sp_input::Deepest;\nfn main() { let _ = Deepest; }\n",
        ),
        // No `use`: a path expression through the crate root.
        (
            "app5",
            "fn main() { let _ = sp_input::Input::new(); }\n",
        ),
        // A glob whose names this file does not use, a private name of its own, a field.
        (
            "app6",
            "use sp_input::*;\nfn helper() {}\nfn main() { helper(); let x = 1; let _ = x.record; }\n",
        ),
        // Across crates only `pub` items are followed; a re-export of std is external.
        (
            "app7",
            "use sp_input::Private;\nuse sp_input::Debug;\nfn main() {}\n",
        ),
        // An alias inside a brace group: `Gamma` is forms.rs's `Beta`.
        ("app8", "use sp_input::Gamma;\nfn main() {}\n"),
        // A macro-generated item: the edge goes to the module the `use` names.
        ("app9", "use sp_input::Made;\nfn main() {}\n"),
        // A `#[path]` module is not followed.
        ("app10", "use sp_input::FromPath;\nfn main() {}\n"),
        // `cfg` is not evaluated: the first `use` that binds the name wins.
        ("app11", "use sp_input::Pick;\nfn main() {}\n"),
        // `use` items inside an inline `mod name { ... }` block are not read.
        ("app12", "use sp_input::inline::InlineAlpha;\nfn main() {}\n"),
    ];
    for (app, text) in apps {
        package(&root, &format!("crates/{app}"), app);
        write(&root, &format!("crates/{app}/src/main.rs"), text);
    }
    map(&root);
    root
}

fn app_deps(root: &Path, app: &str) -> BTreeMap<String, bool> {
    dependencies(root, &format!("crates/{app}/src/main.rs"))
}

/// The crate root (direct) plus one definition reached through it (`via_barrel`).
fn root_and(def: &str) -> BTreeMap<String, bool> {
    BTreeMap::from([(LIB.to_string(), false), (def.to_string(), true)])
}

#[test]
fn a_cross_crate_import_reaches_the_file_that_defines_the_name() {
    let root = workspace("forms");
    assert_eq!(
        dependents(&root, INPUT),
        [
            "crates/app/src/main.rs",
            "crates/app2/src/main.rs",
            "crates/app3/src/main.rs",
            "crates/app5/src/main.rs",
            LIB,
            RECORD,
        ],
    );
    // The edge to the crate root stays; the edge through it is marked `via_barrel`.
    assert_eq!(app_deps(&root, "app"), root_and(INPUT), "`pub use m::Name`");
    assert_eq!(
        app_deps(&root, "app8"),
        root_and(FORMS),
        "`pub use m::{{A, B as C}}`"
    );
    assert_eq!(
        app_deps(&root, "app4"),
        root_and(DEEPEST),
        "a chain through nested modules and a glob ends at the definition"
    );
    // A glob of the crate root links the names the file uses, including the ones the
    // root passes on from its own `pub use record::*`.
    let mut glob = root_and(INPUT);
    glob.insert(RECORD.to_string(), true);
    assert_eq!(app_deps(&root, "app2"), glob);
    // A path that goes on past a type names the type's definition only.
    assert_eq!(
        app_deps(&root, "app5"),
        BTreeMap::from([(INPUT.to_string(), true)])
    );
    // Unused glob names, a field named like a re-exported function, a private `use`
    // across crates, a re-export of std, and a `#[path]` module add nothing.
    for app in ["app6", "app7", "app10"] {
        assert_eq!(
            app_deps(&root, app),
            BTreeMap::from([(LIB.to_string(), false)]),
            "{app}"
        );
    }
    assert_eq!(
        app_deps(&root, "app9"),
        root_and("crates/sp-input/src/gen.rs"),
        "macro-generated"
    );
    assert_eq!(
        app_deps(&root, "app11"),
        root_and("crates/sp-input/src/cfg_a.rs"),
        "cfg"
    );
    assert!(app_deps(&root, "app12").is_empty(), "inline mod");
    // Inside one crate, `pub(crate) use` and a private `use` of the root are followed.
    let user = dependencies(&root, USER);
    assert_eq!(user.get(FORMS), Some(&true), "{user:?}");
    assert_eq!(user.get(HIDDEN), Some(&true), "{user:?}");
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn every_read_tool_sees_the_re_export_edges_and_no_cycle_is_added() {
    let root = workspace("tools");
    let none = flags(&[]);
    let deps = dispatch("get_dependents", &root, &[INPUT.into()], &none);
    assert!(
        strings(&deps, "dependents").contains(&"crates/app/src/main.rs".to_string()),
        "{deps}"
    );
    let prep = dispatch("prepare_edit", &root, &[INPUT.into()], &none);
    assert_eq!(
        strings(&prep, "dependents"),
        dependents(&root, INPUT),
        "{prep}"
    );
    let forward = dispatch(
        "get_dependencies",
        &root,
        &["crates/app/src/main.rs".into()],
        &none,
    );
    assert!(forward.to_string().contains(INPUT), "{forward}");
    // The only cycle is the one the crate already has: `user.rs` names `crate::` and
    // `lib.rs` declares `mod user`. Re-export edges point at definitions, which a file
    // already reached through the module it named, so no new cycle forms.
    let cycles = dispatch("get_cycles", &root, &[], &flags(&[("full", "true")]));
    let sets: Vec<BTreeSet<String>> = cycles
        .get("cycles")
        .and_then(|v| v.as_array())
        .unwrap_or_else(|| panic!("{cycles}"))
        .iter()
        .map(|cycle| strings(cycle, "files").into_iter().collect())
        .collect();
    assert_eq!(
        sets,
        vec![BTreeSet::from([LIB.to_string(), USER.to_string(),])],
        "{cycles}"
    );
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn a_chain_longer_than_four_hops_adds_no_edge() {
    let root = scratch("hops");
    write(&root, "map_paths.txt", "src\n");
    package(&root, ".", "chain");
    // lib.rs -> c1 -> c2 -> c3 -> c4 -> c5 -> c6, where c6 defines `Far`. `Near` is
    // defined in c4, four hops from the root.
    write(&root, "src/lib.rs", "mod c1;\npub use c1::{Far, Near};\n");
    for n in 1..=5 {
        let mut text = format!("mod c{};\npub use c{}::Far;\n", n + 1, n + 1);
        if n < 4 {
            text.push_str(&format!("pub use c{}::Near;\n", n + 1));
        }
        if n == 4 {
            text.push_str("pub struct Near;\n");
        }
        let dir = (1..n).map(|k| format!("c{k}/")).collect::<String>();
        write(&root, &format!("src/{dir}c{n}.rs"), &text);
    }
    write(&root, "src/c1/c2/c3/c4/c5/c6.rs", "pub struct Far;\n");
    write(
        &root,
        "tests/far.rs",
        "use chain::Far;\n#[test]\nfn t() {}\n",
    );
    write(
        &root,
        "tests/near.rs",
        "use chain::Near;\n#[test]\nfn t() {}\n",
    );
    write(&root, "map_paths.txt", "src\ntests\n");
    map(&root);
    assert_eq!(
        dependencies(&root, "tests/near.rs"),
        BTreeMap::from([
            ("src/c1/c2/c3/c4.rs".to_string(), true),
            ("src/lib.rs".to_string(), false),
        ]),
    );
    assert_eq!(
        dependencies(&root, "tests/far.rs"),
        BTreeMap::from([("src/lib.rs".to_string(), false)]),
    );
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn changing_a_re_export_moves_its_importers_edges_on_the_next_map() {
    let root = scratch("incremental");
    write(&root, "map_paths.txt", "src\ntests\n");
    package(&root, ".", "moves");
    write(
        &root,
        "src/lib.rs",
        "pub mod a;\npub mod b;\npub use a::Thing;\n",
    );
    write(&root, "src/a.rs", "pub struct Thing;\n");
    write(&root, "src/b.rs", "pub struct Thing;\n");
    write(
        &root,
        "tests/uses.rs",
        "use moves::Thing;\n#[test]\nfn t() {}\n",
    );
    write(&root, "tests/other.rs", "#[test]\nfn t() {}\n");
    map(&root);
    assert_eq!(
        dependents(&root, "src/a.rs"),
        ["src/lib.rs", "tests/uses.rs"]
    );

    // Only lib.rs changed, but tests/uses.rs reached `Thing` through it: both parse.
    write(
        &root,
        "src/lib.rs",
        "pub mod a;\npub mod b;\npub use b::Thing;\n",
    );
    let moved = map(&root);
    assert_eq!(int(&moved, "files_parsed"), 2, "{moved}");
    assert_eq!(dependents(&root, "src/a.rs"), ["src/lib.rs"]);
    assert_eq!(
        dependents(&root, "src/b.rs"),
        ["src/lib.rs", "tests/uses.rs"]
    );

    // A change that leaves the `use` items and item names alone parses that file only.
    write(
        &root,
        "src/lib.rs",
        "pub mod a;\npub mod b;\n// b's Thing\npub use b::Thing;\n",
    );
    assert_eq!(int(&map(&root), "files_parsed"), 1);

    // Removing the re-export removes the edge through it.
    write(&root, "src/lib.rs", "pub mod a;\npub mod b;\n");
    map(&root);
    assert_eq!(dependents(&root, "src/b.rs"), ["src/lib.rs"]);
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn a_worktree_overlay_follows_the_re_exports_of_its_own_tree() {
    let base = scratch("worktree");
    let main = base.join("main");
    fs::create_dir_all(main.join(".git/worktrees/lane")).unwrap();
    write(&main, "map_paths.txt", "src\ntests\n");
    package(&main, ".", "lane");
    let files = [
        ("src/lib.rs", "pub mod a;\npub mod b;\npub use a::Thing;\n"),
        ("src/a.rs", "pub struct Thing;\n"),
        ("src/b.rs", "pub struct Thing;\n"),
        ("tests/uses.rs", "use lane::Thing;\n#[test]\nfn t() {}\n"),
    ];
    for (rel, text) in files {
        write(&main, rel, text);
    }
    map(&main);
    let tree = base.join("lane");
    for (rel, text) in files {
        write(&tree, rel, text);
    }
    write(
        &tree,
        "Cargo.toml",
        &fs::read_to_string(main.join("Cargo.toml")).unwrap(),
    );
    let gitdir = main.join(".git/worktrees/lane");
    fs::write(gitdir.join("commondir"), "../..\n").unwrap();
    fs::write(tree.join(".git"), format!("gitdir: {}\n", gitdir.display())).unwrap();
    // The branch re-exports b's Thing instead.
    write(
        &tree,
        "src/lib.rs",
        "pub mod a;\npub mod b;\npub use b::Thing;\n",
    );

    let wt = tree.display().to_string();
    let over = dispatch(
        "get_dependents",
        &main,
        &["src/b.rs".into()],
        &flags(&[("worktree_root", &wt)]),
    );
    assert_eq!(
        strings(&over, "dependents"),
        ["src/lib.rs", "tests/uses.rs"],
        "{over}"
    );
    let plain = dispatch("get_dependents", &main, &["src/b.rs".into()], &flags(&[]));
    assert_eq!(strings(&plain, "dependents"), ["src/lib.rs"], "{plain}");
    let _ = fs::remove_dir_all(&base);
}
