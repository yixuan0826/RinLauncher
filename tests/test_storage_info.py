"""存储卡片：盘根显示卷标、文件夹显示目录名。"""

from __future__ import annotations

from types import SimpleNamespace

import rin_launcher.config_manager as cm_module
from rin_launcher.config_manager import ConfigManager


def _fake_usage(free: int, total: int) -> SimpleNamespace:
    return SimpleNamespace(free=free, total=total, used=total - free)


def test_drive_root_uses_volume_label(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(
        cm_module, "_drive_details",
        lambda path: {"root": "E:\\", "label": "课件", "kind": "fixed",
                      "kindLabel": "本地磁盘"},
    )
    monkeypatch.setattr(
        cm_module.shutil, "disk_usage",
        lambda path: _fake_usage(40 * 1024**3, 100 * 1024**3),
    )
    manager = ConfigManager(config_dir=tmp_path)
    manager.setLauncherStoragePath("E:/")

    info = manager.getStorageInfo()
    assert info["isDrive"] is True
    assert info["label"] == "课件"      # 不是 E:\
    assert info["path"] == "E:\\"
    assert info["free"] == "40.00GB"
    assert info["percent"] == 60
    assert info["available"] is True


def test_folder_uses_folder_name(qapp, tmp_path, monkeypatch):
    folder = tmp_path / "工具"
    folder.mkdir()
    monkeypatch.setattr(cm_module, "_drive_details", lambda path: {})
    monkeypatch.setattr(
        cm_module.shutil, "disk_usage",
        lambda path: _fake_usage(5 * 1024**3, 10 * 1024**3),
    )
    manager = ConfigManager(config_dir=tmp_path / "config")
    manager.setLauncherStoragePath(str(folder))

    info = manager.getStorageInfo()
    assert info["isDrive"] is False
    assert info["label"] == "工具"
    assert info["kindLabel"] == ""


def test_missing_path_is_not_silently_replaced(qapp, tmp_path):
    manager = ConfigManager(config_dir=tmp_path / "config")
    missing = tmp_path / "no-such-folder"
    manager.setLauncherStoragePath(str(missing))

    info = manager.getStorageInfo()
    assert info["path"] == str(missing)
    assert info["label"] == "no-such-folder"
    assert info["available"] is False
    assert info["free"] == ""


def test_storage_cache_is_dropped_when_path_changes(qapp, tmp_path, monkeypatch):
    labels = {"E:\\": "课件", "D:\\": "资料"}
    monkeypatch.setattr(
        cm_module, "_drive_details",
        lambda path: {"root": str(path), "label": labels[str(path)],
                      "kind": "fixed", "kindLabel": "本地磁盘"},
    )
    monkeypatch.setattr(
        cm_module.shutil, "disk_usage",
        lambda path: _fake_usage(1 * 1024**3, 2 * 1024**3),
    )
    manager = ConfigManager(config_dir=tmp_path)
    manager.setLauncherStoragePath("E:/")
    assert manager.getStorageInfo()["label"] == "课件"

    manager.setLauncherStoragePath("D:/")
    assert manager.getStorageInfo()["label"] == "资料"
