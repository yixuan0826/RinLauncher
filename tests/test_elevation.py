"""UAC 结构与 Nuitka 下的重启目标。"""

from __future__ import annotations

import ctypes
import subprocess
import sys
import time
from pathlib import Path

import pytest

import rin_launcher.elevation as elevation
from rin_launcher import powershell, runtime


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


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell 重启脚本只在 Windows 可用")
def test_restart_helper_launches_target_after_old_pid_exits(tmp_path):
    fake = tmp_path / "fake_app.py"
    fake.write_text(
        "import pathlib, time\n"
        "pathlib.Path('marker.txt').write_text('ok', encoding='ascii')\n"
        "time.sleep(3)\n",
        encoding="utf-8")
    dummy = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.2)"])
    log = elevation._restart_log_path(dummy.pid)
    log.unlink(missing_ok=True)
    try:
        script = elevation._restart_script(
            sys.executable, [str(fake)], str(tmp_path), dummy.pid,
            run_as=False, timeout=10)
        script_path = powershell.write_script(tmp_path / "restart.ps1", script)
        proc = powershell.spawn_hidden(script_path)
        assert proc.wait(timeout=30) == 0
    finally:
        dummy.wait(timeout=10)
    marker = tmp_path / "marker.txt"
    for _ in range(50):
        if marker.exists():
            break
        time.sleep(0.1)
    assert marker.is_file()
    assert marker.read_text(encoding="ascii").strip() == "ok"
    assert "OK" in powershell.read_text(log)


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell 重启脚本只在 Windows 可用")
def test_restart_helper_does_not_launch_when_old_pid_stays(tmp_path):
    fake = tmp_path / "fake_app.py"
    fake.write_text(
        "import pathlib\npathlib.Path('marker.txt').write_text('ok', encoding='ascii')\n",
        encoding="utf-8")
    dummy = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"])
    log = elevation._restart_log_path(dummy.pid)
    log.unlink(missing_ok=True)
    try:
        script = elevation._restart_script(
            sys.executable, [str(fake)], str(tmp_path), dummy.pid,
            run_as=False, timeout=1)
        script_path = powershell.write_script(tmp_path / "restart.ps1", script)
        proc = powershell.spawn_hidden(script_path)
        assert proc.wait(timeout=30) == 2
    finally:
        dummy.terminate()
        dummy.wait(timeout=10)
    assert not (tmp_path / "marker.txt").exists()
    assert "old-process-timeout" in powershell.read_text(log)
