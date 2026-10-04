"""pytest 公共装置：仓库根进 sys.path，起一个 QApplication。

ConfigManager 里会用到 QFileIconProvider —— 没有 QApplication 时它在原生层
直接崩（Python 捕不住），所以所有配置相关测试都挂这个 qapp。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 测试不去碰真实桌面：无头平台照样能建 QApplication / QFileIconProvider。
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
