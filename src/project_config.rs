//! Thresholds and intervals from `.wikifier/config`, with environment overrides.
//!
//! A missing key uses the default. `WIKIFIER_POLL_INTERVAL` and
//! `WIKIFIER_DAEMON_MAPS_INTERVAL` still win when they are set, which is the
//! behaviour those variables had before the config file grew keys.

use std::fs;
use std::path::Path;

/// Alert when a mapped file has more physical lines than this. `0` disables.
pub(crate) const DEFAULT_MAX_LINES: u64 = 800;
/// Alert when more than this many other mapped files import a file. `0` disables.
pub(crate) const DEFAULT_MAX_FAN_IN: u64 = 12;
/// Cheap health and modularity pass. A few seconds is allowed; the floor is 1.
pub(crate) const DEFAULT_HEALTH_INTERVAL_S: u64 = 30;
/// Full `update-maps` repeat. `0` skips the periodic map (the start map still runs).
pub(crate) const DEFAULT_MAPS_INTERVAL_S: u64 = 600;

pub(crate) struct Thresholds {
    pub max_lines: u64,
    pub max_fan_in: u64,
}

pub(crate) fn thresholds(root: &Path) -> Thresholds {
    Thresholds {
        max_lines: env_or_config(
            root,
            "WIKIFIER_MODULARITY_MAX_LINES",
            "modularity_max_lines",
            DEFAULT_MAX_LINES,
        ),
        max_fan_in: env_or_config(
            root,
            "WIKIFIER_MODULARITY_MAX_FAN_IN",
            "modularity_max_fan_in",
            DEFAULT_MAX_FAN_IN,
        ),
    }
}

pub(crate) fn health_interval_s(root: &Path) -> u64 {
    if env_present("WIKIFIER_POLL_INTERVAL") {
        return crate::daemon_svc::poll_seconds();
    }
    read_u64(root, "health_interval_s")
        .unwrap_or(DEFAULT_HEALTH_INTERVAL_S)
        .max(1)
}

pub(crate) fn maps_interval_s(root: &Path) -> u64 {
    if env_present("WIKIFIER_DAEMON_MAPS_INTERVAL") {
        return crate::daemon_svc::maps_interval_seconds();
    }
    read_u64(root, "maps_interval_s").unwrap_or(DEFAULT_MAPS_INTERVAL_S)
}

fn env_or_config(root: &Path, env: &str, key: &str, default: u64) -> u64 {
    if let Some(raw) = std::env::var(env).ok().map(|s| s.trim().to_string()) {
        if !raw.is_empty() {
            return raw.parse().unwrap_or(default);
        }
    }
    read_u64(root, key).unwrap_or(default)
}

fn env_present(name: &str) -> bool {
    std::env::var(name)
        .ok()
        .is_some_and(|value| !value.trim().is_empty())
}

fn read_u64(root: &Path, key: &str) -> Option<u64> {
    let text = fs::read_to_string(root.join(".wikifier/config")).ok()?;
    for line in text.lines() {
        let line = line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let (name, value) = line.split_once('=')?;
        if name.trim() == key {
            return value.trim().parse().ok();
        }
    }
    None
}
