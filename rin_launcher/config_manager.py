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
import shutil
import sys
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from PySide6.QtCore import QFileInfo, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

# QFileIconProvider 在 Qt6 里搬到了 QtWidgets（QtGui 那个基类要自己实现 icon()）。
from PySide6.QtWidgets import QApplication, QFileDialog, QFileIconProvider
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from rin_launcher import __version__ as APP_VERSION
from rin_launcher import autostart
from rin_launcher.elevation import is_admin, restart_elevated

logger = logging.getLogger(__name__)

APP_REPO = "https://github.com/yixuan0826/RinLauncher"

DEFAULT_CONFIG_DIR = Path.home() / "AppData" / "Roaming" / "RinLauncher"
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
BUNDLED_ICON_DIR = ASSETS_DIR / "icons" / "lawnicons"
APP_ICON_FILE = ASSETS_DIR / "icon.png"

# ── 常驻小窗的两块 ──────────────────────────────────────────────────
# 面板：一块「双行」的格子板（最多 PANEL_CAPACITY 格），小窗把它的槽位按行
# 平分渲染成上下两排；存储区：存储卡片 + 磁盘入口。槽位都写在 launcher.slots。
ROW_PANEL = 0        # 双行面板
ROW_STORAGE = 1      # 存储与磁盘
LAUNCHER_ROWS = 2
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
# 默认面板：挑几个日常用得上的。
DEFAULT_TOOL_KEYS: tuple = ("launcherPage", "settings", "configFolder",
                            "reload", "hide")
TOOL_ICONS: dict[str, str] = {key: icon for key, _title, icon in TOOL_CATALOG}
TOOL_TITLES: dict[str, str] = {key: title for key, title, _icon in TOOL_CATALOG}

# 槽位 kind 的展示信息，给编辑器的下拉用。
SLOT_KIND_LABELS: dict[str, str] = {
    SLOT_ACTION: "动作",
    SLOT_TOOL: "内置功能",
    SLOT_PATH: "打开路径",
    SLOT_USB: "可移动磁盘（自动检测）",
}
SLOT_KIND_ICONS: dict[str, str] = {
    SLOT_ACTION: "ic_fluent_play_20_regular",
    SLOT_TOOL: "ic_fluent_wrench_20_regular",
    SLOT_PATH: "ic_fluent_folder_open_20_regular",
    SLOT_USB: "ic_fluent_usb_plug_20_regular",
}

# 槽位不再引用任何外部条目：动作直接写在槽位里（内联）。
ACTION_TYPES: tuple = ("file", "cmd", "url", "keyboard")
# 旧版「键鼠模拟」已降级为「按键模拟」：读到旧类型名就迁成 keyboard，
# 旧字段 keymouse_steps 中的鼠标步骤直接跳过（执行端不再认识它）。
LEGACY_ACTION_TYPES: dict[str, str] = {"keymouse": "keyboard"}
# 这些后缀是「图片」，走导入；其余（exe/dll/lnk…）走系统图标提取。
IMAGE_ICON_SUFFIXES: tuple = (".svg", ".png", ".ico", ".jpg", ".jpeg", ".bmp")

# 用户自建图标的落盘目录（导入的 svg/png/ico、从程序里抽出来的图标都放这儿）。
ICON_STORE_NAME = "icons"
# 磁盘容量这种系统调用有成本，缓存一小段时间，同一轮刷新里不重复问系统。
STORAGE_TTL = 20.0


def _human_size(size: int) -> str:
    """把字节数写成 32.78GB 这种一眼能读的形式。"""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f}{unit}" if unit == "B" else f"{value:.2f}{unit}"
        value /= 1024
    return f"{value:.2f}TB"


def _drive_kind(code: int) -> str:
    return {2: "removable", 3: "fixed", 4: "network", 5: "cdrom", 6: "ramdisk"}.get(code, "")


def _find_removable_drive() -> str:
    """返回第一个可移动磁盘的根路径（如 ``E:\\``）；找不到或非 Windows 返回空串。"""
    if sys.platform != "win32":
        return ""
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        mask = kernel32.GetLogicalDrives()
    except Exception:
        logger.exception("Failed to enumerate drives")
        return ""

    for index in range(26):
        if not mask & (1 << index):
            continue
        root = f"{chr(ord('A') + index)}:\\"
        if kernel32.GetDriveTypeW(ctypes.c_wchar_p(root)) == 2:  # DRIVE_REMOVABLE
            return root
    return ""


