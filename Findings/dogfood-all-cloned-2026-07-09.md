# Dogfood — all cloned_sample_projects (Wikifier 4.5.5)

**Date:** 2026-07-09 06:27
**Root:** `/Users/aron/Documents/coding_projects/cloned_sample_projects`
**Machine JSON:** `Findings/dogfood-all-cloned-2026-07-09.json`

Note: first pass used wrong API kwarg (`project_root` vs `root`); this report is the corrected pass.

## Results

| Project | OK | Scope | Parseable | Parsed | Edges | Langs | Health G/Y/R | Pending | Issues | Time |
|---------|----|-------|-----------|--------|-------|-------|--------------|---------|--------|------|
| airflow | ✅ | `airflow-core/src max=100` | 1444 | 0 | 0 | — | 0/62/0 | 112 | — | 7.35s |
| Babylon.js | ✅ | `packages/dev/core/src max=100` | 1644 | 0 | 0 | — | 0/48/0 | 0 | — | 12.58s |
| dotnet-dotnet | ✅ | `src max=80 force` | 104289 | 80 | 292 | .cs:79, .py:1 | 0/138/0 | 325 | — | 66.56s |
| linux | ✅ | `init max=50 force` | 13 | 13 | 239 | .c:11, .h:2 | 0/179/0 | 400 | — | 7.21s |
| llama_index | ✅ | `full-tree max=200` | 3837 | 0 | 0 | — | 0/0/0 | 0 | — | 2.67s |
| llvm-project | ✅ | `llvm/lib/Support max=100 force` | 192 | 100 | 541 | .cpp:89, .c:8, .h:3 | 0/617/0 | 524 | — | 31.61s |
| redox | ✅ | `full-tree force` | 31 | 31 | 175 | .rs:21, .c:5, .cpp:1, .go:1, .java:1, .js:1 | 0/31/0 | 29 | — | 0.31s |
| rust | ✅ | `library/std/src max=150 force` | 669 | 150 | 805 | .rs:150 | 0/260/0 | 719 | — | 6.94s |

## Per-project detail

### airflow
- root: `/Users/aron/Documents/coding_projects/cloned_sample_projects/airflow`
- check_changes: `{"success": true, "changes_detected": 0, "ghosts_marked": 0, "message": "Python-primary check_changes complete: 0 files marked/updated. Health + pending + journal touched.", "seconds": 1.15, "error": null, "project_root": "/Users/aron/Documents/coding_projects/cloned_sample_projects/airflow"}`
- update_maps: `{"success": true, "seconds": 5.79, "root": "/Users/aron/Documents/coding_projects/cloned_sample_projects/airflow", "mode": "incremental", "parseable_files": 1444, "files_to_reparse": 0, "files_parsed": 0, "files_skipped": 0, "edges_persisted": 0, "languages_parsed": {}, "health_stubs_seeded": 0, "error": null, "dirty_sample": []}`
- validate: `{"missing_count": 1714, "ghost_count": 0, "total_scanned": 1715, "sample_missing": ["airflow-core/src/airflow/METRICS.md", "airflow-core/src/airflow/__init__.py", "airflow-core/src/airflow/__main__.py", "airflow-core/src/airflow/_shared/AGENTS.md", "airflow-core/src/airflow/_shared/README.md"], "sample_ghosts": []}`
- suggest: `{"red": 0, "yellow": 62, "suggestions": ["1. Review the 62 \ud83d\udfe1 Yellow file(s) only \u2014 record-change intent, refresh wiki, mark-green. Skip green unless a dependent of a yellow/red requires it.", "2. Run `update_maps(directory=...)` only if imports/structure changed (not for wiki-only edits).", "3. On yellow/red hotspots, query dependents (get_dependents) before editing callers."], "ac`
- library: `{'exists': True, 'bytes': 207671, 'lines': 2404, 'has_mermaid': True}`

