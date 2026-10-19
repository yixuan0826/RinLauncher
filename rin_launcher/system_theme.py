"""读取 Windows 系统强调色。

Windows 把强调色以 DWORD 存在注册表里，两个键的字节序还不一样：

* ``HKCU\\Software\\Microsoft\\Windows\\DWM\\AccentColor`` —— ``0xAABBGGRR``（ABGR）
* ``HKCU\\Software\\Microsoft\\Windows\\DWM\\ColorizationColor`` —— ``0xAARRGGBB``（ARGB）

任一来源缺失（精简系统、Win10 早期版本）就继续往下试；全都读不到时返回空串，
让界面自己决定回退色。取灰阶值同样返回空串 —— 那看起来更像「没设置过」。
"""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger(__name__)

DEFAULT_ACCENT = "#0078D4"

# (注册表键, 值名, 字节序)
_ACCENT_SOURCES: tuple[tuple[str, str, str], ...] = (
    (r"Software\Microsoft\Windows\DWM", "AccentColor", "abgr"),
    (r"Software\Microsoft\Windows\CurrentVersion\Explorer\Accent", "AccentColorMenu", "abgr"),
    (r"Software\Microsoft\Windows\DWM", "ColorizationColor", "argb"),
)


def decode_accent_color(value: int, order: str = "abgr") -> str:
    """把注册表里的 DWORD 拆成 ``#RRGGBB``；灰阶或非法字节序返回空串。"""
    if not isinstance(value, int) or value < 0:
        return ""
    value &= 0xFFFFFFFF

    if order == "abgr":
        red = value & 0xFF
        green = (value >> 8) & 0xFF
        blue = (value >> 16) & 0xFF
    elif order == "argb":
        red = (value >> 16) & 0xFF
        green = (value >> 8) & 0xFF
        blue = value & 0xFF
    else:
        raise ValueError(f"unknown byte order: {order}")

    if red == green == blue:
        return ""
    return f"#{red:02X}{green:02X}{blue:02X}"


def read_system_accent_color() -> str:
    """读当前用户的强调色；不是 Windows 或读不到时返回空串。"""
    if not sys.platform.startswith("win"):
        return ""
    try:
        import winreg
    except ImportError:  # pragma: no cover - 非 Windows 环境
        return ""

    for key_path, value_name, order in _ACCENT_SOURCES:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as handle:
                value, _ = winreg.QueryValueEx(handle, value_name)
        except OSError:
            continue
        color = decode_accent_color(value, order)
        if color:
            logger.debug("System accent color from %s\\%s: %s", key_path, value_name, color)
            return color
    return ""
