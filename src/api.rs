//! One function per agent-facing operation. CLI and MCP both call these.

use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};

use crate::artifacts::{self, HealthRow, JournalEntry};
use crate::cache::{self, FileUpdate, Session};
use crate::jsonutil::Json;
use crate::scope::{self, Scope};
use crate::sha256::{file_sha256_prefixed, sha256_prefixed};
use crate::timeutil::local_stamp;

pub const VERSION: &str = env!("CARGO_PKG_VERSION");

pub const MCP_TOOLS: &[&str] = &[
    "check_changes",
    "record_change",
    "record_deletion",
    "mark_green",
    "record_changes",
    "verify_wikis",
    "prepare_edit",
    "session_bootstrap",
    "suggest_next_actions",
    "list_core_tools",
    "list_paths",
    "search_journal",
    "why_file",
    "get_dependencies",
    "get_dependents",
    "get_cycles",
    "get_resolution_diagnostics",
    "get_file_wiki",
    "get_files_needing_attention",
    "get_project_status",
    "get_current_project_root",
    "get_barrel_reports",
    "get_incremental_status",
    "update_maps",
    "health",
    "validate",
    "list_healable_stubs",
    "heal_stubs",
    "seed_source_content_hashes",
    "journal",
    "issues",
];

fn ok(pairs: Vec<(&str, Json)>) -> Json {
    let mut all = vec![("success", Json::Bool(true))];
    all.extend(pairs);
    Json::obj(all)
}

fn fail(error_type: &str, error: impl Into<String>) -> Json {
    Json::obj(vec![
        ("success", Json::Bool(false)),
        ("error", Json::String(error.into())),
        ("error_type", Json::String(error_type.into())),
    ])
}

fn root_or_err(root: Option<&Path>) -> Result<PathBuf, Json> {
    let root = match root {
        Some(p) => p.to_path_buf(),
        None => std::env::current_dir().map_err(|e| fail("ProjectRootError", e.to_string()))?,
    };
    if !root.is_dir() {
        return Err(fail("ProjectRootError", format!("project root does not exist: {}", root.display())));
    }
    Ok(root)
}

fn scope_json(scope: &Scope) -> Json {
    Json::obj(vec![
        ("ok", Json::Bool(scope.ok)),
        ("container", Json::Bool(scope.container)),
        ("child_project_count", Json::Int(scope.child_count as i64)),
        ("child_project_sample", Json::Array(scope.child_sample.iter().cloned().map(Json::String).collect())),
        ("bare_dot_monitor", Json::Bool(scope.bare_dot)),
        ("full_tree", Json::Bool(scope.full_tree)),
        ("missing_dirs", Json::Array(scope.missing_dirs.iter().cloned().map(Json::String).collect())),
        ("prefixes", Json::Array(scope.prefixes.iter().cloned().map(Json::String).collect())),
        ("warnings", Json::Array(scope.warnings.iter().cloned().map(Json::String).collect())),
    ])
}

fn is_red(status: &str) -> bool {
    status.contains("Red") || status.contains('🔴')
}

fn is_yellow(status: &str) -> bool {
    status.contains("Yellow") || status.contains('🟡')
}

fn is_green(status: &str) -> bool {
    status.contains("Green") || status.contains('🟢')
}

fn health_file_present(root: &Path) -> bool {
    root.join("file_health.json").is_file() || root.join("file_health.md").is_file()
}

fn readiness_of(scope: &Scope, has_map: bool, rows: &[crate::artifacts::HealthRow], has_health_file: bool) -> &'static str {
    // A container or a missing configured directory is a scope risk even when
    // there is no health matrix yet. Do not call that ready_for_daemon.
    if scope.container || !scope.missing_dirs.is_empty() {
        return "map_ok_scope_risk";
    }
    if !has_map || !has_health_file || rows.is_empty() {
        return "blocked";
    }
    if !scope.ok {
        return "map_ok_scope_risk";
    }
    if rows.iter().any(|r| is_red(&r.status)) {
        return "not_ready";
    }
    if rows.iter().any(|r| is_yellow(&r.status) && r.reason != "Initial stub") {
        return "ready_with_agent_wiki_work";
    }
    "ready_for_daemon"
}

pub fn update_maps(root: &Path) -> Json {
    update_maps_opts(root, false, false)
}

