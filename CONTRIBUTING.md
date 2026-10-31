# Contributing to Wikifier

Thank you for your interest in Wikifier! This project is intentionally **agent-first** and ultra-light. We want contributions that keep it that way.

## Our Philosophy

- **Zero external dependencies** is sacred. No new Python packages, Node modules, Docker images, or heavy CLIs.
- **Agent-first design** comes first. If something makes life harder for LLMs/Grok Build/Cline/etc., we probably shouldn't do it.
- **Semantic logging** (`record-change`) is the heart of the system. Changes without intent are less valuable.
- Keep it simple: a stdlib-Python package + Markdown artifacts, not a framework.

## How to Contribute

### 1. Reporting Issues

Please use the appropriate GitHub issue template:

- **🐛 Bug Report** — Something is broken in the CLI, health matrix, journal, or dashboard.
- **✨ Feature Request** — New command, better behavior, or quality-of-life improvement.
- **📋 Documentation / Wiki Health Issue** — Problems with file summaries, missing coverage, or incorrect health status.
- **🤖 Agent / LLM Finding** — You (as an LLM) discovered something while using Wikifier on another project. This is highly encouraged.

### 2. Making Changes

1. **Fork** the repository and create a feature branch from `main`.
2. **Follow the rules yourself**:
   ```bash
   wikifier session-bootstrap
   wikifier check-changes
   # Prioritise 🔴 Red → actionable 🟡 Yellow
   ```
3. For **any** code or documentation change you make:
   ```bash
   wikifier record-change "path/to/your/file" "I changed X because Y. This improves Z for agents."
   ```
4. After you update the corresponding wiki summary (if applicable):
   ```bash
   wikifier mark-green "path/to/your/file"
   ```
5. Before opening a PR: `cargo test`, then `wikifier update-maps` and `wikifier validate` on this repo. Parser changes must keep `accuracy_fixtures_match_frozen_edges` green.

### 3. Pull Request Guidelines

- Keep PRs focused. One logical change per PR.
- Update documentation (`README.md`, `docs/spec.md`, `skills/run.md`) when behavior changes.
- If you add a command, implement it in `wikifier/api.py` (library) + `wikifier/cli.py` (argparse), add it to `skills/run.md`, and add a test. The launchers (`wikifier.sh`/`.ps1`/`.bat`) stay thin.
- Fix a bug with a regression test that fails without the fix.
- Add yourself to the journal if you want (`wikifier record-change` is the proper way).

### 4. Code Style

- **Python**: stdlib only, Python 3.8+. Catch specific exceptions; never swallow errors silently — return `{"success": False, "error": …}` at the API boundary instead.
- **Markdown**: Short paragraphs. Use tables for commands. Use emojis sparingly and consistently.
- **No new dependencies**. If your idea requires one, it probably doesn't belong here.
- Test on at least one Unix-like system and (ideally) Windows.

### 5. Documentation Contributions

Wikifier is self-documenting. The best documentation contributions usually come in the form of:

- Improving file summaries in the monitored codebase
- Better `record-change` reasons that future agents will find useful
- Improvements to `skills/run.md` (the agent contract)

## Development Workflow (Meta)

When working on Wikifier itself, treat this repository as a Wikifier project:

```bash
wikifier check-changes
# Work
wikifier record-change "src/api.rs" "Added support for X because..."
# refresh wikifier/api.py.wiki.md if it exists
wikifier mark-green "src/api.rs"
wikifier update-maps
```

## Questions?

Open an issue with the **Agent / LLM Finding** template or just start a discussion.

We especially welcome contributions from other agents and LLM users who have used Wikifier in real projects.

---

*Remember: every good `record-change` you write makes the system more valuable for the next agent that comes along.*
