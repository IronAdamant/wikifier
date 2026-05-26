# `record-change` Must Be Highly Reliable for Agent Workflows

**Date**: 2026-05-15
**Reporter**: Grok
**Severity**: high
**Category**: backend
**Milestone**: M1 - Core Reliability
**Labels**: v0.4

## Problem

`record-change` and `record-deletion` are core primitives for agents to log intent. Current issues include:

- Inconsistent journal formatting
- Occasional silent failures or partial writes
- Poor error messages when something goes wrong
- No structured output option for agents that want to parse results programmatically

## Impact on Agents

If agents cannot reliably log *why* they made a change, the entire value proposition of semantic intent tracking collapses. This is one of the highest-leverage features for long-term agent collaboration.

## Proposed Work

- Make journal writing atomic and resilient
- Add proper input validation and clear error messages
- Add `--json` output support for agent consumption
- Improve consistency of journal entry format
- Add basic tests or self-validation for these commands

## Success Criteria

- `wikifier record-change "file" "reason"` succeeds reliably even under rapid successive calls.
- Structured JSON output is available via `--json`.
- Error messages are clear and actionable for both humans and agents.
- Journal entries are always well-formed and correctly dated.
