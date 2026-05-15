# TRADEOFFS.md — Design Decisions in Wikifier v0.3

## Passive Polling vs Filesystem Events

**Choice**: Simple mtime polling via `find -newermt` + timestamp file (`.wikifier_last_check`).

**Why**:
- Zero dependencies and works identically on Linux, macOS, Windows (via WSL or PowerShell equivalent).
- No `inotifywait`, `fswatch`, or `watchdog` required.
- LLMs can sleep; the monitor loop just keeps the health matrix fresh.

**Downside**: 30s latency on average. Acceptable for documentation/wiki use case.

## Static HTML Dashboard vs Dynamic SPA

**Choice**: Single self-contained `index.html` with embedded JS that fetches/parses local `.md` files (via `fetch` + marked.js or simple regex, or pre-generated JSON).

**Why**:
- No build step, no server, no npm.
- Can be opened directly from disk (`file://`).
- Extremely fast to render even for thousands of files.

**Future option**: A small Node script can be added later to pre-render the dashboard into a richer `dist/index.html` without changing the core zero-dep contract.

## Semantic `record-change` vs Pure Git History

**Choice**: We still encourage `record-change` even when the user is also using git.

**Why**:
- Git tells you *what* changed.
- `record-change` tells the LLM *why* the change was made and the reasoning at decision time.
- This "intent log" is gold for future agents doing archaeology or refactoring.

## Health Matrix as Single Markdown Table

**Choice**: One `file_health.md` with a Markdown table rather than per-file frontmatter or a JSON blob.

**Why**:
- LLMs read Markdown natively with perfect fidelity.
- Humans can read it directly in any editor.
- Easy to append with `>>` in shell.
- Git diffs are human-readable.

## Directory-Based Logged Issues

**Choice**: Nested folders `Logged_issues/{severity}/{category}/` instead of tags or a single SQLite DB.

**Why**:
- Pure filesystem navigation — works in every tool.
- LLMs can `ls` or `find` to discover issues quickly.
- Easy to split large files when a category grows.

## No Code in Wiki MD Files

**Choice**: Wiki summary files contain only filename + imports + prose purpose. Zero source code.

**Why**:
- Massive token savings.
- Prevents the LLM from being distracted by implementation details when it only needs architecture.
- The real source of truth remains the original files.

## Heartbeat Wakes the LLM (Conceptual)

The monitor loop can create a sentinel file `.wikifier_staging/work_ready`. When an LLM starts a new session it sees this and knows to run `check-changes` + triage Yellow/Red items immediately. This is the "LLM can sleep" pattern requested in the spec.

---

These tradeoffs keep Wikifier true to its core promise: **maximum compatibility + agent autonomy + zero external dependencies**.
