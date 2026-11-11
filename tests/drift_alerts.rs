//! Modularity alerts, changed-line ranges, and the split between the cheap
//! heartbeat and update-maps.

use std::fs;
use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};

use wikifier::api::{self, mark_green, update_maps};
use wikifier::jsonutil::Json;

fn scratch(name: &str) -> PathBuf {
    let n = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let dir = std::env::temp_dir().join(format!("wk-drift-{name}-{n}"));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(dir.join("src/pkg")).unwrap();
    fs::write(dir.join("map_paths.txt"), "src\n").unwrap();
    fs::write(dir.join("monitored_paths.txt"), "src\n").unwrap();
    dir
}

fn actions_of(value: &Json) -> &[Json] {
    value
        .get("actions")
        .and_then(|v| v.as_array())
        .unwrap_or_else(|| panic!("no actions in {value}"))
}

fn kind_for<'a>(actions: &'a [Json], file: &str, kind: &str) -> &'a Json {
    actions
        .iter()
        .find(|action| {
            action.get("action").and_then(|v| v.as_str()) == Some("review_modularity")
                && action.get("file").and_then(|v| v.as_str()) == Some(file)
                && action.get("kind").and_then(|v| v.as_str()) == Some(kind)
        })
        .unwrap_or_else(|| panic!("no {kind} alert for {file} in {actions:?}"))
}

fn int_field(value: &Json, key: &str) -> i64 {
    match value.get(key) {
        Some(Json::Int(n)) => *n,
        other => panic!("{key} = {other:?} in {value}"),
    }
}

