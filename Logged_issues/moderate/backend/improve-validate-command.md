# Make `validate` Command Reliable and Agent-Useful

**Date**: 2026-05-15
**Reporter**: Grok
**Severity**: moderate
**Category**: backend
**Milestone**: M1 - Core Reliability
**Labels**: v0.4

## Problem

The `validate` command is currently broken due to subshell scoping and provides limited value to agents trying to understand the state of the health matrix.

## Scope for v0.4

Focus only on making validation accurate and useful. Defer any "auto-fix" ideas.

## Proposed Work

- Fix the validation logic (remove subshell bug)
- Output a clear, readable summary of files missing from the health matrix
- Add `--json` output for agent consumption
- Integrate validation results cleanly into the standard agent workflow

## Success Criteria

- `wikifier validate` correctly and consistently reports all files that exist in monitored paths but are missing from `file_health.md`.
- The command becomes a reliable part of the mandatory "new session" agent protocol.
