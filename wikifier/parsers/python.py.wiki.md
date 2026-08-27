# wikifier/parsers/python.py

**Role**: Core Python import parser for Milestone 2 (Dependency Intelligence).

This is one of the two foundational language parsers in Wikifier v0.4. It is responsible for turning Python source code into rich, structured dependency data that powers `update_maps`, the Mermaid graphs in `library.md`, reverse dependency lookup, and all high-level MCP tools (`get_dependencies`, `get_dependents`, etc.).

## Purpose

Provide a lightweight, zero-dependency, agent-friendly parser that extracts import statements with enough metadata for LLMs to reason about code relationships with minimal ambiguity.

## Key Design Goals

- **Agent-first output**: Every import returns a rich dictionary (not just strings).
- **Best-effort resolution**: Relative imports are resolved against the actual package structure on disk.
- **Pragmatic accuracy**: Good enough for real-world use while staying simple and fast.
- **Extensible**: Same return contract used by the JavaScript/TypeScript parser.
- **4.6.13**: `import a, b` emits two edges; LDSI helpers come from `_ldsi.py` (not `javascript.py`).

## Main Public Function

### `parse_python_imports(filepath: str) -> List[Dict]`

The primary entry point. Called by `cmd_update_maps` in `wikifier.sh` during both full and incremental runs.

**Return Structure** (every item contains):

| Field                | Description                                                                 |
|----------------------|-----------------------------------------------------------------------------|
| `module`             | Best-effort **resolved** module name (e.g. `wikifier.parsers.python`)      |
| `raw_module`         | Original string from the source code (e.g. `.parsers.python`)               |
| `is_relative`        | Boolean — was this a relative import?                                       |
| `level`              | Number of leading dots (1 = same package, 2 = parent package, etc.)        |
| `alias`              | `as` alias if present, otherwise null                                       |
| `imported_names`     | List of names imported in `from X import ...` style (supports `*` and aliases) |
| `original_statement` | The exact import line(s) as they appeared in the file (for traceability)   |
| `statement_type`     | One of: `"import"`, `"import_as"`, `"from_import"`, `"from_import_as"`     |

## Core Internal Functions

### `_resolve_relative_import(current_file, raw_module, level)`

The heart of relative import intelligence in the Python parser.

**How it works**:
1. Walks upward from the current file, collecting directory names only while `__init__.py` exists.
2. Builds the real package hierarchy (handles `src/` layouts gracefully).
3. Applies the relative level (number of dots).
4. Reconstructs the fully qualified module name.

This approach is more robust than simple string manipulation because it inspects the actual filesystem package structure.

Special handling exists for files at the package root (e.g. `__main__.py` or scripts next to `__init__.py`).

### `_strip_docstrings(content)`

Lightweight heuristic that removes triple-quoted strings before parsing.

This dramatically reduces false-positive imports that appear inside docstrings or large multi-line string literals.

## Supported Import Styles

- `import os`
- `import sys as system`
- `import re, json`
- `from pathlib import Path`
- `from typing import List, Dict, Optional`
- `from . import helpers`
- `from ..utils import config`
- `from .auth.jwt import create_token as jwt_auth`
- `from package.sub import func1, func2 as f2`
- `from module import *`
- Multi-line imports using parentheses (black/isort style)

## Integration with the Rest of the System

- Called by `cmd_update_maps` in `wikifier.sh` for every Python file that needs (re)parsing.
- Results are stored in `import_cache.json` (with both raw and resolved forms).
- Resolved modules are used to build the "Resolved Internal Dependencies" table and the Mermaid graph.
- The same data powers `get_dependencies()` and `get_dependents()` MCP tools.

## Known Limitations (Honest Assessment)

- Dynamic imports via `importlib.import_module(variable)` are not detected (by design — would require runtime analysis).
- Very exotic namespace package layouts or editable installs may produce imperfect resolution.
- Heavily commented or malformed multi-line imports can occasionally lose fidelity.
- Wildcard (`*`) imports are recorded but do not expand the names.

These limitations are documented and acceptable for v0.4.

## Why This Design?

Wikifier deliberately chose a pragmatic regex + filesystem-walking approach instead of using the full Python AST or importlib machinery. This keeps the entire system **zero external dependencies** and runnable anywhere with just bash + Python stdlib.

The rich return structure is the real value — it turns a simple parser into a powerful tool that agents can trust when exploring large codebases.

## Related Files

- `wikifier/parsers/javascript.py` — Sister parser with the same return contract
- `wikifier.sh` (`cmd_update_maps`) — Main consumer
- `wikifier/import_cache.py` — Where parsed results are stored for incremental runs
- `library.md` — Final output that uses this data

## Status

As of late M2, this parser is considered mature and reliable for the majority of real-world Python codebases. It has been heavily exercised during self-dogfood and RecipeLab_alt dogfood.

**Last major improvements**: Package hierarchy walking for `src/` layouts + better multi-line support + richer `imported_names` handling.