# tests/dogfood.rs

**Role:** Dogfood checks against fixture trees and this repository's own sources.

`containers_are_refused_and_scoped_children_map` refuses a root that contains several child projects and still maps a scoped child. `prepare_edit_on_this_repo_lists_api_dependents` copies this repo's `Cargo.toml`, `src/`, and `tests/` into a temp root, runs `update_maps`, and checks `prepare_edit` on `src/api.rs`. The dependent set is `src/lib.rs`, `src/mcp.rs`, `src/main.rs`, and the test files that import `wikifier::api` (`cli_surface`, `contract_gaps`, `protocol_v07`, `robustness`, `skip_maps`).
