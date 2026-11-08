"""Windows 系统控制：系统音量、Wi-Fi 无线开关、移动热点。

QML 侧以 ``SystemControls`` 这个 context property 暴露（见 ``main.py``），
小窗底部那排系统卡片直接绑定这里的属性。

这个文件只留 QML 契约、轮询节拍和工作线程调度；真正的系统调用在：

* :mod:`rin_launcher.system_audio` —— pycaw / Core Audio，同步、毫秒级、跑主线程
* :mod:`rin_launcher.system_network` —— WinRT + netsh，只在 MTA 工作线程里跑

设计取舍：Qt 主线程是单线程公寓（STA），WinRT 的 ``IAsyncOperation.get()``
在 STA 上会直接报错；所以所有 WinRT 调用都放在一个 MTA 工作线程里串行执行，
结果用信号回到主线程。开热点 / 关热点可能要一两秒，也不会把桌面挂件卡住。

依赖没装、系统不支持、网卡被禁用等情况一律「降级成不可用」：属性照常可读，
界面显示灰色，而不是让 QML 加载失败。
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Any  # noqa: F401  # 供类型注解与外部补丁使用

from PySide6.QtCore import Property, QObject, Qt, QTimer, Signal, Slot

from rin_launcher.system_audio import AudioBackend
from rin_launcher.system_network import (
    HOTSPOT_PASSWORD,
    HOTSPOT_SSID,
    ApartmentType,
    NetworkBackend,
    init_apartment,
)

logger = logging.getLogger(__name__)

__all__ = ["HOTSPOT_PASSWORD", "HOTSPOT_SSID", "SystemControls"]

# 状态轮询间隔：Windows 快速设置里一拨开关，小窗最多两秒就跟上。
_POLL_INTERVAL_MS = 2000


class SystemControls(QObject):
    """音量 / Wi-Fi / 移动热点，用 Property + Signal 供 QML 绑定。"""

    volumeChanged = Signal()
    mutedChanged = Signal()
    wifiChanged = Signal()
    hotspotChanged = Signal()
    # 操作失败 / 状态不可用时给界面一条提示（由 main.py 接到 ConfigManager.notify）。
    notify = Signal(str, str)

    # 后台线程完成后回到主线程用的内部信号。
    _wifiFinished = Signal(bool, str)
    _hotspotFinished = Signal(bool, str)
    _networkState = Signal(bool, bool, str, bool, bool)
    _winrtReady = Signal()
    _notifyRequested = Signal(str, str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)

        self._audio = AudioBackend()
        self._volume = 0.0
        self._muted = False

        self._wifi_available = False
        self._wifi_enabled = False
        self._wifi_busy = False
        self._wifi_ssid = ""

        self._hotspot_available = False
        self._hotspot_enabled = False
        self._hotspot_busy = False

        self._network = NetworkBackend(
            self._state_from_thread, self._notify_from_thread)

        self._wifiFinished.connect(self._finish_wifi)
        self._hotspotFinished.connect(self._finish_hotspot)
        self._networkState.connect(self._apply_network_state)
        self._winrtReady.connect(self._on_winrt_ready)
        self._notifyRequested.connect(self.notify.emit)

        # Qt 主线程是单线程公寓（STA），WinRT 的 IAsyncOperation.get() 会直接报
        # “Cannot call blocking method from single-threaded apartment”。所以所有
        # WinRT 调用都放在一个 MTA 工作线程里串行执行，结果用信号回到主线程。
        self._winrt_queue: queue.Queue[str | None] = queue.Queue()
        self._poll_pending = False
        # 先置状态再起线程：_winrtReady 可能紧接着从工作线程发出来。
        self._active = False
        # 线程懒启动：恢复模式、或者用户只开了设置页时根本用不到小窗底部那排
        # 系统卡片，没必要白拉一条线程和整条 winrt 导入链。
        self._winrt_thread: threading.Thread | None = None

        # 状态轮询：只在小窗可见时跑，隐藏时停掉，省电也省 COM 调用。
        self._timer = QTimer(self)
        self._timer.setInterval(_POLL_INTERVAL_MS)
        self._timer.setTimerType(Qt.CoarseTimer)
        self._timer.timeout.connect(self.refresh)

    @Slot(bool)
    def setActive(self, active: bool) -> None:
        """小窗显示 / 隐藏时启停轮询；重新显示时立刻读一次。"""
        active = bool(active)
        if active == self._active:
            return
        self._active = active
        if active:
            self._timer.start()
            self._ensure_winrt_thread()
            # 第一帧先让小窗画出来；音量端点（pycaw）的首次导入放到 150ms 后。
            QTimer.singleShot(150, self.refresh)
        else:
            self._timer.stop()

    def _ensure_winrt_thread(self) -> None:
        """懒启动 WinRT 工作线程；重复调用是幂等的。"""
        if self._winrt_thread is not None:
            return
        self._winrt_thread = threading.Thread(
            target=self._winrt_loop, name="rin-winrt", daemon=True)
        self._winrt_thread.start()

    def _state_from_thread(self, wifi_available: bool, wifi_enabled: bool,
                           ssid: str, hotspot_available: bool,
                           hotspot_enabled: bool) -> None:
        """工作线程 → 主线程：状态一律用信号投递，不在工作线程碰 QObject 属性。"""
        self._networkState.emit(
            wifi_available, wifi_enabled, ssid, hotspot_available, hotspot_enabled)

    def _notify_from_thread(self, message: str, level: str) -> None:
        self._notifyRequested.emit(message, level)

    def _queue_winrt_poll(self) -> None:
        """把一次 Wi-Fi / 热点轮询丢给工作线程；主线程从不直接碰 WinRT。"""
        if (self._network.available and self._active and not self._poll_pending
                and not self._wifi_busy and not self._hotspot_busy):
            self._poll_pending = True
            self._winrt_queue.put("poll")

    @Slot()
    def _on_winrt_ready(self) -> None:
        """工作线程加载完 WinRT 后补一次状态读取（不触发音量导入）。"""
        self._queue_winrt_poll()

    # ------------------------------------------------------------------
    # 音量
    # ------------------------------------------------------------------
    @Property(float, notify=volumeChanged)
    def volume(self) -> float:
        return self._volume

    @Property(bool, notify=mutedChanged)
    def muted(self) -> bool:
        return self._muted

    @Slot(float)
    def setVolume(self, value: float) -> None:
        value = max(0.0, min(1.0, float(value)))
        if not self._audio.set_level(value):
            return
        if abs(value - self._volume) > 0.001:
            self._volume = value
            self.volumeChanged.emit()

    @Slot()
    def toggleMute(self) -> None:
        muted = self._audio.toggle_mute()
        if muted is None:
            return
        self._muted = muted
        self.mutedChanged.emit()

    # ------------------------------------------------------------------
    # Wi-Fi
    # ------------------------------------------------------------------
    @Property(bool, notify=wifiChanged)
    def wifiAvailable(self) -> bool:
        return self._wifi_available

    @Property(bool, notify=wifiChanged)
    def wifiEnabled(self) -> bool:
        return self._wifi_enabled

    @Property(bool, notify=wifiChanged)
    def wifiBusy(self) -> bool:
        return self._wifi_busy

    @Property(str, notify=wifiChanged)
    def wifiSsid(self) -> str:
        return self._wifi_ssid

    @Slot()
    def toggleWifi(self) -> None:
        # 依赖还在工作线程里加载时也照常排队，加载完会继续处理。
        if self._network.loaded and not self._network.available:
            self.notify.emit("Wi-Fi 控制不可用：缺少 winrt 依赖", "warning")
            return
        if self._wifi_busy:
            return
        self._wifi_busy = True
        self.wifiChanged.emit()
        self._ensure_winrt_thread()
        self._winrt_queue.put("wifi")

    def _finish_wifi(self, ok: bool, message: str) -> None:
        self._wifi_busy = False
        # busy 变回 false 也要通知一次，哪怕状态本身没变。
        self.wifiChanged.emit()
        if not ok and message:
            self.notify.emit(message, "error")

    # ------------------------------------------------------------------
    # 移动热点
    # ------------------------------------------------------------------
    @Property(bool, notify=hotspotChanged)
    def hotspotAvailable(self) -> bool:
        return self._hotspot_available

    @Property(bool, notify=hotspotChanged)
    def hotspotEnabled(self) -> bool:
        return self._hotspot_enabled

    @Property(bool, notify=hotspotChanged)
    def hotspotBusy(self) -> bool:
        return self._hotspot_busy

    @Property(str, constant=True)
    def hotspotSsid(self) -> str:
        return HOTSPOT_SSID

    @Property(str, constant=True)
    def hotspotPassword(self) -> str:
        return HOTSPOT_PASSWORD

    @Slot()
    def toggleHotspot(self) -> None:
        if self._network.loaded and not self._network.available:
            self.notify.emit("移动热点不可用：缺少 winrt 依赖", "warning")
            return
        if self._hotspot_busy:
            return
        self._hotspot_busy = True
        self.hotspotChanged.emit()
        self._ensure_winrt_thread()
        self._winrt_queue.put("hotspot")

    def _finish_hotspot(self, ok: bool, message: str) -> None:
        self._hotspot_busy = False
        self.hotspotChanged.emit()
        if not ok and message:
            self.notify.emit(message, "error")

    def _apply_network_state(self, wifi_available: bool, wifi_enabled: bool,
                             ssid: str, hotspot_available: bool,
                             hotspot_enabled: bool) -> None:
        """工作线程的结果回到主线程后再更新属性。"""
        if ((wifi_available, wifi_enabled, ssid)
                != (self._wifi_available, self._wifi_enabled, self._wifi_ssid)):
            self._wifi_available = wifi_available
            self._wifi_enabled = wifi_enabled
            self._wifi_ssid = ssid
            self.wifiChanged.emit()
        if ((hotspot_available, hotspot_enabled)
                != (self._hotspot_available, self._hotspot_enabled)):
            self._hotspot_available = hotspot_available
            self._hotspot_enabled = hotspot_enabled
            self.hotspotChanged.emit()

    # ------------------------------------------------------------------
    # 轮询 / 生命周期
    # ------------------------------------------------------------------
    def _winrt_loop(self) -> None:
        """WinRT 专用工作线程：MTA + 串行执行，避免主线程 STA 阻塞报错。"""
        # 依赖在这里才导入（见 system_network.load_winrt），不拖慢小窗的首帧。
        self._network.load()
        if self._network.available:
            try:
                init_apartment(ApartmentType.MULTI_THREADED)
            except Exception:
                logger.debug("WinRT apartment is already initialized", exc_info=True)
        # 依赖就绪后通知主线程补一次轮询；信号跨线程自动排队。
        self._winrtReady.emit()
        while True:
            task = self._winrt_queue.get()
            if task is None:
                break
            try:
                if task == "poll":
                    self._network.poll()
                elif task == "wifi":
                    self._wifiFinished.emit(*self._network.toggle_wifi())
                elif task == "hotspot":
                    self._hotspotFinished.emit(*self._network.toggle_hotspot())
            except Exception:
                logger.exception("WinRT worker task %r failed", task)
            finally:
                if task == "poll":
                    self._poll_pending = False

    @Slot()
    def refresh(self) -> None:
        """重新读一遍三项系统状态；QML 也可以手动调用。"""
        state: tuple[float, bool] | None = self._audio.read()
        if state is not None:
            volume, muted = state
            if abs(volume - self._volume) > 0.001:
                self._volume = volume
                self.volumeChanged.emit()
            if muted != self._muted:
                self._muted = muted
                self.mutedChanged.emit()

        # WinRT 查询丢给工作线程，主线程只读缓存值。
        self._queue_winrt_poll()

    @Slot()
    def stop(self) -> None:
        """退出前停掉轮询，别在 QApplication 析构后再碰系统接口。"""
        self._timer.stop()
        thread = self._winrt_thread
        if thread is not None and thread.is_alive():
            self._winrt_queue.put(None)
            thread.join(timeout=2.0)
