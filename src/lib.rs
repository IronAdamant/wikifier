//! Std-only Wikifier core. CLI and MCP both call this crate.
//! No third-party dependencies.

pub mod api;
pub mod artifacts;
pub mod cache;
mod cache_commit;
mod cycle_report;
mod daemon_svc;
mod drift;
pub mod jsonutil;
mod legacy_cache;
mod low_conf;
pub mod maps_out;
pub mod mcp;
pub mod mcp_compact;
pub mod mcp_groups;
pub mod parse;
mod pending_line;
mod proc;
mod project_config;
mod project_lock;
pub mod scope;
pub mod sha256;
pub mod symbols;
pub mod text_out;
pub mod timeutil;
mod wiki_files;
mod worktree;

pub use api::{
    cache_status, check_changes, health, list_paths, load_dependencies, load_dependents,
    mapped_edges, mark_green, prepare_edit, read_health, read_journal, record_change,
    session_bootstrap, suggest_next_actions, update_maps, VERSION,
};
pub use jsonutil::Json;
