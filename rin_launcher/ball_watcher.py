"""悬浮球展开状态的全局收尾：Esc 与「点外部」。

悬浮球窗口是 ``WS_EX_NOACTIVATE`` + ``WindowDoesNotAcceptFocus``，收不到键盘
事件，也无法通过「失去焦点」判断。这里只在展开期间临时挂两个 pynput 监听：

* 键盘 Esc → 收起；
* 鼠标按下且落点不在悬浮球窗口矩形内 → 收起。

监听器在收起后立即停止，不常驻后台。
"""

from __future__ import annotations

import ctypes
import logging
import sys
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot

logger = logging.getLogger(__name__)


class BallWatcher(QObject):
    collapseRequested = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._hwnd = 0
        self._keyboard: Any = None
        self._mouse: Any = None

    @Slot(QObject)
    def attach(self, window: Any) -> None:
        try:
            self._hwnd = int(window.winId())
        except Exception:
            self._hwnd = 0

    def _rect(self) -> tuple[int, int, int, int] | None:
        if sys.platform != "win32" or not self._hwnd:
            return None
        try:
            from ctypes import wintypes

            rect = wintypes.RECT()
            if ctypes.windll.user32.GetWindowRect(self._hwnd, ctypes.byref(rect)):
                return rect.left, rect.top, rect.right, rect.bottom
        except Exception:
            logger.debug("读取悬浮球窗口矩形失败", exc_info=True)
        return None

    @Slot(bool)
    def setActive(self, active: bool) -> None:
        if active:
            self._start()
        else:
            self._stop()

    def _start(self) -> None:
        if self._keyboard is not None or self._mouse is not None:
            return
        try:
            from pynput import keyboard, mouse
        except Exception:
            logger.debug("pynput 不可用，悬浮球只能用点击收起", exc_info=True)
            return
        try:
            self._keyboard = keyboard.Listener(on_press=self._on_key)
            self._keyboard.daemon = True
            self._keyboard.start()
            self._mouse = mouse.Listener(on_click=self._on_click)
            self._mouse.daemon = True
            self._mouse.start()
        except Exception:
            logger.debug("悬浮球全局监听启动失败", exc_info=True)
            self._stop()

    def _stop(self) -> None:
        for listener in (self._keyboard, self._mouse):
            if listener is None:
                continue
            try:
                listener.stop()
            except Exception:
                logger.debug("停止悬浮球监听失败", exc_info=True)
        self._keyboard = None
        self._mouse = None

    def _on_key(self, key: Any) -> None:
        try:
            from pynput.keyboard import Key

            if key == Key.esc:
                self.collapseRequested.emit()
        except Exception:
            pass

    def _on_click(self, _x: int, _y: int, _button: Any, pressed: bool) -> None:
        if not pressed:
            return
        rect = self._rect()
        if rect is None:
            return
        left, top, right, bottom = rect
        if not (left <= _x <= right and top <= _y <= bottom):
            self.collapseRequested.emit()
