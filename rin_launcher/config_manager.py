"""Configuration store for Rin Launcher.

Owns ``config.yaml`` and exposes it to QML through camelCase ``@Slot`` methods
(QML resolves the Python attribute name, so the QML-facing API *is* camelCase —
there is no separate snake_case layer).

改动只发对应的信号（``launcherChanged`` / ``settingsChanged``），不再一律发
``configChanged``：小窗、设置页各自只关心一块数据，少一次全量刷新就少一次
重复解析与重排。
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
import weakref
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from PySide6.QtCore import (
    Property,
    QCoreApplication,
    QObject,
    Qt,
    QTimer,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QFileDialog

from rin_launcher import __codename__ as APP_CODENAME
from rin_launcher import __version__ as APP_VERSION
from rin_launcher import (
    app_mode,
    autostart,
    drives,
    logging_setup,
    notification_registration,
    notifications,
    risk_rules,
    search,
    shell_tweaks,
    start_menu,
    toast,
)
from rin_launcher import backups as backup_store
from rin_launcher.config_schema import (
    DEFAULT_SETTINGS,
    NOTIFY_CATEGORIES,
    NOTIFY_CHANNELS,
    _action_steps,
    _clamp_int,
    _derive_action_name,
    _new_slot,
    _slot_row,
)
from rin_launcher.config_watcher import ConfigWatcher as _ConfigWatcher
from rin_launcher.elevation import (
    is_admin,
    restart_application,
    restart_elevated_delayed,
)
from rin_launcher.icon_store import IconStore
from rin_launcher.system_theme import read_system_accent_color

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_DIR = Path.home() / "AppData" / "Roaming" / "RinLauncher"
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
BUNDLED_ICON_DIR = ASSETS_DIR / "icons" / "lawnicons"

# ── 常驻小窗的两块 ──────────────────────────────────────────────────
# 面板：一块「双行」的格子板（最多 PANEL_CAPACITY 格），小窗把它的槽位按行
# 平分渲染成上下两排；存储区：存储卡片 + 磁盘入口。槽位都写在 launcher.slots。
ROW_PANEL = 0        # 双行面板
ROW_STORAGE = 1      # 存储与磁盘
PANEL_CAPACITY = 10  # 面板最多固定几格

# 行语义随版本变化：<3 的配置里 0/1/2 是老的「常用应用 / 快捷功能 / 存储与
# 磁盘」，读入时按 ROW_ 常量迁到新模型（见 _normalize）。
CONFIG_VERSION = 3

SLOT_ACTION = "action"   # 一格完整的动作（程序 / 命令 / 网址 / 按键）
SLOT_TOOL = "tool"       # 内置功能
SLOT_PATH = "path"       # 打开任意文件 / 文件夹 / 磁盘
SLOT_USB = "usb"         # 自动检测的可移动磁盘

SLOT_KINDS: tuple = (SLOT_ACTION, SLOT_TOOL, SLOT_PATH, SLOT_USB)

# 内置功能。(key, 标题, Fluent 图标名)
TOOL_CATALOG: tuple = (
    ("launcherPage", "启动台设置", "ic_fluent_apps_20_regular"),
    ("settings", "设置", "ic_fluent_settings_20_regular"),
    ("configFolder", "配置目录", "ic_fluent_folder_open_20_regular"),
    ("configFile", "配置文件", "ic_fluent_document_text_20_regular"),
    ("reload", "重载配置", "ic_fluent_arrow_sync_20_regular"),
    ("elevate", "提权重启", "ic_fluent_shield_20_regular"),
    ("hide", "隐藏小窗", "ic_fluent_eye_off_20_regular"),
    ("quit", "退出程序", "ic_fluent_power_20_regular"),
)
TOOL_ICONS: dict[str, str] = {key: icon for key, _title, icon in TOOL_CATALOG}
TOOL_TITLES: dict[str, str] = {key: title for key, title, _icon in TOOL_CATALOG}

# 槽位 kind 的展示信息，给编辑器的下拉用。
SLOT_KIND_LABELS: dict[str, str] = {
    SLOT_ACTION: "动作",
    SLOT_TOOL: "内置功能",
    SLOT_PATH: "打开路径",
    SLOT_USB: "可移动磁盘（自动检测）",
}

# 槽位不再引用任何外部条目：动作直接写在槽位里（内联）。
ACTION_TYPES: tuple = ("file", "cmd", "url", "uwp", "keyboard")
# 旧版「键鼠模拟」已降级为「按键模拟」：读到旧类型名就迁成 keyboard，
# 旧字段 keymouse_steps 中的鼠标步骤直接跳过（执行端不再认识它）。
LEGACY_ACTION_TYPES: dict[str, str] = {"keymouse": "keyboard"}
# 用户自建图标的落盘目录（导入的 svg/png/ico、从程序里抽出来的图标都放这儿）。
ICON_STORE_NAME = "icons"
# 磁盘容量这种系统调用有成本；小窗每 2 秒轮询一次，缓存留 1.5 秒就够
# （同一次刷新里不重复问系统，又不会让插拔 U 盘等上半分钟）。
STORAGE_TTL = 1.5

# ── 备份 ────────────────────────────────────────────────────────
# 具体文件操作在 backups.py；这里只保留测试和界面会用到的常量别名。
AUTO_BACKUP_KEEP = backup_store.AUTO_KEEP


# 磁盘探测（卷标 / 类型 / 容量）已搬到 drives.py。保留同名别名，调用点与
# 测试都不用改；想单独测这部分纯函数直接 import rin_launcher.drives。
_human_size = drives.human_size
_drive_details = drives.drive_details
_find_removable_drive = drives.find_removable_drive
_list_drives = drives.list_drives
_removable_devices = drives.removable_devices


def _dir_writable(path: Path) -> bool:
    """试着往目录里写一个探针文件，判断能不能落盘（Program Files 下会给 False）。"""
    probe = path / ".write-test"
    try:
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def _migrate_legacy_data(data_dir: Path) -> None:
    """把老位置（%APPDATA%）的配置和图标拷进新的 data/ 目录；只在首次落地时做一次。"""
    if (data_dir / "config.yaml").exists():
        return
    old_config = DEFAULT_CONFIG_DIR / "config.yaml"
    if not old_config.is_file():
        return
    try:
        shutil.copy2(old_config, data_dir / "config.yaml")
        old_icons = DEFAULT_CONFIG_DIR / ICON_STORE_NAME
        if old_icons.is_dir():
            shutil.copytree(old_icons, data_dir / ICON_STORE_NAME, dirs_exist_ok=True)
    except OSError:
        logger.exception("迁移旧数据到 %s 失败，将使用全新数据目录", data_dir)
        return
    logger.info("已把旧数据从 %s 迁移到 %s", DEFAULT_CONFIG_DIR, data_dir)


def resolve_config_dir() -> Path:
    """决定这次运行用哪个数据目录。

    * 打包的 exe：exe 同级的 ``data/``（拷走文件夹数据就跟着走）；目录建不出来
      或不可写（例如被放进 Program Files）时退回 ``%APPDATA%\\RinLauncher``。
    * 源码运行：仍是 ``%APPDATA%\\RinLauncher``，开发习惯不变。
    """
    if not getattr(sys, "frozen", False):
        return DEFAULT_CONFIG_DIR
    data_dir = Path(sys.executable).resolve().parent / "data"
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        logger.warning("数据目录 %s 建不出来，回退到 %s", data_dir, DEFAULT_CONFIG_DIR)
        return DEFAULT_CONFIG_DIR
    if not _dir_writable(data_dir):
        logger.warning("数据目录 %s 不可写，回退到 %s", data_dir, DEFAULT_CONFIG_DIR)
        return DEFAULT_CONFIG_DIR
    _migrate_legacy_data(data_dir)
    return data_dir


# 字段默认值（DEFAULT_SETTINGS）与通知类别/渠道表都在 config_schema.py。


def _sanitize_inline_action(raw: Any) -> dict[str, Any] | None:
    """把外部写进来的内联动作修回可用状态；不合法（或为空）返回 None。"""
    if not isinstance(raw, dict):
        return None
    kind = str(raw.get("type") or "").strip()
    kind = LEGACY_ACTION_TYPES.get(kind, kind)
    if kind not in ACTION_TYPES:
        return None
    action: dict[str, Any] = {
        "type": kind,
        "target": str(raw.get("target") or ""),
        "arguments": str(raw.get("arguments") or ""),
        "working_dir": str(raw.get("working_dir") or ""),
        "run_as": "admin" if raw.get("run_as") == "admin" else "user",
        "keyboard_steps": [],
    }
    if kind == "keyboard":
        action["keyboard_steps"] = _action_steps(raw)
    return action


def _default_slots() -> list[dict[str, Any]]:
    """首次运行只生成一份空启动台，具体内容交给 OOBE / 用户自己添加。"""
    return []


def _default_config() -> dict[str, Any]:
    """Build a fresh default config."""
    return {
        "version": CONFIG_VERSION,
        "launcher": {
            "slots": _default_slots(),
            "storagePath": "",
        },
        "settings": dict(DEFAULT_SETTINGS),
        "notifications": notifications.defaults(),
    }


# 监听器在 config_watcher.py；ConfigManager 只在 startWatching 时用观察者。


class ConfigManager(QObject):
    """Loads/saves ``config.yaml`` and serves it to QML."""

    showToast = Signal(str, str)
    # 整份配置换了（外部修改 / 导入 / 重置）时发这一个。
    configChanged = Signal()
    # 分块信号：各页面只订阅自己关心的那一块，避免无谓重算。
    launcherChanged = Signal()
    settingsChanged = Signal()
    # The window / tray / hotkey owner listens to these and applies the change.
    hotkeyChanged = Signal(str)
    trayEnabledChanged = Signal(bool)
    # 强调色：三个窗口是独立 QML 引擎，靠这个信号让每个引擎各自更新 Theme。
    accentColorChanged = Signal(str)
    # 页面 / 窗口级的请求：QML 侧的页面够不到窗口对象，统一从这里转给 main.py。
    pageRequested = Signal(str)
    # 设置页分组跳转（标题栏「…」菜单里选一个分区）。
    settingsSectionRequested = Signal(str)
    # 任务计划状态的后台刷新完成（启动方式下拉据此回填真实值）。
    startupStateChanged = Signal()
    # 手动 / 自动备份完成后通知设置页刷新。
    backupChanged = Signal()
    # 通知渠道开关被改动（设置页的「通知」分区）。
    notificationsChanged = Signal()
    # 开始菜单扫描完成（后台线程回到主线程后发）。
    startMenuAppsChanged = Signal()
    # 加载态单独一个信号：缩略图批量刷新时不用带着整个列表重算。
    startMenuLoadingChanged = Signal()
    # 工作线程 → GUI 线程的内部通道；QTimer.singleShot 在工作线程里没有事件
    # 循环，不会触发，必须走队列信号。
    _startMenuScanDone = Signal(int, object)

    def __init__(self, config_dir: Path | None = None, parent: QObject | None = None,
                 app_mode_root: Path | None = None):
        super().__init__(parent)
        # 打包后数据目录是 exe 同级的 data/（不可写则回退 %APPDATA%），
        # 源码运行保持 %APPDATA%；首次切换到 data/ 时会把老数据迁过去。
        self.config_dir = Path(config_dir) if config_dir else resolve_config_dir()
        self.config_file = self.config_dir / "config.yaml"
        self.backup_dir = self.config_dir / "backups"
        self.icon_dir = self.config_dir / ICON_STORE_NAME
        self.log_dir = logging_setup.log_dir(self.config_dir)
        self.thumbnail_dir = self.config_dir / "thumbnails"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.icon_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.thumbnail_dir.mkdir(parents=True, exist_ok=True)

        self.action_executor = None
        # watchdog 的 Observer 是延迟导入的，这里只留一个不透明的句柄。
        self._observer: Any | None = None
        self._quiet_until = 0.0  # ignores the watcher echo of our own writes
        self._icons = IconStore(self.icon_dir, BUNDLED_ICON_DIR,
                                notify=self._icon_notify)
        # 磁盘容量缓存：(取值时间, 数据)。
        self._storage_cache: tuple[float, dict[str, Any]] | None = None
        # 可移动磁盘缓存：枚举驱动器有系统调用成本，刷新时只问一次。
        self._removable_cache: tuple[float, list[dict[str, Any]]] | None = None
        # 设置窗口刚建出来时信号可能还没接上，分类请求先存一份（见 takePendingSettingsSection）。
        self._pending_settings_section: str = ""
        # 托盘气泡的投递出口：main.py 在托盘真正起来之后接进来。
        self._tray_sink: Callable[[str, str], Any] | None = None
        # appmodset.conf：启动模式与发布通道的单一来源。
        values, problems, path = app_mode.load(app_mode_root)
        # 安装目录不可写时，OOBE 会把 first-run 写到用户数据目录；这里读回来，
        # 否则「完成了引导但下次还弹」。
        override = self.config_dir / app_mode.CONF_NAME
        if override.is_file():
            try:
                override_values, _, _ = app_mode.load(self.config_dir)
                values["first-run"] = override_values.get("first-run", values["first-run"])
            except OSError:
                logger.debug("读取用户目录 appmodset 覆盖失败", exc_info=True)
        self._app_mode_values = values
        self._app_mode_problems = problems
        self.app_mode_path = path
        self._config = self._load()
        # channel 由 appmodset.conf 决定；设置页的旧字段保留但不再覆盖它。
        self._config["settings"]["updateChannel"] = app_mode.effective_mode(values).channel
        # 开始菜单：扫描在后台线程里跑，结果回到主线程后才发给界面。
        self._start_menu_apps: list[dict[str, Any]] = []
        # 开始菜单磁盘缓存：全量扫描实测约 12 秒，不能每次开对话框都重扫。
        try:
            start_menu.set_cache_path(self.config_dir / "start-menu-cache.json")
        except Exception:
            logger.debug("设置开始菜单缓存路径失败", exc_info=True)
        self._start_menu_loading = False
        # 列表缓存：QML 每次读 startMenuApps 不再深拷贝几百条。
        self._start_menu_view: list[dict[str, Any]] | None = None
        self._start_menu_timeout = 0
        self._start_menu_token = 0
        self._thumb_queue: list[dict[str, Any]] = []
        self._thumb_timer: QTimer | None = None
        self._startMenuScanDone.connect(self._apply_start_menu_apps, Qt.QueuedConnection)
        # 任务计划状态不再在构造时预热：schtasks 子进程会跟小窗抢启动资源，
        # 等主界面稳定后由 main.py 延迟刷新（或第一次打开设置页时再查）。
        # 7 天一次的自动备份：启动先检查，之后每 6 小时再看一次。
        self._maybe_auto_backup()
        self._backup_timer = QTimer(self)
        self._backup_timer.setInterval(6 * 60 * 60 * 1000)
        self._backup_timer.timeout.connect(self._maybe_auto_backup)
        self._backup_timer.start()

        # 跟随系统强调色：注册表读取很轻，几秒一次就够；变化时通知所有窗口。
        self._last_system_accent = (
            read_system_accent_color()
            if self._config["settings"].get("accentColorMode") == "system" else "")
        self._accent_timer = QTimer(self)
        self._accent_timer.setInterval(6000)
        self._accent_timer.setTimerType(Qt.CoarseTimer)
        self._accent_timer.timeout.connect(self._poll_system_accent)
        self._accent_timer.start()

    @property
    def config(self) -> dict[str, Any]:
        return self._config

    @property
    def app_mode(self) -> app_mode.Mode:
        """本次启动的生效模式（含 appmodset.conf 的诊断信息）。"""
        return app_mode.effective_mode(self._app_mode_values)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _load(self) -> dict[str, Any]:
        if not self.config_file.exists():
            config = _default_config()
            self.save(config, changed="all")
            return config
        try:
            with open(self.config_file, encoding="utf-8") as handle:
                raw = yaml.safe_load(handle) or {}
            # _normalize 会就地把旧键 pop 掉，所以先记下「读到过旧库」。
            had_legacy_library = "actions" in raw or "categories" in raw
            raw_settings = raw.get("settings") or {}
            try:
                old_version = int(raw.get("version") or 1)
            except (TypeError, ValueError):
                old_version = 1
            new_keys = {
                "compactMode", "windowCorner", "windowOffsetX", "windowOffsetY",
                "compactTransparency", "miniTransparency",
                "backdropMode", "shortcutArrowGlobal",
            }
            needs_rewrite = (
                had_legacy_library
                or old_version != CONFIG_VERSION
                or "updateChannel" not in raw_settings
                or "autoCheckUpdates" not in raw_settings
                or "notifications" not in raw
                or bool(new_keys - set(raw_settings))
                or bool(set(raw_settings) - set(DEFAULT_SETTINGS))
            )
            config = self._normalize(raw)
            # 旧版「快捷操作」库 / 分区、已下线的设置项、缺失的新设置：
            # 读到就立刻写回一份干净的配置，不用等用户下次改设置。
            if needs_rewrite:
                self.save(config, changed="all")
            return config
        except Exception:
            logger.exception("Failed to read %s, falling back to defaults", self.config_file)
            return _default_config()

    def _normalize(self, data: dict[str, Any]) -> dict[str, Any]:
        # 版本号决定 launcher 的行语义：<3 是老的「三行」模型（0 常用应用 /
        # 1 快捷功能 / 2 存储与磁盘），>=3 是「双行面板」模型（0 面板 /
        # 1 存储与磁盘）。只在读入时迁移一次，下次写盘才落成新版本号。
        try:
            version = int(data.get("version") or 1)
        except (TypeError, ValueError):
            version = 1
        # 「快捷操作」已整体下线：旧配置里的动作库 / 分区不再读入，
        # 下一次写盘就会从 config.yaml 里消失。引用了动作库的旧槽位
        # 在 _normalize_slot 里因为拿不到内联动作而被丢弃。
        data.pop("actions", None)
        data.pop("categories", None)
        # settings keys added by newer builds get their default value
        raw_settings = dict(data.get("settings") or {})
        # 只保留当前版本认识的键：旧版遗留的 language / searchEngine /
        # gridColumns / itemSize / blurBackground 等不再读入，下次保存就消失。
        settings = {key: value for key, value in raw_settings.items()
                    if key in DEFAULT_SETTINGS}
        settings = {**DEFAULT_SETTINGS, **settings}
        # 强调色模式：旧配置没有这个键。旧版颜色选择器的默认可写回红色，
        # 读到 #ff0000 且没有显式模式时视为被写坏，迁到「跟随系统」。
        raw_mode = str(raw_settings.get("accentColorMode") or "").strip()
        if raw_mode not in ("system", "custom"):
            legacy_accent = str(raw_settings.get("accentColor") or "").lower()
            raw_mode = "system" if legacy_accent in ("", "#ff0000") else "custom"
        settings["accentColorMode"] = raw_mode
        if settings.get("updateMirror") not in ("github", "ghfast", "ghproxy"):
            settings["updateMirror"] = "github"
        settings["updateMirrorAuto"] = bool(settings.get("updateMirrorAuto", True))
        # 旧版「开机自动启动」布尔值迁进三态启动方式（关闭 / 登录时启动 / 管理员自启动）。
        if "startupMode" not in raw_settings and raw_settings.get("autoStart"):
            settings["startupMode"] = "normal"
        if settings.get("startupMode") not in ("off", "normal", "admin"):
            settings["startupMode"] = "off"
        if settings.get("updateChannel") not in ("stable", "prerelease"):
            settings["updateChannel"] = "stable"
        if settings.get("tileSize") not in ("small", "medium", "large"):
            settings["tileSize"] = "medium"
        if settings.get("compactMode") not in ("normal", "mini"):
            # 悬浮球已下线：旧配置里的 floating 退回迷你模式，其余非法值回完整模式。
            settings["compactMode"] = (
                "mini" if settings.get("compactMode") == "floating" else "normal")
        if settings.get("windowCorner") not in ("bottom-right", "bottom-left"):
            settings["windowCorner"] = "bottom-right"
        if settings.get("backdropMode") not in ("auto", "mica", "acrylic"):
            settings["backdropMode"] = "auto"
        settings["windowOffsetX"] = _clamp_int(settings.get("windowOffsetX"), 0, -2000, 2000)
        settings["windowOffsetY"] = _clamp_int(settings.get("windowOffsetY"), 0, -2000, 2000)
        for key, default in (("compactTransparency", 82),
                             ("miniTransparency", 30)):
            settings[key] = _clamp_int(settings.get(key), default, 0, 90)
        settings["shortcutArrowGlobal"] = bool(settings.get("shortcutArrowGlobal", True))
        settings["autoCheckUpdates"] = bool(settings.get("autoCheckUpdates", True))
        data["settings"] = settings
        # 通知开关：按类别补齐渠道，写坏的键直接忽略（旧配置没有这一段）。
        data["notifications"] = notifications.normalize(data.get("notifications"))
        # launcher 段必须一起规范化：旧格式迁移、坏槽位剔除、内联动作清洗
        # 都靠这一句，漏掉它读回来的就是没洗过的原始字典。
        data["launcher"] = self._normalize_launcher(data, legacy_rows=version < CONFIG_VERSION)
        data["version"] = CONFIG_VERSION
        return data

    def _normalize_launcher(self, data: dict[str, Any],
                            legacy_rows: bool = False) -> dict[str, Any]:
        """把 launcher 段补成合法槽位列表，并兼容旧版（固定 apps/tools）格式。"""
        raw = data.get("launcher") or {}
        slots = self._migrate_slots(raw, legacy_rows)
        return {
            "slots": [slot for slot in slots if slot["kind"] in SLOT_KINDS],
            "storagePath": str(raw.get("storagePath") or ""),
        }

    def _migrate_slots(self, raw: dict[str, Any],
                       legacy_rows: bool = False) -> list[dict]:
        """产出槽位列表。

        ``launcher.slots`` 是新格式；只有 ``apps`` / ``tools`` 的老配置按老结构
        逐格翻译成槽位，空位直接丢掉（新模型里「空位」没有意义）。
        ``legacy_rows`` 为真时按老的「三行」语义迁移：第一行 + 第二行合并成面板
        （第一行的内容排前面），第三行变成存储区。
        """
        if isinstance(raw.get("slots"), list) and raw["slots"]:
            items = list(raw["slots"])
            if legacy_rows:
                # 稳定按原行号排序：老配置里第一行（0）的槽位要排在第二行（1）
                # 前面，合并进面板后顺序才符合用户的直觉。
                items = [item for _index, item in sorted(
                    enumerate(items), key=lambda pair: _slot_row(pair[1], pair[0]))]
            slots: list[dict[str, Any]] = []
            for index, item in enumerate(items):
                slot = self._normalize_slot(item, index, legacy_rows)
                if slot is not None:
                    slots.append(slot)
            panel_count = sum(1 for slot in slots if slot["row"] == ROW_PANEL)
            if panel_count > PANEL_CAPACITY:
                logger.warning("Panel has %d slots, only %d are shown",
                               panel_count, PANEL_CAPACITY)
            return slots

        if not raw:
            return _default_slots()

        # ── 旧格式迁移 ──
        # 老配置的 apps 引用的是已经下线的快捷操作库，没法再还原成内联动作，
        # 直接跳过；老「功能按钮」里还在 catalog 的照常保留。
        migrated: list[dict[str, Any]] = []
        for key in raw.get("tools") or []:
            if key in TOOL_ICONS:
                migrated.append(_new_slot(SLOT_TOOL, ROW_PANEL, key=str(key)))
        # 老配置里那个「U 盘」按钮变成独立的 usb 槽位。
        migrated.append(_new_slot(SLOT_USB, ROW_STORAGE, label="U 盘"))
        if not migrated:
            return _default_slots()
        return migrated

    def _normalize_slot(self, item: Any, index: int,
                        legacy_rows: bool = False) -> dict[str, Any] | None:
        """把外部写坏的槽位修回可用状态；实在修不了就丢掉（返回 None）。"""
        if not isinstance(item, dict):
            return None
        kind = str(item.get("kind") or "").strip()
        if kind not in SLOT_KINDS:
            return None

        row = _slot_row(item, index)
        if legacy_rows:
            # 老模型 0/1 是两块独立内容，都并进面板；第三行之后归存储区。
            row = ROW_PANEL if row <= 1 else ROW_STORAGE
        else:
            row = ROW_PANEL if row <= ROW_PANEL else ROW_STORAGE

        slot = _new_slot(kind, row)
        slot["label"] = str(item.get("label") or "")
        slot["icon"] = str(item.get("icon") or "")
        if kind == SLOT_ACTION:
            # 动作必须自带完整定义：引用动作库的老槽位（只有 ref）已经没法还原，
            # 直接丢弃，避免小窗上留下一个点了没反应的格子。
            inline = _sanitize_inline_action(item.get("action"))
            if inline is None:
                return None
            slot["action"] = inline
        elif kind == SLOT_TOOL:
            key = str(item.get("key") or "")
            if key not in TOOL_ICONS:   # 老配置里可能留着已经下线的 key
                return None
            slot["key"] = key
        elif kind == SLOT_PATH:
            slot["path"] = str(item.get("path") or "")
            target = Path(slot["path"]).expanduser() if slot["path"] else None
            path_type = str(item.get("pathType") or "")
            if path_type not in ("disk", "file"):
                path_type = "file" if target and target.is_file() else "disk"
            slot["pathType"] = path_type
        return slot

    def save(self, config: dict[str, Any] | None = None, *, changed: str = "all") -> bool:
        """落盘。

        ``changed`` 指哪一块变了：``launcher`` / ``settings`` / ``all``，
        据此只发对应的信号。
        """
        if config is not None:
            self._config = config
        self._storage_cache = None
        try:
            if self.config_file.exists():
                self._rotate_backups()
            self._quiet_until = time.monotonic() + 1.0
            with open(self.config_file, "w", encoding="utf-8") as handle:
                yaml.dump(self._config, handle, allow_unicode=True, sort_keys=False, indent=2)
        except Exception:
            logger.exception("Failed to write %s", self.config_file)
            return False

        if changed == "all":
            self.configChanged.emit()
            self.launcherChanged.emit()
            self.settingsChanged.emit()
        elif changed == "launcher":
            self.launcherChanged.emit()
        elif changed == "settings":
            self.settingsChanged.emit()
        return True

    def _rotate_backups(self, keep: int = 10) -> None:
        backup_store.rotate(self.backup_dir, self.config_file, keep)

    # ------------------------------------------------------------------
    # Backups (manual + 7-day automatic)
    # ------------------------------------------------------------------
    def _create_backup(self, *, manual: bool, silent: bool = False) -> str:
        if not self.config_file.is_file():
            return ""
        target = backup_store.create(self.backup_dir, self.config_file, manual=manual)
        if target is None:
            if not silent:
                self.showToast.emit("备份失败，可以看看日志", "error")
            return ""

        if not manual:
            try:
                keep = max(1, int(self._config["settings"].get(
                    "autoBackupKeep", AUTO_BACKUP_KEEP)))
            except (TypeError, ValueError):
                keep = AUTO_BACKUP_KEEP
            backup_store.prune_auto(self.backup_dir, keep)
        self.backupChanged.emit()
        if not silent:
            self.showToast.emit(
                "已创建手动备份" if manual else "已创建自动备份", "success")
        logger.info("Created %s backup: %s", "manual" if manual else "auto", target)
        return str(target)

    def _backup_interval_days(self) -> int:
        try:
            return max(1, int(self._config["settings"].get("autoBackupIntervalDays", 7)))
        except (TypeError, ValueError):
            return 7

    def _maybe_auto_backup(self) -> None:
        """按设置里的间隔补一份自动备份；启动与每 6 小时各检查一次。"""
        if not bool(self._config["settings"].get("autoBackupEnabled", True)):
            return
        age = backup_store.newest_age_seconds(self.backup_dir)
        if age is not None and age < self._backup_interval_days() * 24 * 60 * 60:
            return
        self._create_backup(manual=False, silent=True)

    @Slot(result=str)
    def backupNow(self) -> str:
        """手动备份一份配置，返回备份文件路径（失败为空串）。"""
        return self._create_backup(manual=True)

    @Slot(result="QVariantMap")
    def getBackupInfo(self) -> dict[str, Any]:
        info = backup_store.describe(self.backup_dir)
        info.update({
            "dir": str(self.backup_dir),
            "autoKeep": AUTO_BACKUP_KEEP,
            "autoEnabled": bool(self._config["settings"].get("autoBackupEnabled", True)),
            "intervalDays": self._backup_interval_days(),
            "keepCount": int(self._config["settings"].get("autoBackupKeep", AUTO_BACKUP_KEEP)),
        })
        return info

    @Slot()
    def openBackupFolder(self) -> None:
        self._reveal(self.backup_dir)

    # ── 备份恢复 ──────────────────────────────────────────────────────
    @Slot(result="QVariantList")
    def listBackups(self) -> list[dict[str, Any]]:
        """最近的备份（手动 + 自动），按时间倒序，供设置页列表用。"""
        return [
            {
                "name": entry["name"],
                "manual": entry["manual"],
                "size": _human_size(entry["size"]),
                "time": entry["time"],
            }
            for entry in backup_store.list_entries(self.backup_dir)
        ]

    @Slot(str, result=bool)
    def restoreBackup(self, name: str) -> bool:
        """用指定备份覆盖配置。只认 backups 目录里的 .yaml，恢复前先兜底一份。"""
        file_name = Path(str(name or "")).name
        target = self.backup_dir / file_name
        if not file_name or target.suffix != ".yaml" or not target.is_file():
            self.showToast.emit("找不到这份备份", "warning")
            return False
        try:
            with open(target, encoding="utf-8") as handle:
                data = yaml.safe_load(handle) or {}
        except (OSError, yaml.YAMLError):
            logger.exception("备份无法解析: %s", target)
            self.showToast.emit("这份备份读不出来，原配置没有改动", "error")
            return False
        if not isinstance(data, dict) or "launcher" not in data:
            self.showToast.emit("这不是 Rin Launcher 的配置备份", "warning")
            return False
        # 先把当前配置存一份手动备份：恢复错了还能退回来。
        self._create_backup(manual=True, silent=True)
        self._config = self._normalize(dict(data))
        if not self.save(changed="all"):
            self.showToast.emit("恢复失败，原配置未改动", "error")
            return False
        self.accentColorChanged.emit(self.accentColor)
        logger.info("Restored backup %s", target.name)
        self.showToast.emit("已恢复备份", "success")
        return True

    @Slot(str, result=bool)
    def deleteBackup(self, name: str) -> bool:
        file_name = Path(str(name or "")).name
        target = self.backup_dir / file_name
        if not file_name or target.suffix != ".yaml" or not target.is_file():
            return False
        try:
            target.unlink()
        except OSError:
            logger.exception("Failed to delete backup %s", target)
            self.showToast.emit("备份删不掉，可能正在被占用", "error")
            return False
        self.backupChanged.emit()
        self.showToast.emit("已删除备份", "success")
        return True

    @Slot(result="QVariantMap")
    def clearBackups(self) -> dict[str, Any]:
        """清空全部备份；返回最新的存储占用。"""
        removed = backup_store.clear(self.backup_dir)
        self.backupChanged.emit()
        self.showToast.emit(f"已删除 {removed} 份备份", "success" if removed else "info")
        return self.getStorageUsage()

    # ── 日志 ──────────────────────────────────────────────────────────
    @Slot(result=str)
    def exportLogs(self) -> str:
        """把最近 30 天日志打包成 zip；返回路径（没有日志时为空串）。"""
        target = logging_setup.export(self.config_dir, logging_setup.KEEP_DAYS)
        if target is None:
            self.showToast.emit("还没有日志可以打包", "warning")
            return ""
        self.showToast.emit(f"日志已打包：{target.name}", "success")
        self._reveal(target)
        return str(target)

    @Slot()
    def openLogFolder(self) -> None:
        self._reveal(self.log_dir)

    @Slot(result=bool)
    def clearLogs(self) -> bool:
        """删除历史日志（当前正在写的文件会被跳过）。"""
        removed = 0
        for path in self.log_dir.glob(logging_setup.FILE_GLOB):
            try:
                path.unlink()
                removed += 1
            except OSError:
                logger.debug("无法删除日志 %s", path, exc_info=True)
        self.showToast.emit(
            f"已清理 {removed} 个日志文件" if removed else "没有可清理的日志",
            "success" if removed else "info")
        return True

    # ── 存储占用 / 诊断 ──────────────────────────────────────────────
    def _app_root(self) -> Path:
        """安装目录：打包后是 exe 同级，源码是仓库根目录。"""
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent
        return Path(__file__).resolve().parent.parent

    @Slot(result="QVariantMap")
    def getStorageUsage(self) -> dict[str, Any]:
        def usage(directory: Path, pattern: str) -> tuple[int, int]:
            count = size = 0
            for path in directory.glob(pattern):
                if not path.is_file():
                    continue
                count += 1
                try:
                    size += path.stat().st_size
                except OSError:
                    pass
            return count, size

        log_count, log_size = usage(self.log_dir, logging_setup.FILE_GLOB)
        backup_count, backup_size = usage(self.backup_dir, "config-*.yaml")
        return {
            "configDir": str(self.config_dir),
            "logDir": str(self.log_dir),
            "logCount": log_count,
            "logSize": _human_size(log_size),
            "backupCount": backup_count,
            "backupSize": _human_size(backup_size),
        }

    @Slot(result=bool)
    def copyDiagnostics(self) -> bool:
        """把关于页展示的诊断信息复制到剪贴板。"""
        text = str(self.getRuntimeInfo().get("diagnostics") or "")
        if not text or not self.copyText(text):
            return False
        self.showToast.emit("诊断信息已复制", "success")
        return True

    @Slot(str, result=bool)
    def copyText(self, text: str) -> bool:
        """把一段文本复制到剪贴板（更新页复制错误详情等）。"""
        value = str(text or "").strip()
        if not value:
            return False
        clipboard = QGuiApplication.clipboard()
        if clipboard is None:
            return False
        clipboard.setText(value)
        return True

    def _write_to(self, path: Path) -> bool:
        try:
            with open(path, "w", encoding="utf-8") as handle:
                yaml.dump(self._config, handle, allow_unicode=True, sort_keys=False, indent=2)
            return True
        except OSError:
            logger.exception("Failed to export config to %s", path)
            return False

    def _read_from(self, path: Path) -> bool:
        try:
            with open(path, encoding="utf-8") as handle:
                data = yaml.safe_load(handle) or {}
        except (OSError, yaml.YAMLError):
            logger.exception("Failed to import config from %s", path)
            return False
        self._config = self._normalize(data)
        return self.save(changed="all")

    # ------------------------------------------------------------------
    # Read API (called from QML)
    # ------------------------------------------------------------------
    @Slot(result="QVariantMap")
    def getSettings(self) -> dict[str, Any]:
        """A detached copy, so the settings dialog can edit it before saving."""
        return dict(self._config["settings"])

    @Property(str, notify=accentColorChanged)
    def accentColor(self) -> str:
        """当前强调色（``#RRGGBB``）；跟随系统时实时读 Windows 设置。"""
        settings = self._config["settings"]
        if settings.get("accentColorMode", "custom") == "system":
            system = read_system_accent_color()
            if system:
                return system
        value = str(settings.get("accentColor") or "")
        return value or str(DEFAULT_SETTINGS["accentColor"])

    # ── 启动台槽位 ────────────────────────────────────────────────────
    def _resolve_slot(self, slot: dict[str, Any]) -> dict[str, Any] | None:
        """把槽位解析成界面直接能画的一条数据；动作不完整时返回 None。"""
        kind = slot["kind"]
        resolved = dict(slot)
        override_icon = slot.get("icon") or ""
        override_label = slot.get("label") or ""

        if kind == SLOT_ACTION:
            inline = slot.get("action")
            if not isinstance(inline, dict) or not inline:
                return None
            resolved.update(
                name=override_label or _derive_action_name(inline),
                icon=override_icon or "",
                type=inline.get("type", ""),
                target=inline.get("target", ""),
                arguments=inline.get("arguments", ""),
                working_dir=inline.get("working_dir", ""),
                keyboard_steps=inline.get("keyboard_steps") or [],
                admin=inline.get("run_as") == "admin",
                inlineAction=True,
            )
        elif kind == SLOT_TOOL:
            key = slot.get("key", "")
            resolved.update(
                name=override_label or TOOL_TITLES.get(key, key),
                icon=override_icon or TOOL_ICONS.get(key, ""),
            )
        elif kind == SLOT_PATH:
            raw = str(slot.get("path") or "")
            expanded = str(Path(raw).expanduser()) if raw else ""
            target = Path(expanded) if expanded else None
            exists = bool(target) and target.exists()
            is_file = bool(target) and target.is_file()
            path_type = str(slot.get("pathType") or ("file" if is_file else "disk"))
            total_text = free_text = ""
            percent = 0
            usage_path = target.parent if is_file and target is not None else target
            if exists and usage_path is not None:
                try:
                    usage = shutil.disk_usage(usage_path)
                except OSError:
                    logger.debug("Cannot read usage of %s", usage_path)
                else:
                    total_text = _human_size(usage.total)
                    free_text = _human_size(usage.free)
                    percent = round(usage.used / usage.total * 100) if usage.total else 0
            resolved.update(
                name=override_label or (
                    target.name if target else "未设置路径"),
                icon=override_icon or (
                    "ic_fluent_document_20_regular" if is_file
                    else "ic_fluent_folder_open_20_regular"),
                path=expanded,
                pathType=path_type,
                isFile=is_file,
                exists=exists,
                total=total_text,
                free=free_text,
                percent=percent,
            )
        elif kind == SLOT_USB:
            device = self._removable_devices()
            first = device[0] if device else {}
            resolved.update(
                name=override_label or str(first.get("name") or "U 盘"),
                icon=override_icon or "ic_fluent_usb_plug_20_regular",
                path=str(first.get("path") or ""),
                paths=list(first.get("paths") or []),
                partitions=list(first.get("partitions") or []),
                total=str(first.get("total") or ""),
                free=str(first.get("free") or ""),
                percent=int(first.get("percent") or 0),
                exists=bool(first),
                available=bool(first),
            )
        if resolved.get("inlineAction"):
            resolved["kindLabel"] = "动作"
        else:
            resolved["kindLabel"] = SLOT_KIND_LABELS.get(kind, kind)
        return resolved

    @Slot(result="QVariantList")
    def getLauncherSlots(self) -> list[dict]:
        """小窗要画的所有槽位（按配置顺序，带 row）；引用失效的会被跳过。

        结果里带上 ``rowIndex``（这一格在本行**原始**列表里的序号）：界面上显示的
        是解析后的列表，编辑 / 删除时要用原始下标才能对上配置里的同一个对象。
        """
        resolved = []
        row_counters: dict[int, int] = {}
        for slot in self._config["launcher"]["slots"]:
            row = int(slot.get("row", 0))
            index = row_counters.get(row, 0)
            row_counters[row] = index + 1
            item = self._resolve_slot(slot)
            if item is not None:
                item["rowIndex"] = index
                resolved.append(item)
        return resolved

    @Slot(result="QVariantList")
    def getToolCatalog(self) -> list[dict]:
        return [{"key": key, "title": title, "icon": icon}
                for key, title, icon in TOOL_CATALOG]

    @Slot(result="QVariantList")
    def getDrives(self) -> list[dict]:
        """本机磁盘列表，给「磁盘」槽位的选择器用。"""
        return _list_drives()

    @Slot(result="QVariantList")
    def getRawLauncherSlots(self) -> list[dict]:
        """编辑器用的原始槽位（不做解析），编辑时要按 row 分组的原始下标。"""
        return [dict(slot) for slot in self._config["launcher"]["slots"]]

    @Slot(result=str)
    def getLauncherStoragePath(self) -> str:
        """第三行那张存储卡片配置的目录（原始值，空串表示用主目录）。"""
        return str(self._config["launcher"].get("storagePath") or "")

    @Slot(result="QVariantMap")
    def getStorageInfo(self) -> dict[str, Any]:
        """第三行的存储卡片：路径、显示名与容量。结果带短缓存，避免反复问系统。

        盘根显示卷标（如 ``课件``），普通文件夹显示目录名 —— 两者都不显示盘符。
        配置的路径不可用时只标记 ``available=False``，不再偷偷换成主目录，免得
        用户以为自己在看另一块盘。
        """
        now = time.monotonic()
        if self._storage_cache and now - self._storage_cache[0] < STORAGE_TTL:
            return self._storage_cache[1]

        path = self._storagePath()
        drive = _drive_details(path)
        label = (drive.get("label") or drive.get("kindLabel") or "磁盘") if drive \
            else (path.name or str(path))
        info: dict[str, Any] = {
            "path": str(path),
            "label": label,
            "isDrive": bool(drive),
            "drive": drive.get("root", ""),
            "kind": drive.get("kind", ""),
            "kindLabel": drive.get("kindLabel", ""),
            "free": "",
            "total": "",
            "percent": 0,
            "available": False,
        }
        try:
            usage = shutil.disk_usage(path)
        except OSError:
            logger.warning("Cannot read disk usage of %s", path)
        else:
            info["available"] = True
            info["free"] = _human_size(usage.free)
            info["total"] = _human_size(usage.total)
            info["percent"] = round(usage.used / usage.total * 100) if usage.total else 0

        self._storage_cache = (now, info)
        return info

    @Slot(result="QVariantMap")
    def refreshStorageInfo(self) -> dict[str, Any]:
        """丢掉缓存重新读一次（磁盘挂载/卸载后手动刷新用）。"""
        self._storage_cache = None
        return self.getStorageInfo()

    def _storagePath(self) -> Path:
        """存储卡片配置的路径；留空表示用户主目录。"""
        raw = str(self._config["launcher"].get("storagePath") or "").strip()
        return Path(raw).expanduser() if raw else Path.home()

    @Slot(result=str)
    def pickFolder(self) -> str:
        path = QFileDialog.getExistingDirectory(None, "选择文件夹", str(Path.home()))
        return path or ""

    @Slot(str)
    def openPath(self, path: str) -> None:
        target = Path(path).expanduser()
        if not target.exists():
            self.showToast.emit(f"路径不存在：{target}", "warning")
            return
        self._reveal(target)

    @Slot(str, result=bool)
    def openSlot(self, path: str) -> bool:
        """打开一个 path 类槽位的目标，找不到就报一句。"""
        if not path:
            self.showToast.emit("这一格还没有设置目标", "warning")
            return False
        target = Path(path).expanduser()
        if not target.exists():
            self.showToast.emit(f"路径不存在：{target}", "warning")
            return False
        self._reveal(target)
        return True

    def _removable_devices(self) -> list[dict[str, Any]]:
        """可移动磁盘（按物理设备分组），带短缓存。"""
        now = time.monotonic()
        if self._removable_cache and now - self._removable_cache[0] < STORAGE_TTL:
            return self._removable_cache[1]
        devices = _removable_devices()
        self._removable_cache = (now, devices)
        return devices

    @Slot(result="QVariantList")
    def getRemovableDevices(self) -> list[dict]:
        """U 盘设备列表：设备名、合并容量与全部分区。"""
        return [dict(item) for item in self._removable_devices()]

    @Slot(result=bool)
    def openRemovableDrive(self) -> bool:
        """打开第一个 U 盘（含多分区）的全部盘符。"""
        devices = self._removable_devices()
        paths = list(devices[0].get("paths") or []) if devices else []
        if not paths:
            self.showToast.emit("没有检测到可移动磁盘", "warning")
            return False
        for raw in paths:
            path = Path(raw)
            if path.exists():
                self._reveal(path)
        return True

    # ── 图标 ──────────────────────────────────────────────────────────
    @Slot(result="QStringList")
    def getBundledIcons(self) -> list[str]:
        """Names of the icon marks shipped under assets/icons/lawnicons."""
        return self._icons.bundled()

    @Slot(result="QVariantList")
    def getCustomIcons(self) -> list[dict]:
        """用户自己的图标库：导入的位图/矢量 + 从程序里抽出来的。"""
        return self._icons.custom()

    def _icon_notify(self, message: str, severity: str) -> None:
        self.showToast.emit(message, severity)

    def _import_icon_file(self, path: str, notify: bool = True) -> str:
        """把一张图片（svg / png / ico / …）复制进图标库，返回它的 icon key。"""
        return self._icons.import_file(path, notify=notify)

    @Slot(result=str)
    def importIcon(self) -> str:
        """把用户挑的图片复制进图标库，返回它的 icon key。"""
        path = IconStore.pick_image()
        return self._import_icon_file(path) if path else ""

    def _icon_from_path(self, source: Path, notify: bool) -> str:
        """从一个具体文件取图标；取不到返回空串。"""
        return self._icons.from_path(source, notify)

    def _extract_icon_file(self, path: str, notify: bool = True) -> str:
        """从程序 / 快捷方式 / DLL 里抽出图标，落成文件存进图标库。"""
        return self._icons.extract(path, notify=notify)

    @Slot(str, result=str)
    def acquireIcon(self, path: str) -> str:
        """「从文件获取图标」的统一入口：程序走提取，图片走导入。

        支持 exe / dll / lnk（跟随快捷方式目标）与 ico / svg / png / jpg / bmp。
        """
        return self._icons.acquire(path)

    @Slot(result=str)
    def pickIconSource(self) -> str:
        """挑一个「图标来源」文件：程序、快捷方式或图片都行。"""
        return IconStore.pick_source()

    @Slot(str, result=bool)
    def deleteCustomIcon(self, key: str) -> bool:
        """删掉图标库里的一张图；配置里还在引用它的地方会退回默认图标。"""
        return self._icons.delete(key)

    # ------------------------------------------------------------------
    # Write API (called from QML)
    # ------------------------------------------------------------------
    # ── 槽位编辑 ──────────────────────────────────────────────────────
    def _slots(self) -> list[dict[str, Any]]:
        return self._config["launcher"]["slots"]

    def _build_slot(self, kind: str, row: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        """按编辑器提交的表单拼一个合法槽位；kind 决定保留哪些字段。

        拼不出合法槽位时返回 None（调用方拒绝这次写入）。动作槽位必须带自己
        的完整定义 —— 以前缺内容时会静默换成「第一个条目」，相当于把用户刚
        填的东西吃掉，所以现在宁可保存失败也不替换。
        """
        created = _new_slot(kind, row)
        created["label"] = str(payload.get("label") or "")
        created["icon"] = str(payload.get("icon") or "")
        if kind == SLOT_ACTION:
            inline = _sanitize_inline_action(payload.get("action"))
            if inline is None:
                return None
            created["action"] = inline
        elif kind == SLOT_TOOL:
            key = str(payload.get("key") or "")
            if key not in TOOL_ICONS:
                return None
            created["key"] = key
        elif kind == SLOT_PATH:
            path = str(payload.get("path") or "").strip()
            if not path:
                return None
            target = Path(path).expanduser()
            path_type = str(payload.get("pathType") or "").strip()
            if path_type not in ("disk", "file"):
                path_type = "file" if target.is_file() else "disk"
            created["path"] = path
            created["pathType"] = path_type

        # 没指定图标时替程序 / 快捷方式抽一张，省得小窗上全是空白格子。
        # 抽图标是「顺手好事」，不能因为它失败就毁掉整个保存。
        try:
            self._auto_fill_icon(created)
        except Exception:
            logger.exception("Auto icon extraction failed for %r", created.get("label"))
        return created

    def _auto_fill_icon(self, slot: dict[str, Any]) -> None:
        """槽位没图标时，试着从它的目标文件里抽一张（只认程序 / 快捷方式）。"""
        if slot.get("icon"):
            return
        action = slot.get("action") if slot["kind"] == SLOT_ACTION else None
        if isinstance(action, dict) and action.get("type") == "file":
            target = str(action.get("target") or "").strip().strip('"')
        elif slot["kind"] == SLOT_PATH:
            target = str(slot.get("path") or "")
        else:
            return
        # 带占位符 / 环境变量的目标现在解不出来，抽图标留到下次编辑再说。
        if not target or "{" in target or "%" in target:
            return
        path = Path(target).expanduser()
        if not path.is_file() or path.suffix.lower() not in (".exe", ".lnk", ".ico"):
            return
        key = self._extract_icon_file(str(path), notify=False)
        if key:
            slot["icon"] = key

    def _panel_slots(self) -> list[dict[str, Any]]:
        """面板上的槽位（小窗按行平分渲染成上下两排）。"""
        return [slot for slot in self._slots() if slot["row"] == ROW_PANEL]

    def _panel_full(self) -> bool:
        return len(self._panel_slots()) >= PANEL_CAPACITY

    @Slot(result="QVariantMap")
    def getLauncherPanelUsage(self) -> dict[str, Any]:
        """面板的容量与占用，给编辑器判断「还能不能再加一格」。"""
        return {"capacity": PANEL_CAPACITY, "used": len(self._panel_slots())}

    @Slot(int, "QVariantMap", result=bool)
    def addLauncherSlot(self, row: int, slot: dict) -> bool:
        """在面板末尾追加一格（或给存储区加一个入口）。面板满时拒绝并提示。"""
        slot = dict(slot)
        kind = str(slot.get("kind") or SLOT_ACTION)
        if kind not in SLOT_KINDS or kind == SLOT_USB:
            # U 盘入口由迷你模式的快捷开关自动提供，不再允许手动新增。
            return False
        row = ROW_PANEL if int(row) <= ROW_PANEL else ROW_STORAGE
        if row == ROW_STORAGE:
            # 存储行两张卡片（存储位置 + U 盘）钉死：不新增、不删除、不移动。
            return False
        if row == ROW_PANEL and self._panel_full():
            self.showToast.emit(f"面板最多放 {PANEL_CAPACITY} 格，先删一格再加。", "warning")
            return False
        built = self._build_slot(kind, row, slot)
        if built is None:
            return False
        self._slots().append(built)
        return self.save(changed="launcher")

    @Slot(int, int, "QVariantMap", result=bool)
    def updateLauncherSlot(self, row: int, index: int, slot: dict) -> bool:
        """改第 ``row`` 行第 ``index`` 个槽位（index 是该行内的原始序号）。

        类型也可以改：``kind`` 变了就按新类型重建字段，旧的无关字段会被丢掉。
        """
        target = self._row_slot(row, index)
        if target is None or int(row) == ROW_STORAGE:
            # 存储行只允许通过 setLauncherStoragePath 改路径，卡片本身不动。
            return False
        slot = dict(slot)
        # 已经存在的 U 盘槽位保持只读：允许删除，但不能改成别的类型，
        # 也不能把别的格子改成 U 盘。
        if target.get("kind") == SLOT_USB:
            return False
        kind = str(slot.get("kind") or target.get("kind") or SLOT_ACTION)
        if kind not in SLOT_KINDS or kind == SLOT_USB:
            return False
        updated = self._build_slot(kind, int(target.get("row", 0)), slot)
        if updated is None:
            return False
        target.clear()
        target.update(updated)
        return self.save(changed="launcher")

    @Slot(int, int, result=bool)
    def deleteLauncherSlot(self, row: int, index: int) -> bool:
        target = self._row_slot(row, index)
        if target is None or int(row) == ROW_STORAGE:
            return False
        self._slots().remove(target)
        return self.save(changed="launcher")

    @Slot(int, int, int, result=bool)
    def moveLauncherSlot(self, row: int, index: int, delta: int) -> bool:
        """在第 ``row`` 行内前后挪一格。"""
        target = self._row_slot(row, index)
        if target is None or int(row) == ROW_STORAGE:
            return False
        slots = self._slots()
        position = slots.index(target)
        peers = [i for i, s in enumerate(slots) if s["row"] == row]
        order = peers.index(position)
        target_order = order + delta
        if not 0 <= target_order < len(peers):
            return False
        # 和同行的另一格交换位置，行内顺序就是列表顺序。
        other = peers[target_order]
        slots[position], slots[other] = slots[other], slots[position]
        return self.save(changed="launcher")

    def _row_slot(self, row: int, index: int) -> dict[str, Any] | None:
        """按「行的第几个」定位槽位，返回列表里的同一个对象（可直接改）。"""
        peers = [slot for slot in self._slots() if slot["row"] == row]
        if not 0 <= index < len(peers):
            return None
        return peers[index]

    @Slot(str, result=bool)
    def setLauncherStoragePath(self, path: str) -> bool:
        self._config["launcher"]["storagePath"] = str(path or "")
        return self.save(changed="launcher")

    @Slot("QVariantMap", result=bool)
    def updateSettings(self, settings: dict) -> bool:
        settings = dict(settings)
        previous = self._config["settings"]
        old_accent = str(previous.get("accentColor") or "")
        old_mode = str(previous.get("accentColorMode") or "")

        # 启动方式不走这里：三态切换要碰注册表 / 任务计划，走 setStartupMode()。
        settings.pop("autoStart", None)
        settings.pop("startupMode", None)

        previous.update(settings)
        saved = self.save(changed="settings")

        if saved:
            if "globalHotkey" in settings:
                self.hotkeyChanged.emit(str(previous["globalHotkey"]))
            if "showTray" in settings:
                self.trayEnabledChanged.emit(bool(previous["showTray"]))
            if "shortcutArrowGlobal" in settings:
                self.applyShellPreferences()
            if any(key in settings for key in (
                    "compactMode", "windowCorner", "windowOffsetX", "windowOffsetY",
                    "compactTransparency", "miniTransparency",
                    "backdropMode")):
                self.settingsChanged.emit()
            mode_changed = ("accentColorMode" in settings
                            and self._config["settings"].get("accentColorMode") != old_mode)
            if mode_changed or ("accentColor" in settings
                                and self.accentColor != old_accent):
                if self._config["settings"].get("accentColorMode") == "system":
                    self._last_system_accent = read_system_accent_color()
                self.accentColorChanged.emit(self.accentColor)
        return saved

    @Slot(bool)
    def _poll_system_accent(self) -> None:
        """只在跟随系统时读注册表；颜色变了就通知界面。"""
        if self._config["settings"].get("accentColorMode", "custom") != "system":
            return
        color = read_system_accent_color()
        if color and color != self._last_system_accent:
            self._last_system_accent = color
            self.accentColorChanged.emit(color)

    # ── 启动方式（关闭 / 登录时启动 / 管理员自启动）─────────────────
    @Slot(str, result="QVariantMap")
    def setStartupMode(self, mode: str) -> dict[str, Any]:
        """切换三态启动方式；需要管理员的重活交给提权后的辅助进程。

        创建 / 删除「最高权限」的计划任务需要管理员：先记下期望值、把活派给
        ``--set-startup-mode`` 辅助分支（会弹一次 UAC），界面过几秒回查真实
        状态自愈（``getStartupState``）。
        """
        mode = mode if mode in ("off", "normal", "admin") else "off"
        self._config["settings"]["startupMode"] = mode
        self.save(changed="settings")
        # 切启动方式是要下判断的路径：拿新鲜的任务状态，别信道缓存。
        needs_admin = mode == "admin" or autostart.task_exists(force=True)
        if needs_admin and not is_admin():
            autostart.spawn_apply_elevated(mode)
            return {"mode": mode, "state": autostart.startup_state(), "pending": True}
        if not autostart.apply_startup_mode(mode):
            self.showToast.emit("启动方式调整失败，可以看看日志", "error")
        return {"mode": mode, "state": autostart.startup_state(), "pending": False}

    @Slot(result="QVariantMap")
    def getStartupState(self) -> dict[str, Any]:
        """配置里期望的启动方式 + 系统里的真实状态（读缓存，绝不阻塞界面）。"""
        return {
            "mode": str(self._config["settings"].get("startupMode", "off")),
            "state": autostart.startup_state(),
        }

    def _start_startup_prefetch(self) -> None:
        """后台预热任务计划状态（由 main.py 在小窗稳定后延迟调用）。

        保留成独立方法，方便设置页 / 启动阶段按需复用；内部仍是异步线程，
        不会阻塞界面。
        """
        if sys.platform != "win32":
            return
        autostart.refresh_task_exists_async(self._startup_refresh_callback())

    @Slot()
    def refreshStartupState(self) -> None:
        """异步刷新任务计划状态；刷完经 ``startupStateChanged`` 通知界面。"""
        autostart.refresh_task_exists_async(self._startup_refresh_callback())

    def _startup_refresh_callback(self) -> Callable[[bool], None]:
        """后台线程只拿弱引用，别让它在页面退出后还攥着 ConfigManager。"""
        ref = weakref.ref(self)

        def done(_value: bool) -> None:
            obj = ref()
            if obj is not None:
                obj.startupStateChanged.emit()

        return done

    @Slot(result=bool)
    def reloadConfig(self) -> bool:
        """Re-read config.yaml from disk and tell the UI about it."""
        self._config = self._load()
        self._storage_cache = None
        self.configChanged.emit()
        self.launcherChanged.emit()
        self.settingsChanged.emit()
        self.accentColorChanged.emit(self.accentColor)
        return True

    @Slot(str, str)
    def notify(self, message: str, severity: str = "info") -> None:
        """Let QML raise a toast through the same path the backend uses."""
        self.notifyEvent("system", message, severity)

    # ── 通知分类 × 渠道 ──────────────────────────────────────────────
    def attachTraySink(self, sink: Callable[[str, str], Any] | None) -> None:
        """登记托盘气泡的出口；托盘关掉时传 None 即可。"""
        self._tray_sink = sink

    def notifyEvent(self, category: str, message: str,
                    severity: str = "info") -> None:
        """按「类别 × 渠道」投递一条通知。

        错误与警告强制补一条应用内提示：渠道全关时用户至少还能在界面上看到。
        托盘 / 系统通知失败都不影响应用内提示。
        """
        text = str(message or "").strip()
        if not text:
            return
        category = category if category in NOTIFY_CATEGORIES else "system"
        channels = dict(self._notification_channels(category))
        if severity in ("error", "warning"):
            channels["toast"] = True
        if channels.get("toast"):
            self.showToast.emit(text, severity)
        if channels.get("tray"):
            sink = self._tray_sink
            if sink is not None:
                try:
                    sink(text, severity)
                except Exception:
                    logger.debug("Tray notification failed", exc_info=True)
        if channels.get("native"):
            toast.show("Rin Launcher", text)

    def _notification_channels(self, category: str) -> dict[str, bool]:
        return notifications.channels_for(self._config, category)

    @Slot(result="QVariantMap")
    def getNotificationSettings(self) -> dict[str, Any]:
        """通知设置页的数据：类别列表、渠道列表，以及每个格子的当前值。"""
        section = self._config.get("notifications")
        values = section if isinstance(section, dict) else {}
        categories: list[dict[str, Any]] = []
        for key, label in NOTIFY_CATEGORIES.items():
            channels = values.get(key) if isinstance(values.get(key), dict) else {}
            categories.append({
                "key": key,
                "label": label,
                "channels": {name: bool(channels.get(name, name == "toast"))
                             for name in NOTIFY_CHANNELS},
            })
        return {
            "categories": categories,
            "channels": [{"key": key, "label": label}
                         for key, label in NOTIFY_CHANNELS.items()],
            "nativeAvailable": sys.platform == "win32",
        }

    @Slot(result="QVariantMap")
    def registerSystemNotification(self) -> dict[str, Any]:
        """创建带 AUMID 的开始菜单快捷方式，并立即发一条测试通知。"""
        result = notification_registration.register(str(ASSETS_DIR / "icon.ico"))
        self.showToast.emit(str(result.get("message") or ""),
                            "success" if result.get("ok") else "error")
        return result

    @Slot(result="QVariantMap")
    def applyShellPreferences(self) -> dict[str, Any]:
        """把「去快捷方式小箭头」偏好应用到当前用户；不自动重启资源管理器。"""
        enabled = bool(self._config["settings"].get("shortcutArrowGlobal", True))
        result = shell_tweaks.set_hidden(enabled, data_dir=self.config_dir)
        if result.get("changed"):
            self.showToast.emit(str(result.get("message") or ""),
                                "info" if result.get("ok") else "error")
        elif not result.get("ok"):
            logger.warning("应用快捷方式箭头设置失败: %s", result.get("message"))
        return result

    @Slot(result=bool)
    def restartExplorer(self) -> bool:
        """重启资源管理器，让快捷方式箭头设置立即生效。"""
        ok = shell_tweaks.restart_explorer()
        self.showToast.emit("资源管理器已重启" if ok else "重启资源管理器失败",
                            "success" if ok else "error")
        return ok

    @Slot(str, str, bool, result=bool)
    def setNotificationChannel(self, category: str, channel: str,
                               enabled: bool) -> bool:
        if category not in NOTIFY_CATEGORIES or channel not in NOTIFY_CHANNELS:
            return False
        section = self._config.setdefault("notifications", notifications.defaults())
        if not isinstance(section, dict):
            section = notifications.defaults()
            self._config["notifications"] = section
        entry = section.setdefault(category, {"toast": True, "tray": False,
                                              "native": False})
        entry[channel] = bool(enabled)
        saved = self.save(changed="settings")
        if saved:
            self.notificationsChanged.emit()
        return saved

    # ── 风险提示 ─────────────────────────────────────────────────────
    @Slot("QVariantMap", result="QVariantMap")
    def checkSlotRisk(self, slot: dict) -> dict[str, Any]:
        """编辑器保存前问一句：这一格会不会动到系统要害。

        只给提示，不拦截；命中后由界面弹二次确认。
        """
        try:
            return risk_rules.check(dict(slot or {}))
        except Exception:
            logger.exception("Risk check failed")
            return {"level": "", "reasons": []}

    # ── 搜索（含拼音）───────────────────────────────────────────────
    @Slot(str, result="QVariantList")
    def searchSlots(self, query: str) -> list[dict]:
        """按名称 / 路径 / 目标搜索启动台槽位，支持全拼与首字母。

        ``index`` 是全局序号（界面排序用），``rowIndex`` 是「本行第几个」——
        编辑 / 删除接口要的是后者。
        """
        needle = str(query or "").strip()
        hits: list[dict] = []
        row_counts: dict[int, int] = {}
        for index, slot in enumerate(self._slots()):
            row = int(slot.get("row", 0))
            row_index = row_counts.get(row, 0)
            row_counts[row] = row_index + 1
            resolved = self._resolve_slot(slot)
            if resolved is None:
                continue
            if not search.matches(
                    needle,
                    str(resolved.get("name") or ""),
                    str(resolved.get("path") or ""),
                    str(resolved.get("target") or ""),
                    str(resolved.get("arguments") or ""),
                    str(resolved.get("kindLabel") or "")):
                continue
            entry = dict(resolved)
            entry["index"] = index
            entry["rowIndex"] = row_index
            hits.append(entry)
        return hits

    # ── 恢复模式 ─────────────────────────────────────────────────────
    @Slot(result=str)
    def getLaunchMode(self) -> str:
        """本次启动的模式：normal / recovery / safe / diagnostic。

        命令行旗标优先于 ``appmodset.conf``；两者都没写时是正常模式。
        """
        args = [str(item) for item in sys.argv[1:]]
        if "--recovery" in args:
            return "recovery"
        if "--safe-mode" in args:
            return "safe"
        if "--diagnostic" in args:
            return "diagnostic"
        return self.app_mode.launch_mode

    @Slot(result=bool)
    def isFirstRun(self) -> bool:
        """是否应该展示 OOBE（appmodset.conf 的 first-run）。"""
        return self.app_mode.first_run

    @Slot("QVariantMap", result=bool)
    def completeOobe(self, settings: dict) -> bool:
        """OOBE 完成：保存设置并把 first-run 写回 false。"""
        payload = dict(settings or {})
        # 启动方式不走 updateSettings（要碰注册表 / 任务计划），单独提出来。
        startup = payload.pop("startupMode", None)
        if payload:
            self.updateSettings(payload)
        if startup in ("off", "normal", "admin"):
            self.setStartupMode(str(startup))
        ok = app_mode.mark_first_run_done(self.app_mode_path.parent)
        if not ok:
            # 安装目录不可写：退到用户数据目录的一份覆盖配置，下次启动仍然生效。
            ok = app_mode.update(self.config_dir, {"first-run": False})
        if ok:
            self._app_mode_values["first-run"] = False
            self.showToast.emit("首次设置已完成", "success")
        else:
            self.showToast.emit("首次设置已应用，但配置目录不可写", "warning")
        self.applyShellPreferences()
        self.settingsChanged.emit()
        return ok

    @Slot()
    def openOobe(self) -> None:
        self.pageRequested.emit("oobe")

    @Slot(result="QVariantMap")
    def getAppModeInfo(self) -> dict[str, Any]:
        """设置页 / 关于页展示的启动配置摘要。"""
        mode = self.app_mode
        return {
            "path": str(self.app_mode_path),
            "firstRun": mode.first_run,
            "normalBoot": bool(self._app_mode_values.get("normal-boot", True)),
            "failsafe": mode.safe_mode,
            "debug": mode.debug,
            "channel": mode.channel,
            "recovery": bool(self._app_mode_values.get("recovery", False)),
            "launchMode": mode.launch_mode,
            "problems": list(self._app_mode_problems),
        }

    @Slot(result=bool)
    def resetAppSettings(self) -> bool:
        """只重置设置与通知开关，保留启动台槽位、图标与备份。"""
        self._create_backup(manual=True, silent=True)
        self._config["settings"] = dict(DEFAULT_SETTINGS)
        self._config["notifications"] = notifications.defaults()
        saved = self.save(changed="settings")
        if saved:
            self.accentColorChanged.emit(self.accentColor)
            self.notificationsChanged.emit()
            self.hotkeyChanged.emit(str(DEFAULT_SETTINGS["globalHotkey"]))
            self.trayEnabledChanged.emit(bool(DEFAULT_SETTINGS["showTray"]))
            self.applyShellPreferences()
            self.showToast.emit("应用设置已重置", "success")
        return saved

    @Slot(result="QVariantMap")
    def cleanTempFiles(self) -> dict[str, Any]:
        """清掉 updates/ 里的下载包与解包残留，返回删了几个、腾出多少。"""
        updates_dir = self.config_dir / "updates"
        removed = 0
        freed = 0
        legacy = self._app_root() / "old.zip"
        if legacy.is_file():
            try:
                freed += legacy.stat().st_size
                legacy.unlink()
                removed += 1
            except OSError:
                logger.debug("无法清理历史回滚包 %s", legacy, exc_info=True)
        if updates_dir.is_dir():
            for path in sorted(updates_dir.iterdir()):
                try:
                    if path.is_dir():
                        size = sum(item.stat().st_size
                                   for item in path.rglob("*") if item.is_file())
                        shutil.rmtree(path, ignore_errors=True)
                    else:
                        size = path.stat().st_size
                        path.unlink()
                except OSError:
                    logger.debug("无法清理临时文件 %s", path, exc_info=True)
                    continue
                removed += 1
                freed += size
        message = (f"已清理 {removed} 个临时文件，释放 {_human_size(freed)}"
                   if removed else "没有可清理的临时文件")
        self.showToast.emit(message, "success" if removed else "info")
        return {"removed": removed, "freed": _human_size(freed)}

    @Slot(result="QVariantMap")
    def getRecoveryInfo(self) -> dict[str, Any]:
        """恢复模式窗口的首屏信息。"""
        backups = self.listBackups()
        usage = self.getStorageUsage()
        return {
            "version": APP_VERSION,
            "launchMode": self.getLaunchMode(),
            "configDir": str(self.config_dir),
            "logDir": str(self.log_dir),
            "backupDir": str(self.backup_dir),
            "backupCount": len(backups),
            "latestBackup": backups[0]["name"] if backups else "",
            "latestBackupTime": backups[0]["time"] if backups else "",
            "logSize": usage.get("logSize", ""),
        }

    @Slot(str, result=bool)
    def restartWithMode(self, mode: str) -> bool:
        """带启动模式参数重启：recovery / safe / diagnostic / normal。"""
        mode = str(mode)
        # appmodset.conf 的 recovery / failsafe 优先级高于命令行之外的一切；
        # 「继续使用」必须先把这两个标记清掉，否则重启后还是恢复进程。
        if mode == "normal" and (self._app_mode_values.get("recovery")
                                 or self._app_mode_values.get("failsafe")):
            if app_mode.update(self.app_mode_path.parent,
                               {"recovery": False, "failsafe": False}):
                self._app_mode_values["recovery"] = False
                self._app_mode_values["failsafe"] = False
        flag = {"recovery": "--recovery", "safe": "--safe-mode",
                "diagnostic": "--diagnostic"}.get(mode, "")
        extra = [flag] if flag else []
        if not restart_application(extra):
            self.showToast.emit("重启失败，可以看看日志", "error")
            return False
        QCoreApplication.quit()
        return True

    @Slot(str)
    def requestPage(self, page: str) -> None:
        """QML 页面请求切到某一页（由 main.py 落到完整窗口上）。"""
        self.pageRequested.emit(str(page))

    @Slot(str)
    def requestSettingsSection(self, name: str) -> None:
        """标题栏「…」菜单里点设置分区：切到设置页对应的分类。"""
        name = str(name or "")
        self._pending_settings_section = name
        self.settingsSectionRequested.emit(name)

    @Slot(result=str)
    def takePendingSettingsSection(self) -> str:
        """设置页刚建好时取走待切的分类（读一次就清空）。"""
        value = self._pending_settings_section
        self._pending_settings_section = ""
        return value

    @Slot(result=str)
    def systemAccentColor(self) -> str:
        """当前 Windows 用户的系统强调色（``#RRGGBB``）；读不到时返回空串。"""
        return read_system_accent_color()

    @Slot(result=bool)
    def resetToDefaults(self) -> bool:
        return self.save(_default_config(), changed="all")

    @Slot(result=bool)
    def restartApplication(self) -> bool:
        """延迟 2 秒普通重启，给单实例锁留出释放时间。"""
        if not restart_application():
            self.showToast.emit("重启失败，可以看看日志", "error")
            return False
        QCoreApplication.quit()
        return True

    @Slot(result=bool)
    def restartAsAdmin(self) -> bool:
        if is_admin():
            return self.restartApplication()
        if not restart_elevated_delayed():
            self.showToast.emit("提权重启失败，可以看看日志", "error")
            return False
        QCoreApplication.quit()
        return True

    @Slot(str, result=bool)
    def setUpdateChannel(self, channel: str) -> bool:
        channel = channel if channel in ("stable", "prerelease") else "stable"
        if self._config["settings"].get("updateChannel") == channel:
            return True
        self._config["settings"]["updateChannel"] = channel
        # appmodset.conf 是通道的单一来源：界面改了要同步写回去，否则重启后
        # 又会被文件里的旧值覆盖。
        if app_mode.update(self.app_mode_path.parent, {"channel": channel}):
            self._app_mode_values["channel"] = channel
        return self.save(changed="settings")

    @Slot(bool, result=bool)
    def setAutoCheckUpdates(self, enabled: bool) -> bool:
        enabled = bool(enabled)
        if bool(self._config["settings"].get("autoCheckUpdates", True)) == enabled:
            return True
        self._config["settings"]["autoCheckUpdates"] = enabled
        return self.save(changed="settings")

    @Slot(str, result=bool)
    def setUpdateMirror(self, mirror: str) -> bool:
        mirror = mirror if mirror in ("github", "ghfast", "ghproxy") else "github"
        if self._config["settings"].get("updateMirror") == mirror:
            return True
        self._config["settings"]["updateMirror"] = mirror
        return self.save(changed="settings")

    @Slot(bool, result=bool)
    def setUpdateMirrorAuto(self, enabled: bool) -> bool:
        enabled = bool(enabled)
        if bool(self._config["settings"].get("updateMirrorAuto", True)) == enabled:
            return True
        self._config["settings"]["updateMirrorAuto"] = enabled
        return self.save(changed="settings")

    @Slot(result=bool)
    def importConfig(self) -> bool:
        path, _ = QFileDialog.getOpenFileName(
            None, "导入配置", str(self.config_dir), "YAML (*.yaml *.yml)")
        return bool(path) and self._read_from(Path(path))

    @Slot(result=bool)
    def exportConfig(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(
            None, "导出配置", str(self.config_file), "YAML (*.yaml *.yml)")
        return bool(path) and self._write_to(Path(path))

    @Slot(result=str)
    def pickFile(self) -> str:
        """Native file picker used by the entry editor's "browse" button."""
        path, _ = QFileDialog.getOpenFileName(None, "选择文件或程序", str(Path.home()))
        return path or ""

    @Slot(result=str)
    def pickShortcut(self) -> str:
        """挑一个开始菜单快捷方式（.lnk）。"""
        start = str(Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows"
                    / "Start Menu" / "Programs")
        path, _ = QFileDialog.getOpenFileName(
            None, "选择快捷方式", start, "快捷方式 (*.lnk);;所有文件 (*)")
        return path or ""

    @Property("QVariantList", notify=startMenuAppsChanged)
    def startMenuApps(self) -> list[dict]:
        """最近一次扫描结果（界面绑定这个，不要在主线程里直接扫）。"""
        if self._start_menu_view is None:
            self._start_menu_view = [dict(item) for item in self._start_menu_apps]
        return self._start_menu_view

    @Property(bool, notify=startMenuLoadingChanged)
    def startMenuLoading(self) -> bool:
        return self._start_menu_loading

    @Slot()
    def refreshStartMenuApps(self) -> None:
        """后台重新扫描开始菜单，完成后经 ``startMenuAppsChanged`` 通知。"""
        if self._start_menu_loading:
            return
        # 先用内存 / 磁盘缓存秒开（不扫盘），再后台强制刷新。
        quick = start_menu.cached_start_menu_apps()
        if quick:
            self._attach_cached_thumbs(quick)
            self._start_menu_apps = quick
            self._start_menu_view = None
            self.startMenuAppsChanged.emit()
        self._start_menu_loading = True
        self.startMenuLoadingChanged.emit()
        self._start_menu_token += 1
        token = self._start_menu_token
        self.startMenuAppsChanged.emit()

        # 超时兜底：扫描卡住时也要把加载态放掉，否则对话框永远转圈。
        self._start_menu_timeout += 1
        timeout_token = self._start_menu_timeout

        def expire() -> None:
            if (timeout_token != self._start_menu_timeout
                    or not self._start_menu_loading):
                return
            logger.warning("开始菜单扫描超时，先按空结果返回")
            self._start_menu_loading = False
            self.startMenuLoadingChanged.emit()
            self.startMenuAppsChanged.emit()

        QTimer.singleShot(20000, expire)

        def worker() -> None:
            try:
                apps = start_menu.list_start_menu_apps(force=True)
            except Exception:
                logger.exception("开始菜单扫描失败")
                apps = []
            # 跨线程 emit 会自动排队到接收者所在线程（GUI）。
            self._startMenuScanDone.emit(token, apps)

        threading.Thread(target=worker, name="rin-start-menu", daemon=True).start()

    def _apply_start_menu_apps(self, token: int, apps: list[dict[str, Any]]) -> None:
        if token != self._start_menu_token:
            return
        # 已经在磁盘上的缩略图首帧就挂回去，对话框重开时不会先闪一列类型图标。
        self._attach_cached_thumbs(apps)
        self._start_menu_apps = apps
        self._start_menu_view = None
        self._start_menu_loading = False
        self.startMenuLoadingChanged.emit()
        self.startMenuAppsChanged.emit()
        # 剩下的缩略图不在打开对话框的瞬间跑：先备好队列，等界面关闭后由
        # startThumbnailQueue() 启动，避免一边浏览一边抽图标卡主线程。
        self._thumb_queue = [app for app in apps if self._needs_thumb(app)]

    def _attach_cached_thumbs(self, apps: list[dict[str, Any]]) -> None:
        """把缩略图目录里已有的图直接挂到条目上（只查文件存在，不抽图）。"""
        for app in apps:
            if app.get("thumb"):
                continue
            cached = self._thumb_path(app)
            if cached is not None and cached.is_file():
                app["thumb"] = f"file:{cached}"

    def _needs_thumb(self, app: dict[str, Any]) -> bool:
        return not app.get("thumb")

    def _thumb_path(self, app: dict[str, Any]) -> Path | None:
        """按「来源路径 + 修改时间」算缓存键；同一个应用不会重复抽图标。"""
        source = Path(str(app.get("source") or ""))
        target = str(app.get("target") or "")
        stamp = ""
        if source.is_file():
            try:
                stamp = str(int(source.stat().st_mtime))
            except OSError:
                stamp = ""
        raw = f"{source}|{stamp}|{target}|{app.get('icon') or ''}"
        key = uuid.uuid5(uuid.NAMESPACE_URL, raw).hex
        return self.thumbnail_dir / f"{key}.png"

    @Slot()
    def startThumbnailQueue(self) -> None:
        """对话框关闭后再生缩略图：GUI 线程分批，不阻塞浏览。"""
        if not self._thumb_queue or self._thumb_timer is not None:
            return
        self._thumb_timer = QTimer(self)
        self._thumb_timer.setInterval(200)
        self._thumb_timer.timeout.connect(self._build_thumb_batch)
        self._thumb_timer.start()

    def _build_thumb_batch(self) -> None:
        if not self._thumb_queue:
            if self._thumb_timer is not None:
                self._thumb_timer.stop()
                self._thumb_timer.deleteLater()
                self._thumb_timer = None
            return
        changed = False
        for _ in range(2):
            if not self._thumb_queue:
                break
            app = self._thumb_queue.pop(0)
            cached = self._thumb_path(app)
            if cached is not None and cached.is_file():
                app["thumb"] = f"file:{cached}"
                changed = True
                continue
            key = self._make_thumb(app, cached)
            if key:
                app["thumb"] = key
                changed = True
        if changed:
            self._start_menu_view = None
            self.startMenuAppsChanged.emit()

    def _thumb_candidate(self, raw: str) -> Path | None:
        """把条目里的路径落成真实文件；``wsl.exe`` 这类裸命令走 PATH 解析。"""
        text = str(raw or "").strip().removeprefix("file:")
        if not text:
            return None
        path = Path(text)
        if path.is_file():
            return path
        found = shutil.which(text)
        return Path(found) if found else None

    def _make_thumb(self, app: dict[str, Any], target: Path | None) -> str:
        if target is None:
            return ""
        icon = str(app.get("icon") or "")
        origin: Path | None = None
        temporary = False
        # 现成图片优先（UWP 包清单图标、WSA 的 IconLocation）。
        if icon.startswith("file:"):
            origin = self._thumb_candidate(icon)
        # 没有图片就从快捷方式 / 目标程序里抽：extract() 内部会依次试
        # IconLocation → 快捷方式本身 → 目标，覆盖 lnk / wsa / wsl。
        if origin is None:
            for candidate in (app.get("source"), app.get("target")):
                path = self._thumb_candidate(str(candidate or ""))
                if path is None:
                    continue
                extracted = self._icons.extract(str(path), notify=False)
                if extracted:
                    origin = Path(extracted.removeprefix("file:"))
                    temporary = True
                    break
        if origin is None:
            return ""
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origin, target)
        except OSError:
            logger.debug("缩略图缓存失败: %s", origin, exc_info=True)
            return ""
        finally:
            # 只有「为了缓存临时抽出来」的图标才删；用户图标库里的原图必须保留。
            if temporary and origin.parent == self.icon_dir and origin != target:
                origin.unlink(missing_ok=True)
        return f"file:{target}"

    @Slot(str, result="QVariantMap")
    def parseShortcut(self, path: str) -> dict:
        app = start_menu.parse_shortcut(path)
        return dict(app) if app else {}

    @Slot("QVariantMap", int, result=bool)
    def addAppSlot(self, app: dict, row: int) -> bool:
        """把开始菜单条目直接建成一格；扫描阶段拿到的图标会一并入库。"""
        kind = str(app.get("kind") or "lnk")
        name = str(app.get("name") or "").strip()
        target = str(app.get("target") or "").strip()
        if not target:
            return False
        if kind == "uwp":
            action = {"type": "uwp", "target": target, "arguments": "",
                      "working_dir": "", "run_as": "user", "keyboard_steps": []}
        elif kind == "wsl":
            action = {"type": "cmd", "target": target,
                      "arguments": str(app.get("arguments") or ""),
                      "working_dir": "", "run_as": "user", "keyboard_steps": []}
        else:
            action = {"type": "file", "target": target,
                      "arguments": str(app.get("arguments") or ""),
                      "working_dir": str(app.get("working_dir") or ""),
                      "run_as": "user", "keyboard_steps": []}
        icon = ""
        source_icon = str(app.get("icon") or "")
        if source_icon.startswith("file:"):
            # 扫描阶段已经定位到真实图片：UWP 的包清单图标、WSA 的 LocalState .ico。
            # 直接入库，不再从 target 里瞎猜。
            icon = self._icon_from_path(
                Path(source_icon[len("file:"):]), notify=False)
        elif kind in ("lnk", "wsa"):
            # 没有现成图片时退回快捷方式：WSA 的正确图标在 .lnk 的 IconLocation
            # 里，传 target 只会拿到 WsaClient.exe 的通用图标。
            icon = self._extract_icon_file(
                str(app.get("source") or target), notify=False)
        payload = {"kind": SLOT_ACTION, "label": name, "icon": icon, "action": action}
        return self.addLauncherSlot(int(row), payload)

    @Slot("QVariantMap")
    def executeAction(self, action: dict) -> None:
        name = action.get("name", "")
        if self.action_executor is None:
            self.showToast.emit("动作执行器未初始化", "error")
            return
        # 启动程序 / 打开网址也可能卡在 shell 解析或网络路径上；统一放后台线程，
        # 小窗点击后立刻回收事件，不再等动作跑完。
        if action.get("type") in ("keyboard", "keymouse"):
            self.showToast.emit(f"按键序列已开始: {name}", "info")
        threading.Thread(
            target=self._execute_action_worker,
            args=(dict(action), name), name="rin-action", daemon=True,
        ).start()

    def _execute_action_worker(self, action: dict, name: str) -> None:
        try:
            ok = self.action_executor.execute(action) if self.action_executor else False
        except Exception:
            logger.exception("Background action failed")
            ok = False
        self.showToast.emit(
            f"已执行: {name}" if ok else f"执行失败: {name}",
            "success" if ok else "error")

    @Slot("QVariantMap", result=bool)
    def runLauncherSlot(self, slot: dict) -> bool:
        """执行小窗上的一个槽位。

        ``tool`` 类槽位牵扯窗口操作，由 QML 自己处理；这里只管能把活儿干完的
        ``action`` / ``path`` / ``usb``。
        """
        kind = str(slot.get("kind") or "")
        if kind == SLOT_ACTION:
            inline = slot.get("action")
            if not isinstance(inline, dict) or not inline:
                self.showToast.emit("这一格还没有配置动作", "warning")
                return False
            if inline.get("type") != "keyboard" \
                    and not str(inline.get("target") or "").strip():
                self.showToast.emit("这一格还没有配置目标", "warning")
                return False
            payload = dict(inline)
            payload["name"] = str(slot.get("name") or "")
            self.executeAction(payload)
            return True
        if kind == SLOT_USB:
            return self.openRemovableDrive()
        if kind == SLOT_PATH:
            return self.openSlot(str(slot.get("path") or ""))
        return False

    # ------------------------------------------------------------------
    # Shell integration
    # ------------------------------------------------------------------
    @Slot()
    def openConfigFolder(self) -> None:
        self._reveal(self.config_dir)

    @Slot()
    def openConfigFile(self) -> None:
        self._reveal(self.config_file)

    @Slot()
    def openIconFolder(self) -> None:
        self._reveal(self.icon_dir)

    @Slot(result="QVariantMap")
    def getRuntimeInfo(self) -> dict[str, Any]:
        """关于页要显示的运行环境信息（含可一键复制的诊断文本）。"""
        import platform

        from PySide6 import __version__ as pyside_version
        from PySide6.QtCore import qVersion

        windows_build = ""
        if sys.platform == "win32":
            try:
                windows_build = f"Build {sys.getwindowsversion().build}"
            except Exception:
                windows_build = ""
        # 发布通道由 appmodset.conf 决定；界面上仍用 Release / Pre-Release 这种
        # 人话，而不是内部的 stable / prerelease。
        channel = "Pre-Release" if self.app_mode.channel == "prerelease" else "Release"

        system = f"{platform.system()} {platform.release()}"
        if windows_build:
            system = f"{system} ({windows_build})"
        log_file = logging_setup.file_for(self.log_dir)
        info: dict[str, Any] = {
            "version": APP_VERSION,
            "codename": APP_CODENAME,
            "branch": channel,
            "python": platform.python_version(),
            "qt": qVersion(),
            "pyside": pyside_version,
            "system": system,
            "windowsBuild": windows_build or platform.version(),
            "configDir": str(self.config_dir),
            "configFile": str(self.config_file),
            "iconDir": str(self.icon_dir),
            "logDir": str(self.log_dir),
            "logFile": str(log_file),
            "backend": "RinUI 0.5.0（pip 依赖，MIT）",
        }
        info["diagnostics"] = (
            f"Rin Launcher {APP_VERSION} ({APP_CODENAME}, {channel})\n"
            f"Python {platform.python_version()}\n"
            f"Qt {qVersion()} / PySide6 {pyside_version}\n"
            f"Windows {platform.release()} {info['windowsBuild']}\n"
            f"Config: {self.config_dir}\n"
            f"Log: {log_file}"
        )
        return info

    @staticmethod
    def _reveal(path: Path) -> None:
        """打开目录；传入文件时打开所在目录并选中它。"""
        if path.is_file():
            if sys.platform == "win32":
                subprocess.Popen(["explorer.exe", "/select,", str(path)])
                return
            path = path.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    # ------------------------------------------------------------------
    # External change watching
    # ------------------------------------------------------------------
    def startWatching(self) -> None:
        if self._observer is not None:
            return
        try:
            from watchdog.observers import Observer
        except Exception:
            logger.exception("watchdog is unavailable; config hot reload is disabled")
            return
        self._observer = Observer()
        self._observer.schedule(
            _ConfigWatcher(self._onExternalChange), str(self.config_dir), recursive=False)
        self._observer.start()
        logger.info("Watching %s for external changes", self.config_file)

    def stopWatching(self) -> None:
        if self._observer is None:
            return
        self._observer.stop()
        self._observer.join()
        self._observer = None

    def _onExternalChange(self) -> None:
        if time.monotonic() < self._quiet_until:  # we just wrote it ourselves
            return
        logger.info("Config changed on disk, reloading")
        self.reloadConfig()
