# src/lib.rs

**Role:** Crate root for the std-only Wikifier core.

Public modules are `api`, `artifacts`, `cache`, `jsonutil`, `maps_out`, `mcp`, `parse`, `scope`, `sha256`, and `timeutil`. `legacy_cache`, `project_lock`, `cache_commit`, and `proc` stay private. The re-exports are the daily loop: bootstrap, check, prepare, record, mark-green, update-maps, and dependency lookup.
