//! Process liveness and signals for the daemon and stale cache locks.
//! Unix calls `kill`. Windows uses `OpenProcess` / `TerminateProcess`.

/// `true` when `pid` is still running. A permission error counts as alive.
pub fn pid_alive(pid: i32) -> bool {
    if pid <= 0 {
        return false;
    }
    signal_process(pid, 0)
}

/// Signal `pid`. `sig == 0` is a liveness probe and does not deliver a signal.
pub fn signal_process(pid: i32, sig: i32) -> bool {
    if pid <= 0 {
        return false;
    }
    #[cfg(unix)]
    {
        unix_signal(pid, sig)
    }
    #[cfg(windows)]
    {
        windows_signal(pid, sig)
    }
    #[cfg(not(any(unix, windows)))]
    {
        let _ = (pid, sig);
        false
    }
}

#[cfg(unix)]
fn unix_signal(pid: i32, sig: i32) -> bool {
    extern "C" {
        fn kill(pid: i32, sig: i32) -> i32;
    }
    let rc = unsafe { kill(pid, sig) };
    if rc == 0 {
        return true;
    }
    if sig != 0 {
        return false;
    }
    // ESRCH (3) means the pid is gone. EPERM means it exists and we cannot signal it.
    std::io::Error::last_os_error().raw_os_error() != Some(3)
}

#[cfg(windows)]
fn windows_signal(pid: i32, sig: i32) -> bool {
    const PROCESS_QUERY_LIMITED_INFORMATION: u32 = 0x1000;
    const PROCESS_TERMINATE: u32 = 0x0001;
    const STILL_ACTIVE: u32 = 259;
    #[link(name = "kernel32")]
    extern "system" {
        fn OpenProcess(access: u32, inherit: i32, pid: u32) -> *mut core::ffi::c_void;
        fn GetExitCodeProcess(process: *mut core::ffi::c_void, code: *mut u32) -> i32;
        fn TerminateProcess(process: *mut core::ffi::c_void, code: u32) -> i32;
        fn CloseHandle(handle: *mut core::ffi::c_void) -> i32;
    }
    unsafe {
        let access = if sig == 0 { PROCESS_QUERY_LIMITED_INFORMATION } else { PROCESS_TERMINATE };
        let handle = OpenProcess(access, 0, pid as u32);
        if handle.is_null() || handle == (-1isize as *mut core::ffi::c_void) {
            return false;
        }
        let ok = if sig == 0 {
            let mut code = 0u32;
            GetExitCodeProcess(handle, &mut code) != 0 && code == STILL_ACTIVE
        } else {
            TerminateProcess(handle, 1) != 0
        };
        CloseHandle(handle);
        ok
    }
}
