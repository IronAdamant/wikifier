# tests/drift_alerts.rs

**Role:** Tests for modularity alerts, changed-line ranges, and the split between the cheap heartbeat and `update-maps`.

`threshold_alerts_show_up_in_actions` sets `modularity_max_lines` and `modularity_max_fan_in` in `.wikifier/config` and expects `review_modularity` on `src/pkg/hub.py` in both `suggest_next_actions` and `session_bootstrap`. A one-line importer stays quiet.

`content_change_records_changed_line_ranges` marks a file green, edits two hunks, and expects `changed_lines` `2-2` and `6-6` on the Yellow action and on the health entry.

`short_interval_does_not_run_update_maps_every_tick` runs `heartbeat_ticks` with `health_interval_s=2` and `maps_interval_s=600` for three virtual ticks. The map runs once, at start. `monitor_passes` runs three cheap passes and does not write `library.md`.
