//! One function per agent-facing operation. CLI and MCP both call these.

use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::fs;
use std::path::{Path, PathBuf};

use crate::artifacts::{self, HealthRow, JournalEntry};
use crate::cache::{self, FileUpdate, Session};
use crate::jsonutil::Json;
use crate::scope::{self, Scope};
use crate::sha256::{content_sha256_prefixed, file_sha256_prefixed};
use crate::timeutil::local_stamp;

pub struct MapRun {
    pub full: bool,
    pub quiet: bool,
    pub directory: Option<String>,
    pub max_files: Option<usize>,
    pub stream: bool,
}

fn lock_or_fail(root: &Path) -> Result<crate::project_lock::ProjectLock, Json> {
    crate::project_lock::ProjectLock::acquire(root).map_err(|err| {
        let kind = if err.contains("locked") {
            "LockTimeoutError"
        } else {
            "LockError"
        };
        let mut value = fail(kind, err);
        if kind == "LockTimeoutError" {
            value.insert("timed_out", Json::Bool(true));
        }
        value
    })
}

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

/// A lookup on a path that is neither on disk nor in the map fails with a next step,
/// instead of a `success: true` reply whose fields are all empty.
fn unknown_file(root: &Path, rel: &str) -> Option<Json> {
    if rel.is_empty() {
        return Some(fail(
            "ValueError",
            "file is required: pass a project-relative path such as src/main.rs",
        ));
    }
    if root.join(rel).exists() || cache::all_paths(root).iter().any(|p| p == rel) {
        return None;
    }
    Some(fail(
        "FileNotFound",
        format!(
            "{rel} is not on disk under {} and not in the map. Pass a path relative to the project root; list_paths shows the mapped files.",
            root.display()
        ),
    ))
}

/// `limit` caps the bootstrap `files` list and adds `files_total`. `0` or no limit keeps
/// every file. `map_index` and `list_paths` are the way to orient on a large tree.
fn cap_files(mut value: Json, flags: &BTreeMap<String, String>) -> Json {
    let limit = flags
        .get("limit")
        .and_then(|s| s.parse::<usize>().ok())
        .filter(|n| *n > 0);
    if let (Some(limit), Some(Json::Array(files))) = (limit, value.get("files")) {
        if files.len() > limit {
            let total = files.len();
            let kept = files[..limit].to_vec();
            value.insert("files", Json::Array(kept));
            value.insert("files_total", Json::Int(total as i64));
        }
    }
    value
}

fn root_or_err(root: Option<&Path>) -> Result<PathBuf, Json> {
    let root = match root {
        Some(p) => p.to_path_buf(),
        None => std::env::current_dir().map_err(|e| fail("ProjectRootError", e.to_string()))?,
    };
    if !root.is_dir() {
        return Err(fail(
            "ProjectRootError",
            format!("project root does not exist: {}", root.display()),
        ));
    }
    Ok(root)
}