/// `full` rehashes every file, including ones whose size and mtime still match.
/// `quiet` keeps `edges_persisted` and omits the edge list.
pub fn update_maps_opts(root: &Path, full: bool, quiet: bool) -> Json {
    let scope = scope::detect(root);
    if scope.container {
        return ok(vec![
            ("readiness", Json::String("map_ok_scope_risk".into())),
            ("map_complete", Json::Bool(false)),
            ("full_tree", Json::Bool(false)),
            ("parseable_files", Json::Int(0)),
            ("files_parsed", Json::Int(0)),
            ("edges", Json::Array(vec![])),
            ("scope", scope_json(&scope)),
            ("message", Json::String("container root refused; target one child project".into())),
        ]);
    }
    if !scope.missing_dirs.is_empty() {
        return fail("ScopeError", format!("missing map directory: {}", scope.missing_dirs.join(", ")));
    }
    let files = match scope::collect(root, &scope) {
        Ok(f) => f,
        Err(e) => return fail("ScopeError", e),
    };
    let mut session = match Session::open(root) {
        Ok(session) => session,
        Err(err) => {
            let kind = if err.contains("locked") { "CacheLocked" } else { "CacheError" };
            return fail_warnings(kind, err, &[]);
        }
    };
    let mut seen = BTreeSet::new();
    let mut skipped = 0i64;
    let mut hashed = 0i64;
    let mut to_parse: Vec<(PathBuf, String, u128, u64, String)> = Vec::new();
    for file in &files {
        let rel = scope::rel_of(root, file);
        seen.insert(rel.clone());
        let (mtime, size) = cache::stat_ns(file).unwrap_or((0, 0));
        let known = session.known(&rel);
        let stat_hit = !full && known.as_ref().is_some_and(|(old_mtime, old_size, old_hash)| {
            *old_mtime != 0 && *old_mtime == mtime && *old_size == size && old_hash.starts_with("sha256:")
        });
        if stat_hit {
            skipped += 1;
            continue;
        }
        let bytes = fs::read(file).unwrap_or_default();
        let hash = sha256_prefixed(&bytes);
        let (mtime, size) = if mtime == 0 && size == 0 {
            cache::stat_ns(file).unwrap_or((0, bytes.len() as u64))
        } else {
            (mtime, if size == 0 { bytes.len() as u64 } else { size })
        };
        hashed += 1;
        if let Some((_, _, old_hash)) = &known {
            if old_hash == &hash && old_hash.starts_with("sha256:") {
                session.note_stat(&rel, mtime, size);
                continue;
            }
        }
        to_parse.push((file.clone(), rel, mtime, size, hash));
    }
    let changed_paths: Vec<PathBuf> = to_parse.iter().map(|(path, _, _, _, _)| path.clone()).collect();
    let analysis = if to_parse.is_empty() {
        crate::parse::Analysis { facts: BTreeMap::new(), scans: std::collections::HashMap::new(), warnings: Vec::new() }
    } else if changed_paths.len() == files.len() {
        crate::parse::analyze_files(root, &files)
    } else {
        crate::parse::analyze_changed(root, &files, &changed_paths)
    };
    let warnings = analysis.warnings.clone();
    for (path, rel, mtime, size, hash) in &to_parse {
        let _ = path;
        let fact = analysis.facts.get(rel);
        let dsts = fact.map(|f| f.dsts.clone()).unwrap_or_default();
        let scan = analysis.scans.get(rel);
        let barrel = scan.map(|s| s.imports.iter().any(|i| matches!(i.kind, crate::parse::Kind::ExportFrom | crate::parse::Kind::ExportStar))).unwrap_or(false);
        let imports: Vec<String> = scan.map(|s| s.imports.iter().map(|i| i.spec.clone()).collect()).unwrap_or_default();
        let barrel_dsts: Vec<String> = dsts.iter().cloned().collect();
        let edge_lines = fact.map(|f| {
            f.internal.iter().map(|(dst, line, names)| format!("{dst}\t{line}\t{}", names.join(","))).collect()
        }).unwrap_or_default();
        let external = fact.map(|f| f.external.clone()).unwrap_or_default();
        let unresolved = fact.map(|f| f.unresolved.clone()).unwrap_or_default();
        session.upsert(&FileUpdate {
            rel: rel.clone(),
            mtime_ns: *mtime,
            size: *size,
            hash: hash.clone(),
            imports,
            dsts,
            edge_lines,
            external,
            unresolved,
        });
        if barrel {
            session.stage_barrel(rel, &barrel_dsts);
        }
    }
    let parsed = to_parse.len() as i64;
    let stale: Vec<String> = session.rels().into_iter().filter(|rel| !seen.contains(rel)).collect();
    for rel in &stale {
        session.remove(rel);
    }
    let mut edge_pairs: Vec<(String, String)> = Vec::new();
    if !quiet {
        for rel in &seen {
            for dst in session.dsts_of(rel) {
                edge_pairs.push((rel.clone(), dst));
            }
        }
    }
    let edge_n: i64 = if quiet {
        seen.iter().map(|rel| session.dsts_of(rel).len() as i64).sum()
    } else {
        edge_pairs.len() as i64
    };
    if let Err(err) = session.commit() {
        let kind = if err.contains("locked") { "CacheLocked" } else { "CacheError" };
        return fail_warnings(kind, err, &warnings);
    }
    let _ = seed_health_from_map(root);
    let edge_json = Json::Array(edge_pairs.into_iter().map(|(src, dst)| {
        Json::obj(vec![("src", Json::String(src)), ("dst", Json::String(dst))])
    }).collect());
    ok(vec![
        ("map_complete", Json::Bool(true)),
        ("full_tree", Json::Bool(scope.full_tree)),
        ("parseable_files", Json::Int(files.len() as i64)),
        ("files_parsed", Json::Int(parsed)),
        ("files_hashed", Json::Int(hashed)),
        ("files_skipped", Json::Int(skipped)),
        ("rehash", Json::Bool(full)),
        ("edges_persisted", Json::Int(edge_n)),
        ("edges_omitted", Json::Bool(quiet)),
        ("edges", edge_json),
        ("scope", scope_json(&scope)),
        ("cache_backend", Json::String("wk_cache".into())),
        ("warnings", Json::Array(warnings.into_iter().map(Json::String).collect())),
    ])
}

fn fail_warnings(error_type: &str, error: impl Into<String>, warnings: &[String]) -> Json {
    let mut value = fail(error_type, error);
    value.insert("warnings", Json::Array(warnings.iter().cloned().map(Json::String).collect()));
    value
}

fn attach_warning(mut value: Json, warning: Option<String>) -> Json {
    if let Some(warning) = warning {
        value.insert("warnings", Json::Array(vec![Json::String(warning)]));
    }
    value
}

fn seed_health_from_map(root: &Path) -> Result<(), String> {
    let mut rows = artifacts::read_health(root);
    let known: BTreeSet<String> = rows.iter().map(|r| r.file.clone()).collect();
    let stamp = local_stamp();
    let mut changed = false;
    for rel in cache::all_paths(root) {
        if known.contains(&rel) {
            continue;
        }
        let hash = file_sha256_prefixed(&root.join(&rel)).unwrap_or_default();
        rows.push(HealthRow {
            file: rel,
            status: "🟡 Yellow".into(),
            last_updated: stamp.clone(),
            reason: "Initial stub".into(),
            source_hash: hash,
            verification: "no_wiki".into(),
        });
        changed = true;
    }
    if changed || !root.join("file_health.json").is_file() && !rows.is_empty() {
        artifacts::write_health(root, &rows)?;
    }
    Ok(())
}

pub fn mapped_edges(root: &Path) -> BTreeSet<(String, String)> {
    cache::edges(root)
}

pub fn load_dependencies(root: &Path, rel: &str) -> Json {
    match cache::load_dependency_view(root, rel) {
        Ok(view) => ok(vec![
            ("file", Json::String(rel.into())),
            ("detail", Json::String("compact".into())),
            ("internal", Json::Array(view.internal.into_iter().map(|e| Json::obj(vec![
                ("path", Json::String(e.path)),
                ("line", Json::Int(e.line)),
                ("names", Json::Array(e.names.into_iter().map(Json::String).collect())),
            ])).collect())),
            ("external", Json::Array(view.external.into_iter().map(Json::String).collect())),
            ("needs_review", Json::Array(view.unresolved.into_iter().map(|(raw, line)| Json::obj(vec![
                ("raw", Json::String(raw)),
                ("line", Json::Int(line)),
            ])).collect())),
        ]),
        Err(e) => fail("CacheError", e),
    }
}

pub fn load_dependents(root: &Path, rel: &str) -> Json {
    match cache::load_dependents(root, rel) {
        Ok(srcs) => ok(vec![
            ("file", Json::String(rel.into())),
            ("dependents", Json::Array(srcs.into_iter().map(Json::String).collect())),
        ]),
        Err(e) => fail("CacheError", e),
    }
}

pub fn list_paths(root: &Path, prefix: &str) -> Json {
    let paths = cache::list_prefix(root, prefix).unwrap_or_default();
    let pref = prefix.trim_matches('/');
    let mut dirs: BTreeMap<String, i64> = BTreeMap::new();
    let mut files = Vec::new();
    for path in &paths {
        let rest = if pref.is_empty() { path.as_str() } else if let Some(r) = path.strip_prefix(pref) { r.trim_start_matches('/') } else { continue };
        if rest.is_empty() {
            files.push(path.clone());
            continue;
        }
        if let Some((dir, _)) = rest.split_once('/') {
            *dirs.entry(dir.to_string()).or_insert(0) += 1;
        } else if !pref.is_empty() && path == pref {
            files.push(path.clone());
        } else if pref.is_empty() {
            files.push(path.clone());
        } else {
            files.push(path.clone());
        }
    }
    // depth-1: a path directly under prefix is a file; a longer path contributes to its first segment
    let mut direct_files = Vec::new();
    let mut dir_counts: BTreeMap<String, i64> = BTreeMap::new();
    for path in &paths {
        let rest = if pref.is_empty() {
            path.clone()
        } else if path == pref {
            continue;
        } else if let Some(r) = path.strip_prefix(&(pref.to_string() + "/")) {
            r.to_string()
        } else {
            continue;
        };
        if let Some((dir, _)) = rest.split_once('/') {
            *dir_counts.entry(format!("{dir}/")).or_insert(0) += 1;
        } else if !rest.is_empty() {
            direct_files.push(path.clone());
        }
    }
    let _ = (dirs, files);
    ok(vec![
        ("prefix", Json::String(pref.into())),
        ("files", Json::Array(direct_files.into_iter().map(Json::String).collect())),
        ("dirs", Json::Array(dir_counts.into_iter().map(|(p, n)| Json::obj(vec![("p", Json::String(p)), ("n", Json::Int(n))])).collect())),
        ("file_count", Json::Int(paths.len() as i64)),
    ])
}