### Babylon.js
- root: `/Users/aron/Documents/coding_projects/cloned_sample_projects/Babylon.js`
- check_changes: `{"success": true, "changes_detected": 0, "ghosts_marked": 0, "message": "Python-primary check_changes complete: 0 files marked/updated. Health + pending + journal touched.", "seconds": 1.33, "error": null, "project_root": "/Users/aron/Documents/coding_projects/cloned_sample_projects/Babylon.js"}`
- update_maps: `{"success": true, "seconds": 10.67, "root": "/Users/aron/Documents/coding_projects/cloned_sample_projects/Babylon.js", "mode": "incremental", "parseable_files": 1644, "files_to_reparse": 0, "files_parsed": 0, "files_skipped": 0, "edges_persisted": 0, "languages_parsed": {}, "health_stubs_seeded": 0, "error": null, "dirty_sample": []}`
- validate: `{"missing_count": 2278, "ghost_count": 0, "total_scanned": 2282, "sample_missing": ["packages/dev/core/src/Actions/abstractActionManager.ts", "packages/dev/core/src/Actions/action.ts", "packages/dev/core/src/Actions/actionEvent.ts", "packages/dev/core/src/Actions/actionManager.ts", "packages/dev/core/src/Actions/condition.ts"], "sample_ghosts": []}`
- suggest: `{"red": 0, "yellow": 48, "suggestions": ["1. Review the 48 \ud83d\udfe1 Yellow file(s) only \u2014 record-change intent, refresh wiki, mark-green. Skip green unless a dependent of a yellow/red requires it.", "2. Run `update_maps(directory=...)` only if imports/structure changed (not for wiki-only edits).", "3. On yellow/red hotspots, query dependents (get_dependents) before editing callers."], "ac`
- library: `{'exists': True, 'bytes': 226482, 'lines': 2401, 'has_mermaid': True}`

### dotnet-dotnet
- root: `/Users/aron/Documents/coding_projects/cloned_sample_projects/dotnet-dotnet`
- check_changes: `{"success": true, "changes_detected": 26, "ghosts_marked": 0, "message": "Python-primary check_changes complete: 26 files marked/updated. Health + pending + journal touched.", "seconds": 0.44, "error": null, "project_root": "/Users/aron/Documents/coding_projects/cloned_sample_projects/dotnet-dotnet"}`
- update_maps: `{"success": true, "seconds": 66.07, "root": "/Users/aron/Documents/coding_projects/cloned_sample_projects/dotnet-dotnet", "mode": "full", "parseable_files": 104289, "files_to_reparse": 104289, "files_parsed": 80, "files_skipped": 104209, "edges_persisted": 292, "languages_parsed": {".py": 1, ".cs": 79}, "health_stubs_seeded": 80, "error": null, "dirty_sample": ["/Users/aron/Documents/coding_projects/cloned_sample_projects/dotnet-dotnet/src/arcade/eng/common/cross/install-debs.py", "/Users/aron/Documents/coding_projects/cloned_sample_projects/dotnet-dotnet/src/arcade/src/Common/Internal/BuildTask.cs", "/Users/aron/Documents/coding_projects/cloned_sample_projects/dotnet-dotnet/src/arcade/src/Common/Internal/DisposeAction.cs"]}`
- validate: `{"missing_count": 16, "ghost_count": 0, "total_scanned": 42, "sample_missing": ["test/Microsoft.DotNet.SourceBuild.Tests/Microsoft.DotNet.SourceBuild.Tests.csproj", "test/Microsoft.DotNet.SourceBuild.Tests/README.md", "test/Microsoft.DotNet.SourceBuild.Tests/assets/ArtifactsSizeTests/ZeroSizeExclusions.txt", "test/Microsoft.DotNet.SourceBuild.Tests/assets/LicenseScanTests/LicenseExclusions.txt", "`
- suggest: `{"red": 0, "yellow": 138, "suggestions": ["1. Review the 138 \ud83d\udfe1 Yellow file(s) only \u2014 record-change intent, refresh wiki, mark-green. Skip green unless a dependent of a yellow/red requires it.", "2. Run `update_maps(directory=...)` only if imports/structure changed (not for wiki-only edits).", "3. On yellow/red hotspots, query dependents (get_dependents) before editing callers."], "`
- library: `{'exists': True, 'bytes': 214476, 'lines': 2401, 'has_mermaid': True}`

