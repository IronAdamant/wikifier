# wikifier/diagnostics.py

**Purpose:** classify why an import is low-confidence or unresolved and summarize it for agents (`_resolution_diagnostics`, MCP `get_resolution_diagnostics`, `library.md`).

- `Diagnostic` dataclass + `make_diagnostic` / `make_unknown_diagnostic` / `make_creative_dynamic_diagnostic` build the per-edge diagnostic: `category` (`external_or_bare`, `creative_dynamic`, `unknown`, …), `reason`, `suggestion_for_agent`.
- `summarize_diagnostics(pairs, max_samples_per_category=5, max_total_samples=50)` — O(n) counts by category plus samples capped per category, ordered actionable-first (external noise last) so fixable imports are always visible.
- `is_high_confidence`, `empty_diagnostics_summary()` (stable empty shape), `diagnostics_summary_as_json` (shell/pipe helper).
