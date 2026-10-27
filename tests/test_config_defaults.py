"""默认配置与版本号：库不带预设条目、版本号只有一个来源。"""

from __future__ import annotations

from pathlib import Path

import tomllib

from rin_launcher import __version__

ROOT = Path(__file__).resolve().parent.parent


def test_version_single_source():
    import rin_launcher.config_manager as cm

    assert __version__ == "1.1.8"
    # config_manager 的 APP_VERSION 必须就是包版本本身，不是另一只手维护的副本。
    assert cm.APP_VERSION == __version__


def test_pyproject_reads_version_dynamically():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]
    assert "version" not in project
    assert "version" in project["dynamic"]
    attr = data["tool"]["setuptools"]["dynamic"]["version"]["attr"]
    assert attr == "rin_launcher.__version__"


def test_default_config_has_no_quick_action_library():
    import rin_launcher.config_manager as cm

    config = cm._default_config()
    # 「快捷操作」已经整体下线：默认配置里不再有动作库和分区。
    assert "actions" not in config
    assert "categories" not in config

    slots = config["launcher"]["slots"]
    # 面板 5 个内置功能 + 存储区（U 盘 + 磁盘）。
    assert len(slots) == 7
    assert all(slot["kind"] == "tool" for slot in slots[:5])
    assert [slot["kind"] for slot in slots[5:]] == ["usb", "path"]
    assert config["settings"]["startupMode"] == "off"
    assert config["settings"]["updateChannel"] == "stable"
    assert config["settings"]["autoCheckUpdates"] is True
    assert "compactAcrylic" not in config["settings"]


def test_accent_color_is_persisted_and_signalled(qapp, tmp_path):
    """强调色以 config.yaml 为准：重启后仍能读回，变化时通知所有窗口。"""
    from rin_launcher.config_manager import ConfigManager

    first = ConfigManager(config_dir=tmp_path)
    try:
        # 新配置默认跟随系统；测试固定到自定义模式再验证持久化。
        first.updateSettings({"accentColorMode": "custom"})
        assert first.accentColor == "#0078d4"
        colours = []
        first.accentColorChanged.connect(colours.append)
        assert first.updateSettings({"accentColor": "#5175a1"})
        assert first.accentColor == "#5175a1"
        assert colours == ["#5175a1"]
    finally:
        first.stopWatching()

    second = ConfigManager(config_dir=tmp_path)
    try:
        assert second.getSettings()["accentColorMode"] == "custom"
        assert second.accentColor == "#5175a1"
    finally:
        second.stopWatching()
