# src/export_sigs.rs

**Role:** Keeps each Rust file's export entries between map runs so a changed re-export moves its importers' edges.

`Sigs` loads `wk_cache/rust_exports.tsv` (one line per file: the path, then its `parse::export_entries`, tab-separated; missing or unreadable is empty). `update` records the entries of parsed Rust files and returns each file whose entries changed with a `Changed`: the names whose entries differ, or `All` when a glob changed or nothing was recorded. `forget` drops a removed file, and `save` writes the file after the cache commit (only when something changed).

`importers_to_reparse` walks the stored reverse edges from the changed files. An importer is parsed again when its text names a changed name as a whole word (always for `All`). The walk goes on from an importer whose `use` items can pass such a name on (a glob, or an item binding the name), for up to the re-export hop limit. Files already parsed and files out of scope are not returned.

A lost or stale entries file only costs extra parsing on the next run.
