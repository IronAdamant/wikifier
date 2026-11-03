//! Actionable low-confidence edge counts.
//! Updated for files `update-maps` actually parsed, so a warm skip does not rescan the tree.

use std::collections::BTreeMap;
use std::fs;
use std::path::Path;

use crate::cache;

const NAME: &str = "low_conf.tsv";

fn path(root: &Path) -> std::path::PathBuf {
    root.join(".wikifier_staging").join(NAME)
}

fn confidence(conditional: bool, dynamic: bool, via_barrel: bool) -> f64 {
    cache::confidence_of(conditional, dynamic, via_barrel)
}

/// Resolved internal edges an agent should look at: below 0.65 and not dynamic.
pub fn count_edges(edges: &[(bool, bool, bool)]) -> i64 {
    edges
        .iter()
        .filter(|(conditional, dynamic, via_barrel)| {
            !dynamic && confidence(*conditional, *dynamic, *via_barrel) < 0.65
        })
        .count() as i64
}

/// Merge counts for files parsed in this run. Missing files are left as they were.
pub fn store_updates(root: &Path, updates: &[(String, i64)], removed: &[String]) {
    if updates.is_empty() && removed.is_empty() && path(root).is_file() {
        return;
    }
    let mut map = read_map(root);
    for rel in removed {
        map.remove(rel);
    }
    for (rel, count) in updates {
        if *count <= 0 {
            map.remove(rel);
        } else {
            map.insert(rel.clone(), *count);
        }
    }
    let _ = fs::create_dir_all(root.join(".wikifier_staging"));
    let mut body = String::new();
    for (rel, count) in &map {
        body.push_str(rel);
        body.push('\t');
        body.push_str(&count.to_string());
        body.push('\n');
    }
    let _ = fs::write(path(root), body);
}

pub fn actionable_total(root: &Path, directory: Option<&str>) -> i64 {
    let prefix = directory
        .map(|d| d.trim_matches('/'))
        .filter(|d| !d.is_empty());
    read_map(root)
        .into_iter()
        .filter(|(rel, _)| {
            prefix
                .map(|p| rel == p || rel.starts_with(&format!("{p}/")))
                .unwrap_or(true)
        })
        .map(|(_, n)| n)
        .sum()
}

fn read_map(root: &Path) -> BTreeMap<String, i64> {
    let mut map = BTreeMap::new();
    let text = fs::read_to_string(path(root)).unwrap_or_default();
    for line in text.lines() {
        if let Some((rel, count)) = line.split_once('\t') {
            if let Ok(n) = count.trim().parse::<i64>() {
                if n > 0 {
                    map.insert(rel.to_string(), n);
                }
            }
        }
    }
    map
}
