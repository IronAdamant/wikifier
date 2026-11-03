# README.md

**Role:** The public entry point for the std-only Rust program.

Install is a release archive (`wikifier-<version>-<target>`, plus `SHA256SUMS`) or `cargo build --release`. `pip install wikifier` still installs Python 4.7. Agents start in this repo at `AGENTS.md` and follow `skills/run.md` (protocol v0.7, package 5.0.0). Bootstrap a target with `wikifier init`. The language table describes the comment-masked regex scans, including Rust crate-name imports. The lookup benchmark that cited a missing `scripts/benchmark_lookup.py` is gone. The performance table that remains says its numbers are from the Python package. `mark-green` checks Rust `pub` items, impl methods, and trait-impl items, as well as Python and JS/TS. Rust also reads `[workspace] members`. MCP is `wikifier mcp`.
