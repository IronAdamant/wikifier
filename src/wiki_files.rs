//! Where a source file's wiki lives.
//! Sibling `<file>.wiki.md` wins, then the same fallbacks the Python package used.

use std::path::{Path, PathBuf};

const WIKI_DIRS: &[&str] = &["docs/wiki", "docs", "wiki", "documentation", ".wiki"];

/// First existing wiki for `rel`, or None when the source has no companion summary.
/// For a worktree each candidate is the tree's file, else main's (wikis are often
/// gitignored, so a fresh worktree has none of its own).
pub fn find_wiki(root: &Path, rel: &str) -> Option<PathBuf> {
    let rel_path = Path::new(rel);
    let source = root.join(rel);
    let mut candidates: Vec<String> = Vec::new();
    candidates.push(format!("{rel}.wiki.md"));
    candidates.push(format!("{rel}.md"));
    let joined = |dir: &Path, name: String| -> String {
        let dir = dir.to_string_lossy().replace('\\', "/");
        if dir.is_empty() {
            name
        } else {
            format!("{dir}/{name}")
        }
    };
    if let (Some(parent), Some(stem)) = (rel_path.parent(), rel_path.file_stem()) {
        let stem = stem.to_string_lossy();
        candidates.push(joined(parent, format!("{stem}.wiki.md")));
        candidates.push(joined(parent, format!("{stem}.md")));
    }
    let name = rel_path
        .file_name()
        .map(|s| s.to_string_lossy().to_string())
        .unwrap_or_default();
    let stem = rel_path
        .file_stem()
        .map(|s| s.to_string_lossy().to_string())
        .unwrap_or_default();
    for dir in WIKI_DIRS {
        candidates.push(format!("{dir}/{name}.wiki.md"));
        candidates.push(format!("{dir}/{name}.md"));
        candidates.push(format!("{dir}/{stem}.wiki.md"));
        candidates.push(format!("{dir}/{stem}.md"));
    }
    candidates
        .into_iter()
        .map(|candidate| crate::worktree::state(root, &candidate))
        .find(|path| path.is_file() && path != &source)
}

pub fn read_wiki(root: &Path, rel: &str) -> (Option<PathBuf>, String) {
    match find_wiki(root, rel) {
        Some(path) => {
            let text = std::fs::read_to_string(&path).unwrap_or_default();
            (Some(path), text)
        }
        None => (None, String::new()),
    }
}
