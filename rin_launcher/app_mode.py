"""``appmodset.conf``：启动模式与发布通道的单一来源。

1.1.11 起，安装目录下的 ``appmodset.conf`` 取代 ``channel.txt``。文件是逐行的
``key==value``，支持 ``#`` 注释；布尔项只认 ``true`` / ``false``（对大小写和
首尾空白宽容，但不接受 1/yes/on 之类的写法，避免「看起来生效了」）。

优先级（从高到低）::

    failsafe > recovery > first-run > debug

``failsafe`` 与 ``recovery`` 都会让进程只加载恢复窗口；``first-run`` 额外决定
是否展示 OOBE；``debug`` 只把日志级别拉到 DEBUG。``normal-boot == false`` 表示
启动后不自动显示小窗（等同「启动时最小化」）。

老版本的 ``channel.txt`` 只在首次读取时迁移一次，旧文件保留，方便回退。
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rin_launcher import atomic

logger = logging.getLogger(__name__)

CONF_NAME = "appmodset.conf"
LEGACY_CHANNEL_NAME = "channel.txt"

# 键名与默认值。channel 沿用 updater / 设置页现有的取值。
DEFAULTS: dict[str, Any] = {
    "first-run": True,
    "normal-boot": True,
    "failsafe": False,
    "debug": False,
    "channel": "stable",
    "recovery": False,
}
CHANNEL_VALUES: tuple[str, ...] = ("stable", "prerelease")

_TEMPLATE = """\
# Rin Launcher 启动配置
# 布尔项只写 true / false；channel 只写 stable / prerelease。
# 修改后重启程序生效。
first-run==true
normal-boot==true
failsafe==false
debug==false
channel==stable
recovery==false
"""


def app_root() -> Path:
    """安装目录：冻结包是 exe 同级，源码运行是仓库根。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _bool_value(raw: str) -> bool | None:
    text = str(raw or "").strip().lower()
    if text == "true":
        return True
    if text == "false":
        return False
    return None


def parse(text: str) -> tuple[dict[str, Any], list[str]]:
    """解析配置文本，返回 ``(值, 诊断)``；坏行不会抛异常。"""
    values = dict(DEFAULTS)
    problems: list[str] = []
    for number, raw_line in enumerate(str(text or "").splitlines(), 1):
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if "==" not in line:
            problems.append(f"第 {number} 行缺少 ==")
            continue
        key, value = (part.strip() for part in line.split("==", 1))
        if key not in DEFAULTS:
            problems.append(f"第 {number} 行未知键 {key!r}")
            continue
        if key == "channel":
            if value in CHANNEL_VALUES:
                values[key] = value
            else:
                problems.append(
                    f"第 {number} 行 channel 只能是 {' / '.join(CHANNEL_VALUES)}")
            continue
        parsed = _bool_value(value)
        if parsed is None:
            problems.append(f"第 {number} 行 {key} 只能是 true / false")
            continue
        values[key] = parsed
    return values, problems


def _read_text(path: Path) -> str:
    """UTF-8 读取并去掉 BOM；坏字节用替换符兜住，绝不抛 UnicodeDecodeError。

    冻结包里 ``encoding="utf-8-sig"`` 会触发 ``LookupError``（1.1.6~1.1.8
    踩过的坑），所以编码器固定用 utf-8，BOM 自己处理。用户用 GBK 编辑器写
    中文注释时会出现非法字节；这种文件仍要能读出其余键，程序不能启动即崩。
    """
    return path.read_text(encoding="utf-8", errors="replace").lstrip("\ufeff")


def _migrate_channel(root: Path, target: Path) -> None:
    """``channel.txt`` → ``appmodset.conf``，只迁一次，旧文件保留。"""
    legacy = root / LEGACY_CHANNEL_NAME
    if not legacy.is_file() or target.exists():
        return
    try:
        value = _read_text(legacy).strip().lower()
    except OSError:
        logger.debug("无法读取 %s，跳过迁移", legacy, exc_info=True)
        return
    channel = "prerelease" if ("pre" in value or "-" in value) else "stable"
    if not atomic.atomic_write_text(
            target, _TEMPLATE.replace("channel==stable", f"channel=={channel}", 1)):
        logger.debug("无法写入 %s，跳过迁移", target)