#[test]
fn threshold_alerts_show_up_in_actions() {
    let root = scratch("alerts");
    fs::create_dir_all(root.join(".wikifier")).unwrap();
    fs::write(
        root.join(".wikifier/config"),
        "modularity_max_lines=3\nmodularity_max_fan_in=1\n",
    )
    .unwrap();
    fs::write(root.join("src/pkg/__init__.py"), "").unwrap();
    fs::write(
        root.join("src/pkg/hub.py"),
        "VALUE = 1\ndef one():\n    return VALUE\ndef two():\n    return 2\n",
    )
    .unwrap();
    for name in ["a.py", "b.py", "c.py"] {
        fs::write(root.join("src/pkg").join(name), "from . import hub\n").unwrap();
    }
    assert_eq!(
        update_maps(&root).get("success").and_then(|v| v.as_bool()),
        Some(true)
    );
    let next = api::suggest_next_actions(&root);
    let actions = actions_of(&next);
    let lines = kind_for(actions, "src/pkg/hub.py", "line_count");
    assert_eq!(int_field(lines, "value"), 5, "{lines}");
    assert_eq!(int_field(lines, "threshold"), 3, "{lines}");
    assert_eq!(int_field(lines, "priority"), 3, "{lines}");
    let fan = kind_for(actions, "src/pkg/hub.py", "fan_in");
    assert_eq!(int_field(fan, "value"), 3, "{fan}");
    assert_eq!(int_field(fan, "threshold"), 1, "{fan}");
    assert!(
        !actions.iter().any(|action| {
            action.get("action").and_then(|v| v.as_str()) == Some("review_modularity")
                && action.get("file").and_then(|v| v.as_str()) == Some("src/pkg/a.py")
        }),
        "a one-line importer is inside both limits: {actions:?}"
    );
    let bootstrap = api::session_bootstrap(&root);
    let shared = actions_of(&bootstrap);
    assert!(
        shared.iter().any(|action| {
            action.get("kind").and_then(|v| v.as_str()) == Some("fan_in")
                && action.get("file").and_then(|v| v.as_str()) == Some("src/pkg/hub.py")
        }),
        "bootstrap actions: {shared:?}"
    );
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn content_change_records_changed_line_ranges() {
    let root = scratch("lines");
    let rel = "src/pkg/edit.py";
    fs::write(
        root.join(rel),
        "def alpha():\n    return 1\n\ndef beta():\n    return 2\n",
    )
    .unwrap();
    assert_eq!(
        mark_green(&root, rel, "baseline", false)
            .get("success")
            .and_then(|v| v.as_bool()),
        Some(true)
    );
    fs::write(
        root.join(rel),
        "def alpha():\n    return 9\n\ndef beta():\n    return 2\n    return 3\n",
    )
    .unwrap();
    let checked = api::check_changes(&root);
    assert_eq!(
        checked.get("success").and_then(|v| v.as_bool()),
        Some(true),
        "{checked}"
    );
    let next = api::suggest_next_actions(&root);
    let action = actions_of(&next)
        .iter()
        .find(|action| {
            action.get("action").and_then(|v| v.as_str()) == Some("prepare_edit")
                && action.get("file").and_then(|v| v.as_str()) == Some(rel)
        })
        .unwrap_or_else(|| panic!("no prepare_edit for the yellow file: {next}"));
    let ranges = action
        .get("changed_lines")
        .and_then(|v| v.as_array())
        .unwrap_or_else(|| panic!("no changed_lines on {action}"));
    let pair = |item: &Json| (int_field(item, "start"), int_field(item, "end"));
    assert_eq!(
        ranges.iter().map(pair).collect::<Vec<_>>(),
        vec![(2, 2), (6, 6)],
        "{action}"
    );
    let health = api::health(&root);
    let entry = health
        .get("entries")
        .and_then(|v| v.as_array())
        .and_then(|rows| {
            rows.iter()
                .find(|row| row.get("file").and_then(|v| v.as_str()) == Some(rel))
        })
        .unwrap_or_else(|| panic!("health entry missing: {health}"));
    let stored = entry
        .get("changed_lines")
        .and_then(|v| v.as_array())
        .unwrap_or_else(|| panic!("health row dropped changed_lines: {entry}"));
    assert_eq!(
        stored.iter().map(pair).collect::<Vec<_>>(),
        vec![(2, 2), (6, 6)]
    );
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn short_interval_does_not_run_update_maps_every_tick() {
    let daemon_root = scratch("daemon");
    fs::write(daemon_root.join("src/pkg/a.py"), "x = 1\n").unwrap();
    fs::create_dir_all(daemon_root.join(".wikifier")).unwrap();
    fs::write(
        daemon_root.join(".wikifier/config"),
        "health_interval_s=2\nmaps_interval_s=600\n",
    )
    .unwrap();
    let mut opts = api::HeartbeatOptions::from_root(&daemon_root);
    opts.virtual_clock = true;
    opts.follow_pid = false;
    opts.periodic_ticks = 3;
    let report = api::heartbeat_ticks(&daemon_root, opts);
    assert_eq!(int_field(&report, "poll_s"), 2, "{report}");
    assert_eq!(int_field(&report, "maps_every_s"), 600, "{report}");
    assert_eq!(int_field(&report, "periodic_ticks"), 3, "{report}");
    assert_eq!(int_field(&report, "health_passes"), 4, "{report}");
    assert_eq!(int_field(&report, "map_passes"), 1, "{report}");
    let log = fs::read_to_string(daemon_root.join(".wikifier_staging/daemon.log")).unwrap();
    assert!(log.contains("check every 2s; maps every 600s"), "{log}");
    assert_eq!(log.matches("update-maps (start)").count(), 1, "{log}");
    assert_eq!(log.matches("update-maps (interval)").count(), 0, "{log}");

    let monitor_root = scratch("monitor");
    fs::write(monitor_root.join("src/pkg/a.py"), "x = 1\n").unwrap();
    let passes = api::monitor_passes(&monitor_root, 3);
    assert_eq!(int_field(&passes, "health_passes"), 3, "{passes}");
    assert_eq!(int_field(&passes, "map_passes"), 0, "{passes}");
    assert!(
        !monitor_root.join("library.md").is_file(),
        "monitor wrote a map"
    );
    assert!(
        monitor_root
            .join(".wikifier_staging/modularity.json")
            .is_file(),
        "the cheap pass did not write the shared modularity snapshot"
    );
    let _ = fs::remove_dir_all(&daemon_root);
    let _ = fs::remove_dir_all(&monitor_root);
}
