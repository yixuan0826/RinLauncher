"""System tray icon.

Qt has no QML tray element, so the tray lives in Python: a ``QSystemTrayIcon``
with a ``QMenu``.  Menu actions are re-emitted as Qt signals that the QML layer
listens to, and ``activated`` is forwarded so a left double click can toggle the
launcher window.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

logger = logging.getLogger(__name__)


class TrayIcon(QObject):
    """Wraps QSystemTrayIcon and exposes its menu as signals."""

    showLauncherRequested = Signal()
    hideLauncherRequested = Signal()
    toggleLauncherRequested = Signal()
    openPageRequested = Signal(str)
    openConfigFolderRequested = Signal()
    reloadConfigRequested = Signal()
    quitRequested = Signal()

    def __init__(self, icon_path: Path, parent: QObject | None = None):
        super().__init__(parent)
        self._icon_path = Path(icon_path)
        self._tray: QSystemTrayIcon | None = None

    @property
    def available(self) -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable()

    @property
    def started(self) -> bool:
        """True while the icon is on screen (used to decide hide-vs-quit)."""
        return self._tray is not None

    def start(self, title: str = "Rin Launcher") -> bool:
        """Create and show the tray icon. Returns False when unsupported."""
        if self._tray is not None:
            return True
        if not self.available:
            logger.warning("No system tray on this platform, skipping the tray icon")
            return False

        icon = QIcon(str(self._icon_path)) if self._icon_path.is_file() else QIcon()

        self._tray = QSystemTrayIcon(icon, self)
        self._tray.setToolTip(title)
        self._tray.setContextMenu(self._build_menu(title))
        self._tray.activated.connect(self._on_activated)
        self._tray.show()
        logger.info("Tray icon ready")
        return True

    def stop(self) -> None:
        if self._tray is not None:
            self._tray.hide()
            self._tray.setContextMenu(None)
            self._tray = None

    def show_message(self, title: str, text: str) -> None:
        if self._tray is not None:
            self._tray.showMessage(title, text, QSystemTrayIcon.Information, 3000)

    def _build_menu(self, title: str) -> QMenu:
        menu = QMenu()

        show = QAction(f"显示 {title}", menu)
        show.triggered.connect(self.showLauncherRequested.emit)
        menu.addAction(show)

        hide = QAction("隐藏", menu)
        hide.triggered.connect(self.hideLauncherRequested.emit)
        menu.addAction(hide)

        menu.addSeparator()

        launcher = QAction("启动台编辑", menu)
        launcher.triggered.connect(lambda: self.openPageRequested.emit("launcher"))
        menu.addAction(launcher)

        settings = QAction("设置", menu)
        settings.triggered.connect(lambda: self.openPageRequested.emit("settings"))
        menu.addAction(settings)

        about = QAction("关于", menu)
        about.triggered.connect(lambda: self.openPageRequested.emit("about"))
        menu.addAction(about)

        menu.addSeparator()

        open_folder = QAction("打开配置目录", menu)
        open_folder.triggered.connect(self.openConfigFolderRequested.emit)
        menu.addAction(open_folder)

        reload_config = QAction("重新加载配置", menu)
        reload_config.triggered.connect(self.reloadConfigRequested.emit)
        menu.addAction(reload_config)

        menu.addSeparator()

        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(self.quitRequested.emit)
        menu.addAction(quit_action)

        return menu

    def _on_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.toggleLauncherRequested.emit()
