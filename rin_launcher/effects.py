"""桌面挂件相关的系统调用。

小窗的材质已经统一交给 RinUI 的云母 / 增强云母（见 main.apply_backdrop），这里
只剩两件与材质无关的事：

* **无焦点工具窗口** —— 桌面挂件不该抢焦点，也不能进任务栏。
* **置底** —— 小窗应该被普通窗口盖住，而不是浮在上面。

非 Windows 上全部是安全的空操作。
"""

from __future__ import annotations

import ctypes
import logging
import sys
from typing import Any

logger = logging.getLogger(__name__)


def _hwnd(window: Any) -> int:
    """拿到原生窗口句柄；窗口还没建出来时返回 0。"""
    try:
        return int(window.winId())
    except Exception:  # 窗口已销毁 / 平台不支持
        return 0


def apply_no_focus_tool_window(window: Any) -> None:
    """把窗口调成「不进任务栏、不抢焦点」的桌面挂件。

    ``WS_EX_NOACTIVATE`` 是关键：鼠标点得动，但窗口不会变成前台窗口，也不会把
    用户正在打字的目标窗口挤下去。窗口的 Z 序（置底）由 QML 的
    ``WindowStaysOnBottomHint`` 声明，这里只补扩展样式。
    """
    if sys.platform != "win32":
        return
    hwnd = _hwnd(window)
    if not hwnd:
        return
    try:
        user32 = ctypes.windll.user32
        GWL_EXSTYLE = -20
        WS_EX_NOACTIVATE = 0x08000000
        WS_EX_TOOLWINDOW = 0x00000080
        style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongPtrW(
            hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
    except Exception:
        logger.debug("Failed to set no-activate window style", exc_info=True)


def apply_bottom_layer(window: Any) -> None:
    """把小窗兜底压到 Z 序最底（桌面之上、所有普通窗口之下）。

    QML 的 ``WindowStaysOnBottomHint`` 已经会做这件事，但窗口刚显示 / 主题或
    分辨率切换之后偶尔会被抬到前台，这里再补一次 ``HWND_BOTTOM``，成本是一次
    ``SetWindowPos``，不移动、不缩放、不激活。
    """
    if sys.platform != "win32":
        return
    hwnd = _hwnd(window)
    if not hwnd:
        return
    try:
        HWND_BOTTOM = 1
        SWP_NOSIZE = 0x0001
        SWP_NOMOVE = 0x0002
        SWP_NOACTIVATE = 0x0010
        ctypes.windll.user32.SetWindowPos(
            hwnd, HWND_BOTTOM, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)
    except Exception:
        logger.debug("Failed to push window to the bottom layer", exc_info=True)


def apply_win11_round_corners(window: Any) -> None:
    """给无边框窗口套上 Win11 的 8px 圆角。

    小窗是自绘卡片 + 云母背景：窗口本身没有标题栏 / 边框，DWM 不会自动圆角，
    云母就会按矩形铺满整个窗口，QML 卡片画得再圆，外面还是露着直角。
    ``DWMWA_WINDOW_CORNER_PREFERENCE``（33）设为 ``DWMWCP_ROUND``（2）后，
    窗口表面与背景材质一起被裁成圆角。Win10 没有这个属性，调用失败即忽略。
    """
    if sys.platform != "win32":
        return
    hwnd = _hwnd(window)
    if not hwnd:
        return
    try:
        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        DWMWCP_ROUND = 2
        preference = ctypes.c_int(DWMWCP_ROUND)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(preference),
            ctypes.sizeof(preference),
        )
    except Exception:
        logger.debug("Failed to apply Win11 round corners", exc_info=True)


# ──────────────────────────────────────────────────────────────────────
# 系统材质（DWM）
#
# 刻意不走 RinUI 的 ThemeManager.apply_backdrop_effect()：那边的窗口句柄列表
# 是**类级共享**的（ThemeManager.windows），调一次等于给所有窗口上同一种材质，
# 做不出「启动台亚克力、其它窗口云母」。这里直接对单个 hwnd 下 DWM 属性。
# ──────────────────────────────────────────────────────────────────────

_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWA_BORDER_COLOR = 34
_DWMWA_CAPTION_COLOR = 35
_DWMWA_SYSTEMBACKDROP_TYPE = 38
_DWMWA_MICA_EFFECT = 1029  # Win11 21H2 旧接口
_DWMWA_COLOR_NONE = 0xFFFFFFFE
_DWMWCP_ROUND = 2
# DWMWA_SYSTEMBACKDROP_TYPE 的取值：2 = Mica，3 = Acrylic，4 = Mica Alt。
_DWMSBT = {"auto": 0, "none": 1, "mica": 2, "acrylic": 3, "tabbed": 4}
_WCA_ACCENT_POLICY = 19
_ACCENT_ENABLE_ACRYLICBLURBEHIND = 4
_WIN11_BUILD = 22000
_WIN11_22H2_BUILD = 22621


