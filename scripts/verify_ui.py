"""真机 UI 验证：在真实桌面上启动三个窗口并抓图。

测试窗口全部压到 Z 序最底（``HWND_BOTTOM`` + ``WS_EX_NOACTIVATE``），不会挡住
用户正在用的窗口；抓图走 ``QQuickWindow.grabWindow()``，窗口被别的窗口盖住也
能拿到内容。结果写到 ``build/verify-ui/``。

用法：``python scripts/verify_ui.py``
"""

from __future__ import annotations

# 先补好 sys.path 再导入项目包，和 main.py 一样整份文件豁免 E402。
# ruff: noqa: E402
import ctypes
import json
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QEventLoop, QMetaObject, QObject, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtQml import QQmlExpression
from PySide6.QtWidgets import QApplication

import RinUI  # noqa: F401
from rin_launcher import __version__
from rin_launcher.effects import apply_bottom_layer
from rin_launcher.main import Launcher, _setup_logging

OUTPUT_DIR = PROJECT_ROOT / "build" / "verify-ui"
DWMWA_WINDOW_CORNER_PREFERENCE = 33
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008
WS_EX_NOACTIVATE = 0x08000000


def wait(milliseconds: int) -> None:
    """跑事件循环等一会儿：窗口要真正渲染出第一帧才能抓图。"""
    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


def grab(window: Any, name: str, background: str = "#cdd8e4") -> str:
    """抓窗口内容，并合成到一块纯色底上（云母背景在抓图里是透明的）。"""
    image = window.grabWindow()
    if image.isNull():
        return ""
    # grabWindow 的图带着 DPR；直接 drawImage 会按逻辑尺寸缩放，抓图会糊。
    image.setDevicePixelRatio(1.0)
    canvas = QImage(image.size(), QImage.Format_ARGB32)
    canvas.fill(QColor(background))
    painter = QPainter(canvas)
    painter.drawImage(0, 0, image)
    painter.end()
    path = OUTPUT_DIR / f"{name}.png"
    canvas.save(str(path))
    return str(path)


def actual_theme(window: Any) -> str:
    """从窗口引擎里读实际主题；抓图底色要跟着主题走，否则白字会糊在白底上。"""
    expression = QQmlExpression(
        window.engine.rootContext(), window.root_window, "ThemeManager.get_theme()")
    value = expression.evaluate()
    return str(value[0]) if isinstance(value, tuple) else str(value)


def window_info(window: Any) -> dict[str, Any]:
    """窗口样式与 Win11 圆角偏好。"""
    hwnd = int(window.winId())
    user32 = ctypes.windll.user32
    ex_style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    corner = ctypes.c_int(-1)
    try:
        ctypes.windll.dwmapi.DwmGetWindowAttribute(
            hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(corner), ctypes.sizeof(corner))
    except Exception:
        pass
    return {
        "hwnd": hwnd,
        "rect": [rect.left, rect.top, rect.right, rect.bottom],
        "noactivate": bool(ex_style & WS_EX_NOACTIVATE),
        "toolwindow": bool(ex_style & WS_EX_TOOLWINDOW),
        "topmost": bool(ex_style & WS_EX_TOPMOST),
        "corner_preference": corner.value,
    }


