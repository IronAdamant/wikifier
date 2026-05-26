# Evolve `skills/run.md` into a Stronger, More Formal Agent Protocol

**Date**: 2026-05-15
**Reporter**: Grok
**Severity**: high
**Category**: other
**Milestone**: M3 - Agent Interface & Ergonomics
**Labels**: v0.4

## Problem

`skills/run.md` is currently a good starting point but needs to become a more rigorous, versioned protocol that different LLMs can follow with high consistency and low deviation.

## Proposed Work

- Rewrite the mandatory new-session rule to be extremely clear and step-by-step
- Define expected inputs and outputs for each major command in the workflow
- Add sections on error handling, structured output usage, and best practices
- Version the protocol (e.g., Protocol v0.4)
- Make it the authoritative reference for any agent using Wikifier

## Success Criteria

- An agent following `skills/run.md` can execute the full recommended workflow with minimal ambiguity.
- Different models (Grok, Claude, GPT, etc.) can follow the protocol and produce similar, predictable behavior.
- The document is treated as a living specification for agent behavior.
