"""Windows 快捷方式小箭头的全局开关。

只改当前用户的 ``HKCU\\...\\Explorer\\Shell Icons``（值名 ``29``），不需要管理员
权限，也不会碰系统级注册表。第一次关闭前会把原值备份到数据目录；重新打开时
按备份恢复，删掉值即可回到系统默认。

资源管理器只在启动时读取这个值，所以改完必须重启 ``explorer.exe`` 才看得到；
这个动作会对用户桌面造成一次闪烁，界面侧必须先确认。
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


_SHELL_ICONS = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Icons"
_VALUE_NAME = "29"
BACKUP_NAME = "shortcut-arrow-backup.json"

# 32x32、32bpp 的全透明 ICO：不依赖第三方库，也不会因为引用了系统图标资源
# 在新系统上变样。结构 = ICONDIR(6) + ICONDIRENTRY(16) + BITMAPINFOHEADER(40)
# + 1 像素 XOR(4) + AND 掩码(4)。
_BLANK_ICO = bytes([
    0, 0, 1, 0, 1, 0,
    32, 32, 0, 0, 1, 0, 32, 0,
    48, 0, 0, 0, 22, 0, 0, 0,
    40, 0, 0, 0, 32, 0, 0, 0, 64, 0, 0, 0, 1, 0, 32, 0,
    0, 0, 0, 0, 4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0,
    0, 0, 0, 0,
])


def _data_dir(fallback: Path) -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "data"
    return Path(fallback)


def _blank_icon(data_dir: Path) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    target = data_dir / "shortcut-arrow-blank.ico"
    if not target.is_file() or target.read_bytes() != _BLANK_ICO:
        target.write_bytes(_BLANK_ICO)
    return target


def _backup_path(data_dir: Path) -> Path:
    return data_dir / BACKUP_NAME


def _read_value() -> str | None:
    if sys.platform != "win32":
        return None
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _SHELL_ICONS) as key:
            value, _kind = winreg.QueryValueEx(key, _VALUE_NAME)
            return str(value)
    except OSError:
        return None


def set_hidden(hidden: bool, *, data_dir: Path) -> dict[str, Any]:
    """关闭 / 恢复快捷方式小箭头；返回 ``{"ok", "changed", "message"}``。"""
    if sys.platform != "win32":
        return {"ok": False, "changed": False, "message": "仅 Windows 支持"}
    try:
        import winreg
    except Exception:
        return {"ok": False, "changed": False, "message": "注册表模块不可用"}

    base = _data_dir(data_dir)
    backup = _backup_path(base)
    previous = _read_value()
    if hidden:
        if previous:
            return {"ok": True, "changed": False,
                    "message": "快捷方式小箭头已经是隐藏状态"}
        try:
            backup.write_text(json.dumps({"value": None}), encoding="utf-8")
        except OSError:
            logger.debug("无法写入箭头备份", exc_info=True)
        icon = _blank_icon(base)
        try:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _SHELL_ICONS,
                                    0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, str(icon))
        except OSError:
            logger.exception("写入快捷方式箭头设置失败")
            return {"ok": False, "changed": False, "message": "写入注册表失败"}
        return {"ok": True, "changed": True,
                "message": "已隐藏快捷方式小箭头，重启资源管理器后生效"}

    if not previous:
        return {"ok": True, "changed": False, "message": "快捷方式小箭头本来就是系统默认"}
    restore = None
    if backup.is_file():
        try:
            restore = json.loads(backup.read_text(encoding="utf-8")).get("value")
        except (OSError, ValueError):
            restore = None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _SHELL_ICONS,
                            0, winreg.KEY_SET_VALUE) as key:
            if restore:
                winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, str(restore))
            else:
                winreg.DeleteValue(key, _VALUE_NAME)
    except OSError:
        logger.exception("恢复快捷方式箭头设置失败")
        return {"ok": False, "changed": False, "message": "恢复注册表失败"}
    return {"ok": True, "changed": True,
            "message": "已恢复快捷方式小箭头，重启资源管理器后生效"}


def restart_explorer() -> bool:
    """重启资源管理器；失败时返回 False（不影响其它设置）。"""
    if sys.platform != "win32":
        return False
    try:
        subprocess.run(
            ["taskkill", "/f", "/im", "explorer.exe"],
            capture_output=True, timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        logger.debug("结束资源管理器失败", exc_info=True)
    try:
        subprocess.Popen(
            ["explorer.exe"], close_fds=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True
    except Exception:
        logger.exception("重新启动资源管理器失败")
        return False
