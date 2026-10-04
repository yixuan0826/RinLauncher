"""全局键盘录制：给「按键模拟」的编辑器提供「开始录制键盘输入」。

语义参考 SystemTools 的「模拟键盘」（录制虚拟键码 + 延迟），录制时多做了一层
整理，把原始事件收成更好用的步骤：

* 快速点按（按下之后紧挨着就是自己的抬起）→ 一步「单击」；
* 按住期间敲了别的键（组合键的修饰键、和弦）→「按住」+ 稍后「释放」两步，
  录完即可原样回放 —— SystemTools 需要手工把 Press 改成 KeyDown / KeyUp；
* 同键连发（长按时系统自动重复）不产生步骤，只参与配对与计时。

每来一个原始事件就把完整步骤重算一遍并整表发出（列表很短，重建最省心，也省得
UI 端做增量补丁）。步骤结构与执行端一致：

    {"type": "key", "key": 名称, "vk": 虚拟键码（0 时省略）,
     "action": "click" | "press" | "release", "duration": 执行前等待（秒）}
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from PySide6.QtCore import Property, QObject, Signal

logger = logging.getLogger(__name__)

# pynput 的按键名 → 执行端认识的规范写法（执行端查找不区分大小写）。
# 映射不到的按键保留原名：显示看得懂即可，回放走录制到的虚拟键码。
_NAME_MAP = {
    "ctrl_l": "Ctrl", "ctrl_r": "Ctrl",
    "alt_l": "Alt", "alt_r": "Alt", "alt_gr": "Alt",
    "shift_l": "Shift", "shift_r": "Shift",
    "cmd_l": "Win", "cmd_r": "Win", "win": "Win",
    "enter": "Enter", "return": "Enter", "space": "Space",
    "backspace": "Backspace", "tab": "Tab", "esc": "Esc",
    "delete": "Delete", "insert": "Insert",
    "home": "Home", "end": "End",
    "page_up": "PageUp", "page_down": "PageDown",
    "up": "Up", "down": "Down", "left": "Left", "right": "Right",
    "num_lock": "NumLock", "caps_lock": "CapsLock", "scroll_lock": "ScrollLock",
    "print_screen": "PrintScreen", "pause": "Pause", "menu": "Menu",
}


def _key_identity(key: Any) -> tuple[str, int]:
    """pynput 的按键事件对象 → (名称, 虚拟键码)；认不出来也要留个名字。"""
    vk = getattr(key, "vk", None)
    char = getattr(key, "char", None)
    name = getattr(key, "name", None)
    if vk is None:
        # Key 枚举成员自己不带 vk，值（一个 KeyCode）里才有：enter → 13、ctrl_l → 162。
        vk = getattr(getattr(key, "value", None), "vk", None)
    try:
        code = int(vk or 0)
    except (TypeError, ValueError):
        code = 0
    if name:
        display = _NAME_MAP.get(name, name)
        if display.startswith("f") and display[1:].isdigit():
            display = display.upper()  # f5 → F5
        return display, code
    if char:
        if char == "\r":
            return "Enter", code
        if char == "\t":
            return "Tab", code
        if char == "\x08":
            return "Backspace", code
        if char == "\x1b":
            return "Esc", code
        return (char.upper() if len(char) == 1 and char.isalpha() else char), code
    return (f"VK{code}" if code else "?"), code


def _make_step(event: dict[str, Any], action: str) -> dict[str, Any]:
    step: dict[str, Any] = {
        "type": "key",
        "key": event["name"],
        "action": action,
        "duration": round(event["gap"], 3),
    }
    if 0 < event["vk"] < 256:
        step["vk"] = event["vk"]
    return step


def _build_steps(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把原始按键事件整理成步骤列表（纯函数，方便回归测试）。

    ``events`` 每个元素：``{"down": bool, "name": str, "vk": int, "gap": float}``，
    ``gap`` 是相对上一个原始事件的间隔（第一个为 0）。分类规则见模块 docstring。
    """
    # 先配对：每个「按下」找到自己的「抬起」；同键连发的按下不算新一次按下。
    paired: dict[int, int] = {}
    release_ups: set[int] = set()
    repeats: set[int] = set()
    open_keys: dict[str, int] = {}
    for index, event in enumerate(events):
        name = event["name"]
        if event["down"]:
            if name in open_keys:
                repeats.add(index)
            else:
                open_keys[name] = index
        else:
            down_index = open_keys.pop(name, None)
            if down_index is not None:
                paired[down_index] = index
                # 按下和抬起之间夹着别的事件（或稍后才发现一直没抬）→ 算「按住」，
                # 抬起单独记一步「释放」；紧挨着抬起的点按在下面并成「单击」。
                if index != down_index + 1:
                    release_ups.add(index)

    # 再按时间顺序生成步骤。
    steps: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        if index in repeats:
            continue
        if event["down"]:
            up_index = paired.get(index)
            steps.append(_make_step(event, "click" if up_index == index + 1 else "press"))
        elif index in release_ups:
            steps.append(_make_step(event, "release"))
    return steps


