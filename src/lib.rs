//! Std-only Wikifier core. CLI and MCP both call this crate.
//! No third-party dependencies.

pub mod api;
pub mod artifacts;
pub mod cache;
mod cache_commit;
pub mod jsonutil;
pub mod mcp;
pub mod parse;
mod proc;
pub mod scope;
pub mod sha256;
pub mod timeutil;

pub use api::{
    cache_status, check_changes, health, list_paths, load_dependencies, load_dependents,
    mapped_edges, mark_green, prepare_edit, read_health, read_journal, record_change,
    session_bootstrap, suggest_next_actions, update_maps, VERSION,
};
pub use jsonutil::Json;
