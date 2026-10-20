"""开始菜单扫描：快捷方式解析、UWP AUMID 与 WSL 发行版。"""

from __future__ import annotations

import sys

import pytest

from rin_launcher import start_menu

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


def test_parse_shortcut_reads_target_and_arguments(tmp_path):
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    shell = win32com.client.Dispatch("WScript.Shell")
    link = tmp_path / "Notepad.lnk"
    shortcut = shell.CreateShortcut(str(link))
    shortcut.TargetPath = r"C:\Windows\System32\notepad.exe"
    shortcut.Arguments = "--test"
    shortcut.WorkingDirectory = r"C:\Windows"
    shortcut.Save()

    app = start_menu.parse_shortcut(str(link))
    assert app is not None
    assert app["kind"] == "lnk"
    assert app["target"].lower().endswith("notepad.exe")
    assert app["arguments"] == "--test"
    assert app["working_dir"].lower() == r"c:\windows"


def test_uwp_entries_keep_only_aumids(monkeypatch):
    payload = (
        '[{"Name":"计算器","AppID":"Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"},'
        '{"Name":"记事本","AppID":"C:\\\\Windows\\\\notepad.exe"}]'
    )
    monkeypatch.setattr(start_menu, "_run", lambda *args, **kwargs: payload)
    apps = start_menu._list_uwp()
    assert [app["name"] for app in apps] == ["计算器"]
    assert apps[0]["kind"] == "uwp"
    assert "!" in apps[0]["target"]


def test_wsl_distros_become_cmd_entries(monkeypatch):
    monkeypatch.setattr(start_menu, "_run", lambda *args, **kwargs: "Ubuntu\nDebian\n")
    apps = start_menu._list_wsl()
    assert [app["arguments"] for app in apps] == ['-d "Ubuntu"', '-d "Debian"']
    assert all(app["target"] == "wsl.exe" for app in apps)
