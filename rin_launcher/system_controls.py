"""Windows 系统控制：系统音量、Wi-Fi 无线开关、移动热点。

QML 侧以 ``SystemControls`` 这个 context property 暴露（见 ``main.py``），
小窗底部那排系统卡片直接绑定这里的属性。

设计取舍：

* **音量**走 ``pycaw``（Core Audio）。读取是同步的，毫秒级，放在主线程没问题。
* **Wi-Fi / 热点**走 WinRT。``Radio`` 的无线开关不需要管理员权限，
  ``NetworkOperatorTetheringManager`` 就是 Windows 设置里那个「移动热点」。
* Qt 主线程是单线程公寓（STA），WinRT 的 ``IAsyncOperation.get()`` 在 STA 上会
  直接报错；所以所有 WinRT 调用都放在一个 MTA 工作线程里串行执行，结果用信号
  回到主线程。开热点 / 关热点可能要一两秒，也不会把桌面挂件卡住。
* 依赖没装、系统不支持、网卡被禁用等情况一律「降级成不可用」：属性照常可读，
  界面显示灰色，而不是让 QML 加载失败。
"""

from __future__ import annotations

import logging
import queue
import subprocess
import sys
import threading
import time
from typing import Any

from PySide6.QtCore import Property, QObject, Qt, QTimer, Signal, Slot

logger = logging.getLogger(__name__)

_IS_WINDOWS = sys.platform == "win32"

# 移动热点：Windows 设置里那个「移动热点」的默认配置。
HOTSPOT_SSID = "rinlauncher-hotspot"
HOTSPOT_PASSWORD = "12345678"

# 状态轮询间隔：Windows 快速设置里一拨开关，小窗最多两秒就跟上。
_POLL_INTERVAL_MS = 2000
# Wi-Fi SSID 的 netsh 兜底查询有子进程开销，最多 15 秒一次。
_SSID_REFRESH_SECONDS = 15.0

# ── 音量：pycaw + comtypes ──────────────────────────────────────────
# 这几个依赖的导入要一两百毫秒，而小窗显示前根本用不到。做成延迟导入：
# SystemControls 构造不再拖慢冷启动，第一次 refresh（小窗出来之后）才加载。
_AUDIO_LOADED = False
_AUDIO_AVAILABLE = False
AudioUtilities: Any = None
IAudioEndpointVolume: Any = None
CLSCTX_ALL: Any = None
CoInitialize: Any = None
cast: Any = None
POINTER: Any = None


def _load_audio() -> bool:
    global _AUDIO_LOADED, _AUDIO_AVAILABLE
    global AudioUtilities, IAudioEndpointVolume, CLSCTX_ALL, CoInitialize, cast, POINTER
    if _AUDIO_LOADED:
        return _AUDIO_AVAILABLE
    _AUDIO_LOADED = True
    if not _IS_WINDOWS:
        return False
    try:
        from ctypes import POINTER as _POINTER
        from ctypes import cast as _cast

        from comtypes import CLSCTX_ALL as _CLSCTX_ALL
        from comtypes import CoInitialize as _CoInitialize
        from pycaw.pycaw import AudioUtilities as _AudioUtilities
        from pycaw.pycaw import IAudioEndpointVolume as _IAudioEndpointVolume

        AudioUtilities = _AudioUtilities
        IAudioEndpointVolume = _IAudioEndpointVolume
        CLSCTX_ALL = _CLSCTX_ALL
        CoInitialize = _CoInitialize
        cast = _cast
        POINTER = _POINTER
        _AUDIO_AVAILABLE = True
    except Exception:  # pragma: no cover - 依赖缺失时只走降级分支
        logger.debug("pycaw / comtypes is unavailable", exc_info=True)
    return _AUDIO_AVAILABLE