pub fn session_bootstrap(root: &Path) -> Json {
    let scope = scope::detect(root);
    if scope.container || !scope.missing_dirs.is_empty() {
        let actions = Json::Array(vec![Json::obj(vec![
            ("action", Json::String("fix_scope".into())),
            ("priority", Json::Int(1)),
            ("reason", Json::String(scope.warnings.first().cloned().unwrap_or_else(|| "scope risk".into()))),
        ])]);
        return ok(vec![
            ("version", Json::String(VERSION.into())),
            ("readiness", Json::String(readiness_of(&scope, false, &[], false).into())),
            ("health_summary", health_summary(root)),
            ("actions", actions),
            ("files", Json::Array(vec![])),
            ("map_complete", Json::Bool(false)),
            ("scope", scope_json(&scope)),
        ]);
    }
    if cache::all_paths(root).is_empty() {
        let built = update_maps(root);
        if built.get("success").and_then(|s| s.as_bool()) != Some(true) {
            return built;
        }
    }
    let files: Vec<Json> = cache::all_paths(root).into_iter().map(Json::String).collect();
    let rows = artifacts::read_health(root);
    let actions = suggest_next_actions(root);
    let action_list = actions.get("actions").cloned().unwrap_or(Json::Array(vec![]));
    ok(vec![
        ("version", Json::String(VERSION.into())),
        ("readiness", Json::String(readiness_of(&scope, !files.is_empty(), &rows, health_file_present(root)).into())),
        ("health_summary", health_summary(root)),
        ("actions", action_list),
        ("files", Json::Array(files)),
        ("map_complete", Json::Bool(scope.missing_dirs.is_empty() && !scope.container)),
        ("scope", scope_json(&scope)),
    ])
}

fn health_summary(root: &Path) -> Json {
    let rows = artifacts::read_health(root);
    let mut green = 0i64;
    let mut yellow = 0i64;
    let mut red = 0i64;
    for row in &rows {
        if row.status.contains("Green") || row.status.contains('🟢') {
            green += 1;
        } else if row.status.contains("Red") || row.status.contains('🔴') {
            red += 1;
        } else {
            yellow += 1;
        }
    }
    Json::obj(vec![
        ("total", Json::Int(rows.len() as i64)),
        ("green", Json::Int(green)),
        ("yellow", Json::Int(yellow)),
        ("red", Json::Int(red)),
    ])
}

pub fn suggest_next_actions(root: &Path) -> Json {
    let scope = scope::detect(root);
    let mut actions = Vec::new();
    if scope.container || !scope.missing_dirs.is_empty() {
        actions.push(Json::obj(vec![
            ("action", Json::String("fix_scope".into())),
            ("priority", Json::Int(1)),
            ("reason", Json::String("scope risk".into())),
        ]));
    }
    for row in artifacts::read_health(root) {
        if row.status.contains("Red") || row.status.contains('🔴') {
            actions.push(Json::obj(vec![
                ("action", Json::String("record_deletion".into())),
                ("file", Json::String(row.file)),
                ("priority", Json::Int(1)),
                ("reason", Json::String(row.reason)),
            ]));
        } else if row.reason != "Initial stub" && (row.status.contains("Yellow") || row.status.contains('🟡')) {
            actions.push(Json::obj(vec![
                ("action", Json::String("prepare_edit".into())),
                ("file", Json::String(row.file)),
                ("priority", Json::Int(2)),
                ("reason", Json::String(row.reason)),
            ]));
        }
    }
    if actions.is_empty() {
        actions.push(Json::obj(vec![
            ("action", Json::String("lookup_only".into())),
            ("priority", Json::Int(5)),
            ("reason", Json::String("Health clean. Use prepare_edit for lookup.".into())),
        ]));
    }
    let rows = artifacts::read_health(root);
    ok(vec![("actions", Json::Array(actions)), ("readiness", Json::String(readiness_of(&scope, !cache::all_paths(root).is_empty(), &rows, health_file_present(root)).into()))])
}

pub fn check_changes(root: &Path) -> Json {
    let scope = scope::detect(root);
    if scope.container {
        return ok(vec![
            ("dirty_total", Json::Int(0)),
            ("map_complete", Json::Bool(false)),
            ("scope", scope_json(&scope)),
            ("files", Json::Array(vec![])),
        ]);
    }
    let mut rows = artifacts::read_health(root);
    let mut watched: BTreeSet<String> = rows.iter().map(|r| r.file.clone()).collect();
    for rel in cache::all_paths(root) {
        watched.insert(rel);
    }
    let reason = "content changed since last mark-green (check-changes)";
    let mut dirty = Vec::new();
    let mut changed_rows = false;
    for rel in watched {
        let path = root.join(&rel);
        let idx = rows.iter().position(|r| r.file == rel);
        if !path.is_file() {
            dirty.push(rel.clone());
            let already = idx.map(|i| is_red(&rows[i].status)).unwrap_or(false);
            if !already {
                let row = HealthRow {
                    file: rel.clone(),
                    status: "🔴 Red".into(),
                    last_updated: local_stamp(),
                    reason: "missing on disk (check-changes)".into(),
                    source_hash: idx.and_then(|i| Some(rows[i].source_hash.clone())).unwrap_or_default(),
                    verification: idx.map(|i| rows[i].verification.clone()).unwrap_or_default(),
                };
                if let Some(i) = idx { rows[i] = row; } else { rows.push(row); }
                let _ = artifacts::append_journal(root, "check-changes", &rel, "missing on disk");
                changed_rows = true;
            }
            continue;
        }
        let live = file_sha256_prefixed(&path).unwrap_or_default();
        let baseline = idx.and_then(|i| {
            let h = rows[i].source_hash.clone();
            if h.starts_with("sha256:") { Some(h) } else { None }
        });
        let drifted = match &baseline {
            Some(base) => live != *base,
            None => cache::indexed_rows(root).into_iter().find(|r| r.0 == rel).map(|r| r.3 != live).unwrap_or(false),
        };
        if !drifted {
            continue;
        }
        dirty.push(rel.clone());
        let already = idx.map(|i| is_yellow(&rows[i].status) && rows[i].reason.contains("content changed since last mark-green")).unwrap_or(false);
        if !already {
            let keep_hash = baseline.unwrap_or(live);
            let verification = idx.map(|i| rows[i].verification.clone()).unwrap_or_default();
            let row = HealthRow {
                file: rel.clone(),
                status: "🟡 Yellow".into(),
                last_updated: local_stamp(),
                reason: reason.into(),
                source_hash: keep_hash,
                verification,
            };
            if let Some(i) = idx { rows[i] = row; } else { rows.push(row); }
            let _ = artifacts::append_journal(root, "check-changes", &rel, reason);
            let pending = root.join("pending_updates.md");
            let mut text = fs::read_to_string(&pending).unwrap_or_else(|_| "# Pending Updates\n\n".into());
            if !text.contains(&rel) {
                text.push_str(&format!("- {rel} — {reason}\n"));
                let _ = fs::write(&pending, text);
            }
            changed_rows = true;
        }
    }
    if changed_rows {
        let _ = artifacts::write_health(root, &rows);
    }
    ok(vec![
        ("dirty_total", Json::Int(dirty.len() as i64)),
        ("changes_detected", Json::Int(dirty.len() as i64)),
        ("files", Json::Array(dirty.into_iter().map(Json::String).collect())),
        ("scope", scope_json(&scope)),
    ])
}

