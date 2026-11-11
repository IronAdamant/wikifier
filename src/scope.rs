//! Map scope. A missing configured directory is an error scope, not a full-tree walk.
//! Three or more child projects make the root a container: do not walk it.

use std::fs;
use std::path::{Path, PathBuf};

pub const SOURCE_EXTS: &[&str] = &[
    ".py", ".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs", ".mts", ".cts", ".rs", ".go", ".c", ".h",
    ".cpp", ".cc", ".cxx", ".hpp", ".hh", ".cs", ".java",
];

const DEFAULT_EXCLUDES: &[&str] = &[
    "node_modules",
    ".git",
    "dist",
    "build",
    ".next",
    "coverage",
    "__pycache__",
    "tmp",
    "temp",
    ".turbo",
    ".cache",
    "target",
    "out",
    ".wikifier_staging",
    ".venv",
    "venv",
];

#[derive(Clone, Debug)]
pub struct Scope {
    pub prefixes: Vec<String>,
    pub full_tree: bool,
    pub missing_dirs: Vec<String>,
    pub container: bool,
    pub child_count: usize,
    pub child_sample: Vec<String>,
    pub warnings: Vec<String>,
    pub bare_dot: bool,
    pub ok: bool,
}

impl Scope {
    pub fn allows_walk(&self) -> bool {
        !self.container
            && self.missing_dirs.is_empty()
            && (self.full_tree || !self.prefixes.is_empty())
    }
}

pub fn detect(root: &Path) -> Scope {
    let mut warnings = Vec::new();
    let (child_count, child_sample) = child_projects(root);
    let container = child_count >= 3;
    if container {
        warnings.push(format!(
            "project_root looks like a multi-project container ({child_count} child projects e.g. {child_sample:?}). Target a single child project instead."
        ));
    }
    let monitored = read_path_list(root, "monitored_paths.txt");
    let map_paths = read_path_list(root, "map_paths.txt");
    let bare_dot = monitored.is_empty() || monitored.iter().any(|p| p == "." || p == "./");
    if bare_dot && !container {
        warnings
            .push("monitored_paths is bare '.' or missing. Prefer lean package roots.".to_string());
    }
    let (prefixes, missing, full_tree) = resolve_prefixes(root, &map_paths, &monitored);
    if !missing.is_empty() {
        warnings.push(format!(
            "configured directory scope is missing: {}. Not walking the project root.",
            missing.join(", ")
        ));
    }
    let ok = warnings.is_empty();
    Scope {
        prefixes,
        full_tree: full_tree && missing.is_empty() && !container,
        missing_dirs: missing,
        container,
        child_count,
        child_sample,
        warnings,
        bare_dot,
        ok,
    }
}

fn child_projects(root: &Path) -> (usize, Vec<String>) {
    let mut n = 0;
    let mut sample = Vec::new();
    let entries = match fs::read_dir(root) {
        Ok(e) => e,
        Err(_) => return (0, sample),
    };
    for ent in entries.flatten() {
        let name = ent.file_name();
        let name = name.to_string_lossy();
        if name.starts_with('.') {
            continue;
        }
        let path = ent.path();
        if !path.is_dir() {
            continue;
        }
        if path.join(".git").exists()
            || path.join("file_health.json").exists()
            || path.join(".wikifier_staging").is_dir()
        {
            n += 1;
            if sample.len() < 8 {
                sample.push(name.into_owned());
            }
        }
    }
    (n, sample)
}

fn resolve_prefixes(
    root: &Path,
    map_paths: &[String],
    monitored: &[String],
) -> (Vec<String>, Vec<String>, bool) {
    if !map_paths.is_empty() {
        return split_existing(root, map_paths);
    }
    let mon_dirs: Vec<String> = monitored
        .iter()
        .filter(|p| !p.starts_with('#') && *p != "." && *p != "./")
        .filter(|p| {
            let path = resolve_entry(root, p);
            path.is_dir() || looks_like_dir(p)
        })
        .cloned()
        .collect();
    if !mon_dirs.is_empty() {
        return split_existing(root, &mon_dirs);
    }
    (Vec::new(), Vec::new(), true)
}

