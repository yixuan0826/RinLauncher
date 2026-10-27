"""备份列表、恢复与备份策略。"""

from __future__ import annotations

from pathlib import Path

from rin_launcher.config_manager import ConfigManager


def test_list_and_restore_roundtrip(qapp, tmp_path):
    manager = ConfigManager(config_dir=tmp_path)
    manager.updateSettings({"globalHotkey": "Ctrl+Alt+R"})
    backup = Path(manager.backupNow()).name
    assert backup

    manager.updateSettings({"globalHotkey": "Ctrl+Shift+X"})
    assert manager.restoreBackup(backup) is True
    assert manager.config["settings"]["globalHotkey"] == "Ctrl+Alt+R"

    names = [item["name"] for item in manager.listBackups()]
    assert backup in names


def test_restore_rejects_path_outside_backup_dir(qapp, tmp_path):
    manager = ConfigManager(config_dir=tmp_path)
    assert manager.restoreBackup("../config.yaml") is False


def test_backup_interval_follows_settings(qapp, tmp_path):
    manager = ConfigManager(config_dir=tmp_path)
    manager.updateSettings({"autoBackupIntervalDays": 3})
    assert manager._backup_interval_days() == 3


def test_delete_backup(qapp, tmp_path):
    manager = ConfigManager(config_dir=tmp_path)
    backup = Path(manager.backupNow()).name
    assert manager.deleteBackup(backup) is True
    assert manager.deleteBackup(backup) is False
