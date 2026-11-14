"""读取 Windows 系统强调色。

首选 WinRT 的 ``UISettings.GetColorValue(UIColorType.Accent)`` —— 它就是
「设置 → 个性化 → 颜色」里那个强调色本身。``winrt-Windows.UI.ViewManagement``
是可选依赖：没装、COM 初始化失败或被策略禁用时静默回退注册表。

注册表里的两个键语义并不一样（实测 Win11 26340）：

* ``ColorizationColor`` —— ``0xAARRGGBB``，与 UISettings 的强调色只差舍入；
* ``AccentColor`` —— ``0xAABBGGRR``，是**浅色变体**，不是用户选的强调色；
* ``AccentColorMenu`` —— ``0xAABBGGRR``，开始菜单用色，通常与强调色一致。

因此回退顺序是 UISettings → ColorizationColor → AccentColorMenu →
AccentColor。灰阶是合法强调色（用户可能真的选了黑 / 白 / 灰），不再丢弃；
只有整值为 0（无颜色）或解码失败才返回空串。
"""

from __future__ import annotations

import logging
import sys
import time

logger = logging.getLogger(__name__)

# (注册表键, 值名, 字节序)
_ACCENT_SOURCES: tuple[tuple[str, str, str], ...] = (
    (r"Software\Microsoft\Windows\DWM", "ColorizationColor", "argb"),
    (r"Software\Microsoft\Windows\CurrentVersion\Explorer\Accent", "AccentColorMenu", "abgr"),
    (r"Software\Microsoft\Windows\DWM", "AccentColor", "abgr"),
)

# UISettings 的 COM 调用很快（首次 ~4ms，之后 <1ms），但属性被 QML 高频读取，
# 留 2 秒缓存；系统强调色变化本来也不是逐帧事件。
_CACHE_TTL = 2.0
_cache: tuple[float, str] | None = None
_ui_settings = None
_ui_settings_failed = False


def decode_accent_color(value: int, order: str = "abgr") -> str:
    """把注册表里的 DWORD 拆成 ``#RRGGBB``；非法输入返回空串。"""
    if not isinstance(value, int) or value < 0:
        return ""
    value &= 0xFFFFFFFF
    if value == 0:
        return ""

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

    # 灰阶是合法选择（黑 / 白 / 灰）；不再因为 R==G==B 就当成「没设置」。
    return f"#{red:02X}{green:02X}{blue:02X}"


def _read_ui_settings() -> str:
    """WinRT 首选来源；不可用时返回空串。"""
    global _ui_settings, _ui_settings_failed
    if _ui_settings_failed:
        return ""
    try:
        if _ui_settings is None:
            from winrt.windows.ui.viewmanagement import UISettings

            _ui_settings = UISettings()
        from winrt.windows.ui.viewmanagement import UIColorType

        color = _ui_settings.get_color_value(UIColorType.ACCENT)
    except Exception:
        # 依赖缺失 / COM 未初始化 / 系统策略禁用：只记一次，之后走注册表。
        _ui_settings_failed = True
        logger.debug("UISettings accent unavailable, falling back to registry",
                     exc_info=True)
        return ""
    if not color or (color.a == 0 and color.r == color.g == color.b == 0):
        return ""
    return f"#{color.r:02X}{color.g:02X}{color.b:02X}"


def _read_registry() -> str:
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
            logger.debug(
                "System accent color from %s\\%s = 0x%08X: %s",
                key_path, value_name, int(value) & 0xFFFFFFFF, color)
            return color
    return ""


def read_system_accent_color(force: bool = False) -> str:
    """读当前用户的强调色；不是 Windows 或读不到时返回空串。"""
    global _cache
    if not sys.platform.startswith("win"):
        return ""
    now = time.monotonic()
    if not force and _cache is not None and now - _cache[0] < _CACHE_TTL:
        return _cache[1]
    color = _read_ui_settings() or _read_registry()
    _cache = (now, color)
    return color
