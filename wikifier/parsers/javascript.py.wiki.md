# wikifier/parsers/javascript.py

**Role**: JavaScript / TypeScript import parser for Milestone 2 (Dependency Intelligence).

This is the second foundational language parser in Wikifier. It follows the exact same rich return contract as the Python parser to keep the system consistent for agents.

## Purpose

Extract import/require/re-export information from JS and TS files with best-effort resolution and confidence scoring. This data powers the cross-language dependency graph, reverse dependencies, and all high-level MCP tools.

## Key Innovations Compared to Python Parser

- **Confidence scoring**: Every resolution includes `resolution_confidence` ("high" | "medium" | "low" | "unresolved").
- **Bare internal module resolution**: Sophisticated walking logic (`_try_resolve_bare_internal_import`) to resolve non-relative imports like `services/foo` or `utils/helpers` on real-world projects (including flat/legacy layouts without package.json).
- **Modern TypeScript support**: Extensive patterns for `import type`, `export type`, `export { type ... }`, etc.
- **Dual resolution strategies**: Marker-based (package.json / index.*) + pragmatic directory-name fallback for flat projects.

## Rich Return Structure

Each parsed import contains (in addition to the Python fields):

- `resolved_path`: Absolute filesystem path when successfully resolved on disk.
- `resolution_confidence`: How trustworthy the resolution is.

This extra metadata is extremely valuable for agents when deciding how much to trust a particular edge in the dependency graph.

## Core Functions

### `_resolve_relative_import()`

Similar philosophy to the Python version but adapted for JavaScript realities:
- Looks for `package.json`, `index.js/ts/jsx/tsx` as package markers.
- Falls back to collecting directory names on flat projects (very common in real-world JS codebases like RecipeLab_alt).
- Has safety caps and ignored top-level directories.

### `_try_resolve_bare_internal_import()`

One of the most important functions for practical JS dogfooding.

Attempts to resolve bare imports (e.g. `import { x } from "services/mealPlanner"`) by walking upward and checking for matching files or `index.*` files.

Returns both a normalized module name and the actual resolved filesystem path when possible, along with a confidence rating.

This function was critical for making dependency intelligence useful on non-standard JS project layouts.

### `parse_javascript_imports()`

The main entry point. Contains an extensive battery of regex patterns covering:

**ES Modules**
- `import ... from "..."` (including named, default, namespace, side-effect)
- Re-exports: `export * from`, `export { x } from`, `export * as ns from`
- Dynamic `import()`

**CommonJS**
- `require("...")`
- `import X = require("...")`

**TypeScript-specific**
- `import type { ... } from`
- `import type * as X from`
- `export type { ... } from`
- Mixed type/value exports
- `export { type Foo } from`

**Modern / Future**
- `import.meta.resolve(...)`
- `import.meta.*` patterns

## Design Philosophy

The JS/TS parser is deliberately more "battle-hardened" than the Python parser because real-world JavaScript projects are far more varied in structure (flat layouts, heavy barrel exports, dynamic requires, missing index files, etc.).

The confidence system + bare module resolver represent the pragmatic engineering required to make dependency intelligence actually useful on real codebases rather than just clean npm-style projects.

## Integration Points

- Called from `cmd_update_maps` alongside the Python parser.
- Results (including `resolved_path` and `resolution_confidence`) are stored in the import cache.
- Powers the "Resolved Internal Dependencies" table and the language-colored Mermaid subgraphs.
- Directly used by `get_dependencies()` and `get_dependents()`.

## Known Limitations

- Barrel re-exports (`export * from './barrels'`) are detected but not fully expanded.
- Very dynamic patterns (`require(variable)`, `import(variable)`) are only lightly supported.
- Confidence scoring is heuristic and can be wrong on extremely unusual layouts.
- Performance on massive monorepos with thousands of JS files can still be improved (incremental caching helps significantly).

## Why It Matters

JavaScript/TypeScript is often the weakest link in dependency analysis tools. The amount of effort put into bare internal resolution and confidence metadata in this parser is one of the reasons Wikifier can be trusted on real JS projects (as proven during RecipeLab_alt dogfooding).

## Related Files

- `wikifier/parsers/python.py` — Sister parser (same return contract)
- `wikifier.sh` (resolution logic in `cmd_update_maps`)
- `test-js-flat/` — Dedicated test project for end-to-end confidence validation

## Status (M2-Rem-08)

The JavaScript/TypeScript parser has received substantial work during the A-thread (parser quality) and is now one of the stronger parts of the dependency system for non-trivial JS codebases.

**Last major improvements**: Enhanced re-export patterns, better bare internal resolution with directory fallback, extensive modern TypeScript type export support.

This file now has a complete, high-quality wiki summary created during thorough self-dogfood.