### linux
- root: `/Users/aron/Documents/coding_projects/cloned_sample_projects/linux`
- check_changes: `{"success": true, "changes_detected": 0, "ghosts_marked": 0, "message": "Python-primary check_changes complete: 0 files marked/updated. Health + pending + journal touched.", "seconds": 0.05, "error": null, "project_root": "/Users/aron/Documents/coding_projects/cloned_sample_projects/linux"}`
- update_maps: `{"success": true, "seconds": 7.11, "root": "/Users/aron/Documents/coding_projects/cloned_sample_projects/linux", "mode": "full", "parseable_files": 13, "files_to_reparse": 13, "files_parsed": 13, "files_skipped": 0, "edges_persisted": 239, "languages_parsed": {".c": 11, ".h": 2}, "health_stubs_seeded": 13, "error": null, "dirty_sample": ["/Users/aron/Documents/coding_projects/cloned_sample_projects/linux/init/calibrate.c", "/Users/aron/Documents/coding_projects/cloned_sample_projects/linux/init/do_mounts.c", "/Users/aron/Documents/coding_projects/cloned_sample_projects/linux/init/do_mounts.h"]}`
- validate: `{"missing_count": 4, "ghost_count": 0, "total_scanned": 17, "sample_missing": ["init/.gitignore", "init/.kunitconfig", "init/Kconfig", "init/Makefile"], "sample_ghosts": []}`
- suggest: `{"red": 0, "yellow": 179, "suggestions": ["1. Review the 179 \ud83d\udfe1 Yellow file(s) only \u2014 record-change intent, refresh wiki, mark-green. Skip green unless a dependent of a yellow/red requires it.", "2. Run `update_maps(directory=...)` only if imports/structure changed (not for wiki-only edits).", "3. On yellow/red hotspots, query dependents (get_dependents) before editing callers."], "`
- library: `{'exists': True, 'bytes': 111711, 'lines': 2008, 'has_mermaid': True}`

### llama_index
- root: `/Users/aron/Documents/coding_projects/cloned_sample_projects/llama_index`
- check_changes: `{"success": true, "changes_detected": 0, "ghosts_marked": 0, "message": "Python-primary check_changes complete: 0 files marked/updated. Health + pending + journal touched.", "seconds": 0.38, "error": null, "project_root": "/Users/aron/Documents/coding_projects/cloned_sample_projects/llama_index"}`
- update_maps: `{"success": true, "seconds": 2.18, "root": "/Users/aron/Documents/coding_projects/cloned_sample_projects/llama_index", "mode": "incremental", "parseable_files": 3837, "files_to_reparse": 0, "files_parsed": 0, "files_skipped": 0, "edges_persisted": 0, "languages_parsed": {}, "health_stubs_seeded": 0, "error": null, "dirty_sample": []}`
- validate: `{"missing_count": 756, "ghost_count": 0, "total_scanned": 756, "sample_missing": ["llama-index-core/.gitignore", "llama-index-core/.wikifier/config", "llama-index-core/LICENSE", "llama-index-core/Makefile", "llama-index-core/README.md"], "sample_ghosts": []}`
- suggest: `{"red": 0, "yellow": 0, "suggestions": ["1. Health is clean (no red/yellow). Do not re-summarize the tree; use the map for lookup only.", "2. Run `update_maps(directory=...)` only if imports/structure changed (not for wiki-only edits).", "3. On yellow/red hotspots, query dependents (get_dependents) before editing callers."], "acs_note": " ACS actionable_low=7 (raw_low=7, external_noise=0, avg=0.86`
- library: `{'exists': True, 'bytes': 193097, 'lines': 2381, 'has_mermaid': True}`

