"""运行期路径：Nuitka 默认把 sys.executable 指到 <安装目录>\\python.exe，必须归一。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from rin_launcher import runtime

ROOT = Path(__file__).resolve().parent.parent


def _frozen(monkeypatch):
    monkeypatch.setattr(runtime, "_is_compiled", lambda: True)


def test_launch_target_prefers_install_dir_exe(monkeypatch, tmp_path):
    _frozen(monkeypatch)
    canonical = tmp_path / "RinLauncher.exe"
    canonical.write_bytes(b"")
    # 旧入口可以存在，也可以已经被更新删掉；两种都要指回 RinLauncher.exe。
    stale = tmp_path / "python.exe"
    monkeypatch.setattr(sys, "executable", str(stale))
    monkeypatch.setattr(sys, "argv", [str(stale)])

    assert runtime.launch_target() == canonical.resolve()


def test_adopt_canonical_executable_rewrites_stale_launch_path(monkeypatch, tmp_path):
    _frozen(monkeypatch)
    canonical = tmp_path / "RinLauncher.exe"
    canonical.write_bytes(b"")
    stale = tmp_path / "python.exe"
    stale.write_bytes(b"")
    monkeypatch.setattr(sys, "executable", str(stale))
    monkeypatch.setattr(sys, "argv", [str(stale)])

    adopted = runtime.adopt_canonical_executable()

    assert adopted == (str(stale), str(canonical.resolve()))
    assert Path(sys.executable) == canonical.resolve()


def test_adopt_is_noop_when_already_canonical(monkeypatch, tmp_path):
    _frozen(monkeypatch)
    canonical = tmp_path / "RinLauncher.exe"
    canonical.write_bytes(b"")
    monkeypatch.setattr(sys, "executable", str(canonical))
    monkeypatch.setattr(sys, "argv", [str(canonical)])

    assert runtime.adopt_canonical_executable() is None
    assert Path(sys.executable) == canonical.resolve()


def test_launch_target_keeps_working_without_canonical(monkeypatch, tmp_path):
    _frozen(monkeypatch)
    current = tmp_path / "RinLauncher-renamed.exe"
    current.write_bytes(b"")
    monkeypatch.setattr(sys, "executable", str(current))
    monkeypatch.setattr(sys, "argv", [str(current)])

    assert runtime.launch_target() == current.resolve()


def test_launch_target_source_mode_returns_sys_executable(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime, "_is_compiled", lambda: False)
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    python = tmp_path / "python.exe"
    monkeypatch.setattr(sys, "executable", str(python))

    assert runtime.launch_target() == python


def test_describe_reports_paths(monkeypatch, tmp_path):
    _frozen(monkeypatch)
    canonical = tmp_path / "RinLauncher.exe"
    canonical.write_bytes(b"")
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python.exe"))
    monkeypatch.setattr(sys, "argv", ["RinLauncher.exe"])

    info = runtime.describe()

    assert info["frozen"] == "True"
    assert info["rawExecutable"]
    assert Path(info["launchTarget"]) == canonical.resolve()
    assert Path(info["appDir"]) == tmp_path.resolve()


@pytest.mark.skipif(sys.platform != "win32", reason="GetModuleFileNameW 仅 Windows")
def test_process_image_is_a_real_file():
    image = runtime.process_image()
    assert image is not None
    assert image.is_file()


def test_runtime_info_cli_writes_json(tmp_path):
    output = tmp_path / "runtime-info.json"
    result = subprocess.run(
        [sys.executable, "-m", "rin_launcher.main",
         f"--runtime-info={output}"],
        cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    info = json.loads(output.read_text(encoding="utf-8"))
    assert info["frozen"] == "False"
    assert info["rawExecutable"]
    assert info["launchTarget"]


def test_runtime_info_contains_startup_paths(qapp, tmp_path):
    from rin_launcher.config_manager import ConfigManager

    manager = ConfigManager(config_dir=tmp_path)
    info = manager.getRuntimeInfo()

    assert info["executable"]
    assert info["startupMode"] == "off"
    assert "Exe:" in info["diagnostics"]
    assert "Startup:" in info["diagnostics"]


def test_notification_target_uses_canonical_exe(monkeypatch, tmp_path):
    from rin_launcher import notification_registration

    exe = tmp_path / "RinLauncher.exe"
    exe.write_bytes(b"")
    monkeypatch.setattr(
        notification_registration.runtime, "is_frozen", lambda: True)
    monkeypatch.setattr(
        notification_registration.runtime, "launch_target", lambda: exe)

    assert notification_registration._target() == (str(exe), "")
