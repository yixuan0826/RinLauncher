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
