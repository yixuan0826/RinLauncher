"""默认配置与版本号：库不带预设条目、版本号只有一个来源。"""

from __future__ import annotations

import tomllib
from pathlib import Path

from rin_launcher import __version__

ROOT = Path(__file__).resolve().parent.parent


def test_version_single_source():
    import rin_launcher.config_manager as cm

    # 版本号只在包里有唯一来源；这里只校验格式与两处一致，改版本不用改测试。
    parts = __version__.split(".")
    assert len(parts) == 3 and all(part.isdigit() for part in parts)
    # config_manager 的 APP_VERSION 必须就是包版本本身，不是另一只手维护的副本。
    assert cm.APP_VERSION == __version__
    # 每个版本都要在更新日志里留条目，免得发版时忘了写。
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## {__version__}" in changelog


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

    # 首次运行只生成一份空启动台，内容交给 OOBE / 用户自己添加。
    assert config["launcher"]["slots"] == []
    assert config["settings"]["startupMode"] == "off"
    assert config["settings"]["updateChannel"] == "stable"
    assert config["settings"]["autoCheckUpdates"] is True
    assert config["settings"]["compactMode"] == "normal"
    assert config["settings"]["windowCorner"] == "bottom-right"
    assert config["settings"]["compactTransparency"] == 82
    assert "compactAcrylic" not in config["settings"]


def test_accent_color_is_persisted_and_signalled(qapp, tmp_path):
    """强调色以 config.yaml 为准：重启后仍能读回，变化时通知所有窗口。"""
    from rin_launcher.config_manager import ConfigManager

    first = ConfigManager(config_dir=tmp_path)
    try:
        # 新配置默认跟随系统；测试固定到自定义模式再验证持久化。
        first.updateSettings({"accentColorMode": "custom"})
        assert first.accentColor == "#0078D4"
        colours = []
        first.accentColorChanged.connect(colours.append)
        assert first.updateSettings({"accentColor": "#5175a1"})
        # 写入时统一大写（QML/Qt 两种写法都能解析）。
        assert first.accentColor == "#5175A1"
        assert colours == ["#5175A1"]
    finally:
        first.stopWatching()

    second = ConfigManager(config_dir=tmp_path)
    try:
        assert second.getSettings()["accentColorMode"] == "custom"
        assert second.accentColor == "#5175A1"
    finally:
        second.stopWatching()
