# Milestone 2: Dependency Intelligence – Task List

**Status**: Planning Complete → Ready for Execution  
**Parent Issue**: `update-maps-v0.4-planning.md`

**Goal**: Transform `update-maps` into a genuinely useful tool for understanding code dependencies.

---

## How to Use This Document (for Agents)

- Update the **Status** column as work progresses.
- Use `record-change` when completing significant tasks.
- Group tasks logically (e.g., one language at a time).
- When a group of tasks is complete, update the parent planning issue.

---

## Task Overview

| ID     | Task Name                                              | Size   | Status          | Priority | Notes / Dependencies                  |
|--------|--------------------------------------------------------|--------|-----------------|----------|---------------------------------------|
| M2-01  | Complete planning & scope definition                   | Small  | [x] Done        | High     | This document                         |
| M2-02  | Implement Python import parser (core)                  | Medium | [x] Done        | Critical | Very solid + well polished + tested |
| M2-03  | Implement JavaScript/TypeScript parser                 | Medium | [~] In Progress | High     | Resolver modernized + full integration into update-maps (parser called, edges attempted) |
| M2-04  | Implement basic Shell script parser                    | Small  | [ ] Not Started | Medium   | Lower priority                        |
| M2-05  | Build improved Mermaid graph generator                 | Medium | [~] In Progress | High     | Reliability fixes + cross-lang maps + improved resolution strategies. 1 correct edge working |
| M2-06  | Add reverse dependency support ("who imports me?")     | Medium | [x] Done        | High     | Implemented in update-maps            |
| M2-07  | Improve `library.md` output format + structure         | Medium | [~] In Progress | Medium   | Valid Mermaid (nodes before edges), multi-lang summary, correct stats, combined table |
| M2-08  | Add optional structured/JSON output for agents         | Small  | [ ] Not Started | Medium   | Depends on M2-07                      |
| M2-09  | Testing + dogfooding on real projects                  | Medium | [~] In Progress | High     | First working integration into update-maps completed |
| M2-10  | Documentation & `skills/run.md` updates                | Small  | [ ] Not Started | Medium   | Final step                            |

---

## Grouped by Phase

### Phase 1: Foundation
- M2-01 (Done)
- M2-02 (Python parser) ← **Recommended starting point**

### Phase 2: Language Support
- M2-03 (JavaScript/TypeScript)
- M2-04 (Shell – basic)

### Phase 3: Graph & Output Improvements
- M2-05 (Mermaid graph generator)
- M2-06 (Reverse dependencies)
- M2-07 (Improved `library.md` formatting)
- M2-08 (Structured/JSON output)

### Phase 4: Validation & Documentation
- M2-09 (Testing & dogfooding)
- M2-10 (Documentation)

---

## Recommended Execution Order

1. **M2-02** – Python parser (highest value)
2. **M2-05** – Graph generator (once Python works)
3. **M2-03** – JavaScript/TypeScript parser
4. **M2-06 + M2-07** – Reverse deps + output improvements
5. **M2-08** – JSON output for agents
6. **M2-04** – Shell parser (can be done in parallel with others)
7. **M2-09 + M2-10** – Testing and documentation

---

## Definition of Success (Reminder)

- Python import detection is reliable on real codebases.
- At least one other language has meaningful support.
- The Mermaid graph shows real, useful relationships.
- Agents can use the output to meaningfully reduce context and understand project structure.

---

**Current Focus**: Executing the long-term scalable M2 closure plan (post Gap #1). See the authoritative roadmap with detailed checkboxes and architecture: `Findings/m2-full-closure-longterm-scalable-plan.md`.  

**Note**: This task list is partially historical. The full M2 scope (scale UX, health hygiene, state durability, transparency, Python library + protocol) is now defined in the long-term plan above, which prioritizes solutions that work from tiny to 50k+ creative monorepos without shortcuts.  
**Last Updated**: 2026-05-22 (Linked to full long-term M2 closure plan)

---

**Next Action**: Begin implementation with **M2-02** (Python import parser) once approved.