# src/drift.rs

**Role:** Modularity alerts and changed-line ranges for the agent loop.

`alerts` reports mapped files whose physical line count is over `modularity_max_lines` or whose fan-in (other mapped files that import them) is over `modularity_max_fan_in`. `refresh` writes `.wikifier_staging/modularity.json`, reuses a size-and-mtime line cache, and journals a crossing once. Neither call changes health status or splits a file.

`save_baseline` and `ensure_baseline` store the LF-normalized bytes `mark-green` last accepted, under `.wikifier_staging/baselines/`. `ranges_since_baseline` diffs that snapshot against the current file. `changed_line_ranges` returns 1-based inclusive ranges in the new file. A pure deletion is the surviving line beside the gap. `whole_file_range` covers a change that has no snapshot. `lines_json` and `format_ranges` are the JSON and journal forms. `line_count` is the physical line count of one file. `snapshot_path` is the shared modularity file.

The line diff anchors on a line that is unique in both sides of a window, then splits. It is a review aid, not a linter.

5.5.0: alerts sort by `severity` (`value / threshold`), worst first. A crate root or package entry point (`lib.rs`, `main.rs`, `__init__.py`, `index.*`) gets no `fan_in` alert. `LISTED` (10) is how many alerts a reply lists without `full`. Baselines are read from `crate::worktree::baselines`, which is main's for a worktree, and `save_baseline` does nothing for a worktree.

For a worktree, a file the branch did not change is counted in main's copy with main's line cache.
