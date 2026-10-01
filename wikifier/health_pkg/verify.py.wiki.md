# wikifier/health_pkg/verify.py

**Purpose:** what makes 🟢 Green mean something — checks a file's wiki against its code at `mark_green`.

- `public_symbols(path)`: Python → `__all__` if present, else top-level functions/classes without `_`; JS/TS → exported declarations and `export { … }` lists (comments and string literals ignored via the JS lexer). Other languages → `None` (`unchecked`).
- `verify_wiki(root, rel, entry)`: diff current symbols against `entry["public_symbols"]` (the last Green baseline). Blocking `issues`: `undocumented_new_symbols` (added, not mentioned), `wiki_mentions_removed_symbols` (removed, still in backticks), `wiki_not_updated_for_api_change` (surface changed, wiki bytes identical to last Green). Internal-only changes pass. No baseline yet ⇒ warnings only. Returns `verification` (`verified` / `no_wiki` / `unchecked`), `coverage`, `warnings`.
- `verify_wikis(root, directory, limit)`: read-only audit of every Green file with a wiki; `green_breakdown`, `failing`, `avg_symbol_coverage`.
- `WikiVerificationError(rel, check)` raised by `freshness._do_mark_green_checked` unless `force` (then `verification: "forced"`). `symbols_field` stores the list as a space-separated string; constants `VERIFIED`, `NO_WIKI`, `UNCHECKED`, `FORCED`.
