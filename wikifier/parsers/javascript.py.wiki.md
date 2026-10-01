# wikifier/parsers/javascript.py

**Purpose:** JS/TS import edges (`.js .ts .jsx .tsx .mjs .cjs .mts .cts`).

- `_lex_mask` blanks `//` and `/* */` comments and records string/template/regex spans; a match whose keyword sits in a string is ignored. Code inside template `${…}` still counts.
- Patterns run most-specific first; each string specifier is claimed once (no duplicate edges from overlapping patterns).
- Resolution delegates to `wikifier.resolution` (relative, tsconfig `paths`, package `exports`/`imports`, workspaces, bare internal). Unresolved package specifiers are external, never barrels.
- `import('./x')` / `import.meta.resolve('./x')` with a literal ⇒ `is_dynamic`, `dynamic_type: "literal"`; template/expression specifiers get LDSI candidate recovery.
- Barrels: a direct entry-barrel edge plus BREE-expanded leaves (routed by imported names, capped otherwise) with `via_barrel` / `barrel_depth` / `barrel_v2`.
- Conditional context from CDIA (enclosing guards only).
