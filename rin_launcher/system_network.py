"""Wi-Fi 无线开关与移动热点后端：WinRT + netsh。

**只在一个 MTA 工作线程里调用。** Qt 主线程是单线程公寓（STA），WinRT 的
``IAsyncOperation.get()`` 在 STA 上会直接报错；所以这个后端不含任何 Qt 对象，
状态就绪时通过构造时传入的回调通知调用方，由调用方负责跨线程投递。

依赖缺失、系统不支持、网卡被禁用等情况一律降级为「不可用」：不抛异常，
调用方照常轮询即可。
"""

from __future__ import annotations

import logging
import subprocess
import sys
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

_IS_WINDOWS = sys.platform == "win32"

# 移动热点：Windows 设置里那个「移动热点」的默认配置。
HOTSPOT_SSID = "rinlauncher-hotspot"
HOTSPOT_PASSWORD = "12345678"

# Wi-Fi SSID 的 netsh 兜底查询有子进程开销，最多 15 秒一次。
_SSID_REFRESH_SECONDS = 15.0

# 网卡不存在 / 被硬件关闭时不要每 2 秒重新枚举一遍，30 秒后再试。
_RADIO_RESCAN_SECONDS = 30.0

# 状态就绪：(wifi 可用, wifi 开启, 当前 SSID, 热点可用, 热点开启)
StateCallback = Callable[[bool, bool, str, bool, bool], None]
# 需要提示用户的消息：(文案, 级别)
NotifyCallback = Callable[[str, str], None]

# ── WinRT 延迟导入 ────────────────────────────────────────────────
# winrt 的导入链会顺带拖进 asyncio 等模块，所以放到工作线程里再加载。
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


def load_winrt() -> bool:
    """导入 WinRT 并解析出需要的类型；幂等，失败后不再重试。"""
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
        from winrt.windows.devices.radios import Radio as _Radio
        from winrt.windows.devices.radios import (
            RadioAccessStatus as _RadioAccessStatus,
        )
        from winrt.windows.devices.radios import RadioKind as _RadioKind
        from winrt.windows.devices.radios import RadioState as _RadioState
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
        _WIFI_RADIO_KIND = (
            getattr(_RadioKind, "WI_FI", None)
            or getattr(_RadioKind, "WIFI", None))
        _WINRT_AVAILABLE = True
    except Exception:  # pragma: no cover - 依赖缺失时只走降级分支
        logger.debug("winrt is unavailable", exc_info=True)
    return _WINRT_AVAILABLE


