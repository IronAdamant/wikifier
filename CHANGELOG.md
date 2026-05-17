# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.3.2] - 2026-05-17

### Added
- **Gap #1 (Dependency Intelligence Quality) — Substantially Closed (~94–96%)**
  - Completed the dedicated M2-Rem-08 deep closure pass on the dependency system.
  - **JS/TS Parser Enhancements** (via 6 parallel specialized agents):
    - Barrel following depth increased from 2 → 3 (`_BARREL_MAX_DEPTH`)
    - Significantly improved barrel detection heuristics (now catches common "import-then-local-re-export" index barrels)
    - Full `barrel_chain` propagation through the entire pipeline (now visible in Mermaid, MCP tools, and cache)
    - Added support for modern `package.json` `"exports"` maps in both normal resolution and barrel following
    - Performance optimizations for barrel probing (regex hoisting, memoization, lightweight extractor + cheap pre-checks)
    - Conditional context now properly propagates through barrel chains (OR logic + forced `low` confidence)
  - Rich dependency metadata (`via_barrel`, `barrel_depth`, `barrel_chain`, `is_conditional`, `is_dynamic`, etc.) is now robust and flows reliably everywhere.
  - Cycle detection and deep barrel intelligence are now production-grade features.

### Changed
- Dependency intelligence is no longer the dominant blocker. Focus has shifted to `update-maps` performance at scale as the primary remaining practical concern.

### Fixed
- Numerous long-standing limitations in barrel resolution and data flow that were blocking trustworthy dependency graphs on modern and complex projects.

---

## [0.3.1] - 2026-05-17

### Added
- **Health Matrix Auto-Healing**
  - New `heal_outdated_stubs()` system that automatically detects "Initial stub" entries which now have substantial wiki summaries.
  - Smarter wiki quality heuristics (headings, purpose/overview sections, structure, word count, semantic signals).
  - High-quality wikis can now be promoted directly to 🟢 Green.
  - New commands:
    - `wikifier heal-stubs [--dry-run]`
    - `wikifier healable-stubs`
    - `wikifier healing-stats`
  - New MCP tools: `heal_stubs()`, `list_healable_stubs()`, and `health(format="healing-stats")`.
  - Automatic healing now runs at the end of every `check-changes`.

- **Dependency Intelligence Improvements** (major work on M2-Rem-08)
  - Complete refactor of the first-pass engine (`perform_first_pass_graph_and_cache_update`).
  - `resolved_pairs` now stored with `confidence` (`high` / `medium` / `low`).
  - Full reverse dependency recording and persistence (`_reverse_dependencies` in the cache).
  - `get_dependencies()` and `get_dependents()` now prefer rich cached data and are significantly more reliable.
  - Per-file `dependents` lists are now stored in the cache for impact analysis.
  - `import_cache.json` now contains richer, more structured data.

- **Developer Experience**
  - `WIKIFIER_DEBUG=1` mode for the first-pass (shows exactly what would be re-parsed without side effects).
  - Multiple helper extractions and major cleanup of the first-pass function for better maintainability.
  - `reparse_file_list()`, `determine_files_to_reparse()`, and `persist_rich_cache_data()` helpers.

- **MCP Tool Improvements**
  - `get_dependencies()` and `get_dependents()` now leverage the rich cache + reverse dependencies.
  - New tools for stub healing and healing statistics.
  - New `get_cycles()` tool (text + JSON) exposing full cycle detection.

- **Gap #1 Closure — Dependency Intelligence (Major Milestone)**
  - JS/TS parser: 4-phase improvements (dynamic classification, barrel following with depth, conditional detection, confidence propagation).
  - Full end-to-end rich data pipeline (`parse_parser_json_output`, `process_file_imports`, `persist_rich_cache_data`).
  - **Cycle Detection** (complete stack):
    - DFS cycle finder + deduplication in `import_cache.py`
    - Automatic computation and persistence during `update-maps`
    - `wikifier cycles` CLI command
    - `get_cycles()` MCP tool
    - Dedicated "Circular Dependencies" section in `library.md` with recommendations
    - Visual warnings in Mermaid graphs (red dashed `cycleNode` styling)
  - Deeper barrel support: Normal imports that resolve to barrels are now expanded (probe logic + relative resolution fix in the parser).
  - Rich metadata (`via_barrel`, `barrel_depth`, `is_conditional`, `is_dynamic`, etc.) now flows reliably to cache, MCP tools, Mermaid, and `library.md`.

### Changed
- `update_file_data()` in `import_cache.py` now properly normalizes and stores confidence in `resolved_pairs`.
- Cache writing now includes both forward (`resolved_pairs` + confidence) and reverse (`dependents`) data.
- First-pass function is significantly more readable and modular after helper extraction.

### Fixed
- Old "Initial stub" health entries can now be automatically healed when real documentation exists.
- Reverse dependencies are now properly persisted and available for incremental runs.

---

## [0.3.0] - 2026-05-?? (Initial Public Release)

- Initial public release of Wikifier.
- Core agent-first features: `check-changes`, health matrix, `record-change`, `mark-green`, `update-maps`, MCP server, etc.
- Zero-dependency design.
- Self-maintaining wiki system.

[0.3.1]: https://github.com/IronAdamant/wikifier/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/IronAdamant/wikifier/releases/tag/v0.3.0
