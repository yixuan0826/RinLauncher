"""通知分类 / 渠道、风险规则、拼音搜索与恢复模式的配置层。"""

from __future__ import annotations

import yaml

from rin_launcher import risk_rules, search
from rin_launcher.config_manager import (
    NOTIFY_CATEGORIES,
    NOTIFY_CHANNELS,
    ConfigManager,
)


def _manager(tmp_path) -> ConfigManager:
    return ConfigManager(config_dir=tmp_path)


# ----------------------------------------------------------------------
# 通知
# ----------------------------------------------------------------------
def test_default_notifications_cover_every_category(qapp, tmp_path):
    manager = _manager(tmp_path)
    info = manager.getNotificationSettings()
    assert [item["key"] for item in info["categories"]] == list(NOTIFY_CATEGORIES)
    assert [item["key"] for item in info["channels"]] == list(NOTIFY_CHANNELS)
    # 默认只开应用内提示，免得一启动就弹系统通知。
    for category in info["categories"]:
        assert category["channels"]["toast"] is True
        assert category["channels"]["tray"] is False
        assert category["channels"]["native"] is False


def test_notification_channel_persists(qapp, tmp_path):
    manager = _manager(tmp_path)
    assert manager.setNotificationChannel("update", "native", True) is True
    # 未知类别 / 渠道直接拒绝，不往配置里写垃圾。
    assert manager.setNotificationChannel("nope", "native", True) is False
    assert manager.setNotificationChannel("update", "pigeon", True) is False

    again = _manager(tmp_path)
    assert again.getNotificationSettings()["categories"][1]["channels"]["native"] is True


def test_broken_notification_section_is_repaired(qapp, tmp_path):
    raw = {
        "version": 3,
        "settings": {},
        "notifications": {"update": {"tray": True}, "ghost": {"toast": False}},
    }
    (tmp_path / "config.yaml").write_text(
        yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")

    manager = _manager(tmp_path)
    channels = {item["key"]: item["channels"]
                for item in manager.getNotificationSettings()["categories"]}
    assert channels["update"]["tray"] is True
    assert "ghost" not in channels
    # 未知键补齐成默认值，不会因为缺字段而 KeyError。
    assert channels["system"]["toast"] is True


def test_notify_event_routes_by_channel(qapp, tmp_path):
    manager = _manager(tmp_path)
    toasts: list[tuple[str, str]] = []
    tray: list[str] = []
    manager.showToast.connect(lambda message, severity: toasts.append(
        (message, severity)))
    manager.attachTraySink(lambda message, _severity: tray.append(message))

    manager.setNotificationChannel("action", "toast", False)
    manager.setNotificationChannel("action", "tray", True)
    manager.notifyEvent("action", "打开了记事本", "info")
    assert toasts == []
    assert tray == ["打开了记事本"]

    # 错误与警告永远补一条应用内提示，渠道全关也不会漏。
    manager.notifyEvent("action", "执行失败", "error")
    assert toasts == [("执行失败", "error")]


# ----------------------------------------------------------------------
# 风险规则
# ----------------------------------------------------------------------
def test_risk_rules_flag_dangerous_commands():
    verdict = risk_rules.check({
        "action": {"type": "cmd", "target": "cmd.exe",
                   "arguments": "/c format d: /y"},
    })
    assert verdict["level"] == risk_rules.HIGH
    assert "格式化磁盘" in verdict["reasons"]


def test_risk_rules_flag_elevation_and_ignore_plain_slots():
    elevated = risk_rules.check({
        "action": {"type": "file", "target": "tool.exe", "run_as": "admin"},
    })
    assert elevated["level"] == risk_rules.MEDIUM
    assert "需要管理员权限" in elevated["reasons"]

    assert risk_rules.check({"action": {"type": "url", "target": "https://example.com"}}) == {
        "level": "", "reasons": []}
    assert risk_rules.check(None) == {"level": "", "reasons": []}


# ----------------------------------------------------------------------
# 搜索
# ----------------------------------------------------------------------
def test_search_matches_plain_pinyin_and_initials():
    assert search.matches("启动", "启动台")
    assert search.matches("qidongtai", "启动台")
    assert search.matches("qdt", "启动台")
    assert search.matches("", "任意内容")
    assert not search.matches("zzzz", "启动台")


def test_search_slots_returns_row_index(qapp, tmp_path):
    manager = _manager(tmp_path)
    assert manager.addLauncherSlot(0, {
        "kind": "action",
        "label": "启动台测试",
        "action": {"type": "file", "target": "C:\\example.exe"},
    })

    hits = manager.searchSlots("qdt")
    names = [hit["name"] for hit in hits]
    # 默认面板里的「启动台设置」也命中 qdt，这里只关心新加的这一格。
    assert "启动台测试" in names
    hit = next(item for item in hits if item["name"] == "启动台测试")
    assert hit["row"] == 0
    # rowIndex 是「本行第几个」，编辑 / 删除接口要的就是它。
    row_slots = [slot for slot in manager.getRawLauncherSlots()
                 if int(slot.get("row", 0)) == hit["row"]]
    assert 0 <= hit["rowIndex"] < len(row_slots)
    assert row_slots[hit["rowIndex"]]["label"] == "启动台测试"


# ----------------------------------------------------------------------
# 恢复模式
# ----------------------------------------------------------------------
def test_clean_temp_files_removes_update_residue(qapp, tmp_path):
    updates = tmp_path / "updates"
    (updates / "staging-1").mkdir(parents=True)
    (updates / "staging-1" / "payload.bin").write_bytes(b"0" * 32)
    (updates / "RinLauncher-9.9.9.zip").write_bytes(b"0" * 16)

    manager = _manager(tmp_path)
    result = manager.cleanTempFiles()
    assert result["removed"] == 2
    assert list(updates.iterdir()) == []


def test_reset_app_settings_keeps_launcher(qapp, tmp_path):
    manager = _manager(tmp_path)
    manager.updateSettings({"theme": "dark", "tileSize": "large"})
    slots_before = len(manager.getRawLauncherSlots())

    assert manager.resetAppSettings() is True
    settings = manager.getSettings()
    assert settings["theme"] == "system"
    assert settings["tileSize"] == "medium"
    assert len(manager.getRawLauncherSlots()) == slots_before


def test_recovery_info_lists_latest_backup(qapp, tmp_path):
    manager = _manager(tmp_path)
    manager.backupNow()
    info = manager.getRecoveryInfo()
    assert info["backupCount"] >= 1
    assert info["latestBackup"].endswith(".yaml")
    assert info["launchMode"] in ("normal", "safe", "diagnostic")
    assert info["version"]
