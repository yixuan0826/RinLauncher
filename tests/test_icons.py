"""图标提取：快捷方式的 IconLocation 优先于目标程序。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QImage, QPixmap

from rin_launcher import start_menu
from rin_launcher.config_manager import ConfigManager
from rin_launcher.icon_store import ICON_MIN_SIZE

ROOT = Path(__file__).resolve().parent.parent


def test_ico_icon_is_converted_to_256_png(qapp, tmp_path):
    manager = ConfigManager(config_dir=tmp_path)
    key = manager._icon_from_path(ROOT / "assets" / "icon.ico", notify=False)

    assert key.startswith("file:")
    output = Path(key.split(":", 1)[1])
    assert output.is_file()
    assert output.suffix == ".png"
    image = QImage(str(output))
    assert not image.isNull()
    assert image.width() >= 32 and image.height() >= 32


def test_shortcut_icon_location_is_tried_before_target(qapp, tmp_path, monkeypatch):
    icon = ROOT / "assets" / "icon.ico"
    link = tmp_path / "WSA.lnk"
    link.write_bytes(b"not a real shortcut")

    monkeypatch.setattr(start_menu, "shortcut_icon_path", lambda path: str(icon))
    manager = ConfigManager(config_dir=tmp_path / "config")
    seen: list[Path] = []

    def fake_icon_from_path(source: Path, notify: bool) -> str:
        seen.append(source)
        # 第一个候选故意取不到，确认下一个候选是快捷方式本身。
        return "file:second" if len(seen) == 2 else ""

    monkeypatch.setattr(manager._icons, "from_path", fake_icon_from_path)
    assert manager._extract_icon_file(str(link), notify=False) == "file:second"
    assert seen[0] == icon
    # 第二个候选是快捷方式本身，而不是它指向的目标。
    assert seen[1] == link


def test_small_shell_pixmap_is_upscaled_to_128(qapp, tmp_path):
    manager = ConfigManager(config_dir=tmp_path)
    pixmap = QPixmap(32, 32)
    pixmap.fill()
    target = tmp_path / "small.png"
    key = manager._icons._save_pixmap(pixmap, target)

    assert key.startswith("file:")
    image = QImage(str(target))
    assert image.width() >= ICON_MIN_SIZE
    assert image.height() >= ICON_MIN_SIZE


def test_thumbnail_is_at_least_128(qapp, tmp_path):
    manager = ConfigManager(config_dir=tmp_path)
    source = tmp_path / "small-source.png"
    QImage(24, 24, QImage.Format_ARGB32).save(str(source))
    target = tmp_path / "thumb.png"

    assert manager._save_thumbnail(source, target)
    image = QImage(str(target))
    assert image.width() >= 128
    assert image.height() >= 128


def test_uwp_icon_prefers_largest_variant(monkeypatch, tmp_path):
    package = tmp_path / "package"
    assets = package / "Assets"
    assets.mkdir(parents=True)
    QImage(44, 44, QImage.Format_ARGB32).save(str(assets / "Logo.scale-100.png"))
    QImage(256, 256, QImage.Format_ARGB32).save(
        str(assets / "Logo.targetsize-256.png"))
    manifest = """<?xml version="1.0" encoding="utf-8"?>
    <Package xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10">
      <Applications>
        <Application Id="App">
          <uap:VisualElements
            Square44x44Logo="Assets\\Logo.png"
            Square150x150Logo="Assets\\Logo.png" />
        </Application>
      </Applications>
    </Package>"""
    (package / "AppxManifest.xml").write_text(manifest, encoding="utf-8")

    monkeypatch.setattr(
        start_menu, "_load_package_roots",
        lambda: {"family_publisher": package})
    start_menu._uwp_icon_cache.clear()
    icon = start_menu._uwp_icon("Family_Publisher!App")

    assert icon.endswith("Logo.targetsize-256.png")
