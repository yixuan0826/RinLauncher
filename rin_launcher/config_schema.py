"""配置的字段默认值与清洗规则。

``config_manager`` 只留编排（读写、信号、QML 门面）；字段默认值、类型夹取和
外部数据的清洗规则放这里。这一层刻意不 import Qt，可以脱离 QApplication 单测。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rin_launcher import notifications

DEFAULT_SETTINGS: dict[str, Any] = {
    "theme": "system",
    "showTray": True,
    "startMinimized": False,
    "startupMode": "off",
    "globalHotkey": "Ctrl+Space",
    "animationEnabled": True,
    "accentColor": "#0078d4",
    # system = 跟随 Windows 强调色；custom = 使用 accentColor。
    "accentColorMode": "system",
    "adminAutoElevate": True,
    "confirmAdminActions": True,
    "logLevel": "INFO",
    # 面板磁贴尺寸：small / medium / large。档位只定「目标边长」，
    # 每行放几格由小窗宽度自动算（见 qml/components/CompactPanel.qml）。
    "tileSize": "medium",
    "autoBackupEnabled": True,
    "autoBackupIntervalDays": 7,
    "autoBackupKeep": 8,
    "updateChannel": "stable",
    "autoCheckUpdates": True,
    "updateMirror": "github",
    "updateMirrorAuto": True,
    # 小窗形态：normal（完整启动台）/ mini（单行工具条）。
    "compactMode": "normal",
    # 贴角位置与像素偏移，两种形态都适用。
    "windowCorner": "bottom-right",
    "windowOffsetX": 0,
    "windowOffsetY": 0,
    # 三套形态各自的透明度（0 = 不透明，90 = 很透）。上限留给可读性。
    # 完整版默认 82% 透明，与 1.1.10 的云母观感一致。
    "compactTransparency": 82,
    "miniTransparency": 30,
    # auto = 检测到 Wallpaper Engine 时用 Acrylic，否则 Mica。
    "backdropMode": "auto",
    # 全局去掉 Windows 快捷方式小箭头（改 HKCU，重启资源管理器后生效）。
    "shortcutArrowGlobal": True,
}

# 通知分两级：功能类别 × 投递渠道。表的定义与归一化在 notifications 模块里，
# 这里只保留同名引用，避免调用方到处改 import。
NOTIFY_CATEGORIES = notifications.CATEGORIES
NOTIFY_CHANNELS = notifications.CHANNELS


def _clamp_int(raw: Any, default: int, low: int, high: int) -> int:
    """把外部写进来的整数夹到安全区间；写坏了就用默认值。"""
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, value))


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


def _derive_action_name(action: dict[str, Any]) -> str:
    """内联动作没有名字，按类型从目标里取一个一看就懂的显示名。"""
    kind = action.get("type")
    if kind == "keyboard":
        return "按键动作"
    if kind == "uwp":
        return "UWP 应用"
    target = str(action.get("target") or "").strip().strip('"')
    if not target:
        return "未配置动作"
    if kind == "url":
        return target
    return Path(target).name or target
