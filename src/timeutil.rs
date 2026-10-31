//! Local wall time via `localtime_r` / `localtime_s`. No timezone-file parser.

use std::io::Write;

#[cfg(unix)]
pub fn local_stamp() -> String {
    #[repr(C)]
    struct Tm {
        tm_sec: i32,
        tm_min: i32,
        tm_hour: i32,
        tm_mday: i32,
        tm_mon: i32,
        tm_year: i32,
        tm_wday: i32,
        tm_yday: i32,
        tm_isdst: i32,
        tm_gmtoff: i64,
        tm_zone: *const i8,
    }
    extern "C" {
        fn time(tloc: *mut i64) -> i64;
        fn localtime_r(clock: *const i64, result: *mut Tm) -> *mut Tm;
    }
    unsafe {
        let mut t: i64 = 0;
        time(&mut t);
        let mut tm = std::mem::zeroed::<Tm>();
        if localtime_r(&t, &mut tm).is_null() {
            return "1970-01-01 00:00:00".to_string();
        }
        format!(
            "{:04}-{:02}-{:02} {:02}:{:02}:{:02}",
            tm.tm_year + 1900,
            tm.tm_mon + 1,
            tm.tm_mday,
            tm.tm_hour,
            tm.tm_min,
            tm.tm_sec
        )
    }
}

#[cfg(windows)]
pub fn local_stamp() -> String {
    // Windows is out of the ship promise. UTC is a visible fallback, not a TZif reader.
    use std::time::{SystemTime, UNIX_EPOCH};
    let secs = SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0);
    format_unix(secs)
}

#[cfg(windows)]
fn format_unix(secs: u64) -> String {
    let days = secs / 86400;
    let tod = secs % 86400;
    let mut y = 1970i32;
    let mut rem = days;
    loop {
        let diy = if is_leap(y) { 366 } else { 365 };
        if rem < diy {
            break;
        }
        rem -= diy;
        y += 1;
    }
    let mdays = [31, if is_leap(y) { 29 } else { 28 }, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    let mut m = 0;
    while m < 12 && rem >= mdays[m] {
        rem -= mdays[m];
        m += 1;
    }
    format!("{:04}-{:02}-{:02} {:02}:{:02}:{:02}", y, m + 1, rem + 1, tod / 3600, (tod % 3600) / 60, tod % 60)
}

#[cfg(windows)]
fn is_leap(y: i32) -> bool {
    y % 4 == 0 && (y % 100 != 0 || y % 400 == 0)
}

pub fn date_parts(stamp: &str) -> Option<(String, String, String)> {
    let date = stamp.split(' ').next()?;
    let mut p = date.split('-');
    Some((p.next()?.to_string(), p.next()?.to_string(), p.next()?.to_string()))
}

pub fn flush_stdout(text: &str) {
    let mut out = std::io::stdout().lock();
    let _ = out.write_all(text.as_bytes());
    if !text.ends_with('\n') {
        let _ = out.write_all(b"\n");
    }
    let _ = out.flush();
}
