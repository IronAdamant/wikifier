# Logged Issues Map

This directory organises all issues reported by humans and LLMs using Wikifier.

## Severity Levels

- **simple/** — Minor nits, documentation typos, small UX annoyances
- **moderate/** — Features that are incomplete, medium refactoring debt
- **high/** — Broken functionality, performance regressions, important missing wiki coverage
- **critical/** — Security issues, data loss risk, core workflow broken, agent loop failures

## Category Subfolders (inside each severity)

- `frontend/` — UI, HTML dashboard, CSS, presentation layer
- `backend/` — Shell logic, health matrix, journal system, import scanning
- `import/` — Issues with the `update-maps` / library.md generation
- `staleness/` — Health matrix becoming out of date, heartbeat problems
- `security/` — Anything touching file system, execution of untrusted input, etc.
- `other/`

## How to Log a New Issue (LLM or Human)

1. Choose severity + category.
2. Create a new `.md` file with a descriptive name, e.g. `Logged_issues/high/backend/heartbeat-stops-on-macos.md`
3. Include: date, reporter (LLM or name), reproduction steps, impact, and proposed fix.
4. After resolution, either delete the file or move it to an `archive/` subfolder with resolution notes.

**Current open issues:** (auto-populated by agents running `wikifier issues`)

See the individual severity folders for concrete items.

---

## v0.4 Roadmap

A dedicated roadmap is tracked here:

→ [`v0.4-roadmap.md`](v0.4-roadmap.md)

**Focus**: Agent-to-Agent Codebase Memory System  
**Success Markers**: Defined in the roadmap file (7 markers)

All v0.4-related issues are tagged with `v0.4` in their filename or content and are primarily filed under:

- `moderate/backend/`
- `high/backend/`
- `moderate/import/`
- `high/import/`
- `moderate/other/`
- `high/other/`

The roadmap is currently in early execution phase. See `v0.4-roadmap.md` for detailed milestones and current status.
