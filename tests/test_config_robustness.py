"""配置持久化：坏 YAML 恢复、schema 兜底、写失败不改内存、appmodset 容错。"""

from __future__ import annotations

from pathlib import Path

import yaml

from rin_launcher import app_mode, atomic
from rin_launcher.config_manager import ConfigManager


def _slot(label: str) -> dict:
    return {
        "kind": "tool",
        "row": 0,
        "label": label,
        "icon": "",
        "key": "settings",
    }


def test_empty_launcher_stays_empty(qapp, tmp_path: Path):
    ConfigManager(config_dir=tmp_path)
    second = ConfigManager(config_dir=tmp_path)
    assert second.config["launcher"]["slots"] == []


def test_broken_yaml_is_preserved_and_recovered(qapp, tmp_path: Path):
    first = ConfigManager(config_dir=tmp_path)
    first.config["launcher"]["slots"] = [_slot("保留我")]
    assert first.save(changed="all")
    # 再存一次：轮转备份里才会包含这一格（最近一份可用配置）。
    assert first.save(changed="all")
    # 写一份坏 YAML 模拟断电截断。
    (tmp_path / "config.yaml").write_text("launcher: [broken\n", encoding="utf-8")

    recovered = ConfigManager(config_dir=tmp_path)
    assert recovered.config["launcher"]["slots"][0]["label"] == "保留我"
    assert list(tmp_path.glob("config.yaml.broken-*")), "坏文件应被保留"


def test_bad_schema_values_are_clamped(qapp, tmp_path: Path):
    (tmp_path / "config.yaml").write_text(
        yaml.safe_dump({
            "version": 3,
            "launcher": {"slots": [], "storagePath": ""},
            "settings": {
                "autoBackupKeep": "abc",
                "autoBackupIntervalDays": 9999,
                "accentColor": "red",
                "theme": "neon",
            },
        }, allow_unicode=True),
        encoding="utf-8")
    cm = ConfigManager(config_dir=tmp_path)
    settings = cm.config["settings"]
    assert settings["autoBackupKeep"] == 8
    assert settings["autoBackupIntervalDays"] == 365
    assert settings["accentColor"] == "#0078D4"
    assert settings["theme"] == "system"
    # 备份页不再因为非法值抛异常。
    assert cm.getBackupInfo()["keepCount"] == 8


def test_save_failure_keeps_memory_config(qapp, tmp_path: Path, monkeypatch):
    cm = ConfigManager(config_dir=tmp_path)
    original = cm.config
    replacement = cm._normalize(dict(_minimal_config()))
    replacement["settings"]["globalHotkey"] = "Ctrl+Alt+L"

    monkeypatch.setattr(atomic, "atomic_write_text", lambda *_a, **_k: False)
    assert cm.save(replacement, changed="all") is False
    assert cm.config is original
    assert cm.config["settings"]["globalHotkey"] != "Ctrl+Alt+L"


def test_restore_failure_keeps_memory_and_config(qapp, tmp_path: Path, monkeypatch):
    cm = ConfigManager(config_dir=tmp_path)
    backup = cm.backupNow()
    assert backup
    current = cm.config["settings"]["globalHotkey"]
    monkeypatch.setattr(atomic, "atomic_write_text", lambda *_a, **_k: False)
    assert cm.restoreBackup(Path(backup).name) is False
    assert cm.config["settings"]["globalHotkey"] == current


def test_appmodset_non_utf8_does_not_crash(tmp_path: Path):
    target = tmp_path / app_mode.CONF_NAME
    target.write_bytes(b"first-run==true\n# \xff\xfe broken\nchannel==stable\n")
    values, problems, _ = app_mode.load(tmp_path)
    assert values["first-run"] is True
    assert values["channel"] == "stable"
    assert any("解码" in item for item in problems)
    # 写回时保留其余键，并且是原子写。
    assert app_mode.update(tmp_path, {"first-run": False})
    values, _, _ = app_mode.load(tmp_path)
    assert values["first-run"] is False


def _minimal_config() -> dict:
    return {
        "version": 3,
        "launcher": {"slots": [], "storagePath": ""},
        "settings": {},
        "notifications": {},
    }
