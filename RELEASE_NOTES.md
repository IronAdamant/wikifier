# Wikifier v0.3 — Initial Public Release

**Agent-first, zero-dependency, self-maintaining codebase documentation & change tracking system.**

Wikifier is now open source.

## Highlights

- **Full cross-platform CLI**
  - `wikifier.sh` — Complete Linux/macOS implementation (all commands)
  - `wikifier.ps1` + `wikifier.bat` — Real Windows PowerShell support
- **Semantic Intent Logging** — `record-change <file> "I did X because Y"` captures the *why*, not just the diff
- **Documentation Health Matrix** — Per-file 🟢 Green / 🟡 Yellow / 🔴 Red with automatic updates
- **Background Heartbeat** — `wikifier monitor &` keeps the wiki fresh without constant LLM attention
- **Rich Static Dashboard** — Beautiful `index.html` with live health matrix, Mermaid dependency graphs, pending queue, and command launcher
- **MCP / Agent Native** — `skills/run.md` contains the exact contract and mandatory new-session rule every LLM must follow
- **Automated Journaling + Logged Issues** — Dated daily journals + categorized issues (`simple` → `critical`, `frontend`/`backend`/`security`/...)
- **True Zero Dependencies** — Only native OS tools. No Docker, no Node, no Python packages. Runs anywhere.

## New Session Rule (for LLMs)

Every time you start working in a Wikifier project, the first thing you must do is:

```bash
wikifier check-changes
# then read file_health.md + pending_updates.md
# then prioritise Red → Yellow
# use record-change for every edit
# mark-green after updating wiki summaries
```

## Quick Start

```bash
git clone https://github.com/IronAdamant/wikifier.git
cd wikifier
chmod +x wikifier.sh
./wikifier.sh init
./wikifier.sh check-changes
# open index.html
```

## What's Next (v0.4 ideas)

- Language-aware import parsing (better Mermaid graphs)
- Optional git hook integration
- TUI dashboard option
- Obsidian export mode

This is the real initial release of the project described in the original spec.

**Built for agents. Operated by agents. With just bash and determination.**

---

## M4 80-95% — State Durability Foundations (2026-06)

M4 (feature-building for years-scale autonomous "set & forget") complete at 80-95%.

**Delivered** (E1–E5 + D6/C6 bases; strong evidence on allowed targets):
- Reversible bounded compaction + O(changed) state for 50k+ creative monorepos with barrels/dyn/cond/ws/symlinks/high churn/partials/"3" (E1 prototype + B1/B2/D1/D6 Pattern 1; <15% growth / 99%+ success / 0 corruption on "3" paths; 83%+ compaction in 90-sim-day).
- Rich long-horizon obs useful after months (E2/D3/E3).
- Complete additive versioning/migration for all M4 shapes (E2/D3).
- Comprehensive years-scale agent-builder patterns (E5 Guide extending D6 4 + C6 3 with real E1/E3/C5 metrics from harness 25k-50k+/RecipeLab/externals; full 8-step/9GP/spectrum matrices; honest limitations).

**Evidence** (harness 25k-50k+ full patterns + partials/"3" + concurrent chaos, RecipeLab, designated external 50k+ proxies):
- 0 "3" corruption on 100+ partials_3.
- Bounded (~25 MB mem / 80 MB disk in 50k+ 90-sim-day).
- Sub-2 ms recoveries, actionable obs trends, high Prin (0.87–1.0).

**M5 Preparation** (explicit central handoff):
See `Findings/M4-80-95-Completion-Package-Handoff.md` for known limitations and the precise mandate: literal multi-month (toward years) uninterrupted autonomous "set & forget" on user-prepared real 5k-50k+ creative projects under the 9 Guiding Principles (full patterns + sustained concurrent MA+daemon+human; specific metrics for boundedness/recovery/obs usefulness/versioning/"3" fidelity/9GPs/95%+ usefulness + 5-10yr viability).

M4 = capability + proxy evidence on allowed (harness/RecipeLab/externals). Literal broad real-user multi-month dogfood = M5 exclusive.

**Process**: 7–8 agent swarms (E1–E8 + Gamma), visible execution, full discipline (multiple independent FRESH LAST "3" with verbatim 0-def logs, zero new deps, M5 boundary, 8-step DF + 9 GPs, rich diaries).

See central handoff, `Findings/M4-Years-Scale-Agent-Builder-Guide.md`, E7 REV1 report, E1 prototype (e1 WT), updated Milestones.

**Next**: M5 – Broad real-world dogfood on prepared 5k–50k+ projects (literal multi-month autonomous; final 95%+ + 5-10yr gate).
