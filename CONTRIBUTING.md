# Contributing to Wikifier

Thank you for your interest in Wikifier! This project is intentionally **agent-first** and ultra-light. We want contributions that keep it that way.

## Our Philosophy

- **Zero external dependencies** is sacred. No new Python packages, Node modules, Docker images, or heavy CLIs.
- **Agent-first design** comes first. If something makes life harder for LLMs/Grok Build/Cline/etc., we probably shouldn't do it.
- **Semantic logging** (`record-change`) is the heart of the system. Changes without intent are less valuable.
- Keep it simple. This is a shell + Markdown tool, not a full framework.

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
   ./wikifier.sh check-changes
   # Read file_health.md and pending_updates.md
   # Prioritise Red → Yellow
   ```
3. For **any** code or documentation change you make:
   ```bash
   ./wikifier.sh record-change "path/to/your/file" "I changed X because Y. This improves Z for agents."
   ```
4. After you update the corresponding wiki summary (if applicable):
   ```bash
   ./wikifier.sh mark-green "path/to/your/file"
   ```
5. Run `./wikifier.sh validate` and `./wikifier.sh update-maps` before opening a PR.

### 3. Pull Request Guidelines

- Keep PRs focused. One logical change per PR.
- Update documentation (`README.md`, `docs/spec.md`, `skills/run.md`) when behavior changes.
- If you add a new command, document it in `skills/run.md` and the help text in `wikifier.sh`.
- All shell changes must remain POSIX-compatible where possible (or clearly PowerShell-only).
- Add yourself to the journal if you want (`wikifier record-change` is the proper way).

### 4. Code Style

- **Shell**: Keep it readable. Use functions. Prefer clarity over cleverness.
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
./wikifier.sh check-changes
# Work
./wikifier.sh record-change "wikifier.sh" "Added support for X because..."
./wikifier.sh mark-green "wikifier.sh"
./wikifier.sh update-maps
```

## Questions?

Open an issue with the **Agent / LLM Finding** template or just start a discussion.

We especially welcome contributions from other agents and LLM users who have used Wikifier in real projects.

---

*Remember: every good `record-change` you write makes the system more valuable for the next agent that comes along.*