def _list_drives() -> list[dict[str, Any]]:
    """枚举本机磁盘，给「磁盘」槽位的选择器用。

    非 Windows 上只给一个根分区 —— 开发环境（Linux/macOS）里界面照样能跑通，
    不至于整块功能消失。
    """
    if sys.platform != "win32":
        try:
            usage = shutil.disk_usage("/")
        except OSError:
            return []
        return [{
            "path": "/",
            "label": "根目录",
            "kind": "fixed",
            "kindLabel": "本地磁盘",
            "free": _human_size(usage.free),
            "total": _human_size(usage.total),
            "percent": round(usage.used / usage.total * 100) if usage.total else 0,
        }]

    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        mask = kernel32.GetLogicalDrives()
    except Exception:
        logger.exception("Failed to enumerate drives")
        return []

    kind_labels = {
        "removable": "可移动磁盘", "fixed": "本地磁盘", "network": "网络位置",
        "cdrom": "光驱", "ramdisk": "内存盘",
    }
    drives: list[dict[str, Any]] = []
    for index in range(26):
        if not mask & (1 << index):
            continue
        root = f"{chr(ord('A') + index)}:\\"
        kind = _drive_kind(kernel32.GetDriveTypeW(ctypes.c_wchar_p(root)))
        if not kind:
            continue

        label = ""
        try:
            buffer = ctypes.create_unicode_buffer(261)
            if kernel32.GetVolumeInformationW(
                    ctypes.c_wchar_p(root), buffer, 261, None, None, None, None, 0):
                label = buffer.value
        except Exception:
            logger.debug("Cannot read volume label of %s", root)

        free_text = total_text = ""
        percent = 0
        # 光驱／网络盘没插介质时读容量会卡住，直接跳过。
        if kind in ("fixed", "removable", "ramdisk"):
            try:
                free = ctypes.c_ulonglong(0)
                total = ctypes.c_ulonglong(0)
                if kernel32.GetDiskFreeSpaceExW(
                        ctypes.c_wchar_p(root), ctypes.byref(free),
                        ctypes.byref(total), None) and total.value:
                    free_text = _human_size(free.value)
                    total_text = _human_size(total.value)
                    percent = round((total.value - free.value) / total.value * 100)
            except Exception:
                logger.debug("Cannot read free space of %s", root)

        drives.append({
            "path": root,
            "label": label or root,
            "kind": kind,
            "kindLabel": kind_labels.get(kind, kind),
            "free": free_text,
            "total": total_text,
            "percent": percent,
        })
    return drives


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


DEFAULT_SETTINGS: dict[str, Any] = {
    "theme": "system",
    "showTray": True,
    "startMinimized": False,
    "startupMode": "off",
    "globalHotkey": "Ctrl+Space",
    # 完整窗口材质。RinUI 的取值：tabbed(增强云母) | mica(云母) | acrylic(亚克力) | none
    "material": "tabbed",
    # 小窗是桌面挂件，单独走亚克力（不吃完整窗口那套材质设置）。
    "compactAcrylic": True,
    "animationEnabled": True,
    "accentColor": "#0078d4",
    "adminAutoElevate": True,
    "confirmAdminActions": True,
    "logLevel": "INFO",
}


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def _slot_row(item: Any, fallback: int) -> int:
    """槽位声明的行号；写坏了就退回它在列表里的位置。"""
    if isinstance(item, dict):
        try:
            return int(item.get("row", fallback))
        except (TypeError, ValueError):
            pass
    return fallback


def _new_slot(kind: str, row: int, **extra: Any) -> dict[str, Any]:
    """建一个槽位字典；多出来的键补上默认值，保证结构一致。"""
    slot = {
        "kind": kind,
        "row": row,
        "label": "",     # 覆盖显示名，空 = 用目标自己的名字
        "icon": "",      # 覆盖图标，空 = 用目标自己的图标
    }
    slot.update(extra)
    return slot