pub fn prepare_edit(root: &Path, file: &str) -> Json {
    let rel = file.trim_start_matches("./");
    let deps = cache::load_dependencies(root, rel).unwrap_or_default();
    let importers = cache::load_dependents(root, rel).unwrap_or_default();
    let row = artifacts::read_health(root).into_iter().find(|r| r.file == rel);
    ok(vec![
        ("file", Json::String(rel.into())),
        ("status", Json::String(row.as_ref().map(|r| r.status.clone()).unwrap_or_default())),
        ("dependencies", Json::Array(deps.into_iter().map(Json::String).collect())),
        ("dependents", Json::Array(importers.into_iter().map(Json::String).collect())),
        ("wiki", Json::String(fs::read_to_string(root.join(format!("{rel}.wiki.md"))).unwrap_or_default())),
    ])
}

pub fn record_change(root: &Path, file: &str, reason: &str) -> Json {
    let rel = file.trim_start_matches("./");
    let path = root.join(rel);
    if !path.is_file() {
        return fail("FileNotFound", format!("file does not exist: {rel}"));
    }
    let stamp = match artifacts::append_journal(root, "record-change", rel, reason) {
        Ok(s) => s,
        Err(e) => return fail("JournalError", e),
    };
    let hash = file_sha256_prefixed(&path).unwrap_or_default();
    if let Err(e) = artifacts::upsert_health_row(root, HealthRow {
        file: rel.into(),
        status: "🟡 Yellow".into(),
        last_updated: stamp,
        reason: reason.into(),
        source_hash: hash,
        verification: String::new(),
    }) {
        return fail("HealthError", e);
    }
    let pending = root.join("pending_updates.md");
    let mut text = fs::read_to_string(&pending).unwrap_or_else(|_| "# Pending Updates\n\n".into());
    if !text.contains(rel) {
        text.push_str(&format!("- {rel} — {reason}\n"));
        if fs::write(&pending, text).is_err() {
            return fail("PendingError", "could not write pending_updates.md");
        }
    }
    ok(vec![("file", Json::String(rel.into())), ("journaled", Json::Bool(true))])
}

pub fn mark_green(root: &Path, file: &str, reason: &str, force: bool) -> Json {
    let rel = file.trim_start_matches("./");
    let path = root.join(rel);
    if !path.is_file() {
        return fail("FileNotFound", format!("file does not exist: {rel}"));
    }
    if force && reason.trim().is_empty() {
        return fail("ValueError", "force=True needs a reason explaining why the wiki is still accurate");
    }
    let (symbols, symbol_warning) = public_symbols(&path);
    let wiki = fs::read_to_string(root.join(format!("{rel}.wiki.md"))).unwrap_or_default();
    if wiki.is_empty() {
        let stamp = local_stamp();
        let hash = file_sha256_prefixed(&path).unwrap_or_default();
        let _ = artifacts::upsert_health_row(root, HealthRow {
            file: rel.into(),
            status: "🟢 Green".into(),
            last_updated: stamp,
            reason: if reason.is_empty() { "no wiki".into() } else { reason.into() },
            source_hash: hash,
            verification: "no_wiki".into(),
        });
        return attach_warning(ok(vec![("file", Json::String(rel.into())), ("verification", Json::String("no_wiki".into()))]), symbol_warning);
    }
    let mut missing = Vec::new();
    for sym in &symbols {
        if !wiki.contains(sym) {
            missing.push(sym.clone());
        }
    }
    if !missing.is_empty() && !force {
        return attach_warning(Json::obj(vec![
            ("success", Json::Bool(false)),
            ("error", Json::String("wiki misses public symbols".into())),
            ("error_type", Json::String("WikiVerificationError".into())),
            ("file", Json::String(rel.into())),
            ("issues", Json::Array(missing.into_iter().map(Json::String).collect())),
        ]), symbol_warning);
    }
    let verification = if !missing.is_empty() && force { "forced" } else { "verified" };
    let stamp = local_stamp();
    let hash = file_sha256_prefixed(&path).unwrap_or_default();
    if let Err(e) = artifacts::upsert_health_row(root, HealthRow {
        file: rel.into(),
        status: "🟢 Green".into(),
        last_updated: stamp,
        reason: if reason.is_empty() { "mark-green".into() } else { reason.into() },
        source_hash: hash,
        verification: verification.into(),
    }) {
        return attach_warning(fail("HealthError", e), symbol_warning);
    }
    attach_warning(ok(vec![("file", Json::String(rel.into())), ("verification", Json::String(verification.into()))]), symbol_warning)
}

fn public_symbols(path: &Path) -> (Vec<String>, Option<String>) {
    let (text, warning) = crate::parse::read_utf8(path);
    if path.extension().and_then(|s| s.to_str()) != Some("py") {
        return (Vec::new(), warning);
    }
    let mut symbols = Vec::new();
    for line in text.lines() {
        let t = line.trim();
        if t.starts_with("__all__") {
            if let Some(start) = t.find('[') {
                if let Some(end) = t.find(']') {
                    for name in t[start + 1..end].split(',') {
                        let name = name.trim().trim_matches(|c| c == '\'' || c == '"');
                        if !name.is_empty() {
                            symbols.push(name.to_string());
                        }
                    }
                    return (symbols, warning);
                }
            }
        }
    }
    for line in text.lines() {
        if line.starts_with("def ") || line.starts_with("class ") || line.starts_with("async def ") {
            let rest = line.trim_start_matches("async ").trim_start_matches("def ").trim_start_matches("class ");
            let name = rest.split(['(', ':']).next().unwrap_or("").trim();
            if !name.is_empty() && !name.starts_with('_') {
                symbols.push(name.to_string());
            }
        }
    }
    (symbols, warning)
}

pub fn health(root: &Path) -> Json {
    let rows = artifacts::read_health(root);
    ok(vec![
        ("health_summary", health_summary(root)),
        ("entries", Json::Array(rows.into_iter().map(|r| Json::obj(vec![
            ("file", Json::String(r.file)),
            ("status", Json::String(r.status)),
            ("last_updated", Json::String(r.last_updated)),
            ("reason", Json::String(r.reason)),
            ("source_content_hash", Json::String(r.source_hash)),
            ("verification", Json::String(r.verification)),
        ])).collect())),
    ])
}

pub fn read_health(root: &Path) -> Vec<HealthRow> {
    artifacts::read_health(root)
}

pub fn read_journal(root: &Path, date: Option<&str>) -> Vec<JournalEntry> {
    artifacts::read_journal(root, date)
}

