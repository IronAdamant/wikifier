//! Daemon log, heartbeat, and OS service install.
//! The poll loop lives in `api`. This module only writes the side files.

use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};

use crate::jsonutil::Json;

pub fn pid_path(root: &Path) -> PathBuf {
    root.join(".wikifier_staging").join("wikifier.pid")
}

pub fn legacy_pid_path(root: &Path) -> PathBuf {
    root.join(".wikifier_staging").join("daemon.pid")
}

pub fn log_path(root: &Path) -> PathBuf {
    root.join(".wikifier_staging").join("daemon.log")
}

pub fn heartbeat_path(root: &Path) -> PathBuf {
    root.join(".wikifier_staging").join("daemon_heartbeat.json")
}

pub fn poll_seconds() -> u64 {
    std::env::var("WIKIFIER_POLL_INTERVAL")
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or(30)
        .max(1)
}

pub fn maps_interval_seconds() -> u64 {
    std::env::var("WIKIFIER_DAEMON_MAPS_INTERVAL")
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or(600)
}

pub fn maps_enabled() -> bool {
    !matches!(
        std::env::var("WIKIFIER_DAEMON_MAPS").ok().as_deref(),
        Some("0") | Some("false") | Some("no")
    )
}

pub fn append_log(root: &Path, message: &str) {
    let _ = fs::create_dir_all(root.join(".wikifier_staging"));
    let line = format!("[{}] {message}\n", stamp());
    if let Ok(mut file) = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(log_path(root))
    {
        let _ = file.write_all(line.as_bytes());
    }
}

pub fn write_heartbeat(root: &Path, event: &str, ok: bool, detail: &str) {
    let path = heartbeat_path(root);
    let previous = fs::read_to_string(&path)
        .ok()
        .and_then(|text| crate::jsonutil::parse(&text).ok());
    let prior = previous
        .as_ref()
        .and_then(|v| v.get("consecutive_failures"))
        .and_then(|v| match v {
            Json::Int(n) => Some(*n),
            _ => None,
        })
        .unwrap_or(0);
    let streak = if ok { 0 } else { prior + 1 };
    let body = Json::obj(vec![
        ("ts", Json::String(stamp())),
        ("event", Json::String(event.into())),
        ("ok", Json::Bool(ok)),
        ("detail", Json::String(detail.chars().take(400).collect())),
        ("consecutive_failures", Json::Int(streak)),
        ("project_root", Json::String(root.display().to_string())),
    ]);
    let _ = fs::create_dir_all(root.join(".wikifier_staging"));
    let _ = fs::write(path, format!("{body}\n"));
    if streak >= 5 {
        append_log(
            root,
            &format!("WARNING: {streak} consecutive daemon step failures"),
        );
    }
}

pub fn read_log_tail(root: &Path, lines: usize) -> String {
    let text = fs::read_to_string(log_path(root)).unwrap_or_default();
    let all: Vec<&str> = text.lines().collect();
    let start = all.len().saturating_sub(lines);
    all[start..].join("\n")
}

pub fn install(root: &Path, exe: &Path) -> Json {
    match std::env::consts::OS {
        "linux" => write_unit(
            service_file("systemd"),
            &systemd_unit(root, exe),
            "systemd user unit",
        ),
        "macos" => write_unit(
            service_file("launchd"),
            &launchd_plist(root, exe),
            "launchd agent",
        ),
        "windows" => install_windows(root, exe),
        other => fail(&format!(
            "no service manager for {other}; run `wikifier daemon run` in a terminal"
        )),
    }
}

pub fn uninstall(_root: &Path) -> Json {
    match std::env::consts::OS {
        "linux" => remove_unit(service_file("systemd"), "systemd user unit"),
        "macos" => remove_unit(service_file("launchd"), "launchd agent"),
        "windows" => uninstall_windows(),
        other => fail(&format!("no service manager for {other}")),
    }
}

pub fn systemd_unit(root: &Path, exe: &Path) -> String {
    let log = log_path(root);
    format!(
        "[Unit]\n\
Description=Wikifier daemon for {root}\n\
After=network.target\n\
\n\
[Service]\n\
Type=simple\n\
WorkingDirectory={root}\n\
Environment=WIKIFIER_PROJECT_ROOT={root}\n\
ExecStart=\"{exe}\" --target \"{root}\" daemon run\n\
Restart=always\n\
RestartSec=10\n\
KillSignal=SIGTERM\n\
TimeoutStopSec=45\n\
StandardOutput=append:{log}\n\
StandardError=append:{log}\n\
\n\
[Install]\n\
WantedBy=default.target\n",
        root = root.display(),
        exe = exe.display(),
        log = log.display(),
    )
}