### llvm-project
- root: `/Users/aron/Documents/coding_projects/cloned_sample_projects/llvm-project`
- check_changes: `{"success": true, "changes_detected": 324, "ghosts_marked": 0, "message": "Python-primary check_changes complete: 324 files marked/updated. Health + pending + journal touched.", "seconds": 14.72, "error": null, "project_root": "/Users/aron/Documents/coding_projects/cloned_sample_projects/llvm-project"}`
- update_maps: `{"success": true, "seconds": 16.71, "root": "/Users/aron/Documents/coding_projects/cloned_sample_projects/llvm-project", "mode": "full", "parseable_files": 192, "files_to_reparse": 192, "files_parsed": 100, "files_skipped": 92, "edges_persisted": 541, "languages_parsed": {".cpp": 89, ".c": 8, ".h": 3}, "health_stubs_seeded": 100, "error": null, "dirty_sample": ["/Users/aron/Documents/coding_projects/cloned_sample_projects/llvm-project/llvm/lib/Support/AArch64AttributeParser.cpp", "/Users/aron/Documents/coding_projects/cloned_sample_projects/llvm-project/llvm/lib/Support/AArch64BuildAttributes.cpp", "/Users/aron/Documents/coding_projects/cloned_sample_projects/llvm-project/llvm/lib/Support/ABIBreak.cpp"]}`
- validate: `{"missing_count": 55, "ghost_count": 0, "total_scanned": 472, "sample_missing": ["llvm/include/llvm/Support/CMakeLists.txt", "llvm/include/llvm/Support/FileSystem/UniqueID.h", "llvm/include/llvm/Support/LICENSE.TXT", "llvm/include/llvm/Support/LSP/Logging.h", "llvm/include/llvm/Support/LSP/Protocol.h"], "sample_ghosts": []}`
- suggest: `{"red": 0, "yellow": 617, "suggestions": ["1. Review the 617 \ud83d\udfe1 Yellow file(s) only \u2014 record-change intent, refresh wiki, mark-green. Skip green unless a dependent of a yellow/red requires it.", "2. Run `update_maps(directory=...)` only if imports/structure changed (not for wiki-only edits).", "3. On yellow/red hotspots, query dependents (get_dependents) before editing callers."], "`
- library: `{'exists': True, 'bytes': 146147, 'lines': 2417, 'has_mermaid': True}`

### redox
- root: `/Users/aron/Documents/coding_projects/cloned_sample_projects/redox`
- check_changes: `{"success": true, "changes_detected": 1, "ghosts_marked": 0, "message": "Python-primary check_changes complete: 1 files marked/updated. Health + pending + journal touched.", "seconds": 0.01, "error": null, "project_root": "/Users/aron/Documents/coding_projects/cloned_sample_projects/redox"}`
- update_maps: `{"success": true, "seconds": 0.29, "root": "/Users/aron/Documents/coding_projects/cloned_sample_projects/redox", "mode": "full", "parseable_files": 31, "files_to_reparse": 31, "files_parsed": 31, "files_skipped": 0, "edges_persisted": 175, "languages_parsed": {".c": 5, ".cpp": 1, ".go": 1, ".java": 1, ".js": 1, ".py": 1, ".rs": 21}, "health_stubs_seeded": 2, "error": null, "dirty_sample": ["/Users/aron/Documents/coding_projects/cloned_sample_projects/redox/recipes/demos/cairo-demo/cairo-demo.c", "/Users/aron/Documents/coding_projects/cloned_sample_projects/redox/recipes/demos/gears/gears.c", "/Users/aron/Documents/coding_projects/cloned_sample_projects/redox/recipes/demos/osdemo/osdemo.c"]}`
- validate: `{"missing_count": 4, "ghost_count": 0, "total_scanned": 31, "sample_missing": ["recipes/tests/hello-redox/files/test.lua", "recipes/tests/hello-redox/files/test.zig", "src/web/files.html", "src/web/style.css"], "sample_ghosts": []}`
- suggest: `{"red": 0, "yellow": 31, "suggestions": ["1. Review the 31 \ud83d\udfe1 Yellow file(s) only \u2014 record-change intent, refresh wiki, mark-green. Skip green unless a dependent of a yellow/red requires it.", "2. Run `update_maps(directory=...)` only if imports/structure changed (not for wiki-only edits).", "3. On yellow/red hotspots, query dependents (get_dependents) before editing callers."], "ac`
- library: `{'exists': True, 'bytes': 37979, 'lines': 587, 'has_mermaid': True}`

