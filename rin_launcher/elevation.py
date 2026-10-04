"""Windows-only helpers for UAC elevation and "run at login" registration.

Kept separate from the action executor and the config manager because both need
to launch a process through ``ShellExecuteExW`` with the ``runas`` verb.
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
from collections.abc import Iterable

logger = logging.getLogger(__name__)

# SEE_MASK_NOCLOSEPROCESS | SEE_MASK_FLAG_NO_UI — we report failures ourselves
# instead of letting the shell pop its own error dialog.
_SEE_MASK = 0x00000040 | 0x00000400
_ERROR_CANCELLED = 1223
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_VALUE = "RinLauncher"


def _quote(args: Iterable[str]) -> str:
    return " ".join(f'"{arg}"' for arg in args)


def _launch_elevated(target: str, params: str = "", cwd: str = "") -> bool:
    """Run *target* with the ``runas`` verb, triggering a UAC prompt."""
    from ctypes import wintypes

    request = wintypes.SHELLEXECUTEINFOW()
    request.cbSize = ctypes.sizeof(request)
    request.fMask = _SEE_MASK
    request.lpVerb = "runas"
    request.lpFile = target
    request.lpParameters = params
    request.lpDirectory = cwd
    request.nShow = 1

    if ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(request)):
        return True

    error = ctypes.GetLastError()
    if error == _ERROR_CANCELLED:
        logger.info("User declined the UAC prompt")
    else:
        logger.error("ShellExecuteExW failed for %s (error %s)", target, error)
    return False


def is_admin() -> bool:
    """True when the current process already has administrator rights."""
    return sys.platform == "win32" and bool(ctypes.windll.shell32.IsUserAnAdmin())


def run_elevated(target: str, params: str = "", cwd: str = "") -> bool:
    """Run a program as administrator; returns False on non-Windows hosts."""
    if sys.platform != "win32":
        logger.warning("Administrator elevation is only available on Windows")
        return False
    return _launch_elevated(target, params, cwd)


def restart_elevated() -> bool:
    """Re-launch this application as administrator, replacing the current process."""
    if is_admin():
        return True
    if sys.platform != "win32":
        return False

    if getattr(sys, "frozen", False):
        target, params = sys.executable, _quote(sys.argv[1:])
    else:
        target, params = sys.executable, _quote([sys.argv[0], *sys.argv[1:]])

    if _launch_elevated(target, params):
        os._exit(0)  # the elevated copy owns the session from here on
    return False


def set_run_on_startup(enable: bool) -> bool:
    """Add/remove the app from ``HKCU\\...\\Run``. Returns whether it worked."""
    if sys.platform != "win32":
        return False

    import winreg

    command = sys.executable if getattr(sys, "frozen", False) else _quote([sys.executable, sys.argv[0]])
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enable:
                winreg.SetValueEx(key, _RUN_VALUE, 0, winreg.REG_SZ, command)
            else:
                try:
                    winreg.DeleteValue(key, _RUN_VALUE)
                except FileNotFoundError:
                    pass
    except OSError:
        logger.exception("Failed to update the run-at-login registry value")
        return False
    return True


def run_on_startup_enabled() -> bool:
    """注册表里有没有我们的开机自启动值（给三态启动方式的回查用）。"""
    if sys.platform != "win32":
        return False

    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, _RUN_VALUE)
        return True
    except OSError:
        return False
