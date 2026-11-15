# src/parse/rust_reexport.rs

**Role:** Rust re-exports for `parse`: which file defines a name a path reaches through a module's `use` items.

Scan side: `item_def` reads a top-level item's name and whether it has any `pub` (`fn`, `struct`, `enum`, `union`, `trait`, `type`, `static`, `const`, through `async`, `unsafe`, `const fn` and `extern "C" fn`; not `mod`, `use`, `impl`, `extern crate` or macros). `use_entries` turns one `use` item into `RustUse` entries: bound name (the alias, the last segment, or the module for `self`), path, and glob flag; `as _` binds nothing. `bare_idents` lists the identifiers a file names on its own, skipping comments, strings, numbers, and names after `.` or `::`. `export_entries` lists a scan's `rust_uses` and `rust_defs` as sorted text entries, each starting with the name it binds (`*` for a glob).

Lookup side: `Exports` holds each module's table (item names, named `use` items, globs resolved to module files; a glob of an enum or type is dropped) and memoises answers per run. `definer` looks a name up in item names, then named `use` items (following the path with `Resolver::rust_lookup`), then globs, for up to `RUST_GLOB_DEPTH` hops. A named `use` whose target module has no such item answers that module (macro-generated items); a chain over the hop limit answers nothing. `private` admits items without `pub`, for an importer in the same crate; a glob hop admits only `pub` items. `offered` lists every name a glob of a module brings in with its defining file; a name the module binds itself hides the same name from its globs.

Public names: `export_entries`.