pub fn cache_status(root: &Path) -> Json {
    let paths = cache::all_paths(root);
    ok(vec![
        ("cache_backend", Json::String(if paths.is_empty() { "none" } else { "wk_cache" }.into())),
        ("files", Json::Int(paths.len() as i64)),
        ("sha256", Json::Bool(true)),
    ])
}

pub fn validate(root: &Path) -> Json {
    let scope = scope::detect(root);
    let files = scope::collect(root, &scope).unwrap_or_default();
    let known: BTreeSet<String> = artifacts::read_health(root).into_iter().map(|r| r.file).collect();
    let missing: Vec<String> = files.iter().map(|p| scope::rel_of(root, p)).filter(|rel| !known.contains(rel)).collect();
    let check = cache::check_consistency(root);
    // Size and mtime can stay put while the bytes change. Hashing here is the
    // check that `update-maps` skips; repair with `update-maps --full`.
    let mut drift = Vec::new();
    for (rel, _, _, hash) in cache::indexed_rows(root) {
        if !hash.starts_with("sha256:") {
            continue;
        }
        let path = root.join(&rel);
        if !path.is_file() {
            continue;
        }
        if let Some(live) = file_sha256_prefixed(&path) {
            if live != hash {
                drift.push(rel);
            }
        }
    }
    let mut value = if !check.consistent {
        fail("CacheInconsistent", "forward and reverse cache indexes disagree")
    } else if !drift.is_empty() {
        fail("StaleMap", "cached hashes do not match file bytes; run update-maps --full")
    } else {
        ok(vec![])
    };
    value.insert("missing", Json::Array(missing.iter().cloned().map(Json::String).collect()));
    value.insert("missing_count", Json::Int(missing.len() as i64));
    value.insert("cache_consistent", Json::Bool(check.consistent));
    value.insert("cache_incomplete", Json::Bool(check.incomplete));
    value.insert("cache_mismatches", Json::Array(check.mismatches.into_iter().map(Json::String).collect()));
    value.insert("content_drift", Json::Array(drift.iter().cloned().map(Json::String).collect()));
    value.insert("content_drift_count", Json::Int(drift.len() as i64));
    value
}

pub fn cycles(root: &Path) -> Json {
    let edges = cache::edges(root);
    let mut graph: BTreeMap<String, Vec<String>> = BTreeMap::new();
    for (src, dst) in &edges {
        graph.entry(src.clone()).or_default().push(dst.clone());
        graph.entry(dst.clone()).or_default();
    }
    let sccs = tarjan(&graph);
    let cyclic: Vec<Vec<String>> = sccs.into_iter().filter(|c| c.len() > 1).collect();
    ok(vec![
        ("count", Json::Int(cyclic.len() as i64)),
        ("cycles", Json::Array(cyclic.into_iter().map(|files| Json::obj(vec![
            ("size", Json::Int(files.len() as i64)),
            ("files", Json::Array(files.into_iter().map(Json::String).collect())),
        ])).collect())),
    ])
}

fn tarjan(graph: &BTreeMap<String, Vec<String>>) -> Vec<Vec<String>> {
    fn strong(node: &str, graph: &BTreeMap<String, Vec<String>>, index: &mut i64, stack: &mut Vec<String>, on: &mut BTreeSet<String>, idx: &mut BTreeMap<String, i64>, low: &mut BTreeMap<String, i64>, out: &mut Vec<Vec<String>>) {
        idx.insert(node.to_string(), *index);
        low.insert(node.to_string(), *index);
        *index += 1;
        stack.push(node.to_string());
        on.insert(node.to_string());
        for nxt in graph.get(node).into_iter().flatten() {
            if !idx.contains_key(nxt) {
                strong(nxt, graph, index, stack, on, idx, low, out);
                let ln = *low.get(node).unwrap_or(&0);
                let lnxt = *low.get(nxt).unwrap_or(&0);
                low.insert(node.to_string(), ln.min(lnxt));
            } else if on.contains(nxt) {
                let ln = *low.get(node).unwrap_or(&0);
                let inxt = *idx.get(nxt).unwrap_or(&0);
                low.insert(node.to_string(), ln.min(inxt));
            }
        }
        if low.get(node) == idx.get(node) {
            let mut comp = Vec::new();
            while let Some(w) = stack.pop() {
                on.remove(&w);
                let done = w == node;
                comp.push(w);
                if done { break; }
            }
            comp.sort();
            out.push(comp);
        }
    }
    let mut index = 0i64;
    let mut stack = Vec::new();
    let mut on = BTreeSet::new();
    let mut idx = BTreeMap::new();
    let mut low = BTreeMap::new();
    let mut out = Vec::new();
    let nodes: Vec<String> = graph.keys().cloned().collect();
    for n in nodes {
        if !idx.contains_key(&n) {
            strong(&n, graph, &mut index, &mut stack, &mut on, &mut idx, &mut low, &mut out);
        }
    }
    out
}

pub fn verify_wikis(root: &Path) -> Json {
    let rows = artifacts::read_health(root);
    let mut checked = 0i64;
    let mut failed = Vec::new();
    let mut warnings = Vec::new();
    for row in rows {
        if !is_green(&row.status) {
            continue;
        }
        let path = root.join(&row.file);
        if !path.is_file() {
            continue;
        }
        checked += 1;
        let wiki_path = root.join(format!("{}.wiki.md", row.file));
        let wiki = fs::read_to_string(&wiki_path).unwrap_or_default();
        if wiki.is_empty() {
            continue;
        }
        let (symbols, symbol_warning) = public_symbols(&path);
        if let Some(warning) = symbol_warning {
            warnings.push(format!("{}: {warning}", row.file));
        }
        let missing: Vec<String> = symbols.into_iter().filter(|s| !wiki.contains(s)).collect();
        if !missing.is_empty() {
            failed.push(Json::obj(vec![
                ("file", Json::String(row.file)),
                ("issues", Json::Array(missing.into_iter().map(Json::String).collect())),
            ]));
        }
    }
    let warning_json = Json::Array(warnings.into_iter().map(Json::String).collect());
    if failed.is_empty() {
        ok(vec![("checked", Json::Int(checked)), ("failed", Json::Array(vec![])), ("warnings", warning_json)])
    } else {
        Json::obj(vec![
            ("success", Json::Bool(false)),
            ("error", Json::String("one or more Green wikis miss public symbols".into())),
            ("error_type", Json::String("WikiVerificationError".into())),
            ("checked", Json::Int(checked)),
            ("failed", Json::Array(failed)),
            ("warnings", warning_json),
        ])
    }
}

