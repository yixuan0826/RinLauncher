"""冷启动分段计时（无头模式）。

用法::

    python scripts/bench_startup.py

不修改任何配置；窗口用 offscreen 平台渲染，只测「从进程开始到小窗可见」
这条主路径。数字只适合在同一台机器上做前后对比。
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

START = time.perf_counter()
MARKS: list[tuple[str, float]] = []


def mark(name: str) -> None:
    MARKS.append((name, (time.perf_counter() - START) * 1000))


mark("process-imports")

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import RinUI  # noqa: E402,F401

mark("pyside-rinui-import")

from rin_launcher.main import Launcher  # noqa: E402

mark("app-imports")

app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)
mark("qapplication")

launcher = Launcher(app)
mark("launcher-services")

if not launcher.create_compact_window():
    print("compact window failed", file=sys.stderr)
    raise SystemExit(1)
mark("compact-window-loaded")

launcher.show_compact()
app.processEvents()
mark("compact-window-visible")


def finish() -> None:
    launcher.quit()
    previous = 0.0
    for name, value in MARKS:
        print(f"{name:24s} {value:8.1f} ms  (+{value - previous:7.1f})")
        previous = value
    print(f"{'total':24s} {MARKS[-1][1]:8.1f} ms")


QTimer.singleShot(600, finish)
app.exec()
