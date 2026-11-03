//! Cycle severity and reverse-dependency ranking.
//! `library.md` stays the short tree. This rides on `cycles` JSON.

use std::collections::BTreeMap;

use crate::jsonutil::Json;

pub fn enrich(value: Json, analysis: bool, max_items: Option<usize>) -> Json {
    if !analysis {
        return cap_cycles(value, max_items);
    }
    let mut value = value;
    let ranked = reverse_rank(value.get("cycles"));
    if let Some(Json::Array(cycles)) = value.get("cycles").cloned() {
        let scored: Vec<Json> = cycles.into_iter().map(score_cycle).collect();
        value.insert("cycles", Json::Array(scored));
    }
    value.insert("reverse_dependencies", Json::Array(ranked));
    value.insert("analysis", Json::Bool(true));
    cap_cycles(value, max_items)
}

fn cap_cycles(mut value: Json, max_items: Option<usize>) -> Json {
    let Some(limit) = max_items else {
        return value;
    };
    if let Some(Json::Array(cycles)) = value.get("cycles").cloned() {
        let truncated = cycles.len() > limit;
        let kept: Vec<Json> = cycles.into_iter().take(limit).collect();
        value.insert("cycles", Json::Array(kept));
        if truncated {
            value.insert("truncated", Json::Bool(true));
        }
    }
    value
}

fn score_cycle(cycle: Json) -> Json {
    let size = cycle
        .get("size")
        .and_then(|v| match v {
            Json::Int(n) => Some(*n),
            _ => None,
        })
        .unwrap_or(0);
    let blast = cycle
        .get("external_edges")
        .and_then(|v| match v {
            Json::Int(n) => Some(*n),
            _ => None,
        })
        .unwrap_or(0);
    let score = (size as f64) * 2.0 + (blast as f64) * 0.8;
    let severity = if size >= 8 || blast >= 20 {
        "HIGH"
    } else if size >= 3 || blast >= 5 {
        "MEDIUM"
    } else {
        "LOW"
    };
    let (strategy, rationale) = if size <= 2 {
        (
            "audit_and_directional_split",
            "Two-file cycle. Pick the owner of the shared idea and point the other file at it.",
        )
    } else {
        ("extract_shared_module", "More than two files depend on each other. Move the shared types into a module that none of them own.")
    };
    let mut cycle = cycle;
    cycle.insert("severity", Json::String(severity.into()));
    cycle.insert("score", Json::Float(score));
    cycle.insert("external_blast_radius", Json::Int(blast));
    cycle.insert(
        "recommendation",
        Json::obj(vec![
            ("strategy", Json::String(strategy.into())),
            ("rationale", Json::String(rationale.into())),
        ]),
    );
    cycle
}

/// Rank files by how many cycle peers point at them is not the graph rank.
/// Callers pass the cycle list only when they have no edge index.
/// The API fills `reverse_dependencies` from the real edge list before enrich
/// when it can. This helper ranks destinations mentioned inside the cycles
/// so a cycles-only payload still has an order.
fn reverse_rank(cycles: Option<&Json>) -> Vec<Json> {
    let mut counts: BTreeMap<String, i64> = BTreeMap::new();
    if let Some(Json::Array(items)) = cycles {
        for cycle in items {
            if let Some(Json::Array(files)) = cycle.get("files") {
                for file in files {
                    if let Some(name) = file.as_str() {
                        *counts.entry(name.to_string()).or_insert(0) += 1;
                    }
                }
            }
        }
    }
    ranked(counts)
}

pub fn rank_dependents(edges: &[(String, String)]) -> Vec<Json> {
    let mut counts: BTreeMap<String, i64> = BTreeMap::new();
    for (_src, dst) in edges {
        *counts.entry(dst.clone()).or_insert(0) += 1;
    }
    ranked(counts)
}

fn ranked(counts: BTreeMap<String, i64>) -> Vec<Json> {
    let mut rows: Vec<(String, i64)> = counts.into_iter().collect();
    rows.sort_by(|a, b| b.1.cmp(&a.1).then_with(|| a.0.cmp(&b.0)));
    rows.truncate(20);
    rows.into_iter()
        .map(|(file, count)| {
            Json::obj(vec![
                ("file", Json::String(file)),
                ("dependents", Json::Int(count)),
            ])
        })
        .collect()
}