pub fn record_changes(root: &Path, reason_lines: &[String], default_reason: Option<&str>) -> Json {
    let status = std::process::Command::new("git")
        .args(["-C", &root.display().to_string(), "status", "--porcelain"])
        .output();
    let output = match status {
        Ok(o) if o.status.success() => o,
        _ => return fail("GitUnavailableError", "git is not available or this directory is not a repository"),
    };
    let text = String::from_utf8_lossy(&output.stdout);
    let mut files = Vec::new();
    for line in text.lines() {
        if line.len() < 4 {
            continue;
        }
        let path = line[3..].trim();
        let path = path.strip_prefix('"').unwrap_or(path).trim_end_matches('"');
        if path.ends_with(".wiki.md") || path.starts_with(".wikifier_staging/") {
            continue;
        }
        if line.starts_with(" D") || line.starts_with("D ") {
            continue;
        }
        files.push(path.to_string());
    }
    let mut reasons: BTreeMap<String, String> = BTreeMap::new();
    for line in reason_lines {
        if let Some((p, why)) = line.split_once('=') {
            reasons.insert(p.to_string(), why.to_string());
        }
    }
    let mut missing = Vec::new();
    for f in &files {
        let why = reasons.get(f).cloned().or_else(|| default_reason.map(|s| s.to_string()));
        if why.is_none() {
            missing.push(f.clone());
        }
    }
    if !missing.is_empty() {
        return Json::obj(vec![
            ("success", Json::Bool(false)),
            ("error", Json::String("every changed file needs a reason".into())),
            ("error_type", Json::String("MissingReasons".into())),
            ("missing_reasons", Json::Array(missing.into_iter().map(Json::String).collect())),
            ("recorded", Json::Int(0)),
        ]);
    }
    let mut recorded = 0i64;
    for f in &files {
        let why = reasons.get(f).cloned().or_else(|| default_reason.map(|s| s.to_string())).unwrap_or_default();
        let res = record_change(root, f, &why);
        if res.get("success").and_then(|s| s.as_bool()) == Some(true) {
            recorded += 1;
        }
    }
    ok(vec![("recorded", Json::Int(recorded)), ("files", Json::Array(files.into_iter().map(Json::String).collect()))])
}

pub fn heal_stubs(root: &Path, min_len: usize) -> Json {
    let mut rows = artifacts::read_health(root);
    let mut healed = 0i64;
    for row in &mut rows {
        if row.reason != "Initial stub" {
            continue;
        }
        let wiki = fs::read_to_string(root.join(format!("{}.wiki.md", row.file))).unwrap_or_default();
        if wiki.trim().len() >= min_len {
            row.status = "🟢 Green".into();
            row.reason = "healed stub".into();
            row.verification = "verified".into();
            row.last_updated = local_stamp();
            healed += 1;
        }
    }
    if healed > 0 {
        let _ = artifacts::write_health(root, &rows);
    }
    ok(vec![("healed_count", Json::Int(healed)), ("changed", Json::Int(healed))])
}

pub fn prune_health(root: &Path) -> Json {
    let scope = scope::detect(root);
    let rows = artifacts::read_health(root);
    let before = rows.len();
    let kept: Vec<_> = rows.into_iter().filter(|r| in_scope(&scope, &r.file)).collect();
    let changed = before - kept.len();
    let _ = artifacts::write_health(root, &kept);
    ok(vec![("changed", Json::Int(changed as i64))])
}

pub fn prune_pending(root: &Path) -> Json {
    let scope = scope::detect(root);
    let path = root.join("pending_updates.md");
    let text = fs::read_to_string(&path).unwrap_or_default();
    let mut out = String::new();
    let mut changed = 0i64;
    for line in text.lines() {
        let keep = if let Some(rest) = line.trim().strip_prefix("- ") {
            let file = rest.split(" — ").next().unwrap_or(rest).trim();
            if in_scope(&scope, file) { true } else { changed += 1; false }
        } else { true };
        if keep {
            out.push_str(line);
            out.push('\n');
        }
    }
    let _ = fs::write(path, out);
    ok(vec![("changed", Json::Int(changed))])
}

fn in_scope(scope: &Scope, rel: &str) -> bool {
    if scope.full_tree || scope.prefixes.is_empty() {
        return true;
    }
    scope.prefixes.iter().any(|p| rel == p || rel.starts_with(&(p.clone() + "/")))
}

pub fn stale_wikis(root: &Path) -> Json {
    let mut stale = Vec::new();
    for row in artifacts::read_health(root) {
        let wiki = root.join(format!("{}.wiki.md", row.file));
        if !wiki.is_file() {
            continue;
        }
        let live = file_sha256_prefixed(&root.join(&row.file)).unwrap_or_default();
        let source_drift = row.source_hash.starts_with("sha256:") && !live.is_empty() && live != row.source_hash;
        let content_flag = is_yellow(&row.status) && row.reason.contains("content changed since last mark-green");
        if source_drift || content_flag {
            let mut reasons = Vec::new();
            if source_drift {
                reasons.push(Json::String("source_changed_since_mark_green".into()));
            }
            if content_flag {
                reasons.push(Json::String("content changed since last mark-green (check-changes)".into()));
            }
            stale.push(Json::obj(vec![
                ("file", Json::String(row.file)),
                ("is_stale", Json::Bool(true)),
                ("reasons", Json::Array(reasons)),
                ("status", Json::String(row.status)),
            ]));
        }
    }
    ok(vec![
        ("stale", Json::Array(stale.clone())),
        ("files", Json::Array(stale.iter().filter_map(|v| v.get("file").cloned()).collect())),
        ("count", Json::Int(stale.len() as i64)),
    ])
}

pub fn prune_barrels(root: &Path, max_age_days: f64, dry_run: bool) -> Json {
    match cache::prune_barrel_files(root, max_age_days, dry_run) {
        Ok(n) => ok(vec![
            ("pruned", Json::Int(n as i64)),
            ("changed", Json::Int(n as i64)),
            ("dry_run", Json::Bool(dry_run)),
            ("max_age_days", Json::Float(max_age_days)),
        ]),
        Err(e) => fail("CacheError", e),
    }
}

pub fn metrics_snapshot(root: &Path) -> Json {
    let rows = artifacts::read_health(root);
    let mut green = 0i64;
    let mut yellow = 0i64;
    let mut red = 0i64;
    for row in &rows {
        if is_green(&row.status) {
            green += 1;
        } else if is_red(&row.status) {
            red += 1;
        } else if is_yellow(&row.status) {
            yellow += 1;
        }
    }
    let snap = Json::obj(vec![
        ("ts", Json::String(local_stamp())),
        ("source", Json::String("cli".into())),
        ("total", Json::Int(rows.len() as i64)),
        ("green", Json::Int(green)),
        ("yellow", Json::Int(yellow)),
        ("red", Json::Int(red)),
        ("cache_files", Json::Int(cache::all_paths(root).len() as i64)),
    ]);
    let staging = root.join(".wikifier_staging");
    if fs::create_dir_all(&staging).is_err() {
        return fail("MetricsError", "could not create staging dir");
    }
    let latest = staging.join("metrics_latest.json");
    let hist = staging.join("metrics_history.jsonl");
    if fs::write(&latest, format!("{snap}\n")).is_err() {
        return fail("MetricsError", "could not write metrics_latest.json");
    }
    let prev = fs::read_to_string(&hist).unwrap_or_default();
    let mut body = prev;
    if !body.is_empty() && !body.ends_with('\n') {
        body.push('\n');
    }
    body.push_str(&snap.to_string());
    body.push('\n');
    if fs::write(&hist, &body).is_err() {
        return fail("MetricsError", "could not append metrics_history.jsonl");
    }
    ok(vec![
        ("appended", Json::Bool(true)),
        ("total", Json::Int(rows.len() as i64)),
        ("green", Json::Int(green)),
        ("yellow", Json::Int(yellow)),
        ("red", Json::Int(red)),
        ("metrics_latest", Json::String(latest.display().to_string())),
        ("metrics_history", Json::String(hist.display().to_string())),
    ])
}

