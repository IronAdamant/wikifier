# src/project_config.rs

**Role:** Thresholds and intervals from `.wikifier/config`, with environment overrides.

`thresholds` reads `modularity_max_lines` (default `DEFAULT_MAX_LINES`, 800) and `modularity_max_fan_in` (default `DEFAULT_MAX_FAN_IN`, 12). `0` disables that alert. `WIKIFIER_MODULARITY_MAX_LINES` and `WIKIFIER_MODULARITY_MAX_FAN_IN` override the file.

`health_interval_s` is the cheap pass (`DEFAULT_HEALTH_INTERVAL_S`, 30, minimum 1). `WIKIFIER_POLL_INTERVAL` overrides it. `maps_interval_s` is the full `update-maps` repeat (`DEFAULT_MAPS_INTERVAL_S`, 600). `0` skips the repeat. `WIKIFIER_DAEMON_MAPS_INTERVAL` overrides it. A missing key uses the default, so an older config keeps working. Full-line `#` comments are ignored.

5.5.0: the config is read through `crate::worktree::state`, and a line without `=` is skipped instead of ending the scan.