fn scope_json(scope: &Scope) -> Json {
    Json::obj(vec![
        ("ok", Json::Bool(scope.ok)),
        ("container", Json::Bool(scope.container)),
        ("child_project_count", Json::Int(scope.child_count as i64)),
        (
            "child_project_sample",
            Json::Array(
                scope
                    .child_sample
                    .iter()
                    .cloned()
                    .map(Json::String)
                    .collect(),
            ),
        ),
        ("bare_dot_monitor", Json::Bool(scope.bare_dot)),
        ("full_tree", Json::Bool(scope.full_tree)),
        (
            "missing_dirs",
            Json::Array(
                scope
                    .missing_dirs
                    .iter()
                    .cloned()
                    .map(Json::String)
                    .collect(),
            ),
        ),
        (
            "prefixes",
            Json::Array(scope.prefixes.iter().cloned().map(Json::String).collect()),
        ),
        (
            "warnings",
            Json::Array(scope.warnings.iter().cloned().map(Json::String).collect()),
        ),
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

fn readiness_of(
    scope: &Scope,
    has_map: bool,
    rows: &[crate::artifacts::HealthRow],
    has_health_file: bool,
) -> &'static str {
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
    if rows
        .iter()
        .any(|r| is_yellow(&r.status) && r.reason != "Initial stub")
    {
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
    update_maps_run(
        root,
        &MapRun {
            full,
            quiet,
            directory: None,
            max_files: None,
            stream: false,
        },
    )
}

pub fn update_maps_run(root: &Path, run: &MapRun) -> Json {
    let _lock = match lock_or_fail(root) {
        Ok(lock) => lock,
        Err(err) => return err,
    };
    let full = run.full;
    let quiet = run.quiet;
    let mut scope = scope::detect(root);
    if scope.container {
        return ok(vec![
            ("readiness", Json::String("map_ok_scope_risk".into())),
            ("map_complete", Json::Bool(false)),
            ("full_tree", Json::Bool(false)),
            ("parseable_files", Json::Int(0)),
            ("files_parsed", Json::Int(0)),
            ("files_remaining_dirty", Json::Int(0)),
            ("edges", Json::Array(vec![])),
            ("scope", scope_json(&scope)),
            (
                "message",
                Json::String("container root refused; target one child project".into()),
            ),
        ]);
    }
    if let Some(dir) = run
        .directory
        .as_ref()
        .map(|s| s.trim().trim_matches('/'))
        .filter(|s| !s.is_empty())
    {
        let path = root.join(dir);
        if !path.is_dir() {
            return fail("ScopeError", format!("missing map directory: {dir}"));
        }
        scope.prefixes = vec![dir.to_string()];
        scope.full_tree = false;
        scope.missing_dirs.clear();
        scope.ok = true;
    }
    if !scope.missing_dirs.is_empty() {
        return fail(
            "ScopeError",
            format!("missing map directory: {}", scope.missing_dirs.join(", ")),
        );
    }
    stream_event(
        run.stream,
        Json::obj(vec![
            ("event", Json::String("update_maps".into())),
            ("phase", Json::String("start".into())),
        ]),
    );
    let files = match scope::collect(root, &scope) {
        Ok(f) => f,
        Err(e) => return fail("ScopeError", e),
    };
    let mut session = match Session::open(root) {
        Ok(session) => session,
        Err(err) => {
            let kind = if err.contains("locked") {
                "CacheLocked"
            } else {
                "CacheError"
            };
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
        let stat_hit = !full
            && known
                .as_ref()
                .is_some_and(|(old_mtime, old_size, old_hash)| {
                    *old_mtime != 0
                        && *old_mtime == mtime
                        && *old_size == size
                        && old_hash.starts_with("sha256:")
                });
        if stat_hit {
            skipped += 1;
            continue;
        }
        let bytes = fs::read(file).unwrap_or_default();
        let hash = content_sha256_prefixed(&bytes);
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
    let mut files_remaining_dirty = 0i64;
    if let Some(limit) = run.max_files {
        if to_parse.len() > limit {
            files_remaining_dirty = (to_parse.len() - limit) as i64;
            to_parse.truncate(limit);
        }
    }
    let changed_paths: Vec<PathBuf> = to_parse
        .iter()
        .map(|(path, _, _, _, _)| path.clone())
        .collect();
    let analysis = if to_parse.is_empty() {
        crate::parse::Analysis {
            facts: BTreeMap::new(),
            scans: std::collections::HashMap::new(),
            warnings: Vec::new(),
        }
    } else if changed_paths.len() == files.len() {
        crate::parse::analyze_files(root, &files)
    } else {
        crate::parse::analyze_changed(root, &files, &changed_paths)
    };
    let mut warnings = analysis.warnings.clone();
    let mut low_conf_updates = Vec::new();
    for (path, rel, mtime, size, hash) in &to_parse {
        let _ = path;
        let fact = analysis.facts.get(rel);
        let dsts = fact.map(|f| f.dsts.clone()).unwrap_or_default();
        let scan = analysis.scans.get(rel);
        let barrel = scan
            .map(|s| {
                s.imports.iter().any(|i| {
                    matches!(
                        i.kind,
                        crate::parse::Kind::ExportFrom | crate::parse::Kind::ExportStar
                    )
                })
            })
            .unwrap_or(false);
        let imports: Vec<String> = scan
            .map(|s| s.imports.iter().map(|i| i.spec.clone()).collect())
            .unwrap_or_default();
        let barrel_dsts: Vec<String> = dsts.iter().cloned().collect();
        let edge_lines = fact
            .map(|f| {
                f.internal
                    .iter()
                    .map(|edge| {
                        cache::format_edge_line(
                            &edge.dst,
                            edge.line,
                            &edge.names,
                            edge.conditional,
                            edge.dynamic,
                            edge.via_barrel,
                        )
                    })
                    .collect()
            })
            .unwrap_or_default();
        let low_count = fact
            .map(|f| {
                let flags: Vec<(bool, bool, bool)> = f
                    .internal
                    .iter()
                    .map(|edge| (edge.conditional, edge.dynamic, edge.via_barrel))
                    .collect();
                crate::low_conf::count_edges(&flags)
            })
            .unwrap_or(0);
        low_conf_updates.push((rel.clone(), low_count));
        let external = fact.map(|f| f.external.clone()).unwrap_or_default();
        let unresolved = fact.map(|f| f.unresolved.clone()).unwrap_or_default();
        if run.stream {
            stream_event(
                true,
                Json::obj(vec![
                    ("event", Json::String("update_maps".into())),
                    ("phase", Json::String("parsed".into())),
                    ("file", Json::String(rel.clone())),
                ]),
            );
        }
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
    let stale: Vec<String> = session
        .rels()
        .into_iter()
        .filter(|rel| !seen.contains(rel))
        .collect();
    for rel in &stale {
        session.remove(rel);
    }
    crate::low_conf::store_updates(root, &low_conf_updates, &stale);
    let mut edge_pairs: Vec<(String, String)> = Vec::new();
    if !quiet {
        for rel in &seen {
            for dst in session.dsts_of(rel) {
                edge_pairs.push((rel.clone(), dst));
            }
        }
    }
    let edge_n: i64 = if quiet {
        seen.iter()
            .map(|rel| session.dsts_of(rel).len() as i64)
            .sum()
    } else {
        edge_pairs.len() as i64
    };
    let cache_changed = session.has_changes();
    if let Err(err) = session.commit() {
        let kind = if err.contains("locked") {
            "CacheLocked"
        } else {
            "CacheError"
        };
        return fail_warnings(kind, err, &warnings);
    }
    let _ = seed_health_from_map(root);
    if cache_changed || !crate::maps_out::current(root) {
        if let Err(err) = crate::maps_out::write(root) {
            warnings.push(format!("map artifacts: {err}"));
        }
    }
    let map_complete = files_remaining_dirty == 0;
    let status = Json::obj(vec![
        ("map_complete", Json::Bool(map_complete)),
        ("files_remaining_dirty", Json::Int(files_remaining_dirty)),
        ("files_parsed", Json::Int(parsed)),
        ("files_skipped", Json::Int(skipped)),
        (
            "directory",
            Json::String(run.directory.clone().unwrap_or_default()),
        ),
        ("parser", Json::String("regex+reexport".into())),
    ]);
    if let Err(err) = crate::maps_out::write_status(root, &status) {
        warnings.push(format!("incremental status: {err}"));
    }
    let edge_json = Json::Array(
        edge_pairs
            .into_iter()
            .map(|(src, dst)| {
                Json::obj(vec![("src", Json::String(src)), ("dst", Json::String(dst))])
            })
            .collect(),
    );
    stream_event(
        run.stream,
        Json::obj(vec![
            ("event", Json::String("update_maps".into())),
            ("phase", Json::String("done".into())),
            ("map_complete", Json::Bool(map_complete)),
            ("files_remaining_dirty", Json::Int(files_remaining_dirty)),
        ]),
    );
    ok(vec![
        ("map_complete", Json::Bool(map_complete)),
        ("files_remaining_dirty", Json::Int(files_remaining_dirty)),
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
        ("parser", Json::String("regex+reexport".into())),
        (
            "warnings",
            Json::Array(warnings.into_iter().map(Json::String).collect()),
        ),
    ])
}

fn stream_event(stream: bool, value: Json) {
    if stream {
        eprintln!("{value}");
    }
}

fn fail_warnings(error_type: &str, error: impl Into<String>, warnings: &[String]) -> Json {
    let mut value = fail(error_type, error);
    value.insert(
        "warnings",
        Json::Array(warnings.iter().cloned().map(Json::String).collect()),
    );
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
    let scoped = monitored_seed_prefixes(root);
    let indexed = cache::index_by_path(root);
    for rel in cache::all_paths(root) {
        if let Some(prefixes) = &scoped {
            if !prefixes.iter().any(|prefix| under_prefix(prefix, &rel)) {
                continue;
            }
        }
        if known.contains(&rel) {
            continue;
        }
        let path = root.join(&rel);
        let hash = cache::hash_if_unchanged(&path, indexed.get(&rel))
            .unwrap_or_else(|| file_sha256_prefixed(&path).unwrap_or_default());
        rows.push(HealthRow::new(
            rel,
            "🟡 Yellow",
            stamp.clone(),
            "Initial stub",
            hash,
            "no_wiki",
        ));
        changed = true;
    }
    if changed || !root.join("file_health.json").is_file() && !rows.is_empty() {
        artifacts::write_health(root, &rows)?;
    }
    Ok(())
}

/// `None` seeds every mapped file: `monitored_paths.txt` is absent, empty, or only a bare `.`.
/// A list of real paths seeds only those files and directories.
fn monitored_seed_prefixes(root: &Path) -> Option<Vec<String>> {
    if !root.join("monitored_paths.txt").is_file() {
        return None;
    }
    let entries = scope::read_path_list(root, "monitored_paths.txt");
    if entries.is_empty() {
        None
    } else {
        Some(entries)
    }
}

pub fn seed_source_hashes(root: &Path, force: bool, directory: Option<&str>) -> Json {
    let _lock = match lock_or_fail(root) {
        Ok(lock) => lock,
        Err(err) => return err,
    };
    let mut rows = artifacts::read_health(root);
    let mut seeded = 0i64;
    let mut skipped_has_hash = 0i64;
    let mut skipped_not_green = 0i64;
    let mut skipped_missing = 0i64;
    for row in &mut rows {
        if let Some(dir) = directory
            .map(|d| d.trim_matches('/'))
            .filter(|d| !d.is_empty())
        {
            if !under_prefix(dir, &row.file) {
                continue;
            }
        }
        if !is_green(&row.status) {
            skipped_not_green += 1;
            continue;
        }
        if row.source_hash.starts_with("sha256:") && !force {
            skipped_has_hash += 1;
            continue;
        }
        let path = root.join(&row.file);
        if !path.is_file() {
            skipped_missing += 1;
            continue;
        }
        let hash = file_sha256_prefixed(&path).unwrap_or_default();
        if hash.is_empty() {
            skipped_missing += 1;
            continue;
        }
        row.source_hash = hash;
        row.source_mtime_ns = cache::stat_ns(&path)
            .map(|(mtime, _)| mtime.to_string())
            .unwrap_or_default();
        seeded += 1;
    }
    if seeded > 0 {
        if let Err(err) = artifacts::write_health(root, &rows) {
            return fail("HealthError", err);
        }
    }
    ok(vec![
        ("seeded", Json::Int(seeded)),
        ("skipped_has_hash", Json::Int(skipped_has_hash)),
        ("skipped_not_green", Json::Int(skipped_not_green)),
        ("skipped_missing", Json::Int(skipped_missing)),
        ("force", Json::Bool(force)),
    ])
}

pub fn mapped_edges(root: &Path) -> BTreeSet<(String, String)> {
    cache::edges(root)
}

pub fn load_dependencies(root: &Path, rel: &str) -> Json {
    dependency_report(root, rel, false)
}

pub fn dependency_report(root: &Path, rel: &str, full: bool) -> Json {
    let _ = crate::legacy_cache::import_if_empty(root);
    let rel = scope::rel_arg(root, rel);
    let rel = rel.as_str();
    if let Some(err) = unknown_file(root, rel) {
        return err;
    }
    match cache::load_dependency_view(root, rel) {
        Ok(view) => {
            let cycled = if full {
                cycle_pairs(root)
            } else {
                BTreeSet::new()
            };
            let internal: Vec<Json> = view
                .internal
                .iter()
                .map(|edge| {
                    edge_record(
                        edge,
                        full,
                        cycled.contains(&(rel.to_string(), edge.path.clone())),
                    )
                })
                .collect();
            let mut pairs = vec![
                ("file", Json::String(rel.into())),
                (
                    "detail",
                    Json::String(if full { "full" } else { "compact" }.into()),
                ),
                ("internal", Json::Array(internal.clone())),
                (
                    "external",
                    Json::Array(view.external.iter().cloned().map(Json::String).collect()),
                ),
                (
                    "needs_review",
                    Json::Array(
                        view.unresolved
                            .iter()
                            .cloned()
                            .map(|(raw, line, reason)| {
                                Json::obj(vec![
                                    ("raw", Json::String(raw)),
                                    ("line", Json::Int(line)),
                                    ("reason", Json::String(reason)),
                                ])
                            })
                            .collect(),
                    ),
                ),
            ];
            if full {
                pairs.push(("imports", Json::Array(internal)));
            }
            ok(pairs)
        }
        Err(e) => fail("CacheError", e),
    }
}

fn edge_record(edge: &cache::InternalEdge, full: bool, in_cycle: bool) -> Json {
    let mut pairs = vec![
        ("path".into(), Json::String(edge.path.clone())),
        ("line".into(), Json::Int(edge.line)),
        (
            "names".into(),
            Json::Array(edge.names.iter().cloned().map(Json::String).collect()),
        ),
        ("conditional".into(), Json::Bool(edge.conditional)),
        ("dynamic".into(), Json::Bool(edge.dynamic)),
        ("via_barrel".into(), Json::Bool(edge.via_barrel)),
        ("confidence".into(), Json::Float(edge.confidence())),
    ];
    if full {
        pairs.push(("resolved_path".into(), Json::String(edge.path.clone())));
        pairs.push(("confidence_score".into(), Json::Float(edge.confidence())));
        pairs.push((
            "confidence_reasons".into(),
            Json::Array(vec![Json::String(edge.acs_reason().into())]),
        ));
        pairs.push(("acs".into(), Json::String(edge.acs_reason().into())));
        pairs.push(("is_dynamic".into(), Json::Bool(edge.dynamic)));
        pairs.push(("is_conditional".into(), Json::Bool(edge.conditional)));
        pairs.push(("in_cycle".into(), Json::Bool(in_cycle)));
    }
    Json::from_pairs(pairs)
}

pub fn load_dependents(root: &Path, rel: &str) -> Json {
    let _ = crate::legacy_cache::import_if_empty(root);
    let rel = scope::rel_arg(root, rel);
    let rel = rel.as_str();
    if let Some(err) = unknown_file(root, rel) {
        return err;
    }
    match cache::load_dependents(root, rel) {
        Ok(srcs) => ok(vec![
            ("file", Json::String(rel.into())),
            (
                "dependents",
                Json::Array(srcs.into_iter().map(Json::String).collect()),
            ),
        ]),
        Err(e) => fail("CacheError", e),
    }
}

pub fn list_paths(root: &Path, prefix: &str) -> Json {
    list_paths_at(root, prefix, 1, None)
}

pub fn list_paths_at(root: &Path, prefix: &str, depth: i64, max_files: Option<usize>) -> Json {
    let _ = crate::legacy_cache::import_if_empty(root);
    let mut paths = cache::list_prefix(root, prefix).unwrap_or_default();
    let pref = prefix.trim_matches('/');
    if depth <= 0 {
        let mut truncated = false;
        if let Some(max) = max_files {
            if paths.len() > max {
                paths.truncate(max);
                truncated = true;
            }
        }
        let mut value = ok(vec![
            ("prefix", Json::String(pref.into())),
            ("depth", Json::Int(0)),
            (
                "files",
                Json::Array(paths.iter().cloned().map(Json::String).collect()),
            ),
            ("file_count", Json::Int(paths.len() as i64)),
            ("files_truncated", Json::Bool(truncated)),
        ]);
        if truncated {
            value.insert("files_complete", Json::Bool(false));
        }
        return value;
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
    let mut truncated = false;
    if let Some(max) = max_files {
        if direct_files.len() > max {
            direct_files.truncate(max);
            truncated = true;
        }
    }
    let mut value = ok(vec![
        ("prefix", Json::String(pref.into())),
        ("depth", Json::Int(1)),
        (
            "files",
            Json::Array(direct_files.into_iter().map(Json::String).collect()),
        ),
        (
            "dirs",
            Json::Array(
                dir_counts
                    .into_iter()
                    .map(|(p, n)| Json::obj(vec![("p", Json::String(p)), ("n", Json::Int(n))]))
                    .collect(),
            ),
        ),
        ("file_count", Json::Int(paths.len() as i64)),
        ("files_truncated", Json::Bool(truncated)),
    ]);
    if truncated {
        value.insert("files_complete", Json::Bool(false));
    }
    value
}

pub fn session_bootstrap(root: &Path) -> Json {
    session_bootstrap_scoped(root, None)
}

pub fn session_bootstrap_scoped(root: &Path, directory: Option<&str>) -> Json {
    let scope = scope::detect(root);
    if scope.container || !scope.missing_dirs.is_empty() {
        let actions = Json::Array(vec![Json::obj(vec![
            ("action", Json::String("fix_scope".into())),
            ("priority", Json::Int(1)),
            (
                "reason",
                Json::String(
                    scope
                        .warnings
                        .first()
                        .cloned()
                        .unwrap_or_else(|| "scope risk".into()),
                ),
            ),
        ])]);
        return ok(vec![
            ("version", Json::String(VERSION.into())),
            (
                "readiness",
                Json::String(readiness_of(&scope, false, &[], false).into()),
            ),
            ("health_summary", health_summary(root)),
            ("actions", actions),
            ("files", Json::Array(vec![])),
            ("map_complete", Json::Bool(false)),
            ("scope", scope_json(&scope)),
        ]);
    }
    let legacy_warning = crate::legacy_cache::import_if_empty(root).ok().flatten();
    if cache::all_paths(root).is_empty() {
        let built = update_maps(root);
        if built.get("success").and_then(|s| s.as_bool()) != Some(true) {
            return built;
        }
    }
    if artifacts::folder_card(root, "").is_none() && !cache::all_paths(root).is_empty() {
        let _ = crate::maps_out::write(root);
    }
    let mut file_names = cache::all_paths(root);
    let mut rows = artifacts::read_health(root);
    if let Some(dir) = directory
        .map(|d| d.trim_matches('/'))
        .filter(|d| !d.is_empty())
    {
        file_names.retain(|rel| under_prefix(dir, rel));
        rows.retain(|row| under_prefix(dir, &row.file));
    }
    let files: Vec<Json> = file_names.iter().cloned().map(Json::String).collect();
    let actions = suggest_next_scoped(root, directory);
    let action_list = actions
        .get("actions")
        .cloned()
        .unwrap_or(Json::Array(vec![]));
    let map_index = artifacts::folder_card(root, "")
        .and_then(|text| crate::jsonutil::parse(&text).ok())
        .unwrap_or_else(|| Json::obj(vec![]));
    let mut value = ok(vec![
        ("version", Json::String(VERSION.into())),
        (
            "readiness",
            Json::String(
                readiness_of(&scope, !files.is_empty(), &rows, health_file_present(root)).into(),
            ),
        ),
        ("health_summary", health_summary_of(&rows)),
        ("actions", action_list),
        ("files", Json::Array(files)),
        ("map_index", map_index),
        (
            "map_complete",
            Json::Bool(scope.missing_dirs.is_empty() && !scope.container),
        ),
        ("scope", scope_json(&scope)),
    ]);
    if let Some(warning) = legacy_warning {
        value.insert("warnings", Json::Array(vec![Json::String(warning)]));
    }
    let status = crate::maps_out::read_status(root);
    if let Some(Json::Int(n)) = status.get("files_remaining_dirty") {
        value.insert("files_remaining_dirty", Json::Int(*n));
        if *n > 0 {
            value.insert("map_complete", Json::Bool(false));
        }
    }
    value
}

fn health_summary(root: &Path) -> Json {
    health_summary_of(&artifacts::read_health(root))
}

fn health_summary_of(rows: &[HealthRow]) -> Json {
    let mut green = 0i64;
    let mut yellow = 0i64;
    let mut red = 0i64;
    for row in rows {
        if row.status.contains("Green") || row.status.contains('🟢') {
            green += 1;
        } else if row.status.contains("Red") || row.status.contains('🔴') {
            red += 1;
        } else {
            yellow += 1;
        }
    }
    let mut verified = 0i64;
    let mut forced = 0i64;
    let mut no_wiki = 0i64;
    let mut unchecked = 0i64;
    let mut legacy = 0i64;
    let mut other = 0i64;
    for row in rows {
        if !is_green(&row.status) {
            continue;
        }
        match row.verification.as_str() {
            "verified" => verified += 1,
            "forced" => forced += 1,
            "no_wiki" => no_wiki += 1,
            "unchecked" => unchecked += 1,
            "legacy" => legacy += 1,
            _ => other += 1,
        }
    }
    Json::obj(vec![
        ("total", Json::Int(rows.len() as i64)),
        ("green", Json::Int(green)),
        ("yellow", Json::Int(yellow)),
        ("red", Json::Int(red)),
        (
            "green_breakdown",
            Json::obj(vec![
                ("verified", Json::Int(verified)),
                ("forced", Json::Int(forced)),
                ("no_wiki", Json::Int(no_wiki)),
                ("unchecked", Json::Int(unchecked)),
                ("legacy", Json::Int(legacy)),
                ("other", Json::Int(other)),
            ]),
        ),
    ])
}

pub fn suggest_next_actions(root: &Path) -> Json {
    suggest_next_scoped(root, None)
}

pub fn suggest_next_scoped(root: &Path, directory: Option<&str>) -> Json {
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
        if let Some(dir) = directory
            .map(|d| d.trim_matches('/'))
            .filter(|d| !d.is_empty())
        {
            if !under_prefix(dir, &row.file) {
                continue;
            }
        }
        if row.status.contains("Red") || row.status.contains('🔴') {
            actions.push(Json::obj(vec![
                ("action", Json::String("record_deletion".into())),
                ("file", Json::String(row.file)),
                ("priority", Json::Int(1)),
                ("reason", Json::String(row.reason)),
            ]));
        } else if row.reason != "Initial stub"
            && (row.status.contains("Yellow") || row.status.contains('🟡'))
        {
            actions.push(Json::obj(vec![
                ("action", Json::String("prepare_edit".into())),
                ("file", Json::String(row.file)),
                ("priority", Json::Int(2)),
                ("reason", Json::String(row.reason)),
            ]));
        }
    }
    let low_conf = crate::low_conf::actionable_total(root, directory);
    if low_conf > 0 {
        actions.push(Json::obj(vec![
            ("action", Json::String("review_low_confidence_edges".into())),
            ("priority", Json::Int(4)),
            (
                "reason",
                Json::String(format!(
                    "{low_conf} actionable low-confidence project edges (see get_dependencies)"
                )),
            ),
        ]));
    }
    if actions.is_empty() {
        actions.push(Json::obj(vec![
            ("action", Json::String("lookup_only".into())),
            ("priority", Json::Int(5)),
            (
                "reason",
                Json::String("Health clean. Use prepare_edit for lookup.".into()),
            ),
        ]));
    }
    actions.sort_by(|a, b| {
        let pa = match a.get("priority") {
            Some(Json::Int(n)) => *n,
            _ => 9,
        };
        let pb = match b.get("priority") {
            Some(Json::Int(n)) => *n,
            _ => 9,
        };
        pa.cmp(&pb)
    });
    let rows = artifacts::read_health(root);
    ok(vec![
        ("actions", Json::Array(actions)),
        (
            "readiness",
            Json::String(
                readiness_of(
                    &scope,
                    !cache::all_paths(root).is_empty(),
                    &rows,
                    health_file_present(root),
                )
                .into(),
            ),
        ),
    ])
}

pub fn check_changes(root: &Path) -> Json {
    let _lock = match lock_or_fail(root) {
        Ok(lock) => lock,
        Err(err) => return err,
    };
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
    for entry in scope::read_path_list(root, "monitored_paths.txt") {
        if root.join(&entry).is_file() {
            watched.insert(entry);
        }
    }
    let cap = std::env::var("WIKIFIER_CHECK_CHANGES_MAX")
        .ok()
        .and_then(|s| s.parse::<usize>().ok())
        .unwrap_or(2000);
    let mut watched: Vec<String> = watched.into_iter().collect();
    watched.sort();
    let truncated = watched.len() > cap;
    if truncated {
        watched.truncate(cap);
    }
    let reason = "content changed since last mark-green (check-changes)";
    let mut dirty = Vec::new();
    let mut changed_rows = false;
    let indexed = cache::index_by_path(root);
    let mut row_at: HashMap<String, usize> = rows
        .iter()
        .enumerate()
        .map(|(i, row)| (row.file.clone(), i))
        .collect();
    for rel in watched {
        let path = root.join(&rel);
        let idx = row_at.get(&rel).copied();
        if !path.is_file() {
            dirty.push(rel.clone());
            let already = idx.map(|i| is_red(&rows[i].status)).unwrap_or(false);
            if !already {
                let mut row = HealthRow::new(
                    rel.clone(),
                    "🔴 Red",
                    local_stamp(),
                    "missing on disk (check-changes)",
                    idx.map(|i| rows[i].source_hash.clone()).unwrap_or_default(),
                    idx.map(|i| rows[i].verification.clone())
                        .unwrap_or_default(),
                );
                if let Some(i) = idx {
                    row.keep_baseline_from(&rows[i]);
                }
                if let Some(i) = idx {
                    rows[i] = row;
                } else {
                    row_at.insert(rel.clone(), rows.len());
                    rows.push(row);
                }
                let _ = artifacts::append_journal(root, "check-changes", &rel, "missing on disk");
                changed_rows = true;
            }
            continue;
        }
        let baseline = idx.and_then(|i| {
            let h = rows[i].source_hash.clone();
            if h.starts_with("sha256:") {
                Some(h)
            } else {
                None
            }
        });
        let index_row = indexed.get(&rel);
        // Stat first: a file whose size and mtime still match its cache row has the content
        // hash recorded there (the rule update-maps skips by). Read and hash it only when
        // the stat moved or that hash is not the baseline being checked.
        let live = cache::hash_if_unchanged(&path, index_row)
            .filter(|hash| baseline.as_ref().is_none_or(|base| base == hash))
            .unwrap_or_else(|| file_sha256_prefixed(&path).unwrap_or_default());
        let drifted = match &baseline {
            Some(base) => live != *base,
            None => index_row.map(|r| r.2 != live).unwrap_or(false),
        };
        if !drifted {
            continue;
        }
        dirty.push(rel.clone());
        let already = idx
            .map(|i| {
                is_yellow(&rows[i].status)
                    && rows[i]
                        .reason
                        .contains("content changed since last mark-green")
            })
            .unwrap_or(false);
        if !already {
            let keep_hash = baseline.unwrap_or(live);
            let verification = idx
                .map(|i| rows[i].verification.clone())
                .unwrap_or_default();
            let mut row = HealthRow::new(
                rel.clone(),
                "🟡 Yellow",
                local_stamp(),
                reason,
                keep_hash,
                verification,
            );
            if let Some(i) = idx {
                row.keep_baseline_from(&rows[i]);
            }
            if let Some(i) = idx {
                rows[i] = row;
            } else {
                row_at.insert(rel.clone(), rows.len());
                rows.push(row);
            }
            let _ = artifacts::append_journal(root, "check-changes", &rel, reason);
            let pending = root.join("pending_updates.md");
            let text = fs::read_to_string(&pending).unwrap_or_default();
            let text =
                crate::pending_line::append_item(&text, &rel, crate::pending_line::CHECK_MESSAGE);
            let _ = fs::write(&pending, text);
            changed_rows = true;
        }
    }
    if changed_rows {
        let _ = artifacts::write_health(root, &rows);
    }
    let mut value = ok(vec![
        ("dirty_total", Json::Int(dirty.len() as i64)),
        ("changes_detected", Json::Int(dirty.len() as i64)),
        (
            "files",
            Json::Array(dirty.into_iter().map(Json::String).collect()),
        ),
        ("scope", scope_json(&scope)),
    ]);
    if truncated {
        value.insert("truncated", Json::Bool(true));
        value.insert(
            "warnings",
            Json::Array(vec![Json::String(format!(
                "check-changes stopped at {cap} files (WIKIFIER_CHECK_CHANGES_MAX)"
            ))]),
        );
    }
    value
}

pub fn prepare_edit(root: &Path, file: &str) -> Json {
    let rel = scope::rel_arg(root, file);
    let rel = rel.as_str();
    let _ = crate::legacy_cache::import_if_empty(root);
    if let Some(err) = unknown_file(root, rel) {
        return err;
    }
    let deps = cache::load_dependencies(root, rel).unwrap_or_default();
    let importers = cache::load_dependents(root, rel).unwrap_or_default();
    let row = artifacts::read_health(root)
        .into_iter()
        .find(|r| r.file == rel);
    ok(vec![
        ("file", Json::String(rel.into())),
        (
            "status",
            Json::String(row.as_ref().map(|r| r.status.clone()).unwrap_or_default()),
        ),
        (
            "dependencies",
            Json::Array(
                deps.into_iter()
                    .map(|path| {
                        Json::obj(vec![
                            ("path", Json::String(path.clone())),
                            ("resolved_path", Json::String(path)),
                        ])
                    })
                    .collect(),
            ),
        ),
        (
            "dependents",
            Json::Array(importers.into_iter().map(Json::String).collect()),
        ),
        (
            "wiki",
            Json::String(crate::wiki_files::read_wiki(root, rel).1),
        ),
    ])
}

pub fn record_change(root: &Path, file: &str, reason: &str) -> Json {
    let _lock = match lock_or_fail(root) {
        Ok(lock) => lock,
        Err(err) => return err,
    };
    let rel = scope::rel_arg(root, file);
    let rel = rel.as_str();
    let path = root.join(rel);
    if !path.is_file() {
        return fail("FileNotFound", format!("file does not exist: {rel}"));
    }
    let written = match artifacts::append_journal(root, "record-change", rel, reason) {
        Ok(written) => written,
        Err(e) => return fail("JournalError", e),
    };
    let hash = file_sha256_prefixed(&path).unwrap_or_default();
    let mut row = HealthRow::new(rel, "🟡 Yellow", written.stamp, reason, hash, "");
    if let Some(old) = artifacts::read_health(root)
        .into_iter()
        .find(|r| r.file == rel)
    {
        row.keep_baseline_from(&old);
    }
    if let Err(e) = artifacts::upsert_health_row(root, row) {
        return fail("HealthError", e);
    }
    let pending = root.join("pending_updates.md");
    let text = fs::read_to_string(&pending).unwrap_or_default();
    let text =
        crate::pending_line::append_item(&text, rel, &crate::pending_line::record_message(reason));
    if fs::write(&pending, text).is_err() {
        return fail("PendingError", "could not write pending_updates.md");
    }
    ok(vec![
        ("file", Json::String(rel.into())),
        ("journaled", Json::Bool(written.journaled)),
        ("duplicate_skipped", Json::Bool(!written.journaled)),
    ])
}

pub fn mark_green(root: &Path, file: &str, reason: &str, force: bool) -> Json {
    let _lock = match lock_or_fail(root) {
        Ok(lock) => lock,
        Err(err) => return err,
    };
    let rel = scope::rel_arg(root, file);
    let rel = rel.as_str();
    let path = root.join(rel);
    if !path.is_file() {
        return fail("FileNotFound", format!("file does not exist: {rel}"));
    }
    if force && reason.trim().is_empty() {
        return fail(
            "ValueError",
            "force=True needs a reason explaining why the wiki is still accurate",
        );
    }
    let symbols = public_symbols(&path);
    let (found_wiki, wiki) = crate::wiki_files::read_wiki(root, rel);
    let wiki_path = found_wiki.unwrap_or_else(|| root.join(format!("{rel}.wiki.md")));
    let previous = artifacts::read_health(root)
        .into_iter()
        .find(|r| r.file == rel);
    let verdict = wiki_verdict(&symbols, &wiki, previous.as_ref(), &wiki_path);
    if wiki.is_empty() {
        let _ = write_green_row(root, rel, &path, reason, "no_wiki", &symbols.names);
        return attach_warning(
            ok(vec![
                ("file", Json::String(rel.into())),
                ("verification", Json::String("no_wiki".into())),
            ]),
            symbols.warning,
        );
    }
    if !verdict.issues.is_empty() && !force {
        return attach_warning(
            Json::obj(vec![
                ("success", Json::Bool(false)),
                ("error", Json::String("wiki misses public symbols".into())),
                ("error_type", Json::String("WikiVerificationError".into())),
                ("file", Json::String(rel.into())),
                (
                    "issues",
                    Json::Array(verdict.issues.into_iter().map(Json::String).collect()),
                ),
            ]),
            symbols.warning.or(verdict.warning),
        );
    }
    let verification = if !symbols.extractor {
        "unchecked"
    } else if !verdict.issues.is_empty() && force {
        "forced"
    } else {
        "verified"
    };
    if let Err(e) = write_green_row(root, rel, &path, reason, verification, &symbols.names) {
        return attach_warning(fail("HealthError", e), symbols.warning);
    }
    attach_warning(
        ok(vec![
            ("file", Json::String(rel.into())),
            ("verification", Json::String(verification.into())),
        ]),
        symbols.warning.or(verdict.warning),
    )
}

struct SymbolScan {
    names: Vec<String>,
    warning: Option<String>,
    extractor: bool,
}

struct WikiVerdict {
    issues: Vec<String>,
    warning: Option<String>,
}

fn wiki_verdict(
    symbols: &SymbolScan,
    wiki: &str,
    previous: Option<&HealthRow>,
    wiki_path: &Path,
) -> WikiVerdict {
    let mut issues = Vec::new();
    let mut warning = None;
    if wiki.is_empty() || !symbols.extractor {
        return WikiVerdict { issues, warning };
    }
    for sym in &symbols.names {
        if !wiki.contains(sym) {
            issues.push(format!("undocumented_new_symbols: {sym}"));
        }
    }
    let baseline: Vec<String> = previous
        .map(|row| split_symbols(&row.public_symbols))
        .unwrap_or_default();
    let had_baseline =
        previous.is_some_and(|row| !row.public_symbols.is_empty() || !row.wiki_hash.is_empty());
    if !had_baseline {
        warning = Some("no_symbol_baseline".into());
    } else {
        for sym in &baseline {
            if !symbols.names.iter().any(|name| name == sym) && wiki.contains(&format!("`{sym}`")) {
                issues.push(format!("wiki_mentions_removed_symbols: {sym}"));
            }
        }
        let surface_changed = !same_symbols(&baseline, &symbols.names);
        let wiki_hash = file_sha256_prefixed(wiki_path).unwrap_or_default();
        let old_hash = previous
            .map(|row| row.wiki_hash.clone())
            .unwrap_or_default();
        if surface_changed && !old_hash.is_empty() && wiki_hash == old_hash {
            issues.push("wiki_not_updated_for_api_change".into());
        }
    }
    WikiVerdict { issues, warning }
}

fn split_symbols(text: &str) -> Vec<String> {
    text.split(['\n', ','])
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .collect()
}

fn same_symbols(left: &[String], right: &[String]) -> bool {
    let mut a = left.to_vec();
    let mut b = right.to_vec();
    a.sort();
    b.sort();
    a.dedup();
    b.dedup();
    a == b
}

fn write_green_row(
    root: &Path,
    rel: &str,
    path: &Path,
    reason: &str,
    verification: &str,
    symbols: &[String],
) -> Result<(), String> {
    let wiki_path = crate::wiki_files::find_wiki(root, rel)
        .unwrap_or_else(|| root.join(format!("{rel}.wiki.md")));
    let mut row = HealthRow::new(
        rel,
        "🟢 Green",
        local_stamp(),
        if reason.is_empty() {
            if verification == "no_wiki" {
                "no wiki"
            } else {
                "mark-green"
            }
        } else {
            reason
        },
        file_sha256_prefixed(path).unwrap_or_default(),
        verification,
    );
    row.public_symbols = symbols.join("\n");
    row.wiki_hash = if wiki_path.is_file() {
        file_sha256_prefixed(&wiki_path).unwrap_or_default()
    } else {
        String::new()
    };
    row.source_mtime_ns = cache::stat_ns(path)
        .map(|(mtime, _)| mtime.to_string())
        .unwrap_or_default();
    artifacts::upsert_health_row(root, row)?;
    drop_pending_line(root, rel);
    Ok(())
}

fn public_symbols(path: &Path) -> SymbolScan {
    let (text, warning) = crate::parse::read_utf8(path);
    let ext = path
        .extension()
        .and_then(|s| s.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();
    if ext == "py" || ext == "pyi" {
        return SymbolScan {
            names: crate::symbols::python_public_symbols(&text),
            warning,
            extractor: true,
        };
    }
    if matches!(
        ext.as_str(),
        "js" | "ts" | "jsx" | "tsx" | "mjs" | "cjs" | "mts" | "cts"
    ) {
        return SymbolScan {
            names: crate::symbols::js_public_symbols(&text),
            warning,
            extractor: true,
        };
    }
    if ext == "rs" {
        return SymbolScan {
            names: crate::parse::rust_public_symbols(&text),
            warning,
            extractor: true,
        };
    }
    SymbolScan {
        names: Vec::new(),
        warning,
        extractor: false,
    }
}

pub fn health(root: &Path) -> Json {
    health_view(root, None, "json")
}

pub fn health_view(root: &Path, directory: Option<&str>, format: &str) -> Json {
    if format == "healing-stats" {
        return healing_stats(root);
    }
    let mut rows = artifacts::read_health(root);
    if let Some(dir) = directory
        .map(|d| d.trim_matches('/'))
        .filter(|d| !d.is_empty())
    {
        rows.retain(|row| under_prefix(dir, &row.file));
    }
    let summary = health_summary_of(&rows);
    if format == "summary" {
        let mut value = ok(vec![("health_summary", summary)]);
        if let Some(dir) = directory {
            value.insert("directory", Json::String(dir.into()));
        }
        return value;
    }
    ok(vec![
        ("health_summary", summary),
        (
            "entries",
            Json::Array(rows.into_iter().map(health_entry).collect()),
        ),
    ])
}

fn health_entry(row: HealthRow) -> Json {
    Json::obj(vec![
        ("file", Json::String(row.file)),
        ("status", Json::String(row.status)),
        ("last_updated", Json::String(row.last_updated)),
        ("reason", Json::String(row.reason)),
        ("source_content_hash", Json::String(row.source_hash)),
        ("verification", Json::String(row.verification)),
    ])
}

fn under_prefix(prefix: &str, rel: &str) -> bool {
    let prefix = prefix.trim_matches('/');
    prefix.is_empty() || rel == prefix || rel.starts_with(&format!("{prefix}/"))
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
        (
            "cache_backend",
            Json::String(if paths.is_empty() { "none" } else { "wk_cache" }.into()),
        ),
        ("files", Json::Int(paths.len() as i64)),
        ("sha256", Json::Bool(true)),
    ])
}

pub fn validate(root: &Path) -> Json {
    let scope = scope::detect(root);
    let files = scope::collect(root, &scope).unwrap_or_default();
    let known: BTreeSet<String> = artifacts::read_health(root)
        .into_iter()
        .map(|r| r.file)
        .collect();
    let missing: Vec<String> = files
        .iter()
        .map(|p| scope::rel_of(root, p))
        .filter(|rel| !known.contains(rel))
        .collect();
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
        fail(
            "CacheInconsistent",
            "forward and reverse cache indexes disagree",
        )
    } else if !drift.is_empty() {
        fail(
            "StaleMap",
            "cached hashes do not match file bytes; run update-maps --full",
        )
    } else {
        ok(vec![])
    };
    value.insert(
        "missing",
        Json::Array(missing.iter().cloned().map(Json::String).collect()),
    );
    value.insert("missing_count", Json::Int(missing.len() as i64));
    value.insert("cache_consistent", Json::Bool(check.consistent));
    value.insert("cache_incomplete", Json::Bool(check.incomplete));
    value.insert(
        "cache_mismatches",
        Json::Array(check.mismatches.into_iter().map(Json::String).collect()),
    );
    value.insert(
        "content_drift",
        Json::Array(drift.iter().cloned().map(Json::String).collect()),
    );
    value.insert("content_drift_count", Json::Int(drift.len() as i64));
    value
}

pub fn cycles(root: &Path) -> Json {
    cycles_view(root, true, None)
}

pub fn cycles_view(root: &Path, analysis: bool, max_items: Option<usize>) -> Json {
    let _ = crate::legacy_cache::import_if_empty(root);
    let edges = cache::edges(root);
    let mut graph: BTreeMap<String, Vec<String>> = BTreeMap::new();
    for (src, dst) in &edges {
        graph.entry(src.clone()).or_default().push(dst.clone());
        graph.entry(dst.clone()).or_default();
    }
    let sccs = tarjan(&graph);
    let cyclic: Vec<Vec<String>> = sccs.into_iter().filter(|c| c.len() > 1).collect();
    let meta = edge_meta(root, cyclic.iter().flatten());
    let value = ok(vec![
        ("count", Json::Int(cyclic.len() as i64)),
        (
            "cycles",
            Json::Array(
                cyclic
                    .into_iter()
                    .map(|files| {
                        let set: BTreeSet<String> = files.iter().cloned().collect();
                        let mut weakest: Option<(f64, String, String)> = None;
                        for src in &files {
                            for dst in graph.get(src).into_iter().flatten() {
                                if !set.contains(dst) {
                                    continue;
                                }
                                let score = meta
                                    .get(&(src.clone(), dst.clone()))
                                    .map(|edge| edge.confidence())
                                    .unwrap_or(0.9);
                                if weakest
                                    .as_ref()
                                    .map(|(have, _, _)| score < *have)
                                    .unwrap_or(true)
                                {
                                    weakest = Some((score, src.clone(), dst.clone()));
                                }
                            }
                        }
                        let outside = edges
                            .iter()
                            .filter(|(src, dst)| set.contains(src) && !set.contains(dst))
                            .count() as i64;
                        let mut obj = vec![
                            ("size".into(), Json::Int(files.len() as i64)),
                            (
                                "files".into(),
                                Json::Array(files.into_iter().map(Json::String).collect()),
                            ),
                            ("external_edges".into(), Json::Int(outside)),
                        ];
                        if let Some((score, src, dst)) = weakest {
                            obj.push((
                                "break_hint".into(),
                                Json::obj(vec![
                                    ("src", Json::String(src)),
                                    ("dst", Json::String(dst)),
                                    ("confidence", Json::Float(score)),
                                    (
                                        "reason",
                                        Json::String(
                                            "lowest-confidence edge inside the component".into(),
                                        ),
                                    ),
                                ]),
                            ));
                        }
                        Json::from_pairs(obj)
                    })
                    .collect(),
            ),
        ),
    ]);
    let listed: Vec<(String, String)> = edges.iter().cloned().collect();
    let mut value = crate::cycle_report::enrich(value, analysis, max_items);
    if analysis {
        value.insert(
            "reverse_dependencies",
            Json::Array(crate::cycle_report::rank_dependents(&listed)),
        );
    }
    value
}

/// Edge flags for the given source files only. `cycles` needs them for files inside a
/// cycle, so it no longer opens every mapped file's records.
fn edge_meta<'a>(
    root: &Path,
    files: impl Iterator<Item = &'a String>,
) -> BTreeMap<(String, String), cache::InternalEdge> {
    let mut out = BTreeMap::new();
    let files: BTreeSet<&String> = files.collect();
    for rel in files {
        for edge in cache::load_internal_edges(root, rel) {
            out.insert((rel.clone(), edge.path.clone()), edge);
        }
    }
    out
}

fn cycle_pairs(root: &Path) -> BTreeSet<(String, String)> {
    let edges = cache::edges(root);
    let mut graph: BTreeMap<String, Vec<String>> = BTreeMap::new();
    for (src, dst) in &edges {
        graph.entry(src.clone()).or_default().push(dst.clone());
        graph.entry(dst.clone()).or_default();
    }
    let mut pairs = BTreeSet::new();
    for comp in tarjan(&graph).into_iter().filter(|c| c.len() > 1) {
        let set: BTreeSet<String> = comp.iter().cloned().collect();
        for src in &comp {
            for dst in graph.get(src).into_iter().flatten() {
                if set.contains(dst) {
                    pairs.insert((src.clone(), dst.clone()));
                }
            }
        }
    }
    pairs
}

struct Tarjan<'a> {
    graph: &'a BTreeMap<String, Vec<String>>,
    index: i64,
    stack: Vec<String>,
    on: BTreeSet<String>,
    idx: BTreeMap<String, i64>,
    low: BTreeMap<String, i64>,
    out: Vec<Vec<String>>,
}

impl Tarjan<'_> {
    fn strong(&mut self, node: &str) {
        self.idx.insert(node.to_string(), self.index);
        self.low.insert(node.to_string(), self.index);
        self.index += 1;
        self.stack.push(node.to_string());
        self.on.insert(node.to_string());
        let next: Vec<String> = self
            .graph
            .get(node)
            .into_iter()
            .flatten()
            .cloned()
            .collect();
        for nxt in next {
            if !self.idx.contains_key(&nxt) {
                self.strong(&nxt);
                let ln = *self.low.get(node).unwrap_or(&0);
                let lnxt = *self.low.get(&nxt).unwrap_or(&0);
                self.low.insert(node.to_string(), ln.min(lnxt));
            } else if self.on.contains(&nxt) {
                let ln = *self.low.get(node).unwrap_or(&0);
                let inxt = *self.idx.get(&nxt).unwrap_or(&0);
                self.low.insert(node.to_string(), ln.min(inxt));
            }
        }
        if self.low.get(node) == self.idx.get(node) {
            let mut comp = Vec::new();
            while let Some(w) = self.stack.pop() {
                self.on.remove(&w);
                let done = w == node;
                comp.push(w);
                if done {
                    break;
                }
            }
            comp.sort();
            self.out.push(comp);
        }
    }
}

fn tarjan(graph: &BTreeMap<String, Vec<String>>) -> Vec<Vec<String>> {
    let mut search = Tarjan {
        graph,
        index: 0,
        stack: Vec::new(),
        on: BTreeSet::new(),
        idx: BTreeMap::new(),
        low: BTreeMap::new(),
        out: Vec::new(),
    };
    let nodes: Vec<String> = graph.keys().cloned().collect();
    for n in nodes {
        if !search.idx.contains_key(&n) {
            search.strong(&n);
        }
    }
    search.out
}

pub fn verify_wikis(root: &Path) -> Json {
    verify_wikis_under(root, None, None)
}

fn verify_wikis_under(root: &Path, prefix: Option<&str>, limit: Option<usize>) -> Json {
    let rows = artifacts::read_health(root);
    let prefix = prefix
        .map(|p| p.trim_matches('/'))
        .filter(|p| !p.is_empty());
    let mut checked = 0i64;
    let mut failed = Vec::new();
    let mut failing_total = 0i64;
    let mut warnings = Vec::new();
    for row in rows {
        if !is_green(&row.status) {
            continue;
        }
        if let Some(prefix) = prefix {
            if row.file != prefix && !row.file.starts_with(&format!("{prefix}/")) {
                continue;
            }
        }
        let path = root.join(&row.file);
        if !path.is_file() {
            continue;
        }
        checked += 1;
        let (found_wiki, wiki) = crate::wiki_files::read_wiki(root, &row.file);
        let wiki_path = found_wiki.unwrap_or_else(|| root.join(format!("{}.wiki.md", row.file)));
        if wiki.is_empty() {
            continue;
        }
        let symbols = public_symbols(&path);
        if let Some(warning) = &symbols.warning {
            warnings.push(format!("{}: {warning}", row.file));
        }
        let verdict = wiki_verdict(&symbols, &wiki, Some(&row), &wiki_path);
        if let Some(warning) = verdict.warning {
            warnings.push(format!("{}: {warning}", row.file));
        }
        if !verdict.issues.is_empty() {
            failing_total += 1;
            if limit.map(|max| failed.len() < max).unwrap_or(true) {
                failed.push(Json::obj(vec![
                    ("file", Json::String(row.file)),
                    (
                        "issues",
                        Json::Array(verdict.issues.into_iter().map(Json::String).collect()),
                    ),
                ]));
            }
        }
    }
    let warning_json = Json::Array(warnings.into_iter().map(Json::String).collect());
    if failing_total == 0 {
        ok(vec![
            ("checked", Json::Int(checked)),
            ("failed", Json::Array(vec![])),
            ("failing_count", Json::Int(0)),
            ("warnings", warning_json),
        ])
    } else {
        Json::obj(vec![
            ("success", Json::Bool(false)),
            (
                "error",
                Json::String("one or more Green wikis miss public symbols".into()),
            ),
            ("error_type", Json::String("WikiVerificationError".into())),
            ("checked", Json::Int(checked)),
            ("failed", Json::Array(failed)),
            ("failing_count", Json::Int(failing_total)),
            ("warnings", warning_json),
        ])
    }
}

pub fn record_changes(root: &Path, reason_lines: &[String], default_reason: Option<&str>) -> Json {
    record_changes_opts(root, reason_lines, default_reason, &[], None, false, false)
}

pub fn record_changes_opts(
    root: &Path,
    reason_lines: &[String],
    default_reason: Option<&str>,
    only: &[String],
    since: Option<&str>,
    green: bool,
    dry_run: bool,
) -> Json {
    let _lock = if dry_run {
        None
    } else {
        match lock_or_fail(root) {
            Ok(lock) => Some(lock),
            Err(err) => return err,
        }
    };
    let changes = match git_changes(root, since) {
        Ok(changes) => changes,
        Err(err) => return fail("GitUnavailableError", err),
    };
    let reasons: Vec<(String, String)> = reason_lines
        .iter()
        .filter_map(|line| {
            line.split_once('=')
                .map(|(p, w)| (p.to_string(), w.to_string()))
        })
        .collect();
    let mut selected = Vec::new();
    for change in changes {
        if artifact_path(&change.path) {
            continue;
        }
        if !only_allows(&change.path, only) {
            continue;
        }
        selected.push(change);
    }
    let mut missing = Vec::new();
    let mut planned: Vec<(GitChange, String)> = Vec::new();
    for change in &selected {
        let why =
            reason_for(&change.path, &reasons).or_else(|| default_reason.map(|s| s.to_string()));
        match why {
            Some(why) => planned.push((change.clone(), why)),
            None => missing.push(change.path.clone()),
        }
    }
    let unused: Vec<String> = reasons
        .iter()
        .filter(|(key, _)| {
            !selected
                .iter()
                .any(|change| reason_key_matches(key, &change.path))
        })
        .map(|(key, _)| key.clone())
        .collect();
    if !missing.is_empty() {
        return Json::obj(vec![
            ("success", Json::Bool(false)),
            (
                "error",
                Json::String("every changed file needs a reason".into()),
            ),
            ("error_type", Json::String("MissingReasons".into())),
            (
                "missing_reasons",
                Json::Array(missing.iter().cloned().map(Json::String).collect()),
            ),
            (
                "template",
                Json::String(
                    missing
                        .iter()
                        .map(|f| format!("{f}=WHY"))
                        .collect::<Vec<_>>()
                        .join("\n"),
                ),
            ),
            (
                "unused_reasons",
                Json::Array(unused.into_iter().map(Json::String).collect()),
            ),
            ("recorded", Json::Int(0)),
        ]);
    }
    if dry_run {
        return ok(vec![
            ("dry_run", Json::Bool(true)),
            ("recorded", Json::Int(planned.len() as i64)),
            (
                "files",
                Json::Array(
                    planned
                        .iter()
                        .map(|(c, _)| Json::String(c.path.clone()))
                        .collect(),
                ),
            ),
            (
                "unused_reasons",
                Json::Array(unused.into_iter().map(Json::String).collect()),
            ),
        ]);
    }
    let _lock = _lock;
    let mut recorded = 0i64;
    let mut files = Vec::new();
    let mut verification_failed = Vec::new();
    for (change, why) in &planned {
        let res = if change.deleted {
            record_deletion(root, &change.path, why)
        } else {
            record_change(root, &change.path, why)
        };
        if res.get("success").and_then(|s| s.as_bool()) == Some(true) {
            recorded += 1;
            files.push(change.path.clone());
            if green && !change.deleted {
                let marked = mark_green(root, &change.path, why, false);
                if marked.get("success").and_then(|s| s.as_bool()) != Some(true) {
                    verification_failed.push(Json::obj(vec![
                        ("file", Json::String(change.path.clone())),
                        (
                            "error",
                            Json::String(
                                marked
                                    .get("error")
                                    .and_then(|s| s.as_str())
                                    .unwrap_or("wiki verification failed")
                                    .into(),
                            ),
                        ),
                        (
                            "issues",
                            marked.get("issues").cloned().unwrap_or(Json::Array(vec![])),
                        ),
                    ]));
                }
            }
        }
    }
    ok(vec![
        ("recorded", Json::Int(recorded)),
        (
            "files",
            Json::Array(files.into_iter().map(Json::String).collect()),
        ),
        ("verification_failed", Json::Array(verification_failed)),
        (
            "unused_reasons",
            Json::Array(unused.into_iter().map(Json::String).collect()),
        ),
        ("green", Json::Bool(green)),
    ])
}

#[derive(Clone)]
struct GitChange {
    path: String,
    deleted: bool,
}

fn git_changes(root: &Path, since: Option<&str>) -> Result<Vec<GitChange>, String> {
    let root_s = root.display().to_string();
    if let Some(since) = since {
        let diff = std::process::Command::new("git")
            .args(["-C", &root_s, "diff", "--name-status", since])
            .output()
            .map_err(|e| e.to_string())?;
        if !diff.status.success() {
            return Err("git is not available or this directory is not a repository".into());
        }
        let mut out = parse_name_status(&String::from_utf8_lossy(&diff.stdout));
        let untracked = std::process::Command::new("git")
            .args(["-C", &root_s, "ls-files", "--others", "--exclude-standard"])
            .output()
            .map_err(|e| e.to_string())?;
        if untracked.status.success() {
            for line in String::from_utf8_lossy(&untracked.stdout).lines() {
                let path = line.trim();
                if !path.is_empty() {
                    out.push(GitChange {
                        path: path.to_string(),
                        deleted: false,
                    });
                }
            }
        }
        return Ok(out);
    }
    let status = std::process::Command::new("git")
        .args(["-C", &root_s, "status", "--porcelain", "-uall"])
        .output()
        .map_err(|e| e.to_string())?;
    if !status.status.success() {
        return Err("git is not available or this directory is not a repository".into());
    }
    Ok(parse_porcelain(&String::from_utf8_lossy(&status.stdout)))
}

fn parse_porcelain(text: &str) -> Vec<GitChange> {
    let mut out = Vec::new();
    for line in text.lines() {
        if line.len() < 4 {
            continue;
        }
        let code = &line[..2];
        let path = line[3..].trim().trim_matches('"');
        if let Some((old, new)) = path.split_once(" -> ") {
            out.push(GitChange {
                path: old.trim().trim_matches('"').to_string(),
                deleted: true,
            });
            out.push(GitChange {
                path: new.trim().trim_matches('"').to_string(),
                deleted: false,
            });
            continue;
        }
        let deleted = code.contains('D');
        out.push(GitChange {
            path: path.to_string(),
            deleted,
        });
    }
    out
}

fn parse_name_status(text: &str) -> Vec<GitChange> {
    let mut out = Vec::new();
    for line in text.lines() {
        let mut parts = line.split('\t');
        let code = parts.next().unwrap_or("");
        let path = parts.next().unwrap_or("").trim();
        if path.is_empty() {
            continue;
        }
        if code.starts_with('R') || code.starts_with('C') {
            let new = parts.next().unwrap_or("").trim();
            out.push(GitChange {
                path: path.to_string(),
                deleted: true,
            });
            if !new.is_empty() {
                out.push(GitChange {
                    path: new.to_string(),
                    deleted: false,
                });
            }
            continue;
        }
        out.push(GitChange {
            path: path.to_string(),
            deleted: code.starts_with('D'),
        });
    }
    out
}

fn artifact_path(path: &str) -> bool {
    path.ends_with(".wiki.md")
        || path.starts_with(".wikifier_staging/")
        || path == "file_health.md"
        || path == "file_health.json"
        || path == "pending_updates.md"
        || path == "library.md"
        || path.starts_with("journal/")
}

fn only_allows(path: &str, only: &[String]) -> bool {
    if only.is_empty() {
        return true;
    }
    only.iter().any(|item| reason_key_matches(item, path))
}

fn reason_for(path: &str, reasons: &[(String, String)]) -> Option<String> {
    if let Some((_, why)) = reasons.iter().find(|(key, _)| key == path) {
        return Some(why.clone());
    }
    let mut best: Option<(usize, &str)> = None;
    for (key, why) in reasons {
        if key.ends_with('/')
            && (path.starts_with(key.as_str()) || path == key.trim_end_matches('/'))
            && best.map(|(len, _)| key.len() > len).unwrap_or(true)
        {
            best = Some((key.len(), why));
        }
    }
    if let Some((_, why)) = best {
        return Some(why.to_string());
    }
    let mut glob_best: Option<(usize, &str)> = None;
    for (key, why) in reasons {
        if (key.contains('*') || key.contains('?'))
            && glob_match(key, path)
            && glob_best.map(|(len, _)| key.len() > len).unwrap_or(true)
        {
            glob_best = Some((key.len(), why));
        }
    }
    glob_best.map(|(_, why)| why.to_string())
}

fn reason_key_matches(key: &str, path: &str) -> bool {
    if key == path {
        return true;
    }
    if key.ends_with('/') && (path.starts_with(key) || path == key.trim_end_matches('/')) {
        return true;
    }
    (key.contains('*') || key.contains('?')) && glob_match(key, path)
}

fn glob_match(pattern: &str, text: &str) -> bool {
    fn rec(pattern: &[u8], text: &[u8]) -> bool {
        if pattern.is_empty() {
            return text.is_empty();
        }
        if pattern[0] == b'*' {
            return rec(&pattern[1..], text) || (!text.is_empty() && rec(pattern, &text[1..]));
        }
        if pattern[0] == b'?' {
            return !text.is_empty() && rec(&pattern[1..], &text[1..]);
        }
        !text.is_empty() && pattern[0] == text[0] && rec(&pattern[1..], &text[1..])
    }
    rec(pattern.as_bytes(), text.as_bytes())
}

pub fn record_deletion(root: &Path, file: &str, reason: &str) -> Json {
    let _lock = match lock_or_fail(root) {
        Ok(lock) => lock,
        Err(err) => return err,
    };
    let rel = scope::rel_arg(root, file);
    let rel = rel.as_str();
    let written = match artifacts::append_journal(root, "record-deletion", rel, reason) {
        Ok(written) => written,
        Err(e) => return fail("JournalError", e),
    };
    let mut row = HealthRow::new(
        rel,
        "🔴 Red",
        written.stamp.clone(),
        if reason.is_empty() {
            "recorded deletion"
        } else {
            reason
        },
        "",
        "deleted",
    );
    if let Some(old) = artifacts::read_health(root)
        .into_iter()
        .find(|r| r.file == rel)
    {
        row.source_hash = old.source_hash.clone();
        row.keep_baseline_from(&old);
    }
    if let Err(e) = artifacts::upsert_health_row(root, row) {
        return fail("HealthError", e);
    }
    if let Err(e) = cache::remove_file(root, rel) {
        return fail("CacheError", e);
    }
    drop_pending_line(root, rel);
    ok(vec![
        ("file", Json::String(rel.into())),
        ("status", Json::String("🔴 Red".into())),
        ("journaled", Json::Bool(written.journaled)),
        ("duplicate_skipped", Json::Bool(!written.journaled)),
        ("removed_from_graph", Json::Bool(true)),
    ])
}

fn drop_pending_line(root: &Path, rel: &str) {
    let path = root.join("pending_updates.md");
    let text = fs::read_to_string(&path).unwrap_or_default();
    if text.is_empty() {
        return;
    }
    let mut out = String::new();
    for line in text.lines() {
        let hit = crate::pending_line::file_of(line) == Some(rel);
        if !hit {
            out.push_str(line);
            out.push('\n');
        }
    }
    let _ = fs::write(path, out);
}

pub fn heal_stubs(root: &Path, min_len: usize, dry_run: bool) -> Json {
    let _guard = match lock_or_fail(root) {
        Ok(guard) => guard,
        Err(err) => return err,
    };
    let mut rows = artifacts::read_health(root);
    let mut healed = 0i64;
    for row in &mut rows {
        if row.reason != "Initial stub" {
            continue;
        }
        let wiki = crate::wiki_files::read_wiki(root, &row.file).1;
        if wiki.trim().len() >= min_len {
            if !dry_run {
                row.status = "🟢 Green".into();
                row.reason = "healed stub".into();
                row.verification = "verified".into();
                row.last_updated = local_stamp();
            }
            healed += 1;
        }
    }
    if healed > 0 && !dry_run {
        if let Err(err) = artifacts::write_health(root, &rows) {
            return fail("HealthError", err);
        }
    }
    ok(vec![
        ("healed_count", Json::Int(healed)),
        ("changed", Json::Int(if dry_run { 0 } else { healed })),
        ("dry_run", Json::Bool(dry_run)),
    ])
}

pub fn prune_health(root: &Path) -> Json {
    prune_health_opts(root, false)
}

pub fn prune_health_opts(root: &Path, deleted_missing: bool) -> Json {
    let _guard = match lock_or_fail(root) {
        Ok(guard) => guard,
        Err(err) => return err,
    };
    let scope = scope::detect(root);
    let watched = watched_files(root);
    let rows = artifacts::read_health(root);
    let before = rows.len();
    let kept: Vec<_> = rows
        .into_iter()
        .filter(|row| {
            if !kept_path(&scope, &watched, &row.file) {
                return false;
            }
            if deleted_missing && !root.join(&row.file).is_file() {
                return false;
            }
            true
        })
        .collect();
    let changed = before - kept.len();
    let _ = artifacts::write_health(root, &kept);
    if deleted_missing {
        let pending = root.join("pending_updates.md");
        let text = fs::read_to_string(&pending).unwrap_or_default();
        let mut out = String::new();
        for line in text.lines() {
            let drop_line =
                crate::pending_line::file_of(line).is_some_and(|file| !root.join(file).is_file());
            if !drop_line {
                out.push_str(line);
                out.push('\n');
            }
        }
        let _ = fs::write(pending, out);
    }
    ok(vec![
        ("changed", Json::Int(changed as i64)),
        ("deleted_missing", Json::Bool(deleted_missing)),
    ])
}

pub fn prune_pending(root: &Path) -> Json {
    let _guard = match lock_or_fail(root) {
        Ok(guard) => guard,
        Err(err) => return err,
    };
    let scope = scope::detect(root);
    let watched = watched_files(root);
    let path = root.join("pending_updates.md");
    let text = fs::read_to_string(&path).unwrap_or_default();
    let mut out = String::new();
    let mut changed = 0i64;
    for line in text.lines() {
        let keep = if let Some(file) = crate::pending_line::file_of(line) {
            if kept_path(&scope, &watched, file) {
                true
            } else {
                changed += 1;
                false
            }
        } else {
            true
        };
        if keep {
            out.push_str(line);
            out.push('\n');
        }
    }
    let _ = fs::write(path, out);
    ok(vec![("changed", Json::Int(changed))])
}

fn watched_files(root: &Path) -> Vec<String> {
    scope::read_path_list(root, "monitored_paths.txt")
        .into_iter()
        .filter(|rel| root.join(rel).is_file())
        .collect()
}

fn kept_path(scope: &Scope, watched: &[String], rel: &str) -> bool {
    if watched.iter().any(|path| path == rel) {
        return true;
    }
    if scope.full_tree || scope.prefixes.is_empty() {
        return true;
    }
    scope
        .prefixes
        .iter()
        .any(|prefix| rel == prefix || rel.starts_with(&format!("{prefix}/")))
}

pub fn stale_wikis(root: &Path) -> Json {
    stale_wikis_in(root, None, None)
}

pub fn stale_wikis_in(root: &Path, directory: Option<&str>, limit: Option<usize>) -> Json {
    let mut stale = Vec::new();
    for row in artifacts::read_health(root) {
        if let Some(dir) = directory
            .map(|d| d.trim_matches('/'))
            .filter(|d| !d.is_empty())
        {
            if !under_prefix(dir, &row.file) {
                continue;
            }
        }
        let wiki = crate::wiki_files::find_wiki(root, &row.file);
        if wiki.is_none() {
            continue;
        }
        let live = file_sha256_prefixed(&root.join(&row.file)).unwrap_or_default();
        let source_drift =
            row.source_hash.starts_with("sha256:") && !live.is_empty() && live != row.source_hash;
        let content_flag =
            is_yellow(&row.status) && row.reason.contains("content changed since last mark-green");
        if source_drift || content_flag {
            let mut reasons = Vec::new();
            if source_drift {
                reasons.push(Json::String("source_changed_since_mark_green".into()));
            }
            if content_flag {
                reasons.push(Json::String(
                    "content changed since last mark-green (check-changes)".into(),
                ));
            }
            stale.push(Json::obj(vec![
                ("file", Json::String(row.file)),
                ("is_stale", Json::Bool(true)),
                ("reasons", Json::Array(reasons)),
                ("status", Json::String(row.status)),
            ]));
        }
    }
    let total = stale.len() as i64;
    if let Some(max) = limit {
        stale.truncate(max);
    }
    ok(vec![
        ("stale", Json::Array(stale.clone())),
        (
            "files",
            Json::Array(
                stale
                    .iter()
                    .filter_map(|v| v.get("file").cloned())
                    .collect(),
            ),
        ),
        ("count", Json::Int(total)),
    ])
}

pub fn prune_barrels(root: &Path, max_age_days: f64, dry_run: bool) -> Json {
    let _guard = match lock_or_fail(root) {
        Ok(guard) => guard,
        Err(err) => return err,
    };
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
    let _guard = match lock_or_fail(root) {
        Ok(guard) => guard,
        Err(err) => return err,
    };
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
        (
            "cache_files",
            Json::Int(cache::all_paths(root).len() as i64),
        ),
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
    let _ = crate::legacy_cache::import_if_empty(root);
    let mut notes = Vec::new();
    let mut counts: BTreeMap<String, i64> = BTreeMap::new();
    let mut low = Vec::new();
    for rel in cache::all_paths(root) {
        let Ok(view) = cache::load_dependency_view(root, &rel) else {
            continue;
        };
        for name in &view.external {
            *counts.entry("external_or_bare".into()).or_insert(0) += 1;
            notes.push(Json::obj(vec![
                ("file", Json::String(rel.clone())),
                ("raw", Json::String(name.clone())),
                ("reason", Json::String("external_or_bare".into())),
            ]));
        }
        for (raw, line, reason) in &view.unresolved {
            *counts.entry(reason.clone()).or_insert(0) += 1;
            notes.push(Json::obj(vec![
                ("file", Json::String(rel.clone())),
                ("raw", Json::String(raw.clone())),
                ("line", Json::Int(*line)),
                ("reason", Json::String(reason.clone())),
            ]));
        }
        for edge in &view.internal {
            let code = edge.acs_reason();
            if code != "resolved_static" {
                *counts.entry(code.into()).or_insert(0) += 1;
                notes.push(Json::obj(vec![
                    ("file", Json::String(rel.clone())),
                    ("raw", Json::String(edge.path.clone())),
                    ("line", Json::Int(edge.line)),
                    ("reason", Json::String(code.into())),
                    ("confidence", Json::Float(edge.confidence())),
                ]));
            }
            if edge.confidence() < 0.6 && code != "external_or_bare" && code != "dynamic_literal" {
                low.push(Json::obj(vec![
                    ("file", Json::String(rel.clone())),
                    ("path", Json::String(edge.path.clone())),
                    ("confidence", Json::Float(edge.confidence())),
                    ("reason", Json::String(code.into())),
                ]));
            }
        }
    }
    ok(vec![
        ("notes", Json::Array(notes)),
        (
            "reason_code_counts",
            Json::from_pairs(counts.into_iter().map(|(k, n)| (k, Json::Int(n))).collect()),
        ),
        ("actionable_low_conf_edges", Json::Array(low)),
    ])
}

pub fn barrel_reports(root: &Path) -> Json {
    let dir = root
        .join(".wikifier_staging")
        .join("wk_cache")
        .join("barrels");
    let mut barrels = Vec::new();
    if let Ok(entries) = fs::read_dir(&dir) {
        for ent in entries.flatten() {
            let text = fs::read_to_string(ent.path()).unwrap_or_default();
            if let Ok(parsed) = crate::jsonutil::parse(&text) {
                if parsed.get("src").is_some() {
                    barrels.push(parsed);
                }
            }
        }
    }
    barrels.sort_by(|a, b| {
        a.get("src")
            .and_then(|s| s.as_str())
            .unwrap_or("")
            .cmp(b.get("src").and_then(|s| s.as_str()).unwrap_or(""))
    });
    ok(vec![
        ("count", Json::Int(barrels.len() as i64)),
        ("barrels", Json::Array(barrels)),
    ])
}

pub fn incremental_status(root: &Path) -> Json {
    let mut status = crate::maps_out::read_status(root);
    if status.get("map_complete").is_none() {
        status = ok(vec![(
            "map_complete",
            Json::Bool(!cache::all_paths(root).is_empty()),
        )]);
    } else if status.get("success").is_none() {
        status.insert("success", Json::Bool(true));
    }
    status
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

pub fn serve_loop(root: &Path, port: u16) -> Json {
    use std::io::Read;
    use std::net::TcpListener;
    let addr = format!("127.0.0.1:{port}");
    let listener = match TcpListener::bind(&addr) {
        Ok(listener) => listener,
        Err(err) => return fail("ServeError", err.to_string()),
    };
    let bound = listener.local_addr().map(|a| a.port()).unwrap_or(port);
    eprintln!("wikifier serve http://127.0.0.1:{bound}/index.html");
    let _ = fs::create_dir_all(root.join(".wikifier_staging"));
    let _ = fs::write(root.join(".wikifier_staging/serve.port"), bound.to_string());
    let once = std::env::var("WIKIFIER_SERVE_ONCE").ok().as_deref() == Some("1");
    for conn in listener.incoming() {
        let mut sock = match conn {
            Ok(sock) => sock,
            Err(_) => continue,
        };
        let _ = sock.set_read_timeout(Some(std::time::Duration::from_secs(5)));
        let mut buf = [0u8; 8192];
        let n = sock.read(&mut buf).unwrap_or(0);
        let req = String::from_utf8_lossy(&buf[..n]);
        let (method, path, _) = request_line(&req);
        if method == "POST" && path == "/__wikifier/shutdown" {
            let _ = write_http(&mut sock, "200 OK", "application/json", r#"{"ok":true}"#);
            break;
        }
        if method == "POST" && path == "/__wikifier/run" {
            let body = dashboard_run(root, &req);
            let _ = write_http(&mut sock, "200 OK", "application/json", &body);
            if once {
                break;
            }
            continue;
        }
        let (status, content_type, body) = serve_response(root, &req);
        let _ = write_http(&mut sock, status, content_type, &body);
        if once {
            break;
        }
    }
    let _ = fs::remove_file(root.join(".wikifier_staging/serve.port"));
    ok(vec![
        ("bound", Json::Bool(true)),
        ("port", Json::Int(bound as i64)),
        ("served", Json::Bool(true)),
    ])
}

fn write_http(
    sock: &mut std::net::TcpStream,
    status: &str,
    content_type: &str,
    body: &str,
) -> std::io::Result<()> {
    use std::io::Write;
    let resp = format!(
        "HTTP/1.1 {status}\r\nContent-Type: {content_type}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
        body.len()
    );
    sock.write_all(resp.as_bytes())?;
    sock.write_all(body.as_bytes())
}

fn request_line(req: &str) -> (&str, &str, &str) {
    let line = req.lines().next().unwrap_or("");
    let mut parts = line.split_whitespace();
    let method = parts.next().unwrap_or("");
    let target = parts.next().unwrap_or("/");
    let (path, query) = target.split_once('?').unwrap_or((target, ""));
    (method, path, query)
}

fn dashboard_run(root: &Path, req: &str) -> String {
    let body = req
        .split_once("\r\n\r\n")
        .map(|(_, rest)| rest)
        .unwrap_or("");
    let cmd = crate::jsonutil::parse(body)
        .ok()
        .and_then(|value| {
            value
                .get("cmd")
                .and_then(|item| item.as_str())
                .map(|text| text.to_string())
        })
        .unwrap_or_default();
    let started = std::time::Instant::now();
    let result = match cmd.as_str() {
        "update-maps" => update_maps(root),
        "update-maps --full" => update_maps_run(
            root,
            &MapRun {
                full: true,
                quiet: true,
                directory: None,
                max_files: None,
                stream: false,
            },
        ),
        "check-changes" => check_changes(root),
        _ => fail("ValueError", "command is not available from the dashboard"),
    };
    let succeeded = result
        .get("success")
        .and_then(|flag| flag.as_bool())
        .unwrap_or(false);
    let error = if succeeded {
        String::new()
    } else {
        result
            .get("error")
            .and_then(|item| item.as_str())
            .unwrap_or("failed")
            .to_string()
    };
    Json::obj(vec![
        ("ok", Json::Bool(succeeded)),
        ("output", Json::String(result.to_string())),
        ("error", Json::String(error)),
        ("duration_s", Json::Float(started.elapsed().as_secs_f64())),
    ])
    .to_string()
}

fn serve_response(root: &Path, req: &str) -> (&'static str, &'static str, String) {
    let line = req.lines().next().unwrap_or("");
    let mut parts = line.split_whitespace();
    let method = parts.next().unwrap_or("");
    let target = parts.next().unwrap_or("/");
    if method != "GET" && method != "HEAD" {
        return (
            "405 Method Not Allowed",
            "text/plain; charset=utf-8",
            "method not allowed\n".into(),
        );
    }
    let (path, query) = target.split_once('?').unwrap_or((target, ""));
    if path.contains("..") || query.contains("..") {
        return (
            "400 Bad Request",
            "application/json",
            fail("PathError", "path traversal refused").to_string(),
        );
    }
    let file_arg = query_param(query, "path")
        .or_else(|| query_param(query, "file"))
        .unwrap_or_default();
    if file_arg.contains("..") {
        return (
            "400 Bad Request",
            "application/json",
            fail("PathError", "path traversal refused").to_string(),
        );
    }
    match path {
        "/" | "/index.html" => ("200 OK", "text/html; charset=utf-8", dashboard_html(root)),
        "/__wikifier/api/bootstrap" => (
            "200 OK",
            "application/json",
            session_bootstrap(root).to_string(),
        ),
        "/__wikifier/api/dependencies" => (
            "200 OK",
            "application/json",
            load_dependencies(root, &file_arg).to_string(),
        ),
        "/__wikifier/api/dependents" => (
            "200 OK",
            "application/json",
            load_dependents(root, &file_arg).to_string(),
        ),
        "/__wikifier/api/cycles" => ("200 OK", "application/json", cycles(root).to_string()),
        "/__wikifier/api/journal" => {
            let entries = read_journal(root, None);
            let body = ok(vec![(
                "entries",
                Json::Array(
                    entries
                        .into_iter()
                        .map(|e| {
                            Json::obj(vec![
                                ("stamp", Json::String(e.stamp)),
                                ("action", Json::String(e.action)),
                                ("file", Json::String(e.file)),
                                ("reason", Json::String(e.reason)),
                            ])
                        })
                        .collect(),
                ),
            )]);
            ("200 OK", "application/json", body.to_string())
        }
        "/__wikifier/api/diagnostics" => (
            "200 OK",
            "application/json",
            resolution_diagnostics(root).to_string(),
        ),
        "/__wikifier/api/file" => serve_file(root, &file_arg),
        "/__wikifier/status" => {
            let project = root
                .file_name()
                .and_then(|name| name.to_str())
                .unwrap_or("project");
            let body = ok(vec![
                ("wikifier_serve", Json::Bool(true)),
                ("version", Json::String(VERSION.into())),
                ("project", Json::String(project.into())),
                ("root", Json::String(root.display().to_string())),
            ]);
            ("200 OK", "application/json", body.to_string())
        }
        _ => serve_project_file(root, path),
    }
}

fn serve_project_file(root: &Path, path: &str) -> (&'static str, &'static str, String) {
    let rel = path.trim_start_matches('/');
    if rel.is_empty() || rel.contains("..") || rel.split('/').any(|part| part == ".git") {
        return (
            "404 Not Found",
            "application/json",
            fail("NotFound", "unknown path").to_string(),
        );
    }
    let (status, _, body) = serve_file(root, rel);
    if !status.starts_with("200") {
        return (status, "application/json", body);
    }
    let content_type = if rel.ends_with(".json") {
        "application/json"
    } else if rel.ends_with(".html") {
        "text/html; charset=utf-8"
    } else if rel.ends_with(".md") {
        "text/markdown; charset=utf-8"
    } else {
        "text/plain; charset=utf-8"
    };
    (status, content_type, body)
}

fn serve_file(root: &Path, rel: &str) -> (&'static str, &'static str, String) {
    if rel.is_empty() {
        return (
            "400 Bad Request",
            "application/json",
            fail("PathError", "missing path").to_string(),
        );
    }
    let path = root.join(rel);
    let Ok(canon_root) = root.canonicalize() else {
        return (
            "400 Bad Request",
            "application/json",
            fail("PathError", "root is not readable").to_string(),
        );
    };
    let Ok(canon) = path.canonicalize() else {
        return (
            "404 Not Found",
            "application/json",
            fail("FileNotFound", format!("file does not exist: {rel}")).to_string(),
        );
    };
    if !canon.starts_with(&canon_root) {
        return (
            "400 Bad Request",
            "application/json",
            fail("PathError", "path is outside the project").to_string(),
        );
    }
    match fs::read_to_string(&canon) {
        Ok(text) => ("200 OK", "text/plain; charset=utf-8", text),
        Err(err) => (
            "404 Not Found",
            "application/json",
            fail("FileNotFound", err.to_string()).to_string(),
        ),
    }
}

fn dashboard_html(root: &Path) -> String {
    let path = root.join("index.html");
    fs::read_to_string(path).unwrap_or_else(|_| INDEX_HTML.to_string())
}

fn query_param(query: &str, key: &str) -> Option<String> {
    for pair in query.split('&') {
        let (k, v) = pair.split_once('=').unwrap_or((pair, ""));
        if k == key {
            return Some(percent_decode(v));
        }
    }
    None
}

fn percent_decode(text: &str) -> String {
    let bytes = text.as_bytes();
    let mut out = Vec::new();
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%' && i + 2 < bytes.len() {
            if let Ok(byte) = u8::from_str_radix(&text[i + 1..i + 3], 16) {
                out.push(byte);
                i += 3;
                continue;
            }
        }
        if bytes[i] == b'+' {
            out.push(b' ');
        } else {
            out.push(bytes[i]);
        }
        i += 1;
    }
    String::from_utf8_lossy(&out).into_owned()
}

const INDEX_HTML: &str = include_str!("../index.html");

pub fn monitor_loop(root: &Path, interval_s: u64) -> Json {
    let once = std::env::var("WIKIFIER_MONITOR_ONCE").ok().as_deref() == Some("1");
    loop {
        let report = check_changes(root);
        let dirty = report
            .get("dirty_total")
            .and_then(|v| match v {
                Json::Int(n) => Some(*n),
                _ => None,
            })
            .unwrap_or(0);
        eprintln!("monitor dirty={dirty}");
        if once {
            return report;
        }
        let step = interval_s.max(1);
        std::thread::sleep(std::time::Duration::from_secs(step));
    }
}

pub fn daemon_ctl(root: &Path, action: &str, force: bool) -> Json {
    daemon_command(root, action, force, 100, false)
}

pub fn daemon_command(
    root: &Path,
    action: &str,
    force: bool,
    log_lines: usize,
    follow: bool,
) -> Json {
    let pidfile = crate::daemon_svc::pid_path(root);
    match action {
        "run" => daemon_run(root, &pidfile),
        "start" => daemon_start(root, &pidfile, force),
        "restart" => {
            let _ = daemon_stop(root, &pidfile);
            daemon_start(root, &pidfile, force)
        }
        "status" => daemon_status(root, &pidfile),
        "stop" => daemon_stop(root, &pidfile),
        "logs" => daemon_logs(root, log_lines, follow),
        "install-service" | "install_service" => {
            let exe = match std::env::current_exe() {
                Ok(path) => path,
                Err(err) => return fail("DaemonError", err.to_string()),
            };
            crate::daemon_svc::install(root, &exe)
        }
        "uninstall-service" | "uninstall_service" => crate::daemon_svc::uninstall(root),
        other => fail("DaemonError", format!("unknown daemon action {other}")),
    }
}

fn daemon_run(root: &Path, pidfile: &Path) -> Json {
    for _ in 0..50 {
        if pidfile.is_file() || crate::daemon_svc::legacy_pid_path(root).is_file() {
            break;
        }
        std::thread::sleep(std::time::Duration::from_millis(20));
    }
    let poll = crate::daemon_svc::poll_seconds();
    let maps_every = crate::daemon_svc::maps_interval_seconds();
    let maps = crate::daemon_svc::maps_enabled();
    crate::daemon_svc::append_log(
        root,
        &format!("daemon started (check every {poll}s; maps every {maps_every}s)"),
    );
    let checked = check_changes(root);
    let ok_check = checked
        .get("success")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    crate::daemon_svc::write_heartbeat(root, "check-changes:start", ok_check, "");
    let mut last_maps = std::time::Instant::now();
    if maps {
        let mapped = update_maps(root);
        let ok_maps = mapped
            .get("success")
            .and_then(|v| v.as_bool())
            .unwrap_or(false);
        crate::daemon_svc::write_heartbeat(root, "update-maps:start", ok_maps, "");
        crate::daemon_svc::append_log(root, "update-maps (start)");
        last_maps = std::time::Instant::now();
    }
    while pidfile.is_file() {
        let slices = (poll * 5).max(1);
        for _ in 0..slices {
            if !pidfile.is_file() {
                break;
            }
            std::thread::sleep(std::time::Duration::from_millis(200));
        }
        if !pidfile.is_file() {
            break;
        }
        let checked = check_changes(root);
        let ok_check = checked
            .get("success")
            .and_then(|v| v.as_bool())
            .unwrap_or(false);
        crate::daemon_svc::write_heartbeat(root, "check-changes:periodic", ok_check, "");
        if maps && maps_every > 0 && last_maps.elapsed().as_secs() >= maps_every {
            let mapped = update_maps(root);
            let ok_maps = mapped
                .get("success")
                .and_then(|v| v.as_bool())
                .unwrap_or(false);
            crate::daemon_svc::write_heartbeat(root, "update-maps:interval", ok_maps, "");
            crate::daemon_svc::append_log(root, "update-maps (interval)");
            last_maps = std::time::Instant::now();
        }
    }
    crate::daemon_svc::append_log(root, "daemon stopped");
    ok(vec![
        ("running", Json::Bool(false)),
        ("action", Json::String("run".into())),
    ])
}

fn daemon_start(root: &Path, pidfile: &Path, force: bool) -> Json {
    if let Some(pid) = running_pid(root) {
        return ok(vec![
            ("running", Json::Bool(true)),
            ("pid", Json::Int(pid)),
            ("action", Json::String("start".into())),
            ("message", Json::String("already running".into())),
        ]);
    }
    let scope = scope::detect(root);
    let ready = readiness_of(
        &scope,
        !cache::all_paths(root).is_empty(),
        &artifacts::read_health(root),
        health_file_present(root),
    );
    if ready == "blocked" && !force {
        return fail(
            "NotReady",
            format!("readiness is {ready}; pass --force to start the daemon anyway"),
        );
    }
    let _ = fs::create_dir_all(pidfile.parent().unwrap());
    let exe = match std::env::current_exe() {
        Ok(path) => path,
        Err(err) => return fail("DaemonError", err.to_string()),
    };
    match spawn_daemon(&exe, root) {
        Ok(child) => {
            let _ = fs::write(pidfile, child.id().to_string());
            ok(vec![
                ("running", Json::Bool(true)),
                ("pid", Json::Int(child.id() as i64)),
                ("action", Json::String("start".into())),
            ])
        }
        Err(err) => fail("DaemonError", err.to_string()),
    }
}

fn daemon_status(root: &Path, pidfile: &Path) -> Json {
    let pid = running_pid(root);
    ok(vec![
        ("running", Json::Bool(pid.is_some())),
        ("pid", pid.map(Json::Int).unwrap_or(Json::Null)),
        ("action", Json::String("status".into())),
        ("pid_file", Json::String(pidfile.display().to_string())),
        (
            "log",
            Json::String(crate::daemon_svc::log_path(root).display().to_string()),
        ),
    ])
}

fn daemon_stop(root: &Path, pidfile: &Path) -> Json {
    for path in [
        pidfile.to_path_buf(),
        crate::daemon_svc::legacy_pid_path(root),
    ] {
        if let Ok(text) = fs::read_to_string(&path) {
            if let Ok(pid) = text.trim().parse::<i32>() {
                let _ = crate::proc::signal_process(pid, 15);
            }
        }
        let _ = fs::remove_file(path);
    }
    ok(vec![
        ("running", Json::Bool(false)),
        ("action", Json::String("stop".into())),
    ])
}

fn daemon_logs(root: &Path, lines: usize, follow: bool) -> Json {
    if follow {
        let log = crate::daemon_svc::log_path(root);
        let mut seen = fs::read_to_string(&log).map(|text| text.len()).unwrap_or(0);
        while running_pid(root).is_some() {
            std::thread::sleep(std::time::Duration::from_millis(400));
            if let Ok(text) = fs::read_to_string(&log) {
                if text.len() > seen {
                    eprint!("{}", &text[seen..]);
                    seen = text.len();
                }
            }
        }
    }
    let text = crate::daemon_svc::read_log_tail(root, lines.max(1));
    ok(vec![
        ("action", Json::String("logs".into())),
        ("log", Json::String(text)),
        (
            "path",
            Json::String(crate::daemon_svc::log_path(root).display().to_string()),
        ),
    ])
}

fn running_pid(root: &Path) -> Option<i64> {
    for path in [
        crate::daemon_svc::pid_path(root),
        crate::daemon_svc::legacy_pid_path(root),
    ] {
        if pid_alive(&path) {
            return fs::read_to_string(path)
                .ok()
                .and_then(|text| text.trim().parse().ok());
        }
    }
    None
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
    let Ok(text) = fs::read_to_string(pidfile) else {
        return false;
    };
    let Ok(pid) = text.trim().parse::<i32>() else {
        return false;
    };
    crate::proc::pid_alive(pid)
}

pub fn dispatch(
    name: &str,
    root: &Path,
    positional: &[String],
    flags: &BTreeMap<String, String>,
) -> Json {
    let file_arg = positional
        .first()
        .map(|s| scope::rel_arg(root, s))
        .unwrap_or_default();
    let file = file_arg.as_str();
    let reason = if positional.len() > 1 {
        positional[1..].join(" ")
    } else {
        flags.get("reason").cloned().unwrap_or_default()
    };
    match name {
        "check-changes" | "check_changes" => check_changes(root),
        "record-change" | "record_change" => record_change(root, file, &reason),
        "mark-green" | "mark_green" => mark_green(
            root,
            file,
            &reason,
            flags.get("force").map(|s| s == "true").unwrap_or(false),
        ),
        "record-deletion" | "record_deletion" => record_deletion(root, file, &reason),
        "session-bootstrap" | "bootstrap" | "session-start" | "session_bootstrap" => cap_files(
            session_bootstrap_scoped(root, flag_text(flags, "directory")),
            flags,
        ),
        "suggest-next" | "suggest" | "suggest-next-actions" | "suggest_next_actions" => {
            suggest_next_scoped(root, flag_text(flags, "directory"))
        }
        "prepare-edit" | "prepare_edit" | "lookup" | "preflight" => prepare_edit(root, file),
        "dependencies" | "deps" | "get_dependencies" => {
            let low_only =
                flag_on(flags, "low-confidence-only") || flag_on(flags, "low_confidence_only");
            let unresolved_only =
                flag_on(flags, "unresolved-only") || flag_on(flags, "unresolved_only");
            let full = flag_on(flags, "full")
                || flags.get("detail").map(|s| s == "full").unwrap_or(false)
                || low_only
                || unresolved_only;
            let mut report = dependency_report(root, file, full);
            filter_dependency_report(&mut report, low_only, unresolved_only);
            report
        }
        "dependents" | "importers" | "get_dependents" => load_dependents(root, file),
        "list-paths" | "list_paths" => {
            let depth = if flag_on(flags, "recursive") {
                0
            } else {
                flags.get("depth").and_then(|s| s.parse().ok()).unwrap_or(1)
            };
            let max_files = flags
                .get("max-files")
                .or_else(|| flags.get("max_files"))
                .and_then(|s| s.parse().ok());
            list_paths_at(
                root,
                flags.get("prefix").map(|s| s.as_str()).unwrap_or(file),
                depth,
                max_files,
            )
        }
        "update-maps" | "update_maps" => {
            let full = flag_on(flags, "full");
            let quiet = flag_on(flags, "quiet");
            let directory = flags.get("directory").cloned().filter(|s| s != "true");
            let max_files = flags
                .get("max-files")
                .or_else(|| flags.get("max_files"))
                .and_then(|s| s.parse().ok());
            let stream = flag_on(flags, "stream");
            update_maps_run(
                root,
                &MapRun {
                    full,
                    quiet,
                    directory,
                    max_files,
                    stream,
                },
            )
        }
        "health" => {
            let format = if flag_on(flags, "summary") {
                "summary"
            } else {
                flags.get("format").map(|s| s.as_str()).unwrap_or("json")
            };
            let mut value = health_view(root, flag_text(flags, "directory"), format);
            let limit = flags.get("limit").and_then(|s| s.parse::<usize>().ok());
            if let (Some(limit), Some(Json::Array(rows))) = (limit, value.get("entries")) {
                if rows.len() > limit {
                    let total = rows.len();
                    let kept = rows[..limit].to_vec();
                    value.insert("entries", Json::Array(kept));
                    value.insert("entries_total", Json::Int(total as i64));
                }
            }
            value
        }
        "cache-status" | "cache" => cache_status(root),
        "list-core-tools" | "list_core_tools" => ok(vec![
            (
                "core",
                Json::Array(
                    [
                        "session_bootstrap",
                        "check_changes",
                        "prepare_edit",
                        "suggest_next_actions",
                        "record_change",
                        "mark_green",
                        "update_maps",
                        "list_paths",
                    ]
                    .into_iter()
                    .map(|s| Json::String(s.into()))
                    .collect(),
                ),
            ),
            (
                "tools",
                Json::Array(
                    MCP_TOOLS
                        .iter()
                        .map(|s| Json::String((*s).into()))
                        .collect(),
                ),
            ),
        ]),
        "journal" => {
            let date = flags
                .get("date")
                .map(|s| s.as_str())
                .or(positional.first().map(|s| s.as_str()));
            let date_text = date
                .map(|s| s.to_string())
                .unwrap_or_else(|| crate::timeutil::local_stamp().chars().take(10).collect());
            let entries = read_journal(root, date);
            let mut entries: Vec<_> = entries
                .into_iter()
                .map(|e| {
                    Json::obj(vec![
                        ("stamp", Json::String(e.stamp)),
                        ("action", Json::String(e.action)),
                        ("file", Json::String(e.file)),
                        ("reason", Json::String(e.reason)),
                    ])
                })
                .collect();
            if let Some(limit) = flags.get("limit").and_then(|s| s.parse::<usize>().ok()) {
                entries.truncate(limit);
            }
            ok(vec![
                ("date", Json::String(date_text)),
                ("entries", Json::Array(entries)),
            ])
        }
        "why-file" | "why_file" | "why" => {
            let entries = artifacts::read_journal(root, None)
                .into_iter()
                .filter(|e| e.file == file)
                .collect::<Vec<_>>();
            ok(vec![
                ("file", Json::String(file.into())),
                (
                    "entries",
                    Json::Array(
                        entries
                            .into_iter()
                            .map(|e| {
                                Json::obj(vec![
                                    ("stamp", Json::String(e.stamp)),
                                    ("reason", Json::String(e.reason)),
                                ])
                            })
                            .collect(),
                    ),
                ),
            ])
        }
        "search-journal" | "search_journal" => {
            let q = flags
                .get("query")
                .cloned()
                .or_else(|| positional.first().cloned())
                .unwrap_or_default();
            let file_filter = flags
                .get("file")
                .map(|s| s.as_str())
                .filter(|s| !s.is_empty() && *s != "true");
            let mut entries = artifacts::read_journal(root, None)
                .into_iter()
                .filter(|e| {
                    let text_ok = q.is_empty() || e.reason.contains(&q) || e.file.contains(&q);
                    let file_ok = file_filter.map(|f| e.file == f).unwrap_or(true);
                    text_ok && file_ok
                })
                .collect::<Vec<_>>();
            if let Some(limit) = flags.get("limit").and_then(|s| s.parse::<usize>().ok()) {
                entries.truncate(limit);
            }
            ok(vec![(
                "entries",
                Json::Array(
                    entries
                        .into_iter()
                        .map(|e| {
                            Json::obj(vec![
                                ("file", Json::String(e.file)),
                                ("reason", Json::String(e.reason)),
                            ])
                        })
                        .collect(),
                ),
            )])
        }
        "validate" => validate(root),
        "rebuild-cache" | "rebuild_cache" => match cache::rebuild(root) {
            Ok(()) => ok(vec![("rebuilt", Json::Bool(true))]),
            Err(err) => fail("CacheError", err),
        },
        "issues" => suggest_next_scoped(root, flag_text(flags, "directory")),
        "cycles" | "get_cycles" => {
            let max_items = flags
                .get("max-items")
                .or_else(|| flags.get("max_items"))
                .and_then(|s| s.parse().ok());
            cycles_view(root, !flag_on(flags, "no-analysis"), max_items)
        }
        "verify-wikis" | "verify_wikis" => {
            let prefix = flag_text(flags, "directory")
                .map(|s| s.to_string())
                .or_else(|| positional.first().filter(|s| !s.is_empty()).cloned());
            let limit = flags.get("limit").and_then(|s| s.parse().ok());
            verify_wikis_under(root, prefix.as_deref(), limit)
        }
        "autonomous-status" | "readiness" => {
            let scope = scope::detect(root);
            ok(vec![
                (
                    "readiness",
                    Json::String(
                        readiness_of(
                            &scope,
                            !cache::all_paths(root).is_empty(),
                            &artifacts::read_health(root),
                            health_file_present(root),
                        )
                        .into(),
                    ),
                ),
                ("scope", scope_json(&scope)),
            ])
        }
        "init" => init_project(root, flag_on(flags, "no-copy")),
        "get_project_status" => cap_files(
            session_bootstrap_scoped(root, flag_text(flags, "directory")),
            flags,
        ),
        "get_current_project_root" => ok(vec![(
            "project_root",
            Json::String(root.display().to_string()),
        )]),
        "get_file_wiki" => {
            if let Some(err) = unknown_file(root, file) {
                return err;
            }
            let (path, wiki) = crate::wiki_files::read_wiki(root, file);
            ok(vec![
                ("file", Json::String(file.into())),
                ("wiki", Json::String(wiki)),
                (
                    "wiki_file",
                    Json::String(path.map(|p| p.display().to_string()).unwrap_or_default()),
                ),
            ])
        }
        "get_files_needing_attention" => suggest_next_actions(root),
        "get_resolution_diagnostics" => resolution_diagnostics(root),
        "get_barrel_reports" => barrel_reports(root),
        "get_incremental_status" => incremental_status(root),
        "record-changes" | "record_changes" => {
            let lines = flags
                .get("reasons")
                .map(|s| {
                    s.split('\n')
                        .map(|x| x.to_string())
                        .filter(|x| !x.is_empty())
                        .collect::<Vec<_>>()
                })
                .unwrap_or_default();
            let only = flags
                .get("only")
                .map(|s| {
                    s.split('\n')
                        .map(|x| x.to_string())
                        .filter(|x| !x.is_empty())
                        .collect::<Vec<_>>()
                })
                .unwrap_or_default();
            record_changes_opts(
                root,
                &lines,
                flags.get("default").map(|s| s.as_str()),
                &only,
                flags.get("since").map(|s| s.as_str()),
                flag_on(flags, "green"),
                flag_on(flags, "dry-run"),
            )
        }
        "seed-health" => match seed_health_from_map(root) {
            Ok(()) => ok(vec![("seeded", Json::Bool(true))]),
            Err(err) => fail("HealthError", err),
        },
        "seed-source-hashes" | "seed_source_content_hashes" => {
            seed_source_hashes(root, flag_on(flags, "force"), flag_text(flags, "directory"))
        }
        "prune-pending" => prune_pending(root),
        "prune-health" => prune_health_opts(root, flag_on(flags, "deleted-missing")),
        "heal-stubs" | "heal_stubs" => heal_stubs(
            root,
            flags
                .get("min-wiki-length")
                .or_else(|| flags.get("min_wiki_length"))
                .and_then(|s| s.parse().ok())
                .unwrap_or(350),
            flag_on(flags, "dry-run"),
        ),
        "healable-stubs" | "list_healable_stubs" => {
            let min = flags
                .get("min-wiki-length")
                .or_else(|| flags.get("min_wiki_length"))
                .and_then(|s| s.parse().ok())
                .unwrap_or(350usize);
            let files: Vec<Json> = artifacts::read_health(root)
                .into_iter()
                .filter(|r| {
                    r.reason == "Initial stub"
                        && crate::wiki_files::read_wiki(root, &r.file).1.trim().len() >= min
                })
                .map(|r| Json::String(r.file))
                .collect();
            ok(vec![("files", Json::Array(files))])
        }
        "healing-stats" | "stub-stats" => healing_stats(root),
        "stale-wikis" | "detect-stale" => stale_wikis_in(
            root,
            flag_text(flags, "directory").or(positional.first().map(|s| s.as_str())),
            flags.get("limit").and_then(|s| s.parse().ok()),
        ),
        "prune-barrels" | "prune-brc" | "gc-barrels" => {
            let days = positional
                .first()
                .and_then(|s| s.parse().ok())
                .or_else(|| {
                    flags
                        .get("max-age-days")
                        .or_else(|| flags.get("max_age_days"))
                        .and_then(|s| s.parse().ok())
                })
                .unwrap_or(90.0);
            let dry = flags.get("dry-run").map(|s| s == "true").unwrap_or(false);
            prune_barrels(root, days, dry)
        }
        "metrics-snapshot" | "metrics" => metrics_snapshot(root),
        "monitor" => {
            let interval = flags
                .get("interval")
                .and_then(|s| s.parse().ok())
                .unwrap_or(30);
            monitor_loop(root, interval)
        }
        "serve" => {
            let port = positional
                .first()
                .and_then(|s| s.parse().ok())
                .or_else(|| flags.get("port").and_then(|s| s.parse().ok()))
                .unwrap_or(8787);
            serve_loop(root, port)
        }
        "daemon" => {
            let follow =
                flag_on(flags, "follow") || positional.iter().any(|s| s == "-f" || s == "--follow");
            let lines = flags
                .get("lines")
                .and_then(|s| s.parse().ok())
                .unwrap_or(100);
            daemon_command(
                root,
                positional.first().map(|s| s.as_str()).unwrap_or("status"),
                flag_on(flags, "force"),
                lines,
                follow,
            )
        }
        "help" => ok(vec![(
            "commands",
            Json::Array(
                CLI_COMMANDS
                    .iter()
                    .map(|s| Json::String((*s).into()))
                    .collect(),
            ),
        )]),
        other => fail("UnknownCommand", format!("unknown command {other}")),
    }
}

pub const CLI_COMMANDS: &[&str] = &[
    "check-changes",
    "record-change",
    "mark-green",
    "record-changes",
    "record-deletion",
    "session-bootstrap",
    "suggest-next",
    "prepare-edit",
    "dependencies",
    "dependents",
    "why-file",
    "search-journal",
    "list-paths",
    "cycles",
    "journal",
    "issues",
    "update-maps",
    "health",
    "validate",
    "rebuild-cache",
    "seed-health",
    "seed-source-hashes",
    "prune-pending",
    "prune-health",
    "heal-stubs",
    "healable-stubs",
    "healing-stats",
    "stale-wikis",
    "verify-wikis",
    "prune-barrels",
    "cache-status",
    "autonomous-status",
    "metrics-snapshot",
    "list-core-tools",
    "init",
    "monitor",
    "serve",
    "daemon",
    "help",
    "mcp",
];

fn flag_on(flags: &BTreeMap<String, String>, key: &str) -> bool {
    flags
        .get(key)
        .map(|s| s == "true" || s == "1")
        .unwrap_or(false)
}

fn flag_text<'a>(flags: &'a BTreeMap<String, String>, key: &str) -> Option<&'a str> {
    flags
        .get(key)
        .map(|s| s.as_str())
        .filter(|s| !s.is_empty() && *s != "true")
}