pub fn healing_stats(root: &Path) -> Json {
    let rows = artifacts::read_health(root);
    let stubs = rows.iter().filter(|r| r.reason == "Initial stub").count() as i64;
    ok(vec![
        ("stub_count", Json::Int(stubs)),
        ("total", Json::Int(rows.len() as i64)),
    ])
}

pub fn resolution_diagnostics(root: &Path) -> Json {
    let mut notes = Vec::new();
    for rel in cache::all_paths(root) {
        if let Ok(view) = cache::load_dependency_view(root, &rel) {
            for (raw, line) in view.unresolved {
                notes.push(Json::obj(vec![
                    ("file", Json::String(rel.clone())),
                    ("raw", Json::String(raw)),
                    ("line", Json::Int(line)),
                    ("reason", Json::String("unresolved".into())),
                ]));
            }
        }
    }
    ok(vec![("notes", Json::Array(notes))])
}

pub fn serve_once(root: &Path) -> Json {
    use std::io::{Read, Write};
    use std::net::TcpListener;
    let listener = match TcpListener::bind("127.0.0.1:0") {
        Ok(l) => l,
        Err(e) => return fail("ServeError", e.to_string()),
    };
    let port = match listener.local_addr() {
        Ok(a) => a.port(),
        Err(e) => return fail("ServeError", e.to_string()),
    };
    let body = session_bootstrap(root).to_string();
    let port_copy = port;
    let client = std::thread::spawn(move || {
        std::thread::sleep(std::time::Duration::from_millis(30));
        let mut stream = std::net::TcpStream::connect(("127.0.0.1", port_copy)).ok()?;
        let req = b"GET /__wikifier/api/bootstrap HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n";
        stream.write_all(req).ok()?;
        let mut buf = Vec::new();
        stream.read_to_end(&mut buf).ok()?;
        Some(String::from_utf8_lossy(&buf).to_string())
    });
    let accepted = listener.accept();
    let served = match accepted {
        Ok((mut sock, _)) => {
            let mut req = [0u8; 1024];
            let _ = sock.read(&mut req);
            let resp = format!(
                "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
                body.len(), body
            );
            sock.write_all(resp.as_bytes()).is_ok()
        }
        Err(_) => false,
    };
    let client_body = client.join().ok().flatten().unwrap_or_default();
    ok(vec![
        ("bound", Json::Bool(true)),
        ("port", Json::Int(port as i64)),
        ("served", Json::Bool(served && client_body.contains("200"))),
    ])
}

pub fn daemon_ctl(root: &Path, action: &str) -> Json {
    let pidfile = root.join(".wikifier_staging").join("daemon.pid");
    match action {
        "run" => {
            for _ in 0..50 {
                if pidfile.is_file() {
                    break;
                }
                std::thread::sleep(std::time::Duration::from_millis(20));
            }
            for _ in 0..3600 {
                if !pidfile.is_file() {
                    break;
                }
                std::thread::sleep(std::time::Duration::from_millis(200));
            }
            ok(vec![("running", Json::Bool(false)), ("action", Json::String("run".into()))])
        }
        "start" => {
            let _ = fs::create_dir_all(pidfile.parent().unwrap());
            let exe = match std::env::current_exe() {
                Ok(p) => p,
                Err(e) => return fail("DaemonError", e.to_string()),
            };
            match spawn_daemon(&exe, root) {
                Ok(child) => {
                    let _ = fs::write(&pidfile, child.id().to_string());
                    ok(vec![("running", Json::Bool(true)), ("pid", Json::Int(child.id() as i64)), ("action", Json::String("start".into()))])
                }
                Err(e) => fail("DaemonError", e.to_string()),
            }
        }
        "status" => {
            let running = pid_alive(&pidfile);
            ok(vec![("running", Json::Bool(running)), ("action", Json::String("status".into()))])
        }
        "stop" => {
            if let Ok(text) = fs::read_to_string(&pidfile) {
                if let Ok(pid) = text.trim().parse::<i32>() {
                    let _ = crate::proc::signal_process(pid, 15);
                }
            }
            let _ = fs::remove_file(&pidfile);
            ok(vec![("running", Json::Bool(false)), ("action", Json::String("stop".into()))])
        }
        other => fail("DaemonError", format!("unknown daemon action {other}")),
    }
}

fn spawn_daemon(exe: &Path, root: &Path) -> std::io::Result<std::process::Child> {
    let mut cmd = std::process::Command::new(exe);
    cmd.args(["--target", &root.display().to_string(), "daemon", "run"])
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null());
    // Windows CreateProcess copies every inheritable handle, including the
    // pipe `daemon start` is writing its JSON to. Clear that bit first so
    // `Command::output()` returns when start exits, not when the daemon does.
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        prevent_stdio_inheritance();
        const DETACHED_PROCESS: u32 = 0x0000_0008;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(DETACHED_PROCESS | CREATE_NO_WINDOW);
    }
    cmd.spawn()
}

#[cfg(windows)]
fn prevent_stdio_inheritance() {
    const STD_INPUT_HANDLE: u32 = 0xFFFF_FFF6;
    const STD_OUTPUT_HANDLE: u32 = 0xFFFF_FFF5;
    const STD_ERROR_HANDLE: u32 = 0xFFFF_FFF4;
    const HANDLE_FLAG_INHERIT: u32 = 0x1;
    #[link(name = "kernel32")]
    extern "system" {
        fn GetStdHandle(id: u32) -> *mut core::ffi::c_void;
        fn SetHandleInformation(handle: *mut core::ffi::c_void, mask: u32, flags: u32) -> i32;
    }
    unsafe {
        for id in [STD_INPUT_HANDLE, STD_OUTPUT_HANDLE, STD_ERROR_HANDLE] {
            let handle = GetStdHandle(id);
            if !handle.is_null() && handle != (-1isize as *mut core::ffi::c_void) {
                SetHandleInformation(handle, HANDLE_FLAG_INHERIT, 0);
            }
        }
    }
}

fn pid_alive(pidfile: &Path) -> bool {
    let Ok(text) = fs::read_to_string(pidfile) else { return false };
    let Ok(pid) = text.trim().parse::<i32>() else { return false };
    crate::proc::pid_alive(pid)
}

