"""系统通知的「快速注册」。

未打包的桌面程序默认没有 AppUserModelID（AUMID），Windows 会拒绝它的 Toast。
注册做三件事：

1. 在开始菜单程序目录创建/更新一个带 AUMID 的快捷方式；
2. 写 HKCU 的 ``AppUserModelId`` 显示名与图标（设置 → 通知里能认出来）；
3. 立刻发一条测试通知，把「注册成功但系统仍然不显示」的情况暴露给用户。

只改当前用户范围，不需要管理员权限。
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

AUMID = "RinLauncher.Desktop"
DISPLAY_NAME = "Rin Launcher"


def _shortcut_path() -> Path:
    return (Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows"
            / "Start Menu" / "Programs" / "Rin Launcher.lnk")


def _target() -> tuple[str, str]:
    """返回 (可执行文件, 参数)。源码运行时指向 pythonw + main.py。"""
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).resolve()), ""
    python = Path(sys.executable)
    windowed = python.with_name("pythonw.exe")
    exe = windowed if windowed.is_file() else python
    entry = Path(__file__).resolve().parent / "main.py"
    return str(exe), f'"{entry}"'


def _create_shortcut(target: str, arguments: str, icon: str) -> bool:
    try:
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortcut(str(_shortcut_path()))
        shortcut.TargetPath = target
        if arguments:
            shortcut.Arguments = arguments
        shortcut.WorkingDirectory = str(Path(target).resolve().parent)
        if icon:
            shortcut.IconLocation = icon
        shortcut.Description = DISPLAY_NAME
        shortcut.Save()
        return True
    except Exception:
        logger.exception("创建通知快捷方式失败")
        return False


def _set_aumid(path: Path) -> bool:
    try:
        import pythoncom
        from win32com.propsys import propsys, pscon

        pythoncom.CoInitialize()
        # READWRITE = 2；SetValue 需要真正的 PROPVARIANT，不能直接传 str。
        store = propsys.SHGetPropertyStoreFromParsingName(str(path), None, 2)
        store.SetValue(
            pscon.PKEY_AppUserModel_ID, propsys.PROPVARIANTType(AUMID))
        store.Commit()
        return True
    except Exception:
        logger.exception("写入 AUMID 失败")
        return False


def _write_registry(icon: str) -> None:
    try:
        import winreg

        key_path = rf"Software\Classes\AppUserModelId\{AUMID}"
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path, 0,
                                winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, DISPLAY_NAME)
            if icon:
                winreg.SetValueEx(key, "IconUri", 0, winreg.REG_SZ, icon)
            winreg.SetValueEx(key, "ShowInSettings", 0, winreg.REG_DWORD, 0)
    except OSError:
        logger.debug("写入 AUMID 注册表失败", exc_info=True)


def register(icon_path: str = "") -> dict[str, Any]:
    """注册并发送测试通知；返回可直接展示给用户的结果。"""
    if sys.platform != "win32":
        return {"ok": False, "message": "仅 Windows 支持系统通知"}
    target, arguments = _target()
    icon = str(icon_path or "")
    if not _create_shortcut(target, arguments, icon):
        return {"ok": False, "message": "创建开始菜单快捷方式失败"}
    link = _shortcut_path()
    if not _set_aumid(link):
        return {"ok": False, "message": "写入应用标识失败"}
    _write_registry(icon)

    from rin_launcher import toast

    sent = False
    for _ in range(3):
        sent = toast.show(DISPLAY_NAME, "系统通知已注册，这是一条测试通知。", AUMID)
        if sent:
            break
        time.sleep(0.35)
    return {
        "ok": True,
        "tested": sent,
        "shortcut": str(link),
        "message": ("系统通知已注册，测试通知已发送" if sent
                    else "系统通知已注册；如果没看到测试通知，请重启程序后再试"),
    }
