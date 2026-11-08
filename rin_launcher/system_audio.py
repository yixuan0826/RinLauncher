"""系统音量后端：pycaw + comtypes（Core Audio）。

不依赖 Qt：读取是同步的，毫秒级，放在主线程没问题。
依赖缺失或系统不是 Windows 时，所有方法降级为「返回失败」，调用方照常轮询即可，
不会抛异常也不会让 QML 加载失败。
"""

from __future__ import annotations

import logging
import sys
from typing import Any

logger = logging.getLogger(__name__)

_IS_WINDOWS = sys.platform == "win32"


class AudioBackend:
    """默认播放设备的音量与静音状态。

    端点缓存会自己失效：默认播放设备被拔掉 / 切换时读取会失败，
    下一次调用重新枚举一次。
    """

    def __init__(self) -> None:
        self._loaded = False
        self._available = False
        self._speakers: Any = None
        self._endpoint: Any = None
        # (AudioUtilities, IAudioEndpointVolume, CLSCTX_ALL, CoInitialize, cast, POINTER)
        self._mods: tuple[Any, ...] = ()

    @property
    def available(self) -> bool:
        return self._load()

    def _load(self) -> bool:
        """延迟导入：这几个包首次导入要一两百毫秒，冷启动时根本用不到。"""
        if self._loaded:
            return self._available
        self._loaded = True
        if not _IS_WINDOWS:
            return False
        try:
            from ctypes import POINTER, cast

            from comtypes import CLSCTX_ALL, CoInitialize
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

            self._mods = (
                AudioUtilities,
                IAudioEndpointVolume,
                CLSCTX_ALL,
                CoInitialize,
                cast,
                POINTER,
            )
            self._available = True
        except Exception:  # pragma: no cover - 依赖缺失时只走降级分支
            logger.debug("pycaw / comtypes is unavailable", exc_info=True)
        return self._available

    def reset(self) -> None:
        """端点失效后丢掉缓存，下一次调用重新拿。"""
        self._speakers = None
        self._endpoint = None

    def _ensure(self) -> Any:
        if not self._load():
            return None
        if self._endpoint is not None:
            return self._endpoint
        audio_utilities, i_endpoint, clsctx_all, co_init, cast, pointer = self._mods
        try:
            # Qt 在主线程已经初始化过 COM；这里再调一次是幂等的（S_FALSE）。
            try:
                co_init()
            except Exception:
                pass
            self._speakers = audio_utilities.GetSpeakers()
            # 新版 pycaw 直接给 EndpointVolume；旧版要自己 Activate。
            endpoint = getattr(self._speakers, "EndpointVolume", None)
            if endpoint is None:
                interface = self._speakers.Activate(
                    i_endpoint._iid_, clsctx_all, None)
                endpoint = cast(interface, pointer(i_endpoint))
            self._endpoint = endpoint
        except Exception:
            logger.exception("Cannot access the default audio endpoint")
            self.reset()
        return self._endpoint

    def read(self) -> tuple[float, bool] | None:
        """返回 (音量 0~1, 是否静音)；读不到时返回 None。"""
        endpoint = self._ensure()
        if endpoint is None:
            return None
        try:
            return (float(endpoint.GetMasterVolumeLevelScalar()),
                    bool(endpoint.GetMute()))
        except Exception:
            logger.warning(
                "Reading the audio endpoint failed; will reacquire", exc_info=True)
            self.reset()
            return None

    def set_level(self, value: float) -> bool:
        """设置主音量；返回是否真的写进了系统。"""
        endpoint = self._ensure()
        if endpoint is None:
            return False
        try:
            endpoint.SetMasterVolumeLevelScalar(
                max(0.0, min(1.0, float(value))), None)
        except Exception:
            logger.exception("Setting the master volume failed")
            self.reset()
            return False
        return True

    def toggle_mute(self) -> bool | None:
        """切换静音；返回新的静音状态，失败返回 None。"""
        endpoint = self._ensure()
        if endpoint is None:
            return None
        try:
            muted = not bool(endpoint.GetMute())
            endpoint.SetMute(muted, None)
        except Exception:
            logger.exception("Toggling mute failed")
            self.reset()
            return None
        return muted
