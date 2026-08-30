"""
Fylorra - Windows Auto-start helper

Keeps optional "Start with Windows" behavior in one place.
Uses HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from core.branding import APP_NAME


def _startup_command() -> str:
    """
    Returns the command string written to the Run key.
    - Frozen builds: sys.executable (the app exe)
    - Dev: `python main_qt.py`
    """
    if getattr(sys, "frozen", False):
        return f"\"{Path(sys.executable).resolve()}\""

    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "main_qt.py"
    if not script.exists():
        script = repo_root / "main.py"
    return f"\"{Path(sys.executable).resolve()}\" \"{script.resolve()}\""


def set_start_with_windows(*, enabled: bool, app_name: str = APP_NAME) -> None:
    """
    Enable/disable auto-start at login (Windows only).
    """
    if os.name != "nt":
        return

    import winreg  # pyright: ignore[reportMissingImports]

    run_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, _startup_command())
        else:
            try:
                winreg.DeleteValue(key, app_name)
            except FileNotFoundError:
                pass
