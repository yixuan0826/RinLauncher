"""输入法兼容的按键注入：可打印字符走 Unicode，组合键 / 功能键走虚拟键码。

第三方中文输入法（搜狗、QQ、百度）和微软拼音都会把前台窗口收到的字母键拿去做
拼音组词 —— 模拟按键要么变成一串汉字，要么被候选窗吃掉，目标程序什么都收不到。

``SendInput`` + ``KEYEVENTF_UNICODE`` 是绕开输入法的办法：系统直接为目标窗口生成
``WM_CHAR``，不经过 IME 的组词流程。它只对「可打印字符」成立；组合键和功能键本来
就不过输入法，继续用 pynput 的虚拟键码注入。

只在目标线程挂着东亚输入法布局（中文 / 日文 / 韩文）时才切到 Unicode 注入，
英文布局下行为与以前完全一致。

顺带一个坑：``INPUT`` 结构体在 x64 上是 40 字节（``MOUSEINPUT`` 是其中最大的成员），
只声明 ``KEYBDINPUT`` 会让 ``cbSize`` 不对，``SendInput`` 直接返回 0、什么都不发。
"""

from __future__ import annotations

import ctypes
import logging
import sys
import time

logger = logging.getLogger(__name__)

# 键盘布局的主语言 ID（HKL 的低 10 位）
_PRIMARY_CHINESE = 0x04
_PRIMARY_JAPANESE = 0x11
_PRIMARY_KOREAN = 0x12

KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
INPUT_KEYBOARD = 1

try:  # 非 Windows 上直接当空实现，导入本模块不会炸。
    if sys.platform != "win32":
        raise OSError("not windows")

    from ctypes import wintypes

    ULONG_PTR = ctypes.c_size_t

    class MOUSEINPUT(ctypes.Structure):
        """只是为了把 ``INPUT`` 的尺寸撑到系统期望的 40 字节（x64）。"""

        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD),
        ]

    class INPUTUNION(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("union",)
        _fields_ = [("type", wintypes.DWORD), ("union", INPUTUNION)]

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _user32.GetKeyboardLayoutList.argtypes = [
        ctypes.c_int, ctypes.POINTER(wintypes.HANDLE)]
    _user32.GetKeyboardLayoutList.restype = ctypes.c_int
    _user32.SendInput.argtypes = [
        wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    _user32.SendInput.restype = wintypes.UINT
except (OSError, AttributeError) as error:  # pragma: no cover - 非 Windows 环境
    _user32 = None
    INPUT = None
    KEYBDINPUT = None
    logger.debug("Unicode key injection is unavailable: %s", error)

# 布局检测每秒最多做一次；结果缓存，避免每敲一个字都枚举一遍。
_layout_checked_at = 0.0
_layout_active = False


def available() -> bool:
    """当前平台能不能做 Unicode 注入。"""
    return _user32 is not None and INPUT is not None


def _handle(value: object) -> int:
    """把 ctypes 句柄归一成 int；空句柄统一成 0。"""
    if not value:
        return 0
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def east_asian_ime_active() -> bool:
    """当前会话是否装有中日韩输入法布局。

    不再跨线程查询前台窗口的 ``GetKeyboardLayout``：前台线程卡住时，那个调用
    可能把回放线程一起拖死。枚举本会话已加载的键盘布局即可判断是否需要 Unicode
    注入，且没有阻塞风险。
    """
    global _layout_checked_at, _layout_active
    if not available():
        return False
    now = time.monotonic()
    if now - _layout_checked_at < 1.0:
        return _layout_active
    _layout_checked_at = now
    _layout_active = False
    try:
        count = int(_user32.GetKeyboardLayoutList(0, None))
        if count <= 0:
            return False
        layouts = (ctypes.c_void_p * count)()
        got = int(_user32.GetKeyboardLayoutList(count, layouts))
        for index in range(max(0, got)):
            layout = _handle(layouts[index])
            if (layout & 0x3FF) in (_PRIMARY_CHINESE, _PRIMARY_JAPANESE, _PRIMARY_KOREAN):
                _layout_active = True
                break
    except Exception:
        logger.debug("Enumerating keyboard layouts failed", exc_info=True)
        _layout_active = False
    return _layout_active


def send_text(text: str) -> bool:
    """用 ``KEYEVENTF_UNICODE`` 把文本直接注入目标窗口，绕开输入法。

    非 BMP 字符（emoji 等）按 UTF-16 代理对拆成两次注入。返回是否全部送达；
    ``SendInput`` 被 UIPI 拦下时返回 ``False``，调用方可以退回虚拟键码。
    """
    if not available() or not text:
        return False

    units: list[int] = []
    for char in text:
        encoded = char.encode("utf-16-le")
        units.extend(
            int.from_bytes(encoded[index:index + 2], "little")
            for index in range(0, len(encoded), 2))

    events = (INPUT * (len(units) * 2))()
    for index, unit in enumerate(units):
        events[index * 2] = INPUT(
            type=INPUT_KEYBOARD,
            ki=KEYBDINPUT(0, unit, KEYEVENTF_UNICODE, 0, 0))
        events[index * 2 + 1] = INPUT(
            type=INPUT_KEYBOARD,
            ki=KEYBDINPUT(0, unit, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, 0))
    sent = int(_user32.SendInput(len(events), events, ctypes.sizeof(INPUT)))
    if sent != len(events):
        logger.warning("Unicode injection delivered %d/%d events", sent, len(events))
        return False
    return True
