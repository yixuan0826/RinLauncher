"""UAC 结构与 Nuitka 下的重启目标。"""

from __future__ import annotations

import ctypes
from pathlib import Path

import rin_launcher.elevation as elevation
from rin_launcher import runtime


def test_shell_execute_info_struct_exists():
    # Python 3.14 的 ctypes.wintypes 不再导出 SHELLEXECUTEINFOW；这个结构必须
    # 由我们自己定义，否则提权 / 管理员自启动会在运行期 AttributeError。
    request = elevation._SHELLEXECUTEINFOW()
    request.cbSize = ctypes.sizeof(request)
    request.lpVerb = "runas"
    request.lpFile = "notepad.exe"
    assert request.cbSize >= 100
    assert request.lpVerb == "runas"


def test_restart_target_uses_exe_when_compiled(monkeypatch, tmp_path):
    exe = tmp_path / "RinLauncher.exe"
    exe.write_bytes(b"")
    monkeypatch.setattr(runtime, "_is_compiled", lambda: True)
    monkeypatch.setattr(elevation.sys, "executable", str(exe), raising=False)
    monkeypatch.setattr(elevation.sys, "argv", ["RinLauncher.exe"], raising=False)

    target, args, cwd = elevation._restart_target()

    assert Path(target) == exe
    assert args == []
    assert Path(cwd) == tmp_path


def test_restart_target_uses_module_entry_when_source(monkeypatch, tmp_path):
    """源码模式不能把 argv[0] 当脚本路径：README 推荐 ``python -m``。"""
    monkeypatch.setattr(runtime, "_is_compiled", lambda: False)
    monkeypatch.setattr(runtime, "bundle_root", lambda: tmp_path)
    monkeypatch.setattr(elevation.sys, "executable", "python.exe", raising=False)
    monkeypatch.setattr(
        elevation.sys, "argv",
        [str(tmp_path / "rin_launcher" / "main.py"), "--recovery", "--keep"], raising=False)

    target, args, cwd = elevation._restart_target()

    assert target == "python.exe"
    # 一次性的恢复模式参数不能跟着下一次重启走。
    assert args == ["-m", "rin_launcher.main", "--keep"]
    assert Path(cwd) == tmp_path


def test_restart_helper_waits_for_old_process(monkeypatch):
    """固定 sleep 会和慢退出撞上单实例锁；脚本必须等旧 PID 消失。"""
    captured = {}

    def fake_write(path, text):
        captured["script"] = text
        return path

    monkeypatch.setattr(elevation.sys, "platform", "win32", raising=False)
    monkeypatch.setattr(elevation, "is_admin", lambda: True)
    monkeypatch.setattr(elevation.os, "getpid", lambda: 4321)
    monkeypatch.setattr(
        elevation, "_restart_target",
        lambda: (r"C:\Apps\RinLauncher.exe", ["--demo"], r"C:\Apps"))
    monkeypatch.setattr(elevation.powershell, "write_script", fake_write)
    monkeypatch.setattr(elevation.powershell, "spawn_hidden", lambda *a, **k: None)

    assert elevation._spawn_restart_helper(elevated=False) is True

    script = captured["script"]
    assert "Get-Process -Id 4321" in script
    assert "Start-Sleep -Seconds 2" not in script
    assert "Start-Process -FilePath 'C:\\Apps\\RinLauncher.exe'" in script
    assert "-ArgumentList @('--demo')" in script
