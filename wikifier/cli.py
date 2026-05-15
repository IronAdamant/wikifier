#!/usr/bin/env python3
"""
Wikifier CLI Entry Point

Detects the current platform and launches the appropriate Wikifier script.
This allows users to run `wikifier` after `pip install wikifier`.
"""

import os
import sys
import platform
import subprocess
from pathlib import Path

def get_script_path() -> Path:
    """Return the path to the correct platform-specific Wikifier script."""
    package_dir = Path(__file__).parent
    scripts_dir = package_dir / "scripts"

    system = platform.system().lower()

    if system == "windows":
        # Prefer PowerShell on Windows
        ps_script = scripts_dir / "wikifier.ps1"
        if ps_script.exists():
            return ps_script
        return scripts_dir / "wikifier.bat"
    else:
        # Linux, macOS, etc.
        return scripts_dir / "wikifier.sh"


def main():
    script_path = get_script_path()

    if not script_path.exists():
        print(f"Error: Could not find Wikifier script at {script_path}", file=sys.stderr)
        sys.exit(1)

    system = platform.system().lower()

    if system == "windows":
        # On Windows, use PowerShell to execute .ps1 or fall back to .bat
        if script_path.suffix == ".ps1":
            cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path)] + sys.argv[1:]
        else:
            cmd = [str(script_path)] + sys.argv[1:]
    else:
        # Unix-like: execute the shell script directly
        cmd = [str(script_path)] + sys.argv[1:]

    try:
        result = subprocess.run(cmd, check=False)
        sys.exit(result.returncode)
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:
        print(f"Failed to launch Wikifier: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
