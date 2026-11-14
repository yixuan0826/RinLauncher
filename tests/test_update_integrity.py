"""更新包完整性、安装清单与中断标记。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rin_launcher.config_manager import ConfigManager
from rin_launcher.updater import MANIFEST_NAME, UPDATE_MARKER, UpdateManager, _sha256_file


@pytest.fixture
def manager_factory(qapp, tmp_path: Path, monkeypatch):
    def build(config_dir: Path | None = None, root: Path | None = None) -> UpdateManager:
        app_root = root or tmp_path / "install"
        app_root.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(
            UpdateManager, "_app_root", staticmethod(lambda: app_root))
        config = ConfigManager(config_dir=config_dir or tmp_path / "config")
        return UpdateManager(config)

    return build


def _write_manifest(payload: Path, files: dict[str, str] | None = None) -> Path:
    entries = files or {
        path.relative_to(payload).as_posix(): _sha256_file(path)
        for path in payload.rglob("*") if path.is_file()
    }
    manifest = payload / MANIFEST_NAME
    manifest.write_text(
        json.dumps({"version": "1.2.2", "files": entries}, ensure_ascii=False),
        encoding="utf-8")
    return manifest


def test_manifest_accepts_matching_payload(tmp_path: Path):
    payload = tmp_path / "payload"
    payload.mkdir()
    (payload / "RinLauncher.exe").write_bytes(b"new-build")
    (payload / "keep.txt").write_text("ok", encoding="utf-8")
    _write_manifest(payload)

    ok, detail = UpdateManager._verify_payload(payload)
    assert ok, detail


def test_manifest_rejects_missing_and_modified(tmp_path: Path):
    payload = tmp_path / "payload"
    payload.mkdir()
    target = payload / "RinLauncher.exe"
    target.write_bytes(b"new-build")
    manifest = _write_manifest(payload)
    target.write_bytes(b"tampered")
    ok, detail = UpdateManager._verify_payload(payload)
    assert not ok
    assert "哈希" in detail

    target.unlink()
    ok, detail = UpdateManager._verify_payload(payload)
    assert not ok
    assert "缺少" in detail
    assert manifest.is_file()


def test_missing_manifest_is_allowed_with_warning(tmp_path: Path):
    payload = tmp_path / "payload"
    payload.mkdir()
    (payload / "RinLauncher.exe").write_bytes(b"old-zip")
    ok, _detail = UpdateManager._verify_payload(payload)
    assert ok


def test_interrupted_marker_exposes_repair(manager_factory, tmp_path: Path):
    config_dir = tmp_path / "config"
    updates = config_dir / "updates"
    updates.mkdir(parents=True)
    backup = tmp_path / "install" / "backup-20261114"
    backup.mkdir(parents=True)
    (backup / "RinLauncher.exe").write_bytes(b"old")
    (updates / UPDATE_MARKER).write_text(
        json.dumps({"stage": "backup", "backup": str(backup)}), encoding="utf-8")

    manager = manager_factory(config_dir, backup.parent)
    assert manager.canRepair is True
    assert manager.state == "error"
    assert "中断" in manager.message
    assert "修复安装" in manager.takeStartupNote()


def test_completed_marker_is_cleared(manager_factory, tmp_path: Path):
    config_dir = tmp_path / "config"
    updates = config_dir / "updates"
    updates.mkdir(parents=True)
    marker = updates / UPDATE_MARKER
    marker.write_text(json.dumps({"stage": "copied"}), encoding="utf-8")
    (tmp_path / "install" / "backup-1").mkdir(parents=True)

    manager = manager_factory(config_dir, tmp_path / "install")
    assert not marker.exists()
    assert "已完成" in manager.takeStartupNote()


def test_check_installation_reports_missing(manager_factory, tmp_path: Path):
    install = tmp_path / "install"
    install.mkdir()
    (install / "RinLauncher.exe").write_bytes(b"exe")
    (install / "keep.dll").write_bytes(b"dll")
    _write_manifest(install)
    manager = manager_factory(tmp_path / "config", install)
    manager.checkInstallation()
    assert "完整" in manager.installationStatus

    (install / "keep.dll").unlink()
    manager.checkInstallation()
    assert "缺少" in manager.installationStatus
