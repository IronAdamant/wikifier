# wikifier/parsers/python.py

**Purpose:** Python import edges for the dependency map: `parse_python_imports(filepath)` and `parse_python_imports_from_string(source, filepath)`.

- Static imports via stdlib `ast` (exact for multi-line/parenthesized imports, comments and strings); files the interpreter cannot parse fall back to a line regex (`parse_mode: "regex-fallback"`).
- Resolution: relative imports walk up `level` packages; absolute imports search the file's top-level package root, the project root and `<project>/src`. `from pkg import name` where `name` is a submodule resolves to that file (one `from_import_submodule` edge per extra submodule). Not found ⇒ external (`external_or_bare`). Module files must match case exactly (`_exists_exact_case`, cached directory listings keyed by mtime) — on macOS/Windows `from pkg import DagRun` must not resolve to `pkg/dagrun.py` as a phantom `pkg/DagRun.py`.
- Imports under `if`/`try`/loops: `is_conditional` with `conditional_context`.
- Dynamic `importlib.import_module(...)` / `__import__(...)`: LDSI + CDIA analysis; a string literal resolves like a static import (`dynamic_type: "literal"`).
- Edge contract shared with the other parsers (`module`, `raw_module`, `level`, `imported_names`, `line`, `resolved_path`, confidence fields, `strategy`).