class NetworkBackend:
    """Wi-Fi 无线开关与移动热点。

    只在 WinRT 工作线程里使用；构造后先 ``load()`` 再调用其它方法。
    """

    def __init__(self, on_state: StateCallback, on_notify: NotifyCallback) -> None:
        self._on_state = on_state
        self._on_notify = on_notify

        self._wifi_radio: Any = None
        self._wifi_scanned_at = 0.0
        # SSID 缓存：轮询时优先复用，避免每 2 秒起一次 netsh。
        self._ssid_cache = ""
        self._ssid_checked_at = 0.0
        self._last_poll_wifi_on = False

        self._hotspot_manager: Any = None
        self._hotspot_profile_id = ""

    # ── 依赖状态 ──────────────────────────────────────────────────
    @property
    def loaded(self) -> bool:
        return _WINRT_LOADED

    @property
    def available(self) -> bool:
        return _WINRT_AVAILABLE

    def load(self) -> bool:
        return load_winrt()

    # ── Wi-Fi 基础 ────────────────────────────────────────────────
    def _radio(self) -> Any:
        """找到 Wi-Fi 无线网卡。"""
        if not _WINRT_AVAILABLE or _WIFI_RADIO_KIND is None:
            return None
        if self._wifi_radio is not None:
            return self._wifi_radio
        now = time.monotonic()
        if now < self._wifi_scanned_at:
            return None
        self._wifi_scanned_at = now + _RADIO_RESCAN_SECONDS
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
        logger.info(
            "Fallback Wi-Fi connect to %r -> %s (%s)", profile, code, output.strip())

    @staticmethod
    def _wait_radio_state(radio: Any, target: Any, timeout: float = 5.0) -> bool:
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

    # ── 轮询 ──────────────────────────────────────────────────────
    def poll(self) -> None:
        """读一次 Wi-Fi / 热点状态并回调。"""
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

        manager = self._tethering_manager()
        hotspot_available = manager is not None and radio is not None
        hotspot_enabled = False
        if manager is not None:
            try:
                state = manager.tethering_operational_state
                if state == TetheringOperationalState.UNKNOWN:
                    # manager 绑定的连接已经失效，下一次重新创建。
                    self._drop_hotspot_manager()
                    hotspot_available = False
                else:
                    hotspot_enabled = state == TetheringOperationalState.ON
            except Exception:
                logger.warning("Reading the hotspot state failed", exc_info=True)
                self._drop_hotspot_manager()
                hotspot_available = False
        self._on_state(available, enabled, ssid, hotspot_available, hotspot_enabled)

    # ── Wi-Fi 开关 ────────────────────────────────────────────────
    def toggle_wifi(self) -> tuple[bool, str]:
        """切 Wi-Fi；返回 (是否成功, 失败原因)。"""
        if not _WINRT_AVAILABLE:
            return False, "Wi-Fi 控制不可用：缺少 winrt 依赖"
        radio = self._radio()
        if radio is None:
            self.poll()
            return False, "没有检测到 Wi-Fi 无线网卡"
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
        self.poll()
        return ok, message

    # ── 移动热点 ──────────────────────────────────────────────────
    def _drop_hotspot_manager(self) -> None:
        self._hotspot_manager = None
        self._hotspot_profile_id = ""

    def _tethering_manager(self) -> Any:
        """manager 是绑定在「当前 Internet 连接」上的，换了网络就得重新创建。"""
        if not _WINRT_AVAILABLE:
            return None
        try:
            profile = NetworkInformation.get_internet_connection_profile()
            if profile is None:
                # 没有联网时 Windows 也拿不到可共享的连接配置。
                self._drop_hotspot_manager()
                return None
            profile_id = str(getattr(profile, "connection_profile_name", "") or "")
            if (self._hotspot_manager is not None
                    and profile_id == self._hotspot_profile_id):
                return self._hotspot_manager
            manager = NetworkOperatorTetheringManager.create_from_connection_profile(
                profile)
            if manager is None:
                logger.info(
                    "Mobile hotspot manager is unavailable for profile %r", profile_id)
                self._drop_hotspot_manager()
                return None
            self._hotspot_manager = manager
            self._hotspot_profile_id = profile_id
        except Exception:
            logger.warning("Mobile hotspot is not available", exc_info=True)
            self._drop_hotspot_manager()
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

    def configure_hotspot(self, manager: Any) -> tuple[bool, str]:
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

    def toggle_hotspot(self) -> tuple[bool, str]:
        """切移动热点；返回 (是否成功, 失败原因)。"""
        if not _WINRT_AVAILABLE:
            return False, "移动热点不可用：缺少 winrt 依赖"
        manager = self._tethering_manager()
        if manager is None:
            self.poll()
            return False, "移动热点不可用：当前没有可共享的网络连接"
        ok = False
        message = ""
        turn_on = False
        try:
            turn_on = (
                manager.tethering_operational_state != TetheringOperationalState.ON)
            if turn_on:
                ready, ready_message = self._ensure_wifi_for_hotspot()
                if not ready:
                    self.poll()
                    return False, ready_message
                configured, config_message = self.configure_hotspot(manager)
                if not configured:
                    self.poll()
                    return False, config_message
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
                self._on_notify(
                    f"热点已开启：{HOTSPOT_SSID}，密码 {HOTSPOT_PASSWORD}", "success")
        else:
            # 下次重新根据当前网络连接创建 manager。
            self._drop_hotspot_manager()
        self.poll()
        return ok, message
