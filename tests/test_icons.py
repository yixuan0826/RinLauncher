"""图标提取：快捷方式的 IconLocation 优先于目标程序。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QImage

from rin_launcher import start_menu
from rin_launcher.config_manager import ConfigManager

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

    monkeypatch.setattr(manager, "_icon_from_path", fake_icon_from_path)
    assert manager._extract_icon_file(str(link), notify=False) == "file:second"
    assert seen[0] == icon
    # 第二个候选是快捷方式本身，而不是它指向的目标。
    assert seen[1] == link