fn filter_dependency_report(value: &mut Json, low_only: bool, unresolved_only: bool) {
    if !low_only && !unresolved_only {
        return;
    }
    if unresolved_only && !low_only {
        value.insert("internal", Json::Array(vec![]));
        value.insert("external", Json::Array(vec![]));
        return;
    }
    if let Some(Json::Array(items)) = value.get("internal").cloned() {
        let kept: Vec<Json> = items
            .into_iter()
            .filter(|edge| {
                let score = match edge.get("confidence") {
                    Some(Json::Float(n)) => *n,
                    Some(Json::Int(n)) => *n as f64,
                    _ => 1.0,
                };
                let dynamic = edge
                    .get("dynamic")
                    .and_then(|v| v.as_bool())
                    .unwrap_or(false);
                !dynamic && score < 0.65
            })
            .collect();
        value.insert("internal", Json::Array(kept));
    }
    if unresolved_only {
        value.insert("external", Json::Array(vec![]));
    }
}

fn path_list_has_entries(root: &Path, name: &str) -> bool {
    !scope::read_path_list(root, name).is_empty()
}

fn init_project(root: &Path, no_copy: bool) -> Json {
    let _lock = match lock_or_fail(root) {
        Ok(lock) => lock,
        Err(err) => return err,
    };
    let mut created: Vec<String> = Vec::new();
    let write_new = |rel: &str, text: &str, created: &mut Vec<String>| -> bool {
        let path = root.join(rel);
        if path.exists() {
            return true;
        }
        if let Some(parent) = path.parent() {
            if fs::create_dir_all(parent).is_err() {
                return false;
            }
        }
        if fs::write(&path, text).is_err() {
            return false;
        }
        created.push(rel.to_string());
        true
    };
    let roots = scope::default_map_roots(root)
        .into_iter()
        .map(|dir| format!("{dir}\n"))
        .collect::<String>();
    let map_body = format!(
        "# map_paths.txt — import-map package roots for update-maps\n# One directory per line. No bare \".\".\n{roots}"
    );
    let monitored_body = format!(
        "# monitored_paths.txt — wiki and health watch list\n# Mapped sources are watched even when they are not listed here.\n{roots}"
    );
    let exclude_body = "\
node_modules
.git
build
dist
__pycache__
*.pyc
target
";
    let health_body = "\
# Documentation Health Matrix

| File | Status | Last Updated | Reason / Intent |
|------|--------|--------------|-----------------|
";
    let pending_body =
        "# Pending Updates\n\n(no pending items — run check-changes after making edits)\n";
    let library_body = "# Library & Imports Map\n\nRun `wikifier update-maps` to populate.\n";
    if !path_list_has_entries(root, "map_paths.txt")
        && !write_new("map_paths.txt", &map_body, &mut created)
    {
        return fail("InitError", "could not write map_paths.txt");
    }
    if !path_list_has_entries(root, "monitored_paths.txt")
        && !write_new("monitored_paths.txt", &monitored_body, &mut created)
    {
        return fail("InitError", "could not write monitored_paths.txt");
    }
    if !write_new("exclude_patterns.txt", exclude_body, &mut created) {
        return fail("InitError", "could not write exclude_patterns.txt");
    }
    if !write_new("file_health.md", health_body, &mut created) {
        return fail("InitError", "could not write file_health.md");
    }
    if !write_new("pending_updates.md", pending_body, &mut created) {
        return fail("InitError", "could not write pending_updates.md");
    }
    if !write_new("library.md", library_body, &mut created) {
        return fail("InitError", "could not write library.md");
    }
    let config = format!("project_root={}\n", root.display());
    if !write_new(".wikifier/config", &config, &mut created) {
        return fail("InitError", "could not write .wikifier/config");
    }
    for dir in ["journal", "Logged_issues", ".wikifier_staging"] {
        let path = root.join(dir);
        if !path.is_dir() {
            if fs::create_dir_all(&path).is_err() {
                return fail("InitError", format!("could not create {dir}"));
            }
            created.push(dir.to_string());
        }
    }
    let index = root.join("index.html");
    let mut copied = false;
    if !no_copy && !index.is_file() {
        if fs::write(&index, INDEX_HTML).is_err() {
            return fail("InitError", "could not write index.html");
        }
        copied = true;
        created.push("index.html".to_string());
    }
    let marker = root.join(".wikifier");
    let _ = fs::create_dir_all(&marker);
    let _ = fs::write(marker.join("marker"), format!("wikifier {VERSION}\n"));
    let created_json = Json::Array(created.iter().cloned().map(Json::String).collect());
    let seeded_text = if created.is_empty() {
        "kept".to_string()
    } else {
        created.join(",")
    };
    ok(vec![
        ("seeded", Json::String(seeded_text)),
        ("created", created_json),
        ("index_html", Json::Bool(index.is_file())),
        ("index_copied", Json::Bool(copied)),
        ("no_copy", Json::Bool(no_copy)),
        ("marker", Json::String(".wikifier".into())),
    ])
}

pub fn ensure_root(root: Option<&Path>) -> Result<PathBuf, Json> {
    root_or_err(root)
}