def load(root: Path | None = None) -> tuple[dict[str, Any], list[str], Path]:
    """读取安装目录的配置；文件缺失时生成一份带注释的默认文件。"""
    base = Path(root) if root is not None else app_root()
    path = base / CONF_NAME
    _migrate_channel(base, path)
    if not path.is_file():
        if not atomic.atomic_write_text(path, _TEMPLATE):
            logger.warning("%s 写不出来，将只在内存里使用默认值", path)
        return dict(DEFAULTS), [], path
    try:
        text = _read_text(path)
    except OSError:
        logger.warning("无法读取 %s，使用默认启动配置", path, exc_info=True)
        return dict(DEFAULTS), ["配置文件读取失败"], path
    values, problems = parse(text)
    if "\ufffd" in text:
        problems.append("配置文件包含无法解码的字节（已按替换字符处理）")
    return values, problems, path


def update(root: Path | None, updates: dict[str, Any]) -> bool:
    """按行改写配置，保留未知行与用户的注释。

    写不进去（例如安装到 ``Program Files``）时返回 False，由调用方决定是否
    退回到用户数据目录的覆盖文件。
    """
    base = Path(root) if root is not None else app_root()
    path = base / CONF_NAME
    try:
        original = _read_text(path) if path.is_file() else _TEMPLATE
    except OSError:
        original = _TEMPLATE
    pending = {key: value for key, value in updates.items() if key in DEFAULTS}
    lines: list[str] = []
    seen: set[str] = set()
    for raw_line in original.splitlines():
        stripped = raw_line.strip()
        key = stripped.split("==", 1)[0].strip() if "==" in stripped else ""
        if key in pending:
            value = pending[key]
            if isinstance(value, bool):
                text = "true" if value else "false"
            else:
                text = str(value)
            lines.append(f"{key}=={text}")
            seen.add(key)
        else:
            lines.append(raw_line)
    for key, value in pending.items():
        if key in seen:
            continue
        text = ("true" if value else "false") if isinstance(value, bool) else str(value)
        lines.append(f"{key}=={text}")
    if not atomic.atomic_write_text(path, "\n".join(lines).rstrip() + "\n"):
        logger.warning("无法写入 %s", path)
        return False
    return True


@dataclass(frozen=True)
class Mode:
    """本次启动的生效模式。"""

    values: dict[str, Any] = field(default_factory=lambda: dict(DEFAULTS))
    problems: list[str] = field(default_factory=list)

    @property
    def first_run(self) -> bool:
        return bool(self.values.get("first-run"))

    @property
    def debug(self) -> bool:
        return bool(self.values.get("debug"))

    @property
    def recovery_only(self) -> bool:
        return bool(self.values.get("failsafe") or self.values.get("recovery"))

    @property
    def safe_mode(self) -> bool:
        return bool(self.values.get("failsafe"))

    @property
    def start_minimized(self) -> bool:
        return not bool(self.values.get("normal-boot", True))

    @property
    def channel(self) -> str:
        value = str(self.values.get("channel") or "stable")
        return value if value in CHANNEL_VALUES else "stable"

    @property
    def launch_mode(self) -> str:
        if self.values.get("failsafe"):
            return "safe"
        if self.values.get("recovery"):
            return "recovery"
        return "normal"


def effective_mode(values: dict[str, Any]) -> Mode:
    """把解析结果收敛成生效模式（优先级集中在这里，方便测试）。"""
    merged = {**DEFAULTS, **{key: values[key] for key in DEFAULTS if key in values}}
    return Mode(merged)


def mark_first_run_done(root: Path | None = None) -> bool:
    """OOBE 完成后写回 ``first-run==false``。"""
    return update(root, {"first-run": False})