class _AccentPolicy(ctypes.Structure):
    _fields_ = [
        ("AccentState", ctypes.c_int),
        ("AccentFlags", ctypes.c_int),
        ("GradientColor", ctypes.c_uint),
        ("AnimationId", ctypes.c_int),
    ]


class _WindowCompositionAttributeData(ctypes.Structure):
    _fields_ = [
        ("Attrib", ctypes.c_int),
        ("pvData", ctypes.c_void_p),
        ("cbData", ctypes.c_size_t),
    ]


def _windows_build() -> int:
    try:
        return int(sys.getwindowsversion().build)
    except Exception:  # 非 Windows / 老 Python
        return 0


def apply_backdrop(
        window: Any, effect: str = "mica", dark: bool = True,
        legacy_acrylic: bool = False) -> bool:
    """给**这一个窗口**套上系统材质，返回是否真的调到了 DWM。

    ``effect`` 取 auto / none / mica / acrylic / tabbed：

    * Win11 22H2+ 走 ``DWMWA_SYSTEMBACKDROP_TYPE``（2=Mica，3=Acrylic）；
    * Win11 21H2 只有旧接口 ``DWMWA_MICA_EFFECT``，非云母一律按云母处理；
    * Win10 走 ``SetWindowCompositionAttribute`` 的 Acrylic 模糊。

    ``legacy_acrylic=True`` 时即使 Win11 也走 AccentPolicy：系统版的
    Acrylic 只在**激活窗口**上绘制，置底、不抢焦点的桌面挂件用它永远是
    一块实色；旧接口的模糊不挑激活状态，桌面挂件用这个才透得出来。

    顺带把标题栏 / 边框颜色设成 ``DWMWA_COLOR_NONE``：Win11 会给无边框窗口
    补一条 1px 浅色边 —— 那就是用户看到的「一圈讨厌的边框」。
    """
    if sys.platform != "win32":
        return False
    hwnd = _hwnd(window)
    if not hwnd:
        return False
    try:
        dwm = ctypes.windll.dwmapi
        dark_mode = ctypes.c_int(1 if dark else 0)
        dwm.DwmSetWindowAttribute(
            hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(dark_mode), ctypes.sizeof(dark_mode))

        none_color = ctypes.c_int(_DWMWA_COLOR_NONE)
        for attribute in (_DWMWA_BORDER_COLOR, _DWMWA_CAPTION_COLOR):
            dwm.DwmSetWindowAttribute(
                hwnd, attribute,
                ctypes.byref(none_color), ctypes.sizeof(none_color))

        corner = ctypes.c_int(_DWMWCP_ROUND)
        dwm.DwmSetWindowAttribute(
            hwnd, _DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(corner), ctypes.sizeof(corner))

        build = _windows_build()
        if legacy_acrylic and effect == "acrylic":
            return _apply_win10_acrylic(hwnd, effect, dark)
        if build >= _WIN11_22H2_BUILD:
            value = ctypes.c_int(_DWMSBT.get(effect, _DWMSBT["mica"]))
            dwm.DwmSetWindowAttribute(
                hwnd, _DWMWA_SYSTEMBACKDROP_TYPE,
                ctypes.byref(value), ctypes.sizeof(value))
            return True
        if build >= _WIN11_BUILD:
            enable = ctypes.c_int(1 if effect in ("auto", "mica") else 0)
            dwm.DwmSetWindowAttribute(
                hwnd, _DWMWA_MICA_EFFECT,
                ctypes.byref(enable), ctypes.sizeof(enable))
            return True
        return _apply_win10_acrylic(hwnd, effect, dark)
    except Exception:
        logger.exception("Failed to apply backdrop %r", effect)
        return False


def _apply_win10_acrylic(hwnd: int, effect: str, dark: bool) -> bool:
    """Win10 没有 DWM 材质属性，退回 SetWindowCompositionAttribute 模糊。"""
    try:
        gradient = 0x991F1F1F if dark else 0x99F3F3F3
        accent = _AccentPolicy()
        accent.AccentState = (
            _ACCENT_ENABLE_ACRYLICBLURBEHIND
            if effect in ("acrylic", "auto") else 0)
        accent.AccentFlags = 2
        accent.GradientColor = gradient
        data = _WindowCompositionAttributeData()
        data.Attrib = _WCA_ACCENT_POLICY
        data.pvData = ctypes.cast(ctypes.pointer(accent), ctypes.c_void_p)
        data.cbData = ctypes.sizeof(accent)
        ctypes.windll.user32.SetWindowCompositionAttribute(hwnd, ctypes.byref(data))
        return True
    except Exception:
        logger.debug("Failed to apply Win10 acrylic", exc_info=True)
        return False
