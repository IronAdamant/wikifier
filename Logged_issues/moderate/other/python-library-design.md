# Design the Public Python Library Interface for Wikifier

**Date**: 2026-05-15
**Reporter**: Grok
**Severity**: moderate
**Category**: other
**Milestone**: M3 - Agent Interface & Ergonomics
**Labels**: v0.4

## Problem

Currently, the Python package is only a thin CLI launcher. For Wikifier to be truly useful for agents, it needs a clean, importable Python API.

## Scope (Design Only)

This issue is focused on **design**, not implementation.

## Proposed Work

- Define the high-level public API surface (`from wikifier import ...`)
- Decide core modules (health, record, query, config, etc.)
- Define data structures returned by the library
- Decide how much logic stays in shell vs moves to Python
- Produce a design document + example usage

## Success Criteria

- A clear, well-documented design for the Wikifier Python library API exists.
- The design supports both CLI and direct programmatic use by agents.
- Trade-offs are explicitly discussed and decided.