pub fn dispatch(name: &str, root: &Path, positional: &[String], flags: &BTreeMap<String, String>) -> Json {
    let file = positional.first().map(|s| s.as_str()).unwrap_or("");
    let reason = if positional.len() > 1 { positional[1..].join(" ") } else { flags.get("reason").cloned().unwrap_or_default() };
    match name {
        "check-changes" | "check_changes" => check_changes(root),
        "record-change" | "record_change" => record_change(root, file, &reason),
        "mark-green" | "mark_green" => mark_green(root, file, &reason, flags.get("force").map(|s| s == "true").unwrap_or(false)),
        "record-deletion" | "record_deletion" => {
            let _ = artifacts::append_journal(root, "record-deletion", file, &reason);
            ok(vec![("file", Json::String(file.into()))])
        }
        "session-bootstrap" | "bootstrap" | "session-start" | "session_bootstrap" => session_bootstrap(root),
        "suggest-next" | "suggest" | "suggest-next-actions" | "suggest_next_actions" => suggest_next_actions(root),
        "prepare-edit" | "prepare_edit" | "lookup" | "preflight" => prepare_edit(root, file),
        "dependencies" | "deps" | "get_dependencies" => load_dependencies(root, file),
        "dependents" | "importers" | "get_dependents" => load_dependents(root, file),
        "list-paths" | "list_paths" => list_paths(root, flags.get("prefix").map(|s| s.as_str()).unwrap_or(file)),
        "update-maps" | "update_maps" => {
            let full = flags.get("full").map(|s| s == "true").unwrap_or(false);
            let quiet = flags.get("quiet").map(|s| s == "true").unwrap_or(false);
            update_maps_opts(root, full, quiet)
        }
        "health" => health(root),
        "cache-status" | "cache" => cache_status(root),
        "list-core-tools" | "list_core_tools" => ok(vec![
            ("core", Json::Array(["session_bootstrap", "check_changes", "prepare_edit", "suggest_next_actions", "record_change", "mark_green", "update_maps", "list_paths"].into_iter().map(|s| Json::String(s.into())).collect())),
            ("tools", Json::Array(MCP_TOOLS.iter().map(|s| Json::String((*s).into())).collect())),
        ]),
        "journal" => {
            let entries = read_journal(root, flags.get("date").map(|s| s.as_str()).or(positional.first().map(|s| s.as_str())));
            ok(vec![("entries", Json::Array(entries.into_iter().map(|e| Json::obj(vec![
                ("stamp", Json::String(e.stamp)),
                ("action", Json::String(e.action)),
                ("file", Json::String(e.file)),
                ("reason", Json::String(e.reason)),
            ])).collect()))])
        }
        "why-file" | "why_file" | "why" => {
            let entries = artifacts::read_journal(root, None).into_iter().filter(|e| e.file == file).collect::<Vec<_>>();
            ok(vec![("file", Json::String(file.into())), ("entries", Json::Array(entries.into_iter().map(|e| Json::obj(vec![
                ("stamp", Json::String(e.stamp)),
                ("reason", Json::String(e.reason)),
            ])).collect()))])
        }
        "search-journal" | "search_journal" => {
            let q = flags.get("query").cloned().or_else(|| positional.first().cloned()).unwrap_or_default();
            let entries = artifacts::read_journal(root, None).into_iter().filter(|e| e.reason.contains(&q) || e.file.contains(&q)).collect::<Vec<_>>();
            ok(vec![("entries", Json::Array(entries.into_iter().map(|e| Json::obj(vec![
                ("file", Json::String(e.file)),
                ("reason", Json::String(e.reason)),
            ])).collect()))])
        }
        "validate" => validate(root),
        "rebuild-cache" | "rebuild_cache" => match cache::rebuild(root) {
            Ok(()) => ok(vec![("rebuilt", Json::Bool(true))]),
            Err(err) => fail("CacheError", err),
        },
        "issues" => suggest_next_actions(root),
        "cycles" | "get_cycles" => cycles(root),
        "verify-wikis" | "verify_wikis" => verify_wikis(root),
        "autonomous-status" | "readiness" => {
            let scope = scope::detect(root);
            ok(vec![("readiness", Json::String(readiness_of(&scope, !cache::all_paths(root).is_empty(), &artifacts::read_health(root), health_file_present(root)).into())), ("scope", scope_json(&scope))])
        }
        "init" => init_project(root),
        "get_project_status" => session_bootstrap(root),
        "get_current_project_root" => ok(vec![("project_root", Json::String(root.display().to_string()))]),
        "get_file_wiki" => ok(vec![("file", Json::String(file.into())), ("wiki", Json::String(fs::read_to_string(root.join(format!("{file}.wiki.md"))).unwrap_or_default()))]),
        "get_files_needing_attention" => suggest_next_actions(root),
        "get_resolution_diagnostics" => resolution_diagnostics(root),
        "get_barrel_reports" | "get_incremental_status" => resolution_diagnostics(root),
        "record-changes" | "record_changes" => {
            let lines = flags.get("reasons").map(|s| s.split('\n').map(|x| x.to_string()).collect::<Vec<_>>()).unwrap_or_default();
            record_changes(root, &lines, flags.get("default").map(|s| s.as_str()))
        },
        "seed-health" | "seed-source-hashes" | "seed_source_content_hashes" => {
            let _ = seed_health_from_map(root);
            ok(vec![("seeded", Json::Bool(true))])
        }
        "prune-pending" => prune_pending(root),
        "prune-health" => prune_health(root),
        "heal-stubs" | "heal_stubs" => heal_stubs(root, flags.get("min-wiki-length").and_then(|s| s.parse().ok()).unwrap_or(20)),
        "healable-stubs" | "list_healable_stubs" => {
            let min = flags.get("min-wiki-length").and_then(|s| s.parse().ok()).unwrap_or(20usize);
            let files: Vec<Json> = artifacts::read_health(root).into_iter().filter(|r| r.reason == "Initial stub" && fs::read_to_string(root.join(format!("{}.wiki.md", r.file))).unwrap_or_default().len() >= min).map(|r| Json::String(r.file)).collect();
            ok(vec![("files", Json::Array(files))])
        }
        "healing-stats" | "stub-stats" => healing_stats(root),
        "stale-wikis" | "detect-stale" => stale_wikis(root),
        "prune-barrels" | "prune-brc" | "gc-barrels" => {
            let days = positional.first().and_then(|s| s.parse().ok())
                .or_else(|| flags.get("max-age-days").or_else(|| flags.get("max_age_days")).and_then(|s| s.parse().ok()))
                .unwrap_or(90.0);
            let dry = flags.get("dry-run").map(|s| s == "true").unwrap_or(false);
            prune_barrels(root, days, dry)
        }
        "metrics-snapshot" | "metrics" => metrics_snapshot(root),
        "monitor" => check_changes(root),
        "serve" => serve_once(root),
        "daemon" => daemon_ctl(root, positional.first().map(|s| s.as_str()).unwrap_or("status")),
        "help" => ok(vec![("commands", Json::Array(CLI_COMMANDS.iter().map(|s| Json::String((*s).into())).collect()))]),
        other => fail("UnknownCommand", format!("unknown command {other}")),
    }
}

pub const CLI_COMMANDS: &[&str] = &[
    "check-changes", "record-change", "mark-green", "record-changes", "record-deletion",
    "session-bootstrap", "suggest-next", "prepare-edit", "dependencies", "dependents",
    "why-file", "search-journal", "list-paths", "cycles", "journal", "issues", "update-maps",
    "health", "validate", "rebuild-cache", "seed-health", "seed-source-hashes", "prune-pending", "prune-health",
    "heal-stubs", "healable-stubs", "healing-stats", "stale-wikis", "verify-wikis", "prune-barrels",
    "cache-status", "autonomous-status", "metrics-snapshot", "list-core-tools", "init", "monitor",
    "serve", "daemon", "help", "mcp",
];

fn init_project(root: &Path) -> Json {
    let src = root.join("src");
    if src.is_dir() {
        let _ = fs::write(root.join("map_paths.txt"), "src\n");
        let _ = fs::write(root.join("monitored_paths.txt"), "src\n");
        ok(vec![("seeded", Json::String("src".into()))])
    } else {
        let _ = fs::write(root.join("map_paths.txt"), "");
        let _ = fs::write(root.join("monitored_paths.txt"), "");
        fail("ScopeError", "no src/ directory; name map_paths before update-maps")
    }
}

pub fn ensure_root(root: Option<&Path>) -> Result<PathBuf, Json> {
    root_or_err(root)
}