class KeyRecorder(QObject):
    """把真实键盘输入录成按键序列步骤；对应 QML 里的「开始录制键盘输入」。

    ``start()`` 之后所有物理按键（含抬起）都会整理成步骤，通过 ``stepsChanged``
    整表发给界面；``stop()`` 结束并补发一次最终结果。
    """

    stepsChanged = Signal("QVariantList")
    recordingChanged = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._listener: Any = None
        self._raw: list[dict[str, Any]] = []
        self._last_time: float | None = None
        self._lock = threading.Lock()
        try:
            from pynput import keyboard  # noqa: F401
        except Exception:
            self._available = False
            logger.warning("pynput is not available; keyboard recording disabled")
        else:
            self._available = True

    # ------------------------------------------------------------------
    # QML 接口
    # ------------------------------------------------------------------
    def _get_available(self) -> bool:
        return self._available

    #: 录制功能是否可用（装没装 pynput），QML 用它决定按钮的可用性。
    available = Property(bool, _get_available, constant=True)

    def start(self) -> None:
        """开始录制；正在录制时先停掉上一轮，步骤列表从头来过。"""
        if not self._available:
            return
        if self._listener is not None:
            self.stop()
        from pynput import keyboard

        with self._lock:
            self._raw.clear()
            self._last_time = None
        try:
            listener = keyboard.Listener(
                on_press=self._on_press, on_release=self._on_release)
            listener.start()
        except Exception:
            logger.exception("Failed to start keyboard listener")
            return
        self._listener = listener
        self.stepsChanged.emit([])
        self.recordingChanged.emit(True)

    def stop(self) -> None:
        """结束录制；最后把完整结果再发一次。"""
        listener, self._listener = self._listener, None
        if listener is None:
            return
        try:
            listener.stop()
            listener.join(timeout=1.0)
        except Exception:
            logger.exception("Failed to stop keyboard listener")
        self.stepsChanged.emit(self._build())
        self.recordingChanged.emit(False)

    # ------------------------------------------------------------------
    # 事件整理
    # ------------------------------------------------------------------
    def _on_press(self, key: Any) -> None:
        self._record(True, key)

    def _on_release(self, key: Any) -> None:
        self._record(False, key)

    def _record(self, down: bool, key: Any) -> None:
        """收到一个原始事件：记时间差、重算步骤、整表发出。"""
        name, vk = _key_identity(key)
        now = time.monotonic()
        with self._lock:
            gap = 0.0 if self._last_time is None else max(0.0, now - self._last_time)
            self._last_time = now
            self._raw.append({"down": down, "name": name, "vk": vk, "gap": gap})
            steps = _build_steps(list(self._raw))
        self.stepsChanged.emit(steps)

    def _build(self) -> list[dict[str, Any]]:
        with self._lock:
            return _build_steps(list(self._raw))
