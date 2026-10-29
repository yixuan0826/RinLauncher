"""Windows-only helpers for UAC elevation and "run at login" registration.

Kept separate from the action executor and the config manager because both need
to launch a process through ``ShellExecuteExW`` with the ``runas`` verb.
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
import tempfile
from collections.abc import Iterable
from pathlib import Path

from rin_launcher import powershell

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


def _restart_target() -> tuple[str, list[str], str]:
    """返回 (可执行文件, 参数, 工作目录)；打包与源码模式都适用。

    ``--recovery`` / ``--safe-mode`` / ``--diagnostic`` 都是一次的启动模式，
    不能跟着下一次重启走进去 —— 否则从恢复模式里「正常重启」永远退不出来。
    """
    args = [arg for arg in sys.argv[1:]
            if arg not in ("--recovery", "--safe-mode", "--diagnostic")]
    if getattr(sys, "frozen", False):
        exe = sys.executable
        return exe, args, str(Path(exe).resolve().parent)
    entry = str(Path(sys.argv[0]).resolve())
    return sys.executable, [entry, *args], str(Path(entry).parent)


def _spawn_restart_helper(*, elevated: bool, extra: Iterable[str] = ()) -> bool:
    """先让当前进程退出，再由一个隐藏的 PowerShell 脚本在 2 秒后拉起新进程。

    直接 ``Popen`` 会和单实例锁撞车：新进程看到旧进程还在，就会把「显示小窗」
    消息发给旧进程然后退出。延迟 2 秒能确保旧进程先释放锁。
    """
    if sys.platform != "win32":
        logger.warning("Restart is only supported on Windows")
        return False

    exe, args, cwd = _restart_target()
    args = [*args, *extra]

    def quote(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    argument_list = ""
    if args:
        argument_list = "-ArgumentList @(" + ", ".join(quote(arg) for arg in args) + ")"
    verb = "-Verb RunAs" if elevated and not is_admin() else ""
    script = "\n".join([
        "Start-Sleep -Seconds 2",
        f"Start-Process -FilePath {quote(exe)} {argument_list} {verb}".strip(),
        "Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue",
    ])
    script_path = Path(tempfile.gettempdir()) / f"rinlauncher-restart-{os.getpid()}.ps1"
    try:
        # 不用 encoding="utf-8-sig"：冻结包里没有动态收集 encodings.utf_8_sig
        # 时它会抛 LookupError（1.1.6 起更新装不上的真实原因）。
        powershell.write_script(script_path, script)
        powershell.spawn_hidden(script_path, cwd=cwd)
        return True
    except Exception:
        logger.exception("Failed to spawn the restart helper")
        return False


def restart_application(extra: Iterable[str] = ()) -> bool:
    """延迟 2 秒后以普通权限重新启动自身。"""
    return _spawn_restart_helper(elevated=False, extra=extra)


def restart_elevated_delayed(extra: Iterable[str] = ()) -> bool:
    """延迟 2 秒后以管理员权限重新启动自身（会弹 UAC）。"""
    return _spawn_restart_helper(elevated=True, extra=extra)


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