### rust
- root: `/Users/aron/Documents/coding_projects/cloned_sample_projects/rust`
- check_changes: `{"success": true, "changes_detected": 519, "ghosts_marked": 0, "message": "Python-primary check_changes complete: 519 files marked/updated. Health + pending + journal touched.", "seconds": 1.34, "error": null, "project_root": "/Users/aron/Documents/coding_projects/cloned_sample_projects/rust"}`
- update_maps: `{"success": true, "seconds": 5.53, "root": "/Users/aron/Documents/coding_projects/cloned_sample_projects/rust", "mode": "full", "parseable_files": 669, "files_to_reparse": 669, "files_parsed": 150, "files_skipped": 519, "edges_persisted": 805, "languages_parsed": {".rs": 150}, "health_stubs_seeded": 150, "error": null, "dirty_sample": ["/Users/aron/Documents/coding_projects/cloned_sample_projects/rust/library/std/src/alloc.rs", "/Users/aron/Documents/coding_projects/cloned_sample_projects/rust/library/std/src/ascii.rs", "/Users/aron/Documents/coding_projects/cloned_sample_projects/rust/library/std/src/backtrace.rs"]}`
- validate: `{"missing_count": 588, "ghost_count": 0, "total_scanned": 672, "sample_missing": ["library/std/src/collections/hash/map.rs", "library/std/src/collections/hash/map/tests.rs", "library/std/src/collections/hash/mod.rs", "library/std/src/collections/hash/set.rs", "library/std/src/collections/hash/set/tests.rs"], "sample_ghosts": []}`
- suggest: `{"red": 0, "yellow": 260, "suggestions": ["1. Review the 260 \ud83d\udfe1 Yellow file(s) only \u2014 record-change intent, refresh wiki, mark-green. Skip green unless a dependent of a yellow/red requires it.", "2. Run `update_maps(directory=...)` only if imports/structure changed (not for wiki-only edits).", "3. On yellow/red hotspots, query dependents (get_dependents) before editing callers."], "`
- library: `{'exists': True, 'bytes': 137708, 'lines': 1904, 'has_mermaid': True}`

## Coverage

Top-level project dirs scanned: **airflow, Babylon.js, dotnet-dotnet, linux, llama_index, llvm-project, redox, rust** (8).
All dirs under base: ['Babylon.js', 'Logged_issues', 'airflow', 'dotnet-dotnet', 'journal', 'linux', 'llama_index', 'llvm-project', 'redox', 'rust']
Non-project / meta at container root: ['.wikifier_staging', 'journal', 'library.md', 'Logged_issues', 'trammel.db', 'README_WIKIFIER.md']

## Issues to worry about

### Hard failures
- **None.** All 8 projects: `check_changes` + `update_maps` `success: true`, correct `root` isolation, multi-lang edges on force runs.

### Operational / product gaps (real)

1. **`llama_index` has maps but no health matrix**  
   - `library.md` + `.wikifier_staging/import_cache.json` present  
   - **no** `file_health.json` / `file_health.md`  
   - Summary shows `0/0/0`; agents get empty `suggest_next` health signal  
   - **Fix:** run `wikifier init` / seed health stubs (or one `update-maps` path that writes health) on that tree

2. **`validate` vs map-first mismatch (large `missing_count`)**  
   - e.g. airflow `missing_count=1714`, Babylon `2278` when `monitored_paths=.`  
   - Validate expects a health entry for *every monitored file*; map-first only stubs files that were parsed  
   - Not a crash, but agents reading validate will think the wiki is “broken”

3. **Yellow + pending floods**  
   - rust pending ~719, llvm health 617 yellow, linux 179 yellow, etc.  
   - Driven by `monitored_paths=.` + check-changes mtime thrash + Initial stub seeding  
   - **4.5.5 pending counter works** (no dual empty+items); counts are honest, just noisy  
   - **Mitigation:** lean `monitored_paths.txt` (key dirs only), not `.`

4. **Warm incremental = 0 parsed** (airflow, Babylon.js, llama_index)  
   - Expected when cache is clean; `parseable_files` still healthy (1444 / 1644 / 3837)  
   - Not an error — proves incremental short-circuit

5. **Parent container pollution**  
   - `cloned_sample_projects/` itself has `.wikifier_staging`, `journal/`, `library.md`, `trammel.db`, etc.  
   - Setting `project_root` to the **parent** mixes all samples and meta — always target a **child** project dir

6. **Full-tree not exercised** on huge monorepos  
   - Scoped by design (agent-scale). Full linux/rust/dotnet tree maps still multi-minute / memory heavy if required

### Structural notes
- Large monorepos (dotnet ~104k, linux ~64k, llvm ~71k, rust ~37k src-ish files) were **scoped** with directory + max_files for agent-scale sessions.
- `monitored_paths=.` causes large check-changes / yellow growth; lean monitored lists are better for steady state.
- Parent `cloned_sample_projects` itself has wikifier artifacts — do not set project_root there.
- MCP smoke post-restart: `get_project_status(project_root=…/redox)` → 31 yellow / 29 pending (matches CLI).

## Summary

- Success: 8/8
- Wikifier version: 4.5.5

