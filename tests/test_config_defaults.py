"""默认配置与版本号：库不带预设条目、版本号只有一个来源。"""

from __future__ import annotations

from pathlib import Path

import tomllib

from rin_launcher import __version__

ROOT = Path(__file__).resolve().parent.parent


def test_version_single_source():
    import rin_launcher.config_manager as cm

    assert __version__ == "1.0.0"
    # config_manager 的 APP_VERSION 必须就是包版本本身，不是另一只手维护的副本。
    assert cm.APP_VERSION == __version__


def test_pyproject_reads_version_dynamically():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]
    assert "version" not in project
    assert "version" in project["dynamic"]
    attr = data["tool"]["setuptools"]["dynamic"]["version"]["attr"]
    assert attr == "rin_launcher.__version__"


def test_default_config_has_no_preset_actions():
    import rin_launcher.config_manager as cm

    config = cm._default_config()
    # 库从空开始：放什么条目完全由用户决定。
    assert config["actions"] == []

    slots = config["launcher"]["slots"]
    # 面板 6 个内置功能 + 存储区（U 盘 + 磁盘）。
    assert len(slots) == 8
    assert all(slot["kind"] == "tool" for slot in slots[:6])
    assert [slot["kind"] for slot in slots[6:]] == ["usb", "path"]
    # 分区骨架仍然保留，第一个是「常用」。
    assert config["categories"][0]["name"] == "常用"
    assert config["settings"]["startupMode"] == "off"