def _step_duration(raw: Any) -> float:
    """把步骤里的延迟修成 >= 0 的秒数；写坏了就当 0。"""
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return 0.0


def _step_vk(raw: Any) -> int:
    """把步骤里的虚拟键码修成 0-255 的整数；没有或写坏了就当 0（改用名称）。"""
    try:
        vk = int(raw)
    except (TypeError, ValueError):
        return 0
    return vk if 0 < vk < 256 else 0


def _sanitize_steps(raw: Any) -> list[dict[str, Any]]:
    """清洗按键序列：只留「按键 / 等待」两种步骤。

    「按键模拟」参考 SystemTools 的「模拟键盘」：一条按键步骤 = 名称（可写组合键，
    如 ``Ctrl+C``）+ 虚拟键码（可选，执行时优先）+ 动作（单击 / 按住 / 释放）+
    延迟（这一步执行前的等待，秒）。旧版键鼠模拟里的 mouse 步骤不再支持，
    读到时直接跳过。
    """
    steps: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return steps
    for step in raw:
        if not isinstance(step, dict):
            continue
        kind = str(step.get("type") or "")
        if kind == "key":
            command = str(step.get("action") or "click")
            if command not in ("press", "release", "click"):
                command = "click"
            entry: dict[str, Any] = {
                "type": "key",
                "key": str(step.get("key") or ""),
                "action": command,
                "duration": _step_duration(step.get("duration")),
            }
            vk = _step_vk(step.get("vk"))
            if vk:
                entry["vk"] = vk
            steps.append(entry)
        elif kind == "wait":
            steps.append({"type": "wait", "duration": _step_duration(step.get("duration"))})
    return steps


def _action_steps(action: dict[str, Any]) -> list[dict[str, Any]]:
    """取一份动作的按键序列；兼容旧字段名 keymouse_steps 并顺手清洗。"""
    raw = action.get("keyboard_steps")
    if raw is None:
        raw = action.get("keymouse_steps")
    return _sanitize_steps(raw)


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


def _derive_action_name(action: dict[str, Any]) -> str:
    """内联动作没有名字，按类型从目标里取一个一看就懂的显示名。"""
    kind = action.get("type")
    if kind == "keyboard":
        return "按键动作"
    target = str(action.get("target") or "").strip().strip('"')
    if not target:
        return "未配置动作"
    if kind == "url":
        return target
    return Path(target).name or target


def _default_slots() -> list[dict[str, Any]]:
    """默认槽位：面板放 5 个内置功能，存储区放一个 U 盘和一个本机磁盘。"""
    slots = [_new_slot(SLOT_TOOL, ROW_PANEL, key=key) for key in DEFAULT_TOOL_KEYS]
    slots.append(_new_slot(SLOT_USB, ROW_STORAGE, label="U 盘"))

    # 挑一个非系统盘当默认的「磁盘」项；找不到就用主目录。
    target = ""
    for drive in _list_drives():
        if drive["path"].upper() not in ("C:\\", "/"):
            target = drive["path"]
            break
    slots.append(_new_slot(SLOT_PATH, ROW_STORAGE, path=target or str(Path.home())))
    return slots


def _default_config() -> dict[str, Any]:
    """Build a fresh default config."""
    return {
        "version": CONFIG_VERSION,
        "launcher": {
            "slots": _default_slots(),
            "storagePath": "",
        },
        "settings": dict(DEFAULT_SETTINGS),
    }


