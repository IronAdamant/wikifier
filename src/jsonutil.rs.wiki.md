# src/jsonutil.rs

**Role:** The small JSON value this program reads and writes. There is no serde crate.

`parse` reads a JSON document. `parse_jsonc` and `strip_json_comments` accept a tsconfig-style document with comments. `Json` is the value: null, bool, int, float, string, array, and object.

Public names: `Json`, `parse`, `parse_jsonc`, `strip_json_comments`.
