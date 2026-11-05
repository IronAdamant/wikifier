# README.md

**Role:** The public entry point for the std-only Rust program.

Order: what it is, install (release archive `wikifier-<version>-<target>` plus `SHA256SUMS`, or `cargo build --release`), connecting an agent over MCP (`claude mcp add wikifier -- wikifier mcp` or `.mcp.json`, `project_root` on every call), a quick start of the edit loop, how it works (pipeline, artifacts, language table), then the measured Performance and Benchmarks tables (unchanged; the Performance table says its numbers are from the Python package), the dashboard, and links. Detail lives in `skills/run.md` (protocol v0.7, package 5.0.0) and `AGENTS.md`. `pip install wikifier` still installs Python 4.7.