fn looks_like_dir(p: &str) -> bool {
    let suf = Path::new(p.trim_end_matches('/'))
        .extension()
        .and_then(|s| s.to_str())
        .unwrap_or("");
    suf.is_empty()
}

fn split_existing(root: &Path, entries: &[String]) -> (Vec<String>, Vec<String>, bool) {
    let mut prefixes = Vec::new();
    let mut missing = Vec::new();
    for raw in entries {
        let path = resolve_entry(root, raw);
        if path.is_dir() {
            let rel = rel_prefix(root, &path);
            if rel == "." {
                return (Vec::new(), Vec::new(), true);
            }
            if !prefixes.contains(&rel) {
                prefixes.push(rel);
            }
        } else if path.is_file() {
            if let Some(parent) = path.parent() {
                let rel = rel_prefix(root, parent);
                if rel != "." && !prefixes.contains(&rel) {
                    prefixes.push(rel);
                }
            }
        } else if looks_like_dir(raw) {
            missing.push(raw.trim_end_matches('/').to_string());
        }
    }
    if prefixes.is_empty() && !missing.is_empty() {
        return (Vec::new(), missing, false);
    }
    (prefixes, missing, false)
}

fn resolve_entry(root: &Path, raw: &str) -> PathBuf {
    let p = Path::new(raw);
    if p.is_absolute() {
        p.to_path_buf()
    } else {
        root.join(raw.trim_end_matches('/'))
    }
}

fn rel_prefix(root: &Path, path: &Path) -> String {
    path.strip_prefix(root)
        .unwrap_or(path)
        .components()
        .map(|c| c.as_os_str().to_string_lossy())
        .collect::<Vec<_>>()
        .join("/")
}

pub fn read_path_list(root: &Path, name: &str) -> Vec<String> {
    let text = match fs::read_to_string(crate::worktree::state(root, name)) {
        Ok(t) => t,
        Err(_) => return Vec::new(),
    };
    let mut out = Vec::new();
    for line in text.lines() {
        let p = line.trim();
        if p.is_empty() || p.starts_with('#') {
            continue;
        }
        let p = p
            .split_whitespace()
            .next()
            .unwrap_or("")
            .trim_end_matches('/');
        if p.is_empty() || p == "." || p == "./" {
            continue;
        }
        out.push(p.to_string());
    }
    out
}

pub fn excludes(root: &Path) -> (Vec<String>, Vec<String>) {
    let mut names: Vec<String> = DEFAULT_EXCLUDES.iter().map(|s| (*s).to_string()).collect();
    let mut globs = Vec::new();
    let text = fs::read_to_string(crate::worktree::state(root, "exclude_patterns.txt"))
        .unwrap_or_default();
    for line in text.lines() {
        let p = line.trim();
        if p.is_empty() || p.starts_with('#') {
            continue;
        }
        let p = p.split_whitespace().next().unwrap_or("");
        if p.contains('*') || p.contains('?') || p.contains('[') {
            globs.push(p.to_string());
        }
        names.push(p.trim_end_matches("/*").to_string());
    }
    (names, globs)
}

pub fn is_source(path: &Path) -> bool {
    let name = path.file_name().and_then(|s| s.to_str()).unwrap_or("");
    let lower = name.to_ascii_lowercase();
    SOURCE_EXTS.iter().any(|ext| lower.ends_with(ext))
}

pub fn collect(root: &Path, scope: &Scope) -> Result<Vec<PathBuf>, String> {
    if scope.container {
        return Err("container root is not a project".into());
    }
    if !scope.missing_dirs.is_empty() {
        return Err(format!("missing scope: {}", scope.missing_dirs.join(", ")));
    }
    let (ex_names, ex_globs) = excludes(root);
    let mut out = Vec::new();
    if scope.full_tree {
        walk(root, root, &ex_names, &ex_globs, &mut out);
    } else {
        for pref in &scope.prefixes {
            let dir = root.join(pref);
            if dir.is_dir() {
                walk(root, &dir, &ex_names, &ex_globs, &mut out);
            }
        }
    }
    out.sort();
    out.dedup();
    Ok(out)
}

