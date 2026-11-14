"""Windows EcoQoS（能效服务质量）：线程级后台节能。

只给明确的后台工作线程（更新检查 / 下载 / 镜像测速 / 任务状态刷新）打开
``POWER_THROTTLING_EXECUTION_SPEED``。GUI 线程、全局热键监听、按键录制与
键盘回放**永远不碰**：这些路径对调度延迟敏感，被 Windows 降频会出现掉帧、
热键延迟和回放时序漂移。

刻意不使用 ``POWER_THROTTLING_IGNORE_TIMER_RESOLUTION``：那会把线程的定时器
精度让给系统，热键 / 轮询间隔会漂。

Windows 10 上 ``SetThreadInformation(ThreadPowerThrottling)`` 可能返回
``ERROR_INVALID_PARAMETER``；失败只记 DEBUG 并自动降级，不影响任何功能。
非 Windows 平台所有函数都是安全的空操作。
"""

from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes

logger = logging.getLogger(__name__)

# processthreadsapi.h / thread_information_class
_THREAD_POWER_THROTTLING = 3
_PROCESS_POWER_THROTTLING = 4
_POWER_THROTTLING_EXECUTION_SPEED = 0x1
_VERSION = 1

_enabled = True
_thread_supported: bool | None = None
_process_supported: bool | None = None
_api: tuple | None = None


class _PowerThrottlingState(ctypes.Structure):
    _fields_ = [
        ("Version", wintypes.ULONG),
        ("ControlMask", wintypes.ULONG),
        ("StateMask", wintypes.ULONG),
    ]


def _load_api() -> tuple | None:
    """配置一次 ctypes 签名；HANDLE 参数必须显式声明，不能靠默认 c_int。"""
    global _api
    if _api is not None:
        return _api
    if sys.platform != "win32":
        return None
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentThread.argtypes = []
        kernel32.GetCurrentThread.restype = wintypes.HANDLE
        kernel32.GetCurrentProcess.argtypes = []
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.SetThreadInformation.argtypes = [
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel32.SetThreadInformation.restype = wintypes.BOOL
        kernel32.SetProcessInformation.argtypes = [
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel32.SetProcessInformation.restype = wintypes.BOOL
    except (AttributeError, OSError):
        logger.debug("EcoQoS APIs are unavailable", exc_info=True)
        return None
    _api = (kernel32,)
    return _api


def set_enabled(enabled: bool) -> None:
    """设置开关；只影响之后新建的后台线程（已开启的线程保持原状）。"""
    global _enabled
    _enabled = bool(enabled)


def enabled() -> bool:
    return _enabled


def _set_thread(state: bool | None) -> bool:
    """``True`` 开 / ``False`` 关 / ``None`` 交还系统管理。"""
    global _thread_supported
    if not _enabled or sys.platform != "win32":
        return False
    api = _load_api()
    if api is None:
        return False
    kernel32 = api[0]
    payload = _PowerThrottlingState(
        Version=_VERSION,
        ControlMask=0 if state is None else _POWER_THROTTLING_EXECUTION_SPEED,
        StateMask=(_POWER_THROTTLING_EXECUTION_SPEED if state else 0),
    )
    try:
        ok = bool(kernel32.SetThreadInformation(
            kernel32.GetCurrentThread(), _THREAD_POWER_THROTTLING,
            ctypes.byref(payload), ctypes.sizeof(payload)))
    except (AttributeError, OSError):
        logger.debug("SetThreadInformation failed", exc_info=True)
        return False
    if not ok and _thread_supported is not False:
        _thread_supported = False
        logger.debug(
            "Thread-level EcoQoS unavailable (error %s); continuing without it",
            ctypes.get_last_error())
    elif ok:
        _thread_supported = True
    return ok


def enable_current_thread() -> bool:
    """给当前后台线程打开 EcoQoS；不支持 / 关闭时返回 False。"""
    return _set_thread(True)


def disable_current_thread() -> bool:
    """关闭当前线程的 EcoQoS（保留系统默认管理）。"""
    return _set_thread(False)


def reset_current_thread() -> bool:
    """把当前线程的节流策略交还系统（ControlMask / StateMask 清零）。"""
    return _set_thread(None)


def _set_process(state: bool | None) -> bool:
    """进程级 EcoQoS：仅保留给内部实验，默认没有任何调用点。"""
    global _process_supported
    if not _enabled or sys.platform != "win32":
        return False
    api = _load_api()
    if api is None:
        return False
    kernel32 = api[0]
    payload = _PowerThrottlingState(
        Version=_VERSION,
        ControlMask=0 if state is None else _POWER_THROTTLING_EXECUTION_SPEED,
        StateMask=(_POWER_THROTTLING_EXECUTION_SPEED if state else 0),
    )
    try:
        ok = bool(kernel32.SetProcessInformation(
            kernel32.GetCurrentProcess(), _PROCESS_POWER_THROTTLING,
            ctypes.byref(payload), ctypes.sizeof(payload)))
    except (AttributeError, OSError):
        logger.debug("SetProcessInformation failed", exc_info=True)
        return False
    if not ok and _process_supported is not False:
        _process_supported = False
        logger.debug(
            "Process-level EcoQoS unavailable (error %s)",
            ctypes.get_last_error())
    elif ok:
        _process_supported = True
    return ok


def enable_process() -> bool:
    return _set_process(True)


def disable_process() -> bool:
    return _set_process(False)


def reset_process() -> bool:
    return _set_process(None)


def available() -> bool:
    """当前系统是否至少支持线程级 EcoQoS（调用一次探测）。"""
    return sys.platform == "win32" and _load_api() is not None
