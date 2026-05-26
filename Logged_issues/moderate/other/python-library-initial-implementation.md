# Initial Python Library Implementation

**Date**: 2026-05-15
**Reporter**: Grok
**Severity**: moderate
**Category**: other
**Milestone**: M3 - Agent Interface & Ergonomics
**Labels**: v0.4

## Problem

Even after the design is complete, we need a minimal working Python library that agents can actually import and use.

## Scope for v0.4

Focus on a **minimal viable implementation** — not a complete port of all shell functionality.

## Proposed Work

- Set up proper package structure (`wikifier/`, `wikifier/core/`, etc.)
- Implement core functions based on the approved design (e.g., `get_health()`, `record_change()`, `get_pending_files()`)
- Wire the CLI to use the new library where possible
- Add basic documentation and examples

## Success Criteria

- Agents can do `from wikifier import health, record` and perform basic operations without calling the shell.
- The initial implementation covers the most important operations needed for the agent workflow.
- The library is importable and usable (even if incomplete).