fn walk(root: &Path, dir: &Path, ex_names: &[String], ex_globs: &[String], out: &mut Vec<PathBuf>) {
    let entries = match fs::read_dir(dir) {
        Ok(e) => e,
        Err(_) => return,
    };
    for ent in entries.flatten() {
        let path = ent.path();
        let name = ent.file_name().to_string_lossy().to_string();
        if ex_names.iter().any(|n| n == &name) || ex_globs.iter().any(|g| fnmatch(g, &name)) {
            continue;
        }
        // The directory entry already knows its type; a symlink still follows its target.
        let (is_dir, is_file) = match ent.file_type() {
            Ok(kind) if !kind.is_symlink() => (kind.is_dir(), kind.is_file()),
            _ => (path.is_dir(), path.is_file()),
        };
        if is_dir {
            walk(root, &path, ex_names, ex_globs, out);
        } else if is_file && is_source(&path) && path.starts_with(root) {
            out.push(path);
        }
    }
}

fn fnmatch(pat: &str, text: &str) -> bool {
    fn rec(p: &[u8], t: &[u8]) -> bool {
        if p.is_empty() {
            return t.is_empty();
        }
        if p[0] == b'*' {
            return rec(&p[1..], t) || (!t.is_empty() && rec(p, &t[1..]));
        }
        if t.is_empty() {
            return false;
        }
        if p[0] == b'?' || p[0] == t[0] {
            return rec(&p[1..], &t[1..]);
        }
        false
    }
    rec(pat.as_bytes(), text.as_bytes())
}

pub fn rel_of(root: &Path, path: &Path) -> String {
    path.strip_prefix(root)
        .unwrap_or(path)
        .components()
        .map(|c| c.as_os_str().to_string_lossy().replace('\\', "/"))
        .collect::<Vec<_>>()
        .join("/")
}

/// Map roots for a fresh `init`: `src/` when it exists, else every top-level directory that
/// holds a source file (a Cargo workspace's `crates/`, a Python package dir, `tests/`).
/// Falls back to `src/` so the scope error still names a directory to create.
pub fn default_map_roots(root: &Path) -> Vec<String> {
    if root.join("src").is_dir() {
        return vec!["src/".to_string()];
    }
    let mut found: Vec<String> = fs::read_dir(root)
        .map(|entries| {
            entries
                .flatten()
                .filter(|ent| ent.path().is_dir())
                .map(|ent| ent.file_name().to_string_lossy().into_owned())
                .filter(|name| !skip_dir(name) && has_source(&root.join(name), 6))
                .map(|name| format!("{name}/"))
                .collect()
        })
        .unwrap_or_default();
    found.sort();
    if found.is_empty() {
        found.push("src/".to_string());
    }
    found
}

fn skip_dir(name: &str) -> bool {
    name.starts_with('.') || DEFAULT_EXCLUDES.contains(&name)
}

fn has_source(dir: &Path, depth: usize) -> bool {
    let Ok(entries) = fs::read_dir(dir) else {
        return false;
    };
    let mut subdirs = Vec::new();
    for ent in entries.flatten() {
        let path = ent.path();
        if path.is_dir() {
            if depth > 0 && !skip_dir(&ent.file_name().to_string_lossy()) {
                subdirs.push(path);
            }
        } else if is_source(&path) {
            return true;
        }
    }
    subdirs.into_iter().any(|sub| has_source(&sub, depth - 1))
}

/// A caller's file argument as the map and health key: project-relative and `/`-separated.
/// Accepts `./src/a.rs`, `src\a.rs`, and an absolute path under `root`, so a Windows agent
/// does not get an empty lookup or a second health row for the same file.
pub fn rel_arg(root: &Path, file: &str) -> String {
    let path = Path::new(file);
    if path.is_absolute() {
        if let Ok(rel) = path.strip_prefix(root) {
            return rel_of(Path::new(""), rel);
        }
        if let (Ok(real_root), Ok(real_path)) = (root.canonicalize(), path.canonicalize()) {
            if let Ok(rel) = real_path.strip_prefix(&real_root) {
                return rel_of(Path::new(""), rel);
            }
        }
    }
    let slashed = file.replace('\\', "/");
    let mut rel = slashed.as_str();
    while let Some(rest) = rel.strip_prefix("./") {
        rel = rest;
    }
    rel.to_string()
}