# ── Wi-Fi / 热点：WinRT ────────────────────────────────────────────
# 同理：winrt 的导入链会顺带拖进 asyncio 等模块，放到工作线程里再加载。
_WINRT_LOADED = False
_WINRT_AVAILABLE = False
_WIFI_RADIO_KIND: Any = None
ApartmentType: Any = None
init_apartment: Any = None
Radio: Any = None
RadioAccessStatus: Any = None
RadioState: Any = None
NetworkInformation: Any = None
NetworkOperatorTetheringAccessPointConfiguration: Any = None
NetworkOperatorTetheringManager: Any = None
TetheringOperationalState: Any = None
TetheringOperationStatus: Any = None
TetheringWiFiAuthenticationKind: Any = None


def _load_winrt() -> bool:
    global _WINRT_LOADED, _WINRT_AVAILABLE, _WIFI_RADIO_KIND
    global ApartmentType, init_apartment
    global Radio, RadioAccessStatus, RadioState, NetworkInformation
    global NetworkOperatorTetheringAccessPointConfiguration, NetworkOperatorTetheringManager
    global TetheringOperationalState, TetheringOperationStatus, TetheringWiFiAuthenticationKind
    if _WINRT_LOADED:
        return _WINRT_AVAILABLE
    _WINRT_LOADED = True
    if not _IS_WINDOWS:
        return False
    try:
        from winrt.runtime import ApartmentType as _ApartmentType
        from winrt.runtime import init_apartment as _init_apartment
        from winrt.windows.devices.radios import (
            Radio as _Radio,
        )
        from winrt.windows.devices.radios import (
            RadioAccessStatus as _RadioAccessStatus,
        )
        from winrt.windows.devices.radios import (
            RadioKind as _RadioKind,
        )
        from winrt.windows.devices.radios import (
            RadioState as _RadioState,
        )
        from winrt.windows.networking.connectivity import (
            NetworkInformation as _NetworkInformation,
        )
        from winrt.windows.networking.networkoperators import (
            NetworkOperatorTetheringAccessPointConfiguration as _TetheringConfig,
        )
        from winrt.windows.networking.networkoperators import (
            NetworkOperatorTetheringManager as _TetheringManager,
        )
        from winrt.windows.networking.networkoperators import (
            TetheringOperationalState as _TetheringState,
        )
        from winrt.windows.networking.networkoperators import (
            TetheringOperationStatus as _TetheringStatus,
        )
        from winrt.windows.networking.networkoperators import (
            TetheringWiFiAuthenticationKind as _TetheringAuth,
        )

        ApartmentType = _ApartmentType
        init_apartment = _init_apartment
        Radio = _Radio
        RadioAccessStatus = _RadioAccessStatus
        RadioState = _RadioState
        NetworkInformation = _NetworkInformation
        NetworkOperatorTetheringAccessPointConfiguration = _TetheringConfig
        NetworkOperatorTetheringManager = _TetheringManager
        TetheringOperationalState = _TetheringState
        TetheringOperationStatus = _TetheringStatus
        TetheringWiFiAuthenticationKind = _TetheringAuth
        # pywinrt 把 WinRT 的 WiFi 枚举写成 WI_FI；老版本可能叫 WIFI。
        _WIFI_RADIO_KIND = getattr(_RadioKind, "WI_FI", None) or getattr(_RadioKind, "WIFI", None)
        _WINRT_AVAILABLE = True
    except Exception:  # pragma: no cover - 依赖缺失时只走降级分支
        logger.debug("winrt is unavailable", exc_info=True)
    return _WINRT_AVAILABLE


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
    _wifiStateReady = Signal(bool, bool, str)
    _hotspotStateReady = Signal(bool, bool)
    _winrtReady = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)

        # 音量端点懒加载：默认播放设备换了之后要能重新拿。
        self._speakers: Any = None
        self._volume_interface: Any = None
        self._volume = 0.0
        self._muted = False

        self._wifi_radio: Any = None
        self._wifi_scanned_at = 0.0
        self._wifi_available = False
        self._wifi_enabled = False
        self._wifi_busy = False
        self._wifi_ssid = ""
        # SSID 缓存（工作线程读写）：轮询时优先复用，避免每 2 秒起一次 netsh。
        self._ssid_cache = ""
        self._ssid_checked_at = 0.0
        self._last_poll_wifi_on = False

        self._hotspot_manager: Any = None
        self._hotspot_profile_id = ""
        self._hotspot_available = False
        self._hotspot_enabled = False
        self._hotspot_busy = False

        self._wifiFinished.connect(self._finish_wifi)
        self._hotspotFinished.connect(self._finish_hotspot)
        self._wifiStateReady.connect(self._apply_wifi_state)
        self._hotspotStateReady.connect(self._apply_hotspot_state)
        self._winrtReady.connect(self._on_winrt_ready)

        # Qt 主线程是单线程公寓（STA），WinRT 的 IAsyncOperation.get() 会直接报
        # “Cannot call blocking method from single-threaded apartment”。所以所有
        # WinRT 调用都放在一个 MTA 工作线程里串行执行，结果用信号回到主线程。
        self._winrt_queue: queue.Queue[str | None] = queue.Queue()
        self._poll_pending = False
        # 先置状态再起线程：_winrtReady 可能紧接着从工作线程发出来。
        self._active = False
        self._winrt_thread = threading.Thread(
            target=self._winrt_loop, name="rin-winrt", daemon=True)
        self._winrt_thread.start()

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
            # 第一帧先让小窗画出来；音量端点（pycaw）的首次导入放到 150ms 后。
            QTimer.singleShot(150, self.refresh)
        else:
            self._timer.stop()

    def _queue_winrt_poll(self) -> None:
        """把一次 Wi-Fi / 热点轮询丢给工作线程；主线程从不直接碰 WinRT。"""
        if (_WINRT_AVAILABLE and self._active and not self._poll_pending
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

    def _ensure_volume(self) -> Any:
        if not _load_audio():
            return None
        if self._volume_interface is not None:
            return self._volume_interface
        try:
            # Qt 在主线程已经初始化过 COM；这里再调一次是幂等的（S_FALSE）。
            try:
                CoInitialize()
            except Exception:
                pass
            self._speakers = AudioUtilities.GetSpeakers()
            # 新版 pycaw 直接给 EndpointVolume；旧版要自己 Activate。
            endpoint = getattr(self._speakers, "EndpointVolume", None)
            if endpoint is None:
                interface = self._speakers.Activate(
                    IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                endpoint = cast(interface, POINTER(IAudioEndpointVolume))
            self._volume_interface = endpoint
        except Exception:
            logger.exception("Cannot access the default audio endpoint")
            self._speakers = None
            self._volume_interface = None
        return self._volume_interface

    def _read_volume(self) -> tuple[float, bool] | None:
        endpoint = self._ensure_volume()
        if endpoint is None:
            return None
        try:
            return float(endpoint.GetMasterVolumeLevelScalar()), bool(endpoint.GetMute())
        except Exception:
            # 默认播放设备被拔掉 / 切换时端点会失效，下一次重新拿。
            logger.warning("Reading the audio endpoint failed; will reacquire", exc_info=True)
            self._speakers = None
            self._volume_interface = None
            return None

    @Slot(float)
    def setVolume(self, value: float) -> None:
        endpoint = self._ensure_volume()
        if endpoint is None:
            return
        value = max(0.0, min(1.0, float(value)))
        try:
            endpoint.SetMasterVolumeLevelScalar(value, None)
        except Exception:
            logger.exception("Setting the master volume failed")
            self._speakers = None
            self._volume_interface = None
            return
        if abs(value - self._volume) > 0.001:
            self._volume = value
            self.volumeChanged.emit()

    @Slot()
    def toggleMute(self) -> None:
        endpoint = self._ensure_volume()
        if endpoint is None:
            return
        try:
            muted = not bool(endpoint.GetMute())
            endpoint.SetMute(muted, None)
        except Exception:
            logger.exception("Toggling mute failed")
            self._speakers = None
            self._volume_interface = None
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

    def _radio(self) -> Any:
        """找到 Wi-Fi 无线网卡；只在 WinRT 工作线程里调用。"""
        if not _WINRT_AVAILABLE or _WIFI_RADIO_KIND is None:
            return None
        if self._wifi_radio is not None:
            return self._wifi_radio
        # 网卡不存在 / 被硬件关闭时不要每 3 秒重新枚举一遍，30 秒后再试。
        now = time.monotonic()
        if now < self._wifi_scanned_at:
            return None
        self._wifi_scanned_at = now + 30.0
        try:
            access = Radio.request_access_async().get()
            if access != RadioAccessStatus.ALLOWED:
                logger.warning("Radio access denied: %s", access)
                return None
            for radio in Radio.get_radios_async().get():
                if radio.kind == _WIFI_RADIO_KIND:
                    self._wifi_radio = radio
                    break
            if self._wifi_radio is None:
                logger.info("No Wi-Fi radio found on this machine")
        except Exception:
            logger.exception("Enumerating radios failed")
        return self._wifi_radio

    @staticmethod
    def _netsh(*args: str) -> tuple[int, str]:
        """调用 netsh 并返回 (returncode, stdout)；任何异常都降级为空结果。"""
        if not _IS_WINDOWS:
            return 1, ""
        try:
            completed = subprocess.run(
                ["netsh", *args],
                capture_output=True,
                timeout=12,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            raw = completed.stdout or b""
            # 新版 Windows 的 netsh 可能输出 UTF-8，老系统是 ANSI（中文 cp936）。
            for encoding in ("utf-8", "mbcs", "latin-1"):
                try:
                    return completed.returncode, raw.decode(encoding)
                except UnicodeDecodeError:
                    continue
            return completed.returncode, raw.decode("utf-8", errors="replace")
        except Exception:
            logger.warning("netsh %s failed", " ".join(args), exc_info=True)
            return 1, ""

    def _connected_wifi_ssid(self, *, precise: bool = True) -> str:
        """当前已连接的 Wi-Fi SSID；没连上或读取失败时返回空串。

        WinRT 只在「有 Internet 连接」时给得出 profile，所以还要有 netsh 兜底。
        netsh 是子进程，两秒一次的轮询不能每次都跑：``precise=False`` 时结果
        缓存 ``_SSID_REFRESH_SECONDS`` 秒，到期后再真正读一次。
        """
        now = time.monotonic()
        if not precise and now - self._ssid_checked_at < _SSID_REFRESH_SECONDS:
            return self._ssid_cache

        ssid = ""
        if _WINRT_AVAILABLE:
            try:
                profile = NetworkInformation.get_internet_connection_profile()
                if profile is not None and profile.is_wlan_connection_profile:
                    details = profile.wlan_connection_profile_details
                    if details is not None:
                        ssid = str(details.get_connected_ssid() or "")
            except Exception:
                logger.debug("Reading connected SSID via WinRT failed", exc_info=True)

        if not ssid:
            # 没有 Internet 连接（或走的是有线）时 WinRT 拿不到 WLAN profile。
            _code, output = self._netsh("wlan", "show", "interfaces")
            for line in output.splitlines():
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                if key.strip().upper() == "SSID":
                    ssid = value.strip()
                    break

        self._ssid_cache = ssid
        self._ssid_checked_at = now
        return ssid

    def _saved_auto_profile(self) -> str:
        """第一个「自动连接」的已保存 Wi-Fi 配置名。"""
        _code, output = self._netsh("wlan", "show", "profiles")
        profiles: list[str] = []
        for line in output.splitlines():
            if ":" not in line:
                continue
            lowered = line.lower()
            if "profile" not in lowered and "配置文件" not in line:
                continue
            name = line.split(":", 1)[1].strip()
            if name and name not in profiles:
                profiles.append(name)
        for name in profiles[:12]:
            _code, detail = self._netsh("wlan", "show", "profiles", f"name={name}")
            if "自动连接" in detail or "connect automatically" in detail.lower():
                return name
        return ""

    def _try_connect_known_wifi(self, radio: Any) -> None:
        """等系统自动连 3 秒；还没连上就手动连第一个自动配置。"""
        try:
            if radio.state != RadioState.ON:
                return
        except Exception:
            return
        for _ in range(6):
            time.sleep(0.5)
            if self._connected_wifi_ssid():
                return
            try:
                if radio.state != RadioState.ON:
                    return
            except Exception:
                return
        profile = self._saved_auto_profile()
        if not profile:
            logger.info("Wi-Fi is on but no saved auto-connect profile was found")
            return
        code, output = self._netsh("wlan", "connect", f"name={profile}")
        logger.info("Fallback Wi-Fi connect to %r -> %s (%s)", profile, code, output.strip())

    def _winrt_poll(self) -> None:
        """读一次 Wi-Fi / 热点状态；只在 WinRT 工作线程里调用。"""
        if not _WINRT_AVAILABLE:
            return
        radio = self._radio()
        available = False
        enabled = False
        if radio is not None:
            try:
                state = radio.state
                available = state != RadioState.UNKNOWN
                enabled = state == RadioState.ON
            except Exception:
                logger.warning("Reading the Wi-Fi radio state failed", exc_info=True)
                self._wifi_radio = None
                self._wifi_scanned_at = 0.0
        # 刚打开 Wi-Fi 的那一拍强制精确读一次，之后交给缓存，别每 2 秒起 netsh。
        precise = enabled and not self._last_poll_wifi_on
        ssid = self._connected_wifi_ssid(precise=precise) if enabled else ""
        self._last_poll_wifi_on = enabled
        self._wifiStateReady.emit(available, enabled, ssid)

        manager = self._tethering_manager()
        hotspot_available = manager is not None and radio is not None
        hotspot_enabled = False
        if manager is not None:
            try:
                state = manager.tethering_operational_state
                if state == TetheringOperationalState.UNKNOWN:
                    # manager 绑定的连接已经失效，下一次重新创建。
                    self._hotspot_manager = None
                    self._hotspot_profile_id = ""
                    hotspot_available = False
                else:
                    hotspot_enabled = state == TetheringOperationalState.ON
            except Exception:
                logger.warning("Reading the hotspot state failed", exc_info=True)
                self._hotspot_manager = None
                self._hotspot_profile_id = ""
                hotspot_available = False
        self._hotspotStateReady.emit(hotspot_available, hotspot_enabled)

    def _wait_radio_state(self, radio: Any, target: Any, timeout: float = 5.0) -> bool:
        """等网卡真正切到目标状态；系统异步切换时状态不会立刻变。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if radio.state == target:
                    return True
            except Exception:
                return False
            time.sleep(0.25)
        return False

    def _winrt_toggle_wifi(self) -> None:
        """切 Wi-Fi；只在 WinRT 工作线程里调用。"""
        if not _WINRT_AVAILABLE:
            self._wifiFinished.emit(False, "Wi-Fi 控制不可用：缺少 winrt 依赖")
            return
        radio = self._radio()
        if radio is None:
            self._wifiFinished.emit(False, "没有检测到 Wi-Fi 无线网卡")
            self._winrt_poll()
            return
        ok = False
        message = ""
        turn_on = False
        try:
            turn_on = radio.state != RadioState.ON
            target = RadioState.ON if turn_on else RadioState.OFF
            status = radio.set_state_async(target).get()
            ok = status == RadioAccessStatus.ALLOWED
            if not ok:
                message = f"系统拒绝了 Wi-Fi 开关操作（{status}）"
            elif not self._wait_radio_state(radio, target):
                ok = False
                message = "Wi-Fi 状态没有在预期时间内切换，请稍后重试"
        except Exception as exc:
            logger.exception("Toggling the Wi-Fi radio failed")
            message = f"Wi-Fi 开关失败：{exc}"
        if ok and turn_on:
            # 先让 Windows 自己连首选网络；3 秒没连上再兜底。
            self._try_connect_known_wifi(radio)
        self._wifiFinished.emit(ok, message)
        self._winrt_poll()

    def _apply_wifi_state(self, available: bool, enabled: bool, ssid: str) -> None:
        """工作线程的结果回到主线程后再更新属性。"""
        if ((available, enabled, ssid)
                != (self._wifi_available, self._wifi_enabled, self._wifi_ssid)):
            self._wifi_available = available
            self._wifi_enabled = enabled
            self._wifi_ssid = ssid
            self.wifiChanged.emit()

    @Slot()
    def toggleWifi(self) -> None:
        # 依赖还在工作线程里加载时也照常排队，加载完会继续处理。
        if _WINRT_LOADED and not _WINRT_AVAILABLE:
            self.notify.emit("Wi-Fi 控制不可用：缺少 winrt 依赖", "warning")
            return
        if self._wifi_busy:
            return
        self._wifi_busy = True
        self.wifiChanged.emit()
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

    def _tethering_manager(self) -> Any:
        """只在 WinRT 工作线程里调用。

        manager 是绑定在「当前 Internet 连接」上的，换了网络（有线 ↔ Wi-Fi）就得
        重新创建；用连接名做标识，profile 变了就重建。
        """
        if not _WINRT_AVAILABLE:
            return None
        try:
            profile = NetworkInformation.get_internet_connection_profile()
            if profile is None:
                # 没有联网时 Windows 也拿不到可共享的连接配置。
                self._hotspot_manager = None
                self._hotspot_profile_id = ""
                return None
            profile_id = str(getattr(profile, "connection_profile_name", "") or "")
            if self._hotspot_manager is not None and profile_id == self._hotspot_profile_id:
                return self._hotspot_manager
            manager = NetworkOperatorTetheringManager.create_from_connection_profile(profile)
            if manager is None:
                logger.info("Mobile hotspot manager is unavailable for profile %r", profile_id)
                self._hotspot_manager = None
                self._hotspot_profile_id = ""
                return None
            self._hotspot_manager = manager
            self._hotspot_profile_id = profile_id
        except Exception:
            logger.warning("Mobile hotspot is not available", exc_info=True)
            self._hotspot_manager = None
            self._hotspot_profile_id = ""
        return self._hotspot_manager

    def _ensure_wifi_for_hotspot(self) -> tuple[bool, str]:
        """开热点前确保 Wi-Fi 网卡是开的；Windows 的移动热点靠它广播。"""
        radio = self._radio()
        if radio is None:
            return False, "开启热点需要 Wi-Fi 网卡，当前没有检测到"
        try:
            if radio.state == RadioState.ON:
                return True, ""
            if radio.state != RadioState.OFF:
                return False, "Wi-Fi 网卡当前不可用，无法开启热点"
            status = radio.set_state_async(RadioState.ON).get()
            if status != RadioAccessStatus.ALLOWED:
                return False, f"开启热点前无法打开 Wi-Fi（{status}）"
        except Exception as exc:
            logger.exception("Turning Wi-Fi on for the hotspot failed")
            return False, f"开启热点前无法打开 Wi-Fi：{exc}"
        if not self._wait_radio_state(radio, RadioState.ON):
            return False, "Wi-Fi 没有在预期时间内打开，热点未启动"
        return True, ""

    def _winrt_toggle_hotspot(self) -> None:
        if not _WINRT_AVAILABLE:
            self._hotspotFinished.emit(False, "移动热点不可用：缺少 winrt 依赖")
            return
        manager = self._tethering_manager()
        if manager is None:
            self._hotspotFinished.emit(False, "移动热点不可用：当前没有可共享的网络连接")
            self._winrt_poll()
            return
        ok = False
        message = ""
        turn_on = False
        try:
            turn_on = (
                manager.tethering_operational_state != TetheringOperationalState.ON)
            if turn_on:
                ready, ready_message = self._ensure_wifi_for_hotspot()
                if not ready:
                    self._hotspotFinished.emit(False, ready_message)
                    self._winrt_poll()
                    return
                configured, config_message = self._configure_hotspot(manager)
                if not configured:
                    self._hotspotFinished.emit(False, config_message)
                    self._winrt_poll()
                    return
            operation = (manager.start_tethering_async() if turn_on
                         else manager.stop_tethering_async())
            result = operation.get()
            status = getattr(result, "status", None)
            ok = status in (TetheringOperationStatus.SUCCESS,)
            if turn_on and status == TetheringOperationStatus.ALREADY_ON:
                ok = True
            if not ok:
                detail = getattr(result, "additional_error_message", "") or ""
                message = detail or f"移动热点操作失败（{status}）"
        except Exception as exc:
            logger.exception("Toggling the mobile hotspot failed")
            message = f"移动热点操作失败：{exc}"
        if ok:
            # 系统是异步切换的，等状态落到目标值再回报，界面不会「刚开完又弹回去」。
            state = (TetheringOperationalState.ON if turn_on
                     else TetheringOperationalState.OFF)
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                try:
                    if manager.tethering_operational_state == state:
                        break
                except Exception:
                    break
                time.sleep(0.25)
            if turn_on:
                self.notify.emit(
                    f"热点已开启：{HOTSPOT_SSID}，密码 {HOTSPOT_PASSWORD}", "success")
        else:
            # 下次重新根据当前网络连接创建 manager。
            self._hotspot_manager = None
            self._hotspot_profile_id = ""
        self._hotspotFinished.emit(ok, message)
        self._winrt_poll()

    def _configure_hotspot(self, manager: Any) -> tuple[bool, str]:
        """把移动热点固定成 Rin Launcher 的 SSID / 密码。"""
        try:
            configuration = NetworkOperatorTetheringAccessPointConfiguration()
            configuration.ssid = HOTSPOT_SSID
            configuration.passphrase = HOTSPOT_PASSWORD
            try:
                configuration.authentication_kind = TetheringWiFiAuthenticationKind.WPA2
            except Exception:
                logger.debug("WPA2 hotspot auth is not supported", exc_info=True)
            # ConfigureAccessPointAsync 是 IAsyncAction（没有 result 负载）：
            # 直接 get() 等完成即可。旧代码把它当 operation result 读 .status，
            # pywinrt 返回 None，于是点热点就弹 “NoneType has no attribute status”。
            manager.configure_access_point_async(configuration).get()
            current = manager.get_current_access_point_configuration()
            if str(getattr(current, "ssid", "") or "") != HOTSPOT_SSID:
                return False, (
                    "移动热点配置没有生效（当前 SSID："
                    f"{getattr(current, 'ssid', '') or '空'}）")
        except Exception as exc:
            logger.exception("Configuring the mobile hotspot failed")
            return False, f"移动热点配置失败：{exc}"
        return True, ""

    def _apply_hotspot_state(self, available: bool, enabled: bool) -> None:
        if (available, enabled) != (self._hotspot_available, self._hotspot_enabled):
            self._hotspot_available = available
            self._hotspot_enabled = enabled
            self.hotspotChanged.emit()

    @Slot()
    def toggleHotspot(self) -> None:
        if _WINRT_LOADED and not _WINRT_AVAILABLE:
            self.notify.emit("移动热点不可用：缺少 winrt 依赖", "warning")
            return
        if self._hotspot_busy:
            return
        self._hotspot_busy = True
        self.hotspotChanged.emit()
        self._winrt_queue.put("hotspot")

    def _finish_hotspot(self, ok: bool, message: str) -> None:
        self._hotspot_busy = False
        self.hotspotChanged.emit()
        if not ok and message:
            self.notify.emit(message, "error")

    # ------------------------------------------------------------------
    # 轮询 / 生命周期
    # ------------------------------------------------------------------
    def _winrt_loop(self) -> None:
        """WinRT 专用工作线程：MTA + 串行执行，避免主线程 STA 阻塞报错。"""
        # 依赖在这里才导入（见 _load_winrt），不拖慢小窗的首帧。
        _load_winrt()
        if _WINRT_AVAILABLE:
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
                    self._winrt_poll()
                elif task == "wifi":
                    self._winrt_toggle_wifi()
                elif task == "hotspot":
                    self._winrt_toggle_hotspot()
            except Exception:
                logger.exception("WinRT worker task %r failed", task)
            finally:
                if task == "poll":
                    self._poll_pending = False

    @Slot()
    def refresh(self) -> None:
        """重新读一遍三项系统状态；QML 也可以手动调用。"""
        state = self._read_volume()
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
        if self._winrt_thread.is_alive():
            self._winrt_queue.put(None)
            self._winrt_thread.join(timeout=2.0)
