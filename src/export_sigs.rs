//! Rust export tables between `update-maps` runs.
//!
//! An importer's `via_barrel` edge depends on the `use` items and item names of the
//! modules its path went through, not only on its own text. `wk_cache/rust_exports.tsv`
//! keeps each Rust file's export entries (`parse::export_entries`). When a parsed file's
//! entries change, the files that name a changed entry are parsed again, and so on through
//! the modules that pass those names on, up to the re-export hop limit.

use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};

use crate::parse::{self, Scan};

fn path(root: &Path) -> PathBuf {
    crate::cache::cache_root(root).join("rust_exports.tsv")
}

/// Which names of a module changed. `All` when a glob changed or nothing was recorded.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) enum Changed {
    All,
    Names(BTreeSet<String>),
}

impl Changed {
    /// The text names one of the changed names as a whole word.
    fn named_in(&self, text: &str) -> bool {
        match self {
            Changed::All => true,
            Changed::Names(names) => names.iter().any(|name| has_word(text, name)),
        }
    }

    /// The module has a `use` item that can pass a changed name on to its importers.
    fn passed_on_by(&self, scan: &Scan) -> bool {
        match self {
            Changed::All => !scan.rust_uses.is_empty(),
            Changed::Names(names) => scan
                .rust_uses
                .iter()
                .any(|entry| entry.glob || names.contains(&entry.name)),
        }
    }
}

fn has_word(text: &str, word: &str) -> bool {
    let bytes = text.as_bytes();
    let is_word = |b: u8| b.is_ascii_alphanumeric() || b == b'_';
    text.match_indices(word).any(|(at, _)| {
        let end = at + word.len();
        (at == 0 || !is_word(bytes[at - 1])) && (end == bytes.len() || !is_word(bytes[end]))
    })
}

fn key(entry: &str) -> &str {
    entry.split(' ').next().unwrap_or("")
}

/// The names whose entries differ between two sorted entry lists.
fn diff(old: &[String], new: &[String]) -> Changed {
    let group = |entries: &[String]| {
        let mut by: BTreeMap<String, Vec<String>> = BTreeMap::new();
        for entry in entries {
            by.entry(key(entry).to_string())
                .or_default()
                .push(entry.clone());
        }
        by
    };
    let (old, new) = (group(old), group(new));
    let names: BTreeSet<String> = old
        .keys()
        .chain(new.keys())
        .filter(|name| old.get(*name) != new.get(*name))
        .cloned()
        .collect();
    if names.contains("*") {
        Changed::All
    } else {
        Changed::Names(names)
    }
}

pub(crate) struct Sigs {
    map: BTreeMap<String, Vec<String>>,
    dirty: bool,
}

impl Sigs {
    /// A missing or unreadable file is empty: a parsed Rust file then counts as `All`.
    pub(crate) fn load(root: &Path) -> Sigs {
        let text = std::fs::read_to_string(path(root)).unwrap_or_default();
        let map = text
            .lines()
            .filter_map(|line| {
                let mut parts = line.split('\t');
                let rel = parts.next().filter(|rel| !rel.is_empty())?;
                Some((rel.to_string(), parts.map(str::to_string).collect()))
            })
            .collect();
        Sigs { map, dirty: false }
    }

    /// Record the parsed Rust files' entries. Returns each file whose entries changed,
    /// with the names that changed.
    pub(crate) fn update<'a>(
        &mut self,
        parsed: impl Iterator<Item = (&'a String, &'a Scan)>,
    ) -> Vec<(String, Changed)> {
        let mut changed = Vec::new();
        for (rel, scan) in parsed {
            if !rel.ends_with(".rs") {
                continue;
            }
            let entries = parse::export_entries(scan);
            let what = match self.map.get(rel) {
                Some(old) if *old == entries => continue,
                Some(old) => diff(old, &entries),
                None => Changed::All,
            };
            self.map.insert(rel.clone(), entries);
            self.dirty = true;
            changed.push((rel.clone(), what));
        }
        changed
    }

    pub(crate) fn forget(&mut self, rel: &str) {
        if self.map.remove(rel).is_some() {
            self.dirty = true;
        }
    }

    /// Written after the cache commit. A lost write only costs extra parsing next run.
    pub(crate) fn save(&self, root: &Path) -> Result<(), String> {
        if !self.dirty {
            return Ok(());
        }
        let mut text = String::new();
        for (rel, entries) in &self.map {
            text.push_str(rel);
            for entry in entries {
                text.push('\t');
                text.push_str(entry);
            }
            text.push('\n');
        }
        crate::cache::atomic_write(&path(root), text.as_bytes())
    }
}

/// Rust files to parse again because a module they name changed what it offers: the
/// importers of each changed module (from the stored map) whose text names a changed name,
/// then, through those that pass such a name on with a `use` item, their importers, for up
/// to the re-export hop limit. Files in `parsed` are already done; only files in `scoped`
/// are returned.
pub(crate) fn importers_to_reparse(
    root: &Path,
    changed: Vec<(String, Changed)>,
    importers: impl Fn(&str) -> BTreeSet<String>,
    parsed: &BTreeSet<String>,
    scoped: &BTreeSet<String>,
) -> BTreeSet<String> {
    let mut out = BTreeSet::new();
    let mut visited: BTreeSet<String> = changed.iter().map(|(rel, _)| rel.clone()).collect();
    let mut frontier = changed;
    for _ in 0..=parse::RUST_GLOB_DEPTH {
        let mut next = Vec::new();
        for (module, what) in &frontier {
            for importer in importers(module) {
                if !importer.ends_with(".rs")
                    || !scoped.contains(&importer)
                    || visited.contains(&importer)
                {
                    continue;
                }
                let Ok(text) = std::fs::read_to_string(root.join(&importer)) else {
                    continue;
                };
                if !what.named_in(&text) {
                    continue;
                }
                visited.insert(importer.clone());
                if !parsed.contains(&importer) {
                    out.insert(importer.clone());
                }
                if what.passed_on_by(&parse::scan_file(&root.join(&importer))) {
                    next.push((importer, what.clone()));
                }
            }
        }
        if next.is_empty() {
            break;
        }
        frontier = next;
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn entries(list: &[&str]) -> Vec<String> {
        list.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn a_diff_names_what_changed_and_a_glob_change_is_everything() {
        let old = entries(&["Input u input::Input false true", "f d true"]);
        let new = entries(&["Input u other::Input false true", "f d true", "g d true"]);
        assert_eq!(
            diff(&old, &new),
            Changed::Names(["Input", "g"].iter().map(|s| s.to_string()).collect())
        );
        let glob = entries(&["* u record true true"]);
        assert_eq!(diff(&old, &glob), Changed::All);
    }

    #[test]
    fn a_name_counts_only_as_a_whole_word() {
        let what = Changed::Names(["Input".to_string()].into_iter().collect());
        assert!(what.named_in("use sp::Input;"));
        assert!(!what.named_in("use sp::InputMap; let my_Input2 = 1;"));
    }
}