pub fn launchd_plist(root: &Path, exe: &Path) -> String {
    let log_path = log_path(root);
    let log = log_path.display().to_string();
    format!(
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n\
<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">\n\
<plist version=\"1.0\"><dict>\n\
  <key>Label</key><string>com.wikifier.agent</string>\n\
  <key>WorkingDirectory</key><string>{root}</string>\n\
  <key>EnvironmentVariables</key><dict>\n\
    <key>WIKIFIER_PROJECT_ROOT</key><string>{root}</string>\n\
  </dict>\n\
  <key>ProgramArguments</key><array>\n\
    <string>{exe}</string><string>--target</string><string>{root}</string><string>daemon</string><string>run</string>\n\
  </array>\n\
  <key>RunAtLoad</key><true/>\n\
  <key>StandardOutPath</key><string>{log}</string>\n\
  <key>StandardErrorPath</key><string>{log}</string>\n\
</dict></plist>\n",
        root = xml_escape(&root.display().to_string()),
        exe = xml_escape(&exe.display().to_string()),
        log = xml_escape(&log.to_string()),
    )
}

fn install_windows(root: &Path, exe: &Path) -> Json {
    let task = format!(
        "\"{}\" --target \"{}\" daemon run",
        exe.display(),
        root.display()
    );
    let output = std::process::Command::new("schtasks")
        .args([
            "/Create", "/F", "/TN", "Wikifier", "/SC", "ONLOGON", "/TR", &task,
        ])
        .output();
    match output {
        Ok(out) if out.status.success() => ok("windows", "Task Scheduler task Wikifier", &task),
        Ok(out) => fail(&format!(
            "Task Scheduler rejected the task ({}). Create it with: schtasks /Create /F /TN Wikifier /SC ONLOGON /TR {}",
            String::from_utf8_lossy(&out.stderr).trim(),
            task
        )),
        Err(err) => fail(&format!("Task Scheduler is not available ({err}). Run `wikifier daemon run` in a terminal, or create a task whose action is: {task}")),
    }
}

fn uninstall_windows() -> Json {
    let output = std::process::Command::new("schtasks")
        .args(["/Delete", "/F", "/TN", "Wikifier"])
        .output();
    match output {
        Ok(out) if out.status.success() => {
            ok("windows", "removed Task Scheduler task Wikifier", "")
        }
        Ok(out) => fail(&format!(
            "could not delete the Wikifier task: {}",
            String::from_utf8_lossy(&out.stderr).trim()
        )),
        Err(err) => fail(&format!("Task Scheduler is not available ({err})")),
    }
}

fn write_unit(path: PathBuf, body: &str, kind: &str) -> Json {
    if let Some(parent) = path.parent() {
        if fs::create_dir_all(parent).is_err() {
            return fail(&format!("could not create {}", parent.display()));
        }
    }
    if fs::write(&path, body).is_err() {
        return fail(&format!("could not write {}", path.display()));
    }
    ok(
        std::env::consts::OS,
        &format!("wrote {kind}"),
        &path.display().to_string(),
    )
}

fn remove_unit(path: PathBuf, kind: &str) -> Json {
    if path.is_file() {
        if fs::remove_file(&path).is_err() {
            return fail(&format!("could not remove {}", path.display()));
        }
        ok(
            std::env::consts::OS,
            &format!("removed {kind}"),
            &path.display().to_string(),
        )
    } else {
        ok(
            std::env::consts::OS,
            &format!("no {kind} installed"),
            &path.display().to_string(),
        )
    }
}

fn service_file(kind: &str) -> PathBuf {
    let home = service_home();
    match kind {
        "launchd" => home
            .join("Library")
            .join("LaunchAgents")
            .join("com.wikifier.agent.plist"),
        _ => {
            let base = std::env::var_os("XDG_CONFIG_HOME")
                .map(PathBuf::from)
                .unwrap_or_else(|| home.join(".config"));
            base.join("systemd").join("user").join("wikifier.service")
        }
    }
}

fn service_home() -> PathBuf {
    if let Some(path) = std::env::var_os("WIKIFIER_SERVICE_HOME") {
        if !path.is_empty() {
            return PathBuf::from(path);
        }
    }
    if let Some(path) = std::env::var_os("HOME") {
        if !path.is_empty() {
            return PathBuf::from(path);
        }
    }
    if let Some(path) = std::env::var_os("USERPROFILE") {
        return PathBuf::from(path);
    }
    PathBuf::from(".")
}

fn stamp() -> String {
    crate::timeutil::local_stamp()
}

fn xml_escape(text: &str) -> String {
    text.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
}

fn ok(os: &str, message: &str, path: &str) -> Json {
    Json::obj(vec![
        ("success", Json::Bool(true)),
        ("os", Json::String(os.into())),
        ("message", Json::String(message.into())),
        ("path", Json::String(path.into())),
    ])
}

fn fail(message: &str) -> Json {
    Json::obj(vec![
        ("success", Json::Bool(false)),
        ("error", Json::String(message.into())),
        ("error_type", Json::String("DaemonError".into())),
    ])
}
