"""开始菜单缩略图：缓存回填与「来源 → 目标」的抽取兜底。"""

from __future__ import annotations

import shutil
from pathlib import Path

from rin_launcher.config_manager import ConfigManager

ROOT = Path(__file__).resolve().parent.parent


def test_attach_cached_thumbs_reuses_existing_file(qapp, tmp_path):
    manager = ConfigManager(config_dir=tmp_path)
    app = {"source": "shell:AppsFolder", "target": "AUMID!App", "icon": ""}
    cached = manager._thumb_path(app)
    assert cached is not None
    cached.write_bytes(b"png")

    manager._attach_cached_thumbs([app])

    assert app["thumb"] == f"file:{cached}"
    assert manager._needs_thumb(app) is False


def test_make_thumb_falls_back_to_target(qapp, tmp_path, monkeypatch):
    manager = ConfigManager(config_dir=tmp_path)
    picture = tmp_path / "target.png"
    shutil.copy2(ROOT / "assets" / "icon.png", picture)
    calls: list[str] = []

    def fake_extract(path: str, notify: bool = True) -> str:
        calls.append(path)
        return f"file:{picture}"

    monkeypatch.setattr(manager._icons, "extract", fake_extract)
    # UWP 的 source 是 shell:AppsFolder，不是真实文件；只能靠 target 再试一次。
    app = {"source": "shell:AppsFolder", "target": "notepad.exe", "icon": ""}

    thumb = manager._make_thumb(app, manager.thumbnail_dir / "wsl.png")

    assert thumb.startswith("file:")
    assert (manager.thumbnail_dir / "wsl.png").is_file()
    assert calls and calls[0].lower().endswith("notepad.exe")
