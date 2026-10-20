"""配置迁移回归：autoStart → startupMode、内联 keymouse → keyboard、下线功能清理。"""

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


def test_legacy_red_accent_migrates_to_system(qapp, tmp_path):
    """旧颜色选择器把默认红色写进配置；读到它时切到跟随系统。"""
    manager = _load_with(tmp_path, "settings:\n  accentColor: '#ff0000'\n")
    assert manager.config["settings"]["accentColorMode"] == "system"


def test_custom_accent_stays_custom(qapp, tmp_path):
    manager = _load_with(tmp_path, "settings:\n  accentColor: '#123456'\n")
    assert manager.config["settings"]["accentColorMode"] == "custom"


def test_unknown_settings_keys_are_dropped(qapp, tmp_path):
    """已下线的设置键不再跟着配置走：读入时丢掉，并写回干净的文件。"""
    manager = _load_with(
        tmp_path,
        "version: 3\n"
        "settings:\n"
        "  language: zh_CN\n"
        "  gridColumns: 6\n"
        "  theme: dark\n",
    )
    settings = manager.config["settings"]
    assert "language" not in settings
    assert "gridColumns" not in settings
    assert settings["theme"] == "dark"
    on_disk = (tmp_path / "config.yaml").read_text(encoding="utf-8")
    assert "language:" not in on_disk


def test_inline_keymouse_steps_migrate_to_keyboard(qapp, tmp_path):
    manager = _load_with(tmp_path, """
version: 3
launcher:
  slots:
    - kind: action
      row: 0
      action:
        type: keymouse
        keymouse_steps:
          - {type: key, key: "Ctrl+C", action: click, duration: 0.1}
          - {type: mouse, x: 5, y: 6}
settings: {}
""")
    entry = manager.config["launcher"]["slots"][0]["action"]
    assert entry["type"] == "keyboard"
    assert "keymouse_steps" not in entry
    assert entry["keyboard_steps"] == [
        {"type": "key", "key": "Ctrl+C", "action": "click", "duration": 0.1}]


def test_removed_quick_action_library_is_dropped(qapp, tmp_path):
    """旧配置里的动作库 / 分区 / ref 槽位都随功能一起下线。"""
    manager = _load_with(tmp_path, """
version: 2
actions:
  - id: abc123
    name: 老动作
    type: file
    target: notepad.exe
categories:
  - {id: c1, name: 常用}
launcher:
  slots:
    - {kind: action, row: 0, ref: abc123}
    - {kind: tool, row: 0, key: launcherPage}
settings: {}
""")
    assert "actions" not in manager.config
    assert "categories" not in manager.config
    kinds = [slot["kind"] for slot in manager.config["launcher"]["slots"]]
    # ref 槽位没有内联动作，无法还原，直接丢弃；内置功能保留。
    assert kinds == ["tool"]
    # 规范化后的配置会立刻写回磁盘，旧键不应该继续留在文件里。
    on_disk = (tmp_path / "config.yaml").read_text(encoding="utf-8")
    assert "actions:" not in on_disk
    assert "categories:" not in on_disk


def test_obsolete_compact_acrylic_is_removed_on_load(qapp, tmp_path):
    manager = _load_with(tmp_path, """
version: 3
settings:
  compactAcrylic: true
""")
    assert "compactAcrylic" not in manager.config["settings"]
    on_disk = (tmp_path / "config.yaml").read_text(encoding="utf-8")
    assert "compactAcrylic" not in on_disk
    assert "updateChannel:" in on_disk
    assert "autoCheckUpdates:" in on_disk
