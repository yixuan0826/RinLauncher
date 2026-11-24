"""Windows-only helpers for UAC elevation and "run at login" registration.

Kept separate from the action executor and the config manager because both need
to launch a process through ``ShellExecuteExW`` with the ``runas`` verb.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import os
import sys
import tempfile
from collections.abc import Iterable
from pathlib import Path

from rin_launcher import powershell, runtime
from rin_launcher.startup_command import commands_match, first_token

logger = logging.getLogger(__name__)

# SEE_MASK_NOCLOSEPROCESS | SEE_MASK_FLAG_NO_UI — we report failures ourselves
# instead of letting the shell pop its own error dialog.
_SEE_MASK = 0x00000040 | 0x00000400
_ERROR_CANCELLED = 1223
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_VALUE = "RinLauncher"


class _SHELLEXECUTEINFOW(ctypes.Structure):
    """ctypes 没有现成的 SHELLEXECUTEINFOW；Python 3.14 的 wintypes 也不导出它。"""

    _fields_ = [
        ("cbSize", ctypes.wintypes.DWORD),
        ("fMask", ctypes.wintypes.ULONG),
        ("hwnd", ctypes.wintypes.HWND),
        ("lpVerb", ctypes.wintypes.LPCWSTR),
        ("lpFile", ctypes.wintypes.LPCWSTR),
        ("lpParameters", ctypes.wintypes.LPCWSTR),
        ("lpDirectory", ctypes.wintypes.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", ctypes.wintypes.HINSTANCE),
        ("lpIDList", ctypes.c_void_p),
        ("lpClass", ctypes.wintypes.LPCWSTR),
        ("hkeyClass", ctypes.wintypes.HKEY),
        ("dwHotKey", ctypes.wintypes.DWORD),
        ("hIcon", ctypes.wintypes.HANDLE),
        ("hProcess", ctypes.wintypes.HANDLE),
    ]


def _quote(args: Iterable[str]) -> str:
    return " ".join(f'"{arg}"' for arg in args)


def _launch_elevated(target: str, params: str = "", cwd: str = "") -> bool:
    """Run *target* with the ``runas`` verb, triggering a UAC prompt."""
    request = _SHELLEXECUTEINFOW()
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


def _restart_target() -> tuple[str, list[str], str]:
    """返回 (可执行文件, 参数, 工作目录)；打包与源码模式都适用。

    ``--recovery`` / ``--safe-mode`` / ``--diagnostic`` 都是一次的启动模式，
    不能跟着下一次重启走进去 —— 否则从恢复模式里「正常重启」永远退不出来。
    """
    args = [arg for arg in sys.argv[1:]
            if arg not in ("--recovery", "--safe-mode", "--diagnostic")]
    if runtime.is_frozen():
        exe = runtime.launch_target()
        return str(exe), args, str(exe.parent)
    # 源码模式不能拿 sys.argv[0] 当重启目标：README 推荐 ``python -m
    # rin_launcher.main``，此时 argv[0] 是包里的 ``.../rin_launcher/main.py``，
    # 直接按路径启动会走错 bootstrap（相对导入 / 资源根都不对）。统一用
    # 模块入口，工作目录取可导入包的根（源码模式即仓库根）。
    root = runtime.bundle_root()
    return sys.executable, ["-m", "rin_launcher.main", *args], str(root)


def _restart_log_path(pid: int | None = None) -> Path:
    """重启辅助脚本的日志：诊断「关掉后再也没起来」时先看这里。"""
    return Path(tempfile.gettempdir()) / f"rinlauncher-restart-{pid or os.getpid()}.log"


def _restart_script(exe: str, args: list[str], cwd: str, pid: int,
                    run_as: bool, timeout: int = 60) -> str:
    """生成「等旧进程退出 → 拉起新进程」的 PowerShell 脚本。

    关键点：
    * 等旧 PID 真正消失，而不是固定睡几秒；
    * 超时不再硬拉起新实例 —— 旧实例还攥着单实例锁时，新实例只会把 show
      发给旧进程然后自杀，表现就是「重启后程序没了」；
    * 拉起后观察 1.5 秒，子进程提前退出就重试，覆盖退出瞬间的锁竞争；
    * 全过程写日志，失败时可以定位是哪一步。
    """
    def quote(value: str) -> str:
        return "'" + str(value).replace("'", "''") + "'"

    log_path = _restart_log_path(pid)
    argument = ""
    if args:
        argument = "-ArgumentList @(" + ", ".join(quote(arg) for arg in args) + ") "
    verb = "-Verb RunAs " if run_as else ""
    return "\n".join([
        "$ErrorActionPreference = 'Continue'",
        f"$log = {quote(str(log_path))}",
        "function Write-Log([string]$Text) {",
        "  try { Add-Content -LiteralPath $log -Value ((Get-Date -Format 'HH:mm:ss.fff') + ' ' + $Text) -Encoding UTF8 } catch { }",
        "}",
        f"Write-Log 'helper-start old-pid={pid}'",
        f"$deadline = (Get-Date).AddSeconds({int(timeout)})",
        f"while ((Get-Process -Id {pid} -ErrorAction SilentlyContinue) "
        "-and ((Get-Date) -lt $deadline)) { Start-Sleep -Milliseconds 200 }",
        f"if (Get-Process -Id {pid} -ErrorAction SilentlyContinue) {{",
        "  Write-Log 'old-process-timeout'",
        "  exit 2",
        "}",
        "Start-Sleep -Milliseconds 700",
        "$started = $false",
        "for ($i = 1; $i -le 5; $i++) {",
        "  try {",
        f"    $process = Start-Process -FilePath {quote(exe)} {argument}{verb}"
        f"-WorkingDirectory {quote(cwd)} -PassThru -ErrorAction Stop",
        "    Start-Sleep -Milliseconds 1500",
        "    if (-not $process.HasExited) {",
        "      Write-Log ('started pid=' + $process.Id)",
        "      $started = $true",
        "      break",
        "    }",
        "    Write-Log ('child-exited code=' + $process.ExitCode + ' attempt=' + $i)",
        "  } catch {",
        "    Write-Log ('start-failed attempt=' + $i + ': ' + $_.Exception.Message)",
        "  }",
        "  Start-Sleep -Milliseconds 1000",
        "}",
        "if (-not $started) {",
        "  Write-Log 'FAILED'",
        "  exit 1",
        "}",
        "Write-Log 'OK'",
        "Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue",
    ])


def _spawn_restart_helper(*, elevated: bool, extra: Iterable[str] = ()) -> bool:
    """先让当前进程退出，再由一个隐藏的 PowerShell 脚本拉起新进程。

    直接 ``Popen`` 会和单实例锁撞车：新进程看到旧进程还在，就会把「显示小窗」
    消息发给旧进程然后退出。脚本会等旧 PID 消失，并在新进程提前退出时重试。
    """
    if sys.platform != "win32":
        logger.warning("Restart is only supported on Windows")
        return False

    exe, args, cwd = _restart_target()
    args = [*args, *extra]
    run_as = elevated and not is_admin()
    script = _restart_script(exe, args, cwd, os.getpid(), run_as)
    script_path = Path(tempfile.gettempdir()) / f"rinlauncher-restart-{os.getpid()}.ps1"
    try:
        # 不用 encoding="utf-8-sig"：冻结包里没有动态收集 encodings.utf_8_sig
        # 时它会抛 LookupError（1.1.6 起更新装不上的真实原因）。
        powershell.write_script(script_path, script)
        powershell.spawn_hidden(script_path, cwd=cwd)
        logger.info("Restart helper started: script=%s log=%s",
                    script_path, _restart_log_path())
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


def _startup_command() -> str:
    """默认的登录启动命令；调用方可以传入更准确的命令（源码模式启动器）。"""
    # 冻结包的 exe 路径可能含空格（Program Files / 中文目录）：Run 值里必须
    # 带引号，否则 Windows 会把路径截成第一个空格。
    if runtime.is_frozen():
        return f'"{runtime.launch_target()}"'
    return _quote([sys.executable, sys.argv[0]])


def set_run_on_startup(enable: bool, command: str | None = None) -> bool:
    """Add/remove the app from ``HKCU\\...\\Run``. Returns whether it worked.

    ``command`` 让调用方指定真正可用的启动命令（源码模式需要一个带工作目录
    语义的启动器；直接写 ``python main.py`` 会走错 bootstrap）。
    """
    if sys.platform != "win32":
        return False

    import winreg

    value = (command or _startup_command()).strip()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enable:
                winreg.SetValueEx(key, _RUN_VALUE, 0, winreg.REG_SZ, value)
            else:
                try:
                    winreg.DeleteValue(key, _RUN_VALUE)
                except FileNotFoundError:
                    pass
    except OSError:
        logger.exception("Failed to update the run-at-login registry value")
        return False
    return True


def run_on_startup_command() -> str:
    """注册表里那条自启动命令；不存在或读不到时返回空串。"""
    if sys.platform != "win32":
        return ""

    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, _RUN_VALUE)
    except OSError:
        return ""
    return str(value or "")


def run_on_startup_enabled() -> bool:
    """注册表里有没有我们的开机自启动值（给三态启动方式的回查用）。"""
    return bool(run_on_startup_command())


def run_on_startup_current(command: str | None = None) -> bool:
    """注册表值是否指向当前程序；旧路径 / 已删除的 exe 都算失效。"""
    value = run_on_startup_command()
    if not value:
        return False
    expected = command or _startup_command()
    if not commands_match(value, expected):
        return False
    target = first_token(value)
    return bool(target) and Path(target).is_file()
