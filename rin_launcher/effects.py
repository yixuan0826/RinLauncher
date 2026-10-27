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
