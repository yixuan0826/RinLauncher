"""通知的功能类别、投递渠道与配置归一化。

配置里存成 ``{类别: {渠道: bool}}``。单独成一个模块有两个好处：
``config_manager`` 不再继续变胖，测试也能直接对着这张表断言，不用去碰
QObject / 文件系统。
"""

from __future__ import annotations

from typing import Any

# 功能类别：用户按「这条通知是干什么的」来关，而不是按代码里的消息来源。
CATEGORIES: dict[str, str] = {
    "action": "动作执行",
    "update": "更新提示",
    "backup": "备份与恢复",
    "system": "系统与设置",
}

# 投递渠道。toast 是应用内轻提示，tray 是托盘气泡，native 是 Windows 通知。
CHANNELS: dict[str, str] = {
    "toast": "应用内提示",
    "tray": "托盘气泡",
    "native": "Windows 通知",
}

# 默认只开应用内提示：托盘气泡与系统通知要用户自己勾。
DEFAULT_CHANNELS: dict[str, bool] = {"toast": True, "tray": False, "native": False}


def defaults() -> dict[str, dict[str, bool]]:
    """一份完整的默认配置（每个类别都是一套独立字典）。"""
    return {key: dict(DEFAULT_CHANNELS) for key in CATEGORIES}


def normalize(raw: Any) -> dict[str, dict[str, bool]]:
    """把配置里的 ``notifications`` 段补全。

    未知类别、非字典的条目、未知渠道一律忽略；缺的渠道按默认值补齐，
    这样旧配置读进来也不会在界面上出现空洞。
    """
    result = defaults()
    if not isinstance(raw, dict):
        return result
    for category, channels in raw.items():
        if category not in result or not isinstance(channels, dict):
            continue
        for channel in CHANNELS:
            if channel in channels:
                result[category][channel] = bool(channels[channel])
    return result


def channels_for(config: Any, category: str) -> dict[str, bool]:
    """读取某一类的渠道开关；缺配置时退回默认值。"""
    section = config.get("notifications") if isinstance(config, dict) else None
    entry = section.get(category) if isinstance(section, dict) else None
    if not isinstance(entry, dict):
        return dict(DEFAULT_CHANNELS)
    return {channel: bool(entry.get(channel, DEFAULT_CHANNELS[channel]))
            for channel in CHANNELS}
