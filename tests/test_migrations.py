"""配置迁移回归：autoStart → startupMode、keymouse → keyboard、坏值兜底。"""

from __future__ import annotations

import rin_launcher.config_manager as cm


def _load_with(tmp_path, yaml_text: str):
    (tmp_path / "config.yaml").write_text(yaml_text, encoding="utf-8")
    return cm.ConfigManager(config_dir=tmp_path)


def test_autostart_true_migrates_to_normal(qapp, tmp_path):
    manager = _load_with(tmp_path, "settings:\n  autoStart: true\n")
    assert manager.config["settings"]["startupMode"] == "normal"
    assert "autoStart" not in manager.config["settings"]


def test_autostart_false_migrates_to_off(qapp, tmp_path):
    manager = _load_with(tmp_path, "settings:\n  autoStart: false\n")
    assert manager.config["settings"]["startupMode"] == "off"
    assert "autoStart" not in manager.config["settings"]


def test_explicit_startup_mode_wins_over_legacy_bool(qapp, tmp_path):
    manager = _load_with(
        tmp_path, "settings:\n  startupMode: admin\n  autoStart: true\n")
    assert manager.config["settings"]["startupMode"] == "admin"
    assert "autoStart" not in manager.config["settings"]


def test_bogus_startup_mode_falls_back_to_off(qapp, tmp_path):
    manager = _load_with(tmp_path, "settings:\n  startupMode: turbo\n")
    assert manager.config["settings"]["startupMode"] == "off"


def test_keymouse_steps_migrate_to_keyboard(qapp, tmp_path):
    manager = _load_with(tmp_path, """
version: 3
actions:
  - id: abc123
    name: 测试动作
    type: keymouse
    keymouse_steps:
      - {type: key, key: "Ctrl+C", action: click, duration: 0.1}
      - {type: mouse, x: 5, y: 6}
settings: {}
""")
    entry = manager.config["actions"][0]
    assert entry["type"] == "keyboard"
    assert "keymouse_steps" not in entry
    assert entry["keyboard_steps"] == [
        {"type": "key", "key": "Ctrl+C", "action": "click", "duration": 0.1}]
