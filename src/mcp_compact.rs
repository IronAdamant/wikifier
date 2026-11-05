//! Compact default replies for the MCP tools whose output grows with the repository.
//! On a 587-file workspace `health` was 307 KB, `get_resolution_diagnostics` 347 KB,
//! `get_cycles` 47 KB and `get_dependents` of a core file 16 KB. Each now answers with
//! the counts plus the first `limit` items and says how many it left out; `full: true`
//! returns everything. The CLI is unchanged.

use std::collections::BTreeMap;

use crate::jsonutil::Json;

/// Tools with a compact default, and how many items they keep when no `limit` is given.
pub const DEFAULT_LIMITS: &[(&str, usize)] = &[
    ("health", 10),
    ("get_cycles", 5),
    ("get_dependents", 50),
    ("prepare_edit", 25),
    ("get_resolution_diagnostics", 20),
];

/// Files listed per cycle in a compact `get_cycles`; `size` keeps the full count.
pub const CYCLE_FILES: usize = 10;

pub fn default_limit(tool: &str) -> Option<usize> {
    DEFAULT_LIMITS
        .iter()
        .find(|(name, _)| *name == tool)
        .map(|(_, limit)| *limit)
}

/// Shrink `value`, the full result of `tool`, to its compact form.
pub fn compact(tool: &str, mut value: Json, limit: usize) -> Json {
    if value.get("success").and_then(|s| s.as_bool()) != Some(true) {
        return value;
    }
    match tool {
        "health" => {
            let Some(Json::Array(mut rows)) = value.get("entries").cloned() else {
                return value;
            };
            let total = rows.len();
            rows.sort_by_key(health_rank);
            let kept: Vec<Json> = rows
                .into_iter()
                .take(limit)
                .map(|row| without(row, &["source_content_hash"]))
                .collect();
            value.insert("entries", Json::Array(kept));
            value.insert("entries_total", Json::Int(total as i64));
            value.insert(
                "entries_order",
                Json::String("red, then changed yellow, then initial stubs, then green".into()),
            );
        }
        "get_cycles" => {
            if let Some(Json::Array(cycles)) = value.get("cycles").cloned() {
                let trimmed: Vec<Json> = cycles.into_iter().map(trim_cycle).collect();
                value.insert("cycles", Json::Array(trimmed));
            }
            cap(&mut value, "reverse_dependencies", limit, None);
        }
        "get_dependents" | "prepare_edit" => {
            let dirs = value
                .get("dependents")
                .and_then(|v| v.as_array())
                .filter(|items| items.len() > limit)
                .map(by_dir);
            if cap(&mut value, "dependents", limit, Some("dependents_total")) {
                if let Some(dirs) = dirs {
                    value.insert("dependent_dirs", dirs);
                }
            }
        }
        "get_resolution_diagnostics" => {
            for key in ["notes", "actionable_low_conf_edges"] {
                let total_key = format!("{key}_total");
                cap(&mut value, key, limit, Some(&total_key));
            }
        }
        _ => {}
    }
    value
}

/// Keep the first `limit` items of `value[key]`. True when items were left out; then
/// `total_key` (if any) gets the full count.
fn cap(value: &mut Json, key: &str, limit: usize, total_key: Option<&str>) -> bool {
    let Some(Json::Array(items)) = value.get(key).cloned() else {
        return false;
    };
    if items.len() <= limit {
        return false;
    }
    let total = items.len();
    value.insert(key, Json::Array(items.into_iter().take(limit).collect()));
    if let Some(total_key) = total_key {
        value.insert(total_key, Json::Int(total as i64));
    }
    true
}

fn health_rank(row: &Json) -> u8 {
    let status = row.get("status").and_then(|s| s.as_str()).unwrap_or("");
    let reason = row.get("reason").and_then(|s| s.as_str()).unwrap_or("");
    if status.contains("Red") {
        0
    } else if status.contains("Yellow") && reason != "Initial stub" {
        1
    } else if status.contains("Yellow") {
        2
    } else {
        3
    }
}

fn without(mut row: Json, keys: &[&str]) -> Json {
    if let Json::Object(map) = &mut row {
        for key in keys {
            map.remove(*key);
        }
    }
    row
}

fn trim_cycle(mut cycle: Json) -> Json {
    if let Some(Json::Array(files)) = cycle.get("files").cloned() {
        if files.len() > CYCLE_FILES {
            cycle.insert(
                "files",
                Json::Array(files.into_iter().take(CYCLE_FILES).collect()),
            );
            cycle.insert("files_truncated", Json::Bool(true));
        }
    }
    cycle
}

/// Importer counts by parent directory, largest first, at most 20 directories.
fn by_dir(items: &[Json]) -> Json {
    let mut counts: BTreeMap<String, i64> = BTreeMap::new();
    for item in items {
        if let Some(path) = item.as_str() {
            let dir = path.rsplit_once('/').map(|(dir, _)| dir).unwrap_or(".");
            *counts.entry(format!("{dir}/")).or_insert(0) += 1;
        }
    }
    let mut ranked: Vec<(String, i64)> = counts.into_iter().collect();
    ranked.sort_by(|a, b| b.1.cmp(&a.1).then_with(|| a.0.cmp(&b.0)));
    Json::Array(
        ranked
            .into_iter()
            .take(20)
            .map(|(dir, n)| Json::obj(vec![("dir", Json::String(dir)), ("n", Json::Int(n))]))
            .collect(),
    )
}
