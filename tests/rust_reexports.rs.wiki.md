# tests/rust_reexports.rs

**Role:** 5.6.0 tests for following Rust re-exports to the defining file.

`a_cross_crate_import_reaches_the_file_that_defines_the_name` builds a workspace whose `sp-input` crate re-exports in every followed form and a few that are not, with one app crate per import style. It checks `use sp_input::Input`, an alias in a brace group, a chain through nested modules and a glob, a glob import of the crate root, a path past a type with no `use`, unused glob names, a field named like a re-exported function, a private `use` across crates, a std re-export, a `#[path]` module, a macro-generated item, two `cfg` re-exports (first wins), a `use` inside an inline `mod`, and `pub(crate) use` and plain `use` inside the crate.

`every_read_tool_sees_the_re_export_edges_and_no_cycle_is_added` checks `get_dependents`, `prepare_edit`, `get_dependencies`, and that `get_cycles` lists only the crate's own `lib.rs` / `user.rs` cycle. `a_chain_longer_than_four_hops_adds_no_edge` checks the hop limit. `changing_a_re_export_moves_its_importers_edges_on_the_next_map` retargets, comments, and removes a re-export and checks `files_parsed` and the moved edges. `a_worktree_overlay_follows_the_re_exports_of_its_own_tree` checks that a worktree that retargets a re-export answers with its own edges while main keeps its own.