def pin_to_bottom(window: Any) -> None:
    """真机测试专用：窗口不抢焦点、不盖住用户窗口。"""
    window.setFlags(window.flags() | Qt.WindowStaysOnBottomHint
                    | Qt.WindowDoesNotAcceptFocus)
    window.show()
    apply_bottom_layer(window)


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    launcher = Launcher(app)
    _setup_logging(launcher.config_manager)
    report: dict[str, Any] = {"version": __version__, "screenshots": {}}

    # ── 小窗 ──
    if not launcher.create_compact_window():
        report["error"] = "compact window failed"
        (OUTPUT_DIR / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return 1
    launcher.show_compact()
    wait(900)
    compact = launcher.compact.root_window
    backdrop = "#1f1f1f" if actual_theme(launcher.compact) == "Dark" else "#f3f3f3"
    report["theme"] = actual_theme(launcher.compact)
    report["compact"] = window_info(compact)
    report["screenshots"]["compact"] = grab(compact, "compact", backdrop)

    storage = launcher.config_manager.getStorageInfo()
    report["storage"] = {
        "label": storage.get("label"),
        "path": storage.get("path"),
        "isDrive": storage.get("isDrive"),
        "available": storage.get("available"),
    }

    slots = launcher.config_manager.getLauncherSlots()
    report["slots"] = {
        "panel": len([slot for slot in slots if slot.get("row") == 0]),
        "storage": len([slot for slot in slots if slot.get("row") == 1]),
    }

    # ── 磁贴三档：切换档位后看面板算出来的每行格数与行数 ──
    panel = compact.findChild(QObject, "panel")
    if panel is not None:
        tiles: dict[str, Any] = {}
        for mode in ("small", "medium", "large"):
            compact.setProperty("tileSizeMode", mode)
            wait(120)
            tiles[mode] = {
                "perLine": panel.property("perLine"),
                "rows": panel.property("rows"),
                "tile": round(float(panel.property("tileSize") or 0), 1),
            }
        compact.setProperty("tileSizeMode", "medium")
        wait(120)
        report["tiles"] = tiles

    # ── 开始菜单数据 + UWP 图标入库 ──
    apps = launcher.config_manager.listStartMenuApps()
    kinds: dict[str, int] = {}
    for item in apps:
        kinds[item["kind"]] = kinds.get(item["kind"], 0) + 1
    uwp = [item for item in apps if item["kind"] == "uwp"]
    report["start_menu"] = {
        "total": len(apps),
        "kinds": kinds,
        "uwp_with_icon": sum(1 for item in uwp if item.get("icon")),
        "uwp_total": len(uwp),
    }
    if uwp and uwp[0].get("icon"):
        source = Path(str(uwp[0]["icon"])[len("file:"):])
        key = launcher.config_manager._icon_from_path(source, notify=False)
        report["uwp_icon_import"] = {
            "app": uwp[0]["name"],
            "key": key,
            "exists": bool(key) and Path(key[len("file:"):]).is_file(),
        }
        if key:
            Path(key[len("file:"):]).unlink(missing_ok=True)

    # ── 编辑窗口 + 开始菜单选择器 ──
    if launcher.ensure_editor_window():
        editor = launcher.editor
        pin_to_bottom(editor.root_window)
        wait(700)
        report["editor"] = window_info(editor.root_window)
        report["screenshots"]["editor"] = grab(editor.root_window, "editor", backdrop)

        dialog = editor.root_window.findChild(QObject, "startMenuDialog")
        report["start_menu_dialog_found"] = dialog is not None
        if dialog is not None:
            QMetaObject.invokeMethod(dialog, "open")
            wait(800)
            visible = dialog.property("apps") or []
            report["start_menu_dialog"] = {
                "visible": bool(dialog.property("visible")),
                "apps": len(visible),
            }
            report["screenshots"]["start_menu_dialog"] = grab(
                editor.root_window, "start-menu-dialog", backdrop)
            QMetaObject.invokeMethod(dialog, "reject")
            wait(150)

        # ── 拼音搜索：输入首字母看结果条数 ──
        search_field = editor.root_window.findChild(QObject, "slotSearchField")
        page = editor.root_window.findChild(QObject, "launcherSettingsPage")
        report["search_field_found"] = search_field is not None
        if search_field is not None and page is not None:
            # pz = 「配置」；首字母能命中「配置目录」「重载配置」之类的槽位。
            search_field.setProperty("text", "pz")
            wait(250)
            report["search"] = {
                "query": "pz",
                "hits": len(page.property("searchResults") or []),
            }
            search_field.setProperty("text", "")
            wait(150)
        editor.root_window.hide()
    else:
        report["editor_error"] = True

    # ── 设置窗口 ──
    if launcher.ensure_settings_window():
        settings = launcher.settings
        pin_to_bottom(settings.root_window)
        wait(800)
        report["settings"] = window_info(settings.root_window)
        report["screenshots"]["settings"] = grab(
            settings.root_window, "settings", backdrop)

        page = settings.root_window.findChild(QObject, "settingsPage")
        report["notifications"] = launcher.config_manager.getNotificationSettings()[
            "categories"]
        if page is not None:
            for index, name in ((2, "settings-notification"), (5, "settings-storage"),
                                (6, "settings-about")):
                page.setProperty("currentIndex", index)
                wait(400)
                report["screenshots"][name] = grab(
                    settings.root_window, name, backdrop)
            page.setProperty("currentIndex", 0)
        settings.root_window.hide()
    else:
        report["settings_error"] = True

    # ── 恢复模式窗口 ──
    if launcher.create_recovery_window():
        recovery = launcher.recovery
        pin_to_bottom(recovery.root_window)
        wait(700)
        report["recovery"] = {
            "window": window_info(recovery.root_window),
            "info": launcher.config_manager.getRecoveryInfo(),
        }
        report["screenshots"]["recovery"] = grab(
            recovery.root_window, "recovery", backdrop)
        recovery.root_window.hide()
    else:
        report["recovery_error"] = True

    # ── 动作执行（不弹窗的安全命令） ──
    report["action_exec"] = launcher.config_manager.action_executor.execute({
        "type": "file",
        "target": "cmd.exe",
        "arguments": "/c exit 0",
        "working_dir": "",
        "run_as": "user",
    })

    (OUTPUT_DIR / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))

    launcher.quit()
    wait(250)
    sys.stdout.flush()
    # RinUI 的浅色/深色监听线程在解释器退出时偶尔来不及收尾，直接结束进程
    # 避免 “QThread: Destroyed while thread is still running” 把退出码带成 1。
    import os

    os._exit(0)


if __name__ == "__main__":
    sys.exit(main())
