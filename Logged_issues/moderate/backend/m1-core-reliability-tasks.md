# Milestone 1: Core Reliability – Task List

**Status**: Ready to Start  
**Parent Issues**:
- `health-matrix-flakiness.md`
- `record-change-reliability.md`
- `improve-validate-command.md`

**Goal**: Make the core Wikifier commands (especially health matrix and `record-change`) stable, predictable, and trustworthy for agent use.

---

## How to Use This Document (for Agents)

- Update the **Status** column as work progresses.
- Use `record-change` when completing significant tasks.
- Move completed tasks to the bottom or mark them clearly.
- When all tasks in a group are done, update the parent issue.

---

## Task Overview

| ID | Task | Size | Status | Priority | Notes / Dependencies |
|----|------|------|--------|----------|----------------------|
| **M1-A1** | Fix subshell scoping bug in `validate` | Small | [x] Done | Critical | Completed 2026-05-15 |
| **M1-A2** | Make health matrix writes idempotent (prevent duplicates) | Medium | [x] Done | High | Now uses grep -vF + append pattern |
| **M1-A3** | Standardize exit codes across core commands | Medium | [x] Done | High | 0=success, 1=usage, 2=runtime |
| **M1-A4** | Improve error messages and logging for health operations | Small | [x] Done | Medium | Added proper error handling in upsert + mark_green |
| **M1-A5** | Ensure `mark-green` reliably clears pending entries | Small | [x] Done | High | Now uses atomic removal pattern + better logging |
| **M1-B1** | Make journal writing atomic (prevent partial writes) | Medium | [x] Done | High | Implemented mkdir-based lock + temp file |
| **M1-B2** | Add `--json` output to `record-change` / `record-deletion` | Medium | [x] Done | Medium | --json flag supported as first argument |
| **M1-B3** | Improve input validation + error messages for `record-change` | Small | [x] Done | High | Better usage messages + JSON error output |
| **M1-B4** | Standardize journal entry formatting | Small | [x] Done | Medium | Added '---' separator between entries |
| **M1-C1** | Rewrite `validate` logic to be accurate and reliable | Medium | [x] Done | High | Subshell fixed + exclude patterns now respected |
| **M1-C2** | Add `--json` output to `validate` | Small | [ ] Not Started | Medium | Agent consumption |
| **M1-C3** | Improve `validate` output formatting (summary + list) | Small | [ ] Not Started | Medium | Readability |

---

## Group A: Health Matrix Stability

**Parent Issue**: `health-matrix-flakiness.md`

- **M1-A1**: Fix subshell scoping bug in `validate` command
- **M1-A2**: Make health matrix writes idempotent
- **M1-A3**: Standardize exit codes
- **M1-A4**: Improve error messages & logging
- **M1-A5**: Fix `mark-green` pending entry clearing

## Group B: `record-change` Reliability

**Parent Issue**: `record-change-reliability.md`

- **M1-B1**: Make journal writing atomic
- **M1-B2**: Add structured `--json` output
- **M1-B3**: Improve validation and error messages
- **M1-B4**: Standardize journal formatting

## Group C: Validate Command Improvements

**Parent Issue**: `improve-validate-command.md`

- **M1-C1**: Rewrite validation logic (depends on M1-A1)
- **M1-C2**: Add `--json` support
- **M1-C3**: Improve human/agent-friendly output

---

## Recommended Execution Order (Suggested)

1. **M1-A1** → Quick win, unblocks validation work
2. **M1-C1** → Core validation reliability
3. **M1-A2** → High impact on daily agent use
4. **M1-A3** → Agent predictability
5. **M1-B1** → Critical for intent logging
6. **M1-A5 + M1-B3** → Polish
7. Structured output (`--json`) tasks (can run in parallel)

---

## Progress Tracking

- **Tasks Completed**: 0 / 12
- **Current Focus**: Not started yet

**Last Updated**: 2026-05-15

---

**Next Action**: Choose the first task to begin (recommended: **M1-A1**)
