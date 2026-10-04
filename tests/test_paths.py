"""数据目录解析：exe 同级 data/、不可写回退、旧数据一次性迁移。"""

from __future__ import annotations

import rin_launcher.config_manager as cm


def _fake_frozen(monkeypatch, tmp_path, legacy: str = "legacy") -> None:
    exe = tmp_path / "RinLauncher.exe"
    exe.write_bytes(b"")
    monkeypatch.setattr(cm.sys, "frozen", True, raising=False)
    monkeypatch.setattr(cm.sys, "executable", str(exe), raising=False)
    # 迁移的「老目录」也指到临时目录里，别把真实 %APPDATA% 扯进来。
    monkeypatch.setattr(cm, "DEFAULT_CONFIG_DIR", tmp_path / legacy)


def test_dev_mode_keeps_appdata(monkeypatch):
    monkeypatch.delattr(cm.sys, "frozen", raising=False)
    assert cm.resolve_config_dir() == cm.DEFAULT_CONFIG_DIR


def test_frozen_uses_exe_sibling_data_dir(monkeypatch, tmp_path):
    _fake_frozen(monkeypatch, tmp_path)
    target = cm.resolve_config_dir()
    assert target == tmp_path / "data"
    assert target.is_dir()


def test_unwritable_data_dir_falls_back(monkeypatch, tmp_path):
    _fake_frozen(monkeypatch, tmp_path)
    monkeypatch.setattr(cm, "_dir_writable", lambda path: False)
    assert cm.resolve_config_dir() == tmp_path / "legacy"


def test_legacy_data_migration_copies_config_and_icons(monkeypatch, tmp_path):
    legacy = tmp_path / "legacy"
    (legacy / "icons").mkdir(parents=True)
    (legacy / "config.yaml").write_text("version: 3\n", encoding="utf-8")
    (legacy / "icons" / "custom_1.svg").write_text("<svg/>", encoding="utf-8")
    monkeypatch.setattr(cm, "DEFAULT_CONFIG_DIR", legacy)

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    cm._migrate_legacy_data(data_dir)

    assert (data_dir / "config.yaml").read_text(encoding="utf-8") == "version: 3\n"
    assert (data_dir / "icons" / "custom_1.svg").read_text(encoding="utf-8") == "<svg/>"


def test_migration_does_not_overwrite_new_config(monkeypatch, tmp_path):
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    (legacy / "config.yaml").write_text("old\n", encoding="utf-8")
    monkeypatch.setattr(cm, "DEFAULT_CONFIG_DIR", legacy)

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "config.yaml").write_text("new\n", encoding="utf-8")
    cm._migrate_legacy_data(data_dir)

    assert (data_dir / "config.yaml").read_text(encoding="utf-8") == "new\n"
