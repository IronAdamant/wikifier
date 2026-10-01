# wikifier/parsers/cdia.py

**Purpose:** conditional & dynamic import analysis (CDIA v1 payloads).

`ScopeBuilder.build(content, pos, language)` returns only what *encloses* the import: JS/TS unclosed-brace headers (`if (…) {`, `for`, `try`, `catch`, `switch`/`case`), braceless `if (x) require(…)`, ternary and `&&`/`||` guards in the import's own statement; Python enclosing blocks by indentation. Conditional detectors (control flow, ternary, feature flag, env check, lazy wrapper) read that guard context, never arbitrary preceding code. Dynamic detectors classify computed specifiers.