class _ConfigWatcher(FileSystemEventHandler):
    """Debounced listener for edits made to the config file by other programs."""

    def __init__(self, on_change: Callable[[], None]):
        self._on_change = on_change
        self._last_fired = 0.0

    def on_modified(self, event) -> None:
        if event.is_directory or not event.src_path.endswith((".yaml", ".yml")):
            return
        now = time.monotonic()
        if now - self._last_fired > 0.5:
            self._last_fired = now
            self._on_change()


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
    materialChanged = Signal(str)
    # 页面 / 窗口级的请求：QML 侧的页面够不到窗口对象，统一从这里转给 main.py。
    pageRequested = Signal(str)
    # 设置页分组跳转（标题栏「…」菜单里选一个分区）。
    settingsSectionRequested = Signal(str)
    # 任务计划状态的后台刷新完成（启动方式下拉据此回填真实值）。
    startupStateChanged = Signal()
    # 小窗要直接打开某一格的编辑器（row, index；index=-1 表示新增）。
    slotEditRequested = Signal(int, int)

    def __init__(self, config_dir: Path | None = None, parent: QObject | None = None):
        super().__init__(parent)
        # 打包后数据目录是 exe 同级的 data/（不可写则回退 %APPDATA%），
        # 源码运行保持 %APPDATA%；首次切换到 data/ 时会把老数据迁过去。
        self.config_dir = Path(config_dir) if config_dir else resolve_config_dir()
        self.config_file = self.config_dir / "config.yaml"
        self.backup_dir = self.config_dir / "backups"
        self.icon_dir = self.config_dir / ICON_STORE_NAME
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.icon_dir.mkdir(parents=True, exist_ok=True)

        self.action_executor = None
        self._observer: Observer | None = None
        self._quiet_until = 0.0  # ignores the watcher echo of our own writes
        self._icon_provider = QFileIconProvider()
        # 磁盘容量缓存：(取值时间, 数据)。
        self._storage_cache: tuple[float, dict[str, Any]] | None = None
        # 可移动磁盘缓存：枚举驱动器有系统调用成本，刷新时只问一次。
        self._removable_cache: tuple[float, str] | None = None
        # 小窗发起的「编辑这一格」请求（页面建好前先记着，见 requestSlotEditor）。
        self._pending_slot_edit: tuple[int, int] | None = None
        self._config = self._load()
        # 启动就把任务计划状态预热到后台（设置页打开时零等待）。
        self._start_startup_prefetch()

    @property
    def config(self) -> dict[str, Any]:
        return self._config

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
            config = self._normalize(raw)
            # 旧版「快捷操作」库 / 分区不从磁盘上留着：读到就立刻写回一份干净的配置，
            # 不用等用户下次改设置。
            if had_legacy_library:
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
        settings = {**DEFAULT_SETTINGS, **raw_settings}
        # 旧版「开机自动启动」布尔值迁进三态启动方式（关闭 / 登录时启动 / 管理员自启动）。
        settings.pop("autoStart", None)
        if "startupMode" not in raw_settings and raw_settings.get("autoStart"):
            settings["startupMode"] = "normal"
        if settings.get("startupMode") not in ("off", "normal", "admin"):
            settings["startupMode"] = "off"
        # 小窗改成固定置底、固定主屏右下角之后，这两个老键不再有消费方。
        for obsolete in ("alwaysOnTop", "compactPos"):
            settings.pop(obsolete, None)
        data["settings"] = settings
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
        shutil.copy2(self.config_file, self.backup_dir / f"config.yaml.bak.{int(time.time())}")
        for stale in sorted(self.backup_dir.glob("config.yaml.bak.*"))[:-keep]:
            stale.unlink(missing_ok=True)

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
                runAs=inline.get("run_as", "user"),
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
            exists = bool(expanded) and Path(expanded).exists()
            resolved.update(
                name=override_label or (Path(expanded).name if expanded else "未设置路径"),
                icon=override_icon or "ic_fluent_folder_open_20_regular",
                path=expanded,
                exists=exists,
            )
        elif kind == SLOT_USB:
            drive = self._removable_drive()
            resolved.update(
                name=override_label or "U 盘",
                icon=override_icon or "ic_fluent_usb_plug_20_regular",
                path=drive,
                exists=bool(drive),
                available=bool(drive),
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
    def getSlotCatalog(self) -> list[dict]:
        """可选的槽位类型与内置功能，给编辑器的下拉用。"""
        return [
            {"kind": kind, "title": SLOT_KIND_LABELS[kind], "icon": SLOT_KIND_ICONS[kind]}
            for kind in SLOT_KINDS
        ]

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

    @Slot(int, result="QVariantList")
    def getSlotsInRow(self, row: int) -> list[dict]:
        """某一行的槽位解析结果，按显示顺序。"""
        return [item for item in self.getLauncherSlots() if item.get("row") == row]

    @Slot(result="QVariantMap")
    def getStorageInfo(self) -> dict[str, Any]:
        """第三行的存储卡片：路径与容量。结果带短缓存，避免反复问系统。"""
        now = time.monotonic()
        if self._storage_cache and now - self._storage_cache[0] < STORAGE_TTL:
            return self._storage_cache[1]

        path = self._storagePath()
        info: dict[str, Any] = {
            "path": str(path),
            "label": path.name or str(path),
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
        raw = str(self._config["launcher"].get("storagePath") or "").strip()
        candidate = Path(raw).expanduser() if raw else Path.home()
        # 配置里写了个已经不存在的路径时退回主目录，别让小窗显示一片空白。
        return candidate if candidate.exists() else Path.home()

    @Slot(result=str)
    def pickFolder(self) -> str:
        path = QFileDialog.getExistingDirectory(None, "选择文件夹", str(Path.home()))
        return path or ""

    @Slot(result=str)
    def pickProgram(self) -> str:
        """挑一个程序 / 动态库，用于「从程序提取图标」。"""
        path, _ = QFileDialog.getOpenFileName(
            None, "选择程序或 DLL", str(Path.home()),
            "程序与库 (*.exe *.dll *.ico *.lnk);;所有文件 (*)")
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

    def _removable_drive(self) -> str:
        """可移动磁盘路径，带短缓存 —— 一次界面刷新里可能有好几格都要问。"""
        now = time.monotonic()
        if self._removable_cache and now - self._removable_cache[0] < STORAGE_TTL:
            return self._removable_cache[1]
        drive = _find_removable_drive()
        self._removable_cache = (now, drive)
        return drive

    @Slot(result=bool)
    def openRemovableDrive(self) -> bool:
        drive = self._removable_drive()
        if not drive:
            self.showToast.emit("没有检测到可移动磁盘", "warning")
            return False
        self._reveal(Path(drive))
        return True

    # ── 图标 ──────────────────────────────────────────────────────────
    @Slot(result="QStringList")
    def getBundledIcons(self) -> list[str]:
        """Names of the icon marks shipped under assets/icons/lawnicons."""
        if not BUNDLED_ICON_DIR.is_dir():
            return []
        return sorted(path.stem for path in BUNDLED_ICON_DIR.glob("*.svg"))

    @Slot(result="QVariantList")
    def getCustomIcons(self) -> list[dict]:
        """用户自己的图标库：导入的位图/矢量 + 从程序里抽出来的。"""
        if not self.icon_dir.is_dir():
            return []
        items = []
        for path in sorted(self.icon_dir.iterdir(),
                           key=lambda item: item.stat().st_mtime, reverse=True):
            if path.suffix.lower() not in (".svg", ".png", ".ico", ".jpg", ".jpeg", ".bmp"):
                continue
            items.append({
                "name": path.stem,
                "key": self._icon_key(path),
                "size": _human_size(path.stat().st_size),
            })
        return items

    def _icon_key(self, path: Path) -> str:
        """图标在配置里的写法：``file:<绝对路径>``。"""
        return f"file:{path}"

    def _import_icon_file(self, path: str) -> str:
        """把一张图片（svg / png / ico / …）复制进图标库，返回它的 icon key。"""
        source = Path(path)
        if not source.is_file():
            return ""
        target = self.icon_dir / f"{_new_id()}{source.suffix.lower()}"
        try:
            shutil.copy2(source, target)
        except OSError:
            logger.exception("Failed to copy icon %s", source)
            self.showToast.emit("图标复制失败", "error")
            return ""
        self.showToast.emit(f"已添加图标：{source.name}", "success")
        return self._icon_key(target)

    @Slot(result=str)
    def importIcon(self) -> str:
        """把用户挑的图片复制进图标库，返回它的 icon key。"""
        path, _ = QFileDialog.getOpenFileName(
            None, "添加图标", str(Path.home()),
            "图标 (*.svg *.png *.ico *.jpg *.jpeg *.bmp);;所有文件 (*)")
        return self._import_icon_file(path) if path else ""

    @staticmethod
    def _shortcut_target(path: str | Path) -> Path | None:
        """快捷方式（.lnk）指向的目标；不是快捷方式或解析不出来时返回 None。"""
        source = Path(path)
        if source.suffix.lower() != ".lnk":
            return None
        target = QFileInfo(str(source)).symLinkTarget()
        if not target:
            return None
        candidate = Path(target)
        return candidate if candidate.exists() else None

    def _extract_icon_file(self, path: str, notify: bool = True) -> str:
        """从程序 / 快捷方式 / DLL 里抽出图标，落成 png 存进图标库。

        借用 Qt 的 QFileIconProvider：Windows 上它直接问系统外壳，能拿到 exe 内
        嵌的图标；快捷方式优先跟随目标，拿到的是程序自己的图标而不是带小箭头
        的那张；非 Windows 上会退化成一个通用图标，功能不至于报错消失。

        ``notify=False`` 用于保存槽位时的自动补图标：静默失败，不打扰用户。
        """
        # 没有 QApplication（裸脚本／无 GUI 环境）时 QFileIconProvider 会直接
        # 把进程干掉（原生访问冲突，Python 捕不住），先挡一道。
        if QApplication.instance() is None:
            logger.warning("No QApplication instance, skipping icon extraction")
            return ""
        source = self._shortcut_target(path) or Path(path)
        icon = self._icon_provider.icon(QFileInfo(str(source)))
        if icon.isNull():
            if notify:
                self.showToast.emit("这个文件里没有取到图标", "warning")
            return ""

        # 取最大的一档，通常在 32~256 之间。
        pixmap = icon.pixmap(256, 256)
        if pixmap.isNull():
            if notify:
                self.showToast.emit("这个文件里没有取到图标", "warning")
            return ""

        target = self.icon_dir / f"{_new_id()}.png"
        if not pixmap.save(str(target), "PNG"):
            if notify:
                self.showToast.emit("图标保存失败", "error")
            return ""
        if notify:
            self.showToast.emit(f"已提取图标：{source.name}", "success")
        return self._icon_key(target)

    @Slot(str, result=str)
    def extractIcon(self, path: str) -> str:
        """从程序 / 快捷方式 / DLL 里抽出图标（path 为空时弹文件选择框）。"""
        if not path:
            path = self.pickProgram()
        if not path:
            return ""
        return self._extract_icon_file(path)

    @Slot(str, result=str)
    def acquireIcon(self, path: str) -> str:
        """「从文件获取图标」的统一入口：程序走提取，图片走导入。

        支持 exe / dll / lnk（跟随快捷方式目标）与 ico / svg / png / jpg / bmp。
        """
        if not path:
            path = self.pickIconSource()
        if not path:
            return ""
        suffix = Path(path).suffix.lower()
        if suffix in IMAGE_ICON_SUFFIXES:
            return self._import_icon_file(path)
        return self._extract_icon_file(path)

    @Slot(result=str)
    def pickIconSource(self) -> str:
        """挑一个「图标来源」文件：程序、快捷方式或图片都行。"""
        path, _ = QFileDialog.getOpenFileName(
            None, "选择程序、快捷方式或图片", str(Path.home()),
            "程序与图标 (*.exe *.dll *.lnk *.ico *.svg *.png *.jpg *.jpeg *.bmp)"
            ";;程序与库 (*.exe *.dll *.lnk)"
            ";;图标图片 (*.ico *.svg *.png *.jpg *.jpeg *.bmp)"
            ";;所有文件 (*)")
        return path or ""

    @Slot(str, result=bool)
    def deleteCustomIcon(self, key: str) -> bool:
        """删掉图标库里的一张图；配置里还在引用它的地方会退回默认图标。"""
        name = key.removeprefix("file:")
        target = Path(name)
        # 只允许删图标库里的东西，免得被误导着删掉别处的文件。
        if target.parent.resolve() != self.icon_dir.resolve() or not target.is_file():
            return False
        try:
            target.unlink()
        except OSError:
            logger.exception("Failed to delete icon %s", target)
            return False
        self.showToast.emit("图标已删除", "success")
        return True

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
            created["path"] = path

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
        if kind not in SLOT_KINDS:
            return False
        row = ROW_PANEL if int(row) <= ROW_PANEL else ROW_STORAGE
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
        if target is None:
            return False
        slot = dict(slot)
        kind = str(slot.get("kind") or target.get("kind") or SLOT_ACTION)
        if kind not in SLOT_KINDS:
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
        if target is None:
            return False
        self._slots().remove(target)
        return self.save(changed="launcher")

    @Slot(int, int, int, result=bool)
    def moveLauncherSlot(self, row: int, index: int, delta: int) -> bool:
        """在第 ``row`` 行内前后挪一格。"""
        target = self._row_slot(row, index)
        if target is None:
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
            if "material" in settings:
                self.materialChanged.emit(str(previous["material"]))
        return saved

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
        """启动时后台预热任务计划状态：设置页打开时就不用起子进程了。"""
        if sys.platform != "win32":
            return
        autostart.refresh_task_exists_async(
            lambda _value: self.startupStateChanged.emit())

    @Slot()
    def refreshStartupState(self) -> None:
        """异步刷新任务计划状态；刷完经 ``startupStateChanged`` 通知界面。"""
        autostart.refresh_task_exists_async(
            lambda _value: self.startupStateChanged.emit())

    @Slot(result=bool)
    def reloadConfig(self) -> bool:
        """Re-read config.yaml from disk and tell the UI about it."""
        self._config = self._load()
        self._storage_cache = None
        self.configChanged.emit()
        self.launcherChanged.emit()
        self.settingsChanged.emit()
        return True

    @Slot(str, str)
    def notify(self, message: str, severity: str = "info") -> None:
        """Let QML raise a toast through the same path the backend uses."""
        self.showToast.emit(message, severity)

    @Slot(str)
    def requestPage(self, page: str) -> None:
        """QML 页面请求切到某一页（由 main.py 落到完整窗口上）。"""
        self.pageRequested.emit(str(page))

    @Slot(str)
    def requestSettingsSection(self, name: str) -> None:
        """标题栏「…」菜单里点设置分区：滚到设置页对应的分组。"""
        self.settingsSectionRequested.emit(str(name))

    @Slot(int, int)
    def requestSlotEditor(self, row: int, index: int) -> None:
        """小窗右键「编辑这一格 / 再加一格」：切到启动台页并当场打开编辑器。

        ``index`` 为 -1 表示新增。页面可能还没建好，信号发完还留一份待取
        （takePendingSlotEdit）。
        """
        pending = (int(row), int(index))
        self._pending_slot_edit = pending
        self.pageRequested.emit("launcher")
        self.slotEditRequested.emit(*pending)

    @Slot(result="QVariantMap")
    def takePendingSlotEdit(self) -> dict[str, Any]:
        """页面姗姗来迟时，把待编辑的槽位取走（读一次就清空）。"""
        if self._pending_slot_edit is None:
            return {}
        row, index = self._pending_slot_edit
        self._pending_slot_edit = None
        return {"row": row, "index": index}

    @Slot(result=bool)
    def resetToDefaults(self) -> bool:
        return self.save(_default_config(), changed="all")

    @Slot(result=bool)
    def restartAsAdmin(self) -> bool:
        return restart_elevated()

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

    @Slot("QVariantMap")
    def executeAction(self, action: dict) -> None:
        name = action.get("name", "")
        if self.action_executor is None:
            self.showToast.emit("动作执行器未初始化", "error")
        elif self.action_executor.execute(dict(action)):
            self.showToast.emit(f"已执行: {name}", "success")
        else:
            self.showToast.emit(f"执行失败: {name}", "error")

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
        """关于页要显示的运行环境信息。"""
        import platform

        from PySide6 import __version__ as pyside_version
        from PySide6.QtCore import qVersion

        return {
            "version": APP_VERSION,
            "python": platform.python_version(),
            "qt": qVersion(),
            "pyside": pyside_version,
            "system": f"{platform.system()} {platform.release()}",
            "configDir": str(self.config_dir),
            "configFile": str(self.config_file),
            "iconDir": str(self.icon_dir),
            "logFile": str(self.config_dir / "launcher.log"),
            "backend": "RinUI（内联，MIT）",
        }

    @staticmethod
    def _reveal(path: Path) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    # ------------------------------------------------------------------
    # External change watching
    # ------------------------------------------------------------------
    def startWatching(self) -> None:
        if self._observer is not None:
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
