"""三种窗口形态、OOBE 与个性化设置的真机验收。

配置目录切到 build/verify-modes/data，不碰用户的真实设置。
"""

# 先补 sys.path 再导入项目包，导入顺序由这里显式豁免。
# ruff: noqa: E402, I001

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QEventLoop, QObject, QTimer
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

import RinUI  # noqa: F401
import rin_launcher.config_manager as cm_module
from rin_launcher.main import Launcher, _setup_logging

OUTPUT = PROJECT_ROOT / "build" / "verify-modes"
DATA = OUTPUT / "data"


def wait(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def grab(window: Any, name: str, background: str = "#cdd8e4") -> str:
    image = window.grabWindow()
    if image.isNull():
        return ""
    image.setDevicePixelRatio(1.0)
    canvas = QImage(image.size(), QImage.Format_ARGB32)
    canvas.fill(QColor(background))
    painter = QPainter(canvas)
    painter.drawImage(0, 0, image)
    painter.end()
    path = OUTPUT / f"{name}.png"
    canvas.save(str(path))
    return str(path)


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(DATA, ignore_errors=True)
    DATA.mkdir(parents=True, exist_ok=True)
    cm_module.resolve_config_dir = lambda: DATA

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    launcher = Launcher(app)
    _setup_logging(launcher.config_manager)
    cm = launcher.config_manager
    cm.updateSettings({
        "compactMode": "normal", "windowCorner": "bottom-right",
        "windowOffsetX": 0, "windowOffsetY": 0,
        "compactTransparency": 82, "miniTransparency": 30,
        "shortcutArrowGlobal": False,
        "startMinimized": False,
    })
    # 迷你模式只取前三个固定应用；没有槽位就看不出单行布局。
    for name, target in (("记事本", "notepad.exe"),
                         ("资源管理器", "explorer.exe"),
                         ("计算器", "calc.exe")):
        cm.addLauncherSlot(0, {
            "kind": "action", "label": name,
            "action": {"type": "file", "target": target},
        })
    if not launcher.create_compact_window():
        return 1
    launcher.show_compact()
    wait(900)
    compact = launcher.compact.root_window
    report: dict[str, Any] = {"screenshots": {}, "modes": {}}
    report["screenshots"]["normal"] = grab(compact, "normal")

    cm.updateSettings({"compactMode": "mini"})
    wait(700)
    launcher.show_compact()
    wait(500)
    report["modes"]["mini"] = {
        "width": compact.width(), "height": compact.height(),
        "mode": compact.property("windowMode"),
    }
    report["screenshots"]["mini"] = grab(compact, "mini")

    cm.updateSettings({"compactMode": "normal"})
    wait(500)

    # OOBE
    if launcher.show_oobe():
        wait(800)
        report["screenshots"]["oobe"] = grab(launcher.oobe.root_window, "oobe")
        launcher.oobe.root_window.hide()

    # 个性化页
    if launcher.ensure_settings_window():
        launcher.settings.root_window.show()
        wait(900)
        page = launcher.settings.root_window.findChild(QObject, "settingsPage")
        if page is not None:
            page.setProperty("currentIndex", 1)
            wait(600)
            report["screenshots"]["personalization"] = grab(
                launcher.settings.root_window, "personalization")
        launcher.settings.root_window.hide()

    (OUTPUT / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    launcher.quit()
    wait(300)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
