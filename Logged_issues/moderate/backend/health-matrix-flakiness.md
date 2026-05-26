# Health Matrix Updates Are Unreliable and Inconsistent

**Date**: 2026-05-15
**Reporter**: Grok
**Severity**: moderate
**Category**: backend
**Milestone**: M1 - Core Reliability
**Labels**: v0.4

## Problem

The health matrix system has several reliability issues:

- `check-changes` sometimes fails with non-zero exit codes even on success
- Health matrix updates can create duplicate rows
- The `validate` command has a broken counter (lives inside a subshell)
- `mark-green` occasionally fails to remove items from `pending_updates.md`
- Timestamps and status flips can be inconsistent

## Impact on Agents

Agents fundamentally rely on the 🟢 / 🟡 / 🔴 health matrix to prioritize work. If the matrix is flaky, agents cannot trust the system and will waste tokens re-validating state manually.

## Proposed Work

- Audit and refactor all code paths that read/write `file_health.md`
- Fix the subshell scoping bug in `validate`
- Make health matrix updates idempotent (same operation multiple times = same result)
- Improve error handling and make all core commands return consistent exit codes
- Add better logging when the matrix is modified

## Success Criteria

- Running `wikifier check-changes && wikifier health` produces accurate results with zero false positives/negatives in normal usage.
- `validate` correctly reports all files missing from the health matrix.
- `mark-green` reliably clears the corresponding pending entry.
- The health matrix remains stable even when multiple commands are run in quick succession.
