"""开始菜单扫描：快捷方式解析、UWP AUMID 与 WSL 发行版。"""

from __future__ import annotations

import sys
from pathlib import Path

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


def test_wsa_shortcut_keeps_its_own_icon(tmp_path):
    """WSA 安卓应用是普通 .lnk：图标在 IconLocation 里，不能跟着 target 跑。"""
    import pythoncom
    import win32com.client

    icon = Path(__file__).resolve().parent.parent / "assets" / "icon.ico"
    assert icon.is_file()

    pythoncom.CoInitialize()
    shell = win32com.client.Dispatch("WScript.Shell")
    link = tmp_path / "Lawnchair.lnk"
    shortcut = shell.CreateShortcut(str(link))
    shortcut.TargetPath = (
        r"C:\Users\Public\Microsoft\WindowsApps"
        r"\MicrosoftCorporationII.WindowsSubsystemForAndroid_8wekyb3d8bbwe\WsaClient.exe"
    )
    shortcut.Arguments = "/launch wsa://app.lawnchair"
    shortcut.IconLocation = f"{icon},0"
    shortcut.Save()

    app = start_menu.parse_shortcut(str(link))
    assert app is not None
    assert app["kind"] == "wsa"
    assert app["icon"] == f"file:{icon}"
    assert app["icon_location"] == str(icon)
    assert app["arguments"].startswith("/launch wsa://")


def test_shortcut_icon_path_strips_resource_index(tmp_path):
    from rin_launcher import start_menu as menu

    icon = Path(__file__).resolve().parent.parent / "assets" / "icon.ico"

    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    shell = win32com.client.Dispatch("WScript.Shell")
    link = tmp_path / "WithIcon.lnk"
    shortcut = shell.CreateShortcut(str(link))
    shortcut.TargetPath = r"C:\Windows\System32\notepad.exe"
    shortcut.IconLocation = f"{icon},3"
    shortcut.Save()

    assert menu.shortcut_icon_path(link) == str(icon)
    assert menu.shortcut_icon_path(link.with_suffix(".txt")) == ""


def test_list_merges_every_kind_and_sorts(monkeypatch):
    from rin_launcher import start_menu as menu

    monkeypatch.setattr(menu, "_list_shortcuts", lambda: [
        {"kind": "lnk", "name": "Zeta", "target": "z.exe", "arguments": "",
         "working_dir": "", "icon": "", "source": "z.lnk"},
        {"kind": "wsa", "name": "Lawnchair", "target": "WsaClient.exe",
         "arguments": "/launch wsa://app.lawnchair", "working_dir": "",
         "icon": "file:app.ico", "icon_location": "app.ico", "source": "l.lnk"},
    ])
    monkeypatch.setattr(menu, "_list_uwp", lambda: [
        {"kind": "uwp", "name": "Alpha", "target": "Pkg!App", "arguments": "",
         "working_dir": "", "icon": "", "source": "shell:AppsFolder"},
    ])
    monkeypatch.setattr(menu, "_list_wsl", lambda: [
        {"kind": "wsl", "name": "Ubuntu (WSL)", "target": "wsl.exe",
         "arguments": '-d "Ubuntu"', "working_dir": "", "icon": "",
         "source": "wsl"},
    ])

    apps = menu.list_start_menu_apps(force=True)
    assert [app["kind"] for app in apps] == ["uwp", "wsa", "wsl", "lnk"]
    assert [app["name"] for app in apps] == ["Alpha", "Lawnchair",
                                             "Ubuntu (WSL)", "Zeta"]


def test_wsl_distros_become_cmd_entries(monkeypatch):
    monkeypatch.setattr(start_menu, "_run", lambda *args, **kwargs: "Ubuntu\nDebian\n")
    apps = start_menu._list_wsl()
    assert [app["arguments"] for app in apps] == ['-d "Ubuntu"', '-d "Debian"']
    assert all(app["target"] == "wsl.exe" for app in apps)
