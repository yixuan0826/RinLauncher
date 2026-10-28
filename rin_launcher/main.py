"""Rin Launcher entry point.

Run with ``python -m rin_launcher.main`` (or ``python rin_launcher/main.py``).
"""

# 这个文件刻意「先做运行期准备（sys.path、流兜底）再导入」，整份文件豁免 E402。
# ruff: noqa: E402

from __future__ import annotations

import logging
import sys
from pathlib import Path

PROJECT_ROOT = (
    # 打包后资源都解压在 _MEIPASS（onefile）或 exe 同级（onedir）下，不能再依赖
    # __file__ 的层级 —— 冻结环境里入口脚本的 __file__ 布局和源码树不一样。
    Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent.parent
)
COMPACT_ENTRY = PROJECT_ROOT / "qml" / "CompactWindow.qml"
EDITOR_ENTRY = PROJECT_ROOT / "qml" / "LauncherEditorWindow.qml"
SETTINGS_ENTRY = PROJECT_ROOT / "qml" / "SettingsWindow.qml"
RECOVERY_ENTRY = PROJECT_ROOT / "qml" / "RecoveryWindow.qml"
ICON_FILE = PROJECT_ROOT / "assets" / "icon.ico"

# RinUI 启动时会 print 一个带 emoji 的横幅。老终端（cmd.exe 的 GBK 代码页）编码
# 装不下那个字符时 print 会抛 UnicodeEncodeError，把整个程序带走 —— 这里给两个
# 流加一层兜底：编不出来的字符用占位符代替，中文输出不受影响。
for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(errors="replace")
        except Exception:  # 流不支持重配置（被其它程序包了一层）时忽略
            pass

# RinUI is vendored in-tree (MIT), so the package root just has to be importable.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

# RinUI 导入期就要把 HiDPI 配好，必须早于任何 QApplication 的创建。
import RinUI  # noqa: F401
from rin_launcher import __version__, effects, logging_setup
from rin_launcher.action_executor import ActionExecutor
from rin_launcher.config_manager import ConfigManager
from rin_launcher.hotkey import GlobalHotkey
from rin_launcher.key_recorder import KeyRecorder
from rin_launcher.single_instance import (
    SingleInstanceServer,
    acquire_single_instance,
    notify_running_instance,
)
from rin_launcher.system_controls import SystemControls
from rin_launcher.tray import TrayIcon
from rin_launcher.updater import UpdateManager
from RinUI import RinUIWindow
from RinUI.core import BackdropEffect, is_windows
from RinUI.core.config import is_win11

logger = logging.getLogger(__name__)

# 三个窗口统一用云母；Win10 或调用失败时由 apply_backdrop 回退到不透明。
BACKDROP_EFFECT = BackdropEffect.Mica


def _setup_logging(config_manager: ConfigManager) -> None:
    level_name = str(config_manager.config["settings"].get("logLevel", "INFO")).upper()
    # 诊断模式：临时把级别拉到 DEBUG，控制台输出也跟着打开。
    if "--diagnostic" in sys.argv[1:]:
        level_name = "DEBUG"
    log_file = logging_setup.setup(
        config_manager.config_dir, level_name, console=sys.stdout is not None)
    logger.info("Log file: %s", log_file)


class Launcher:
    """Owns the windows plus the OS-level pieces (tray, hotkey, window flags)."""

    def __init__(self, app: QApplication):
        self.app = app
        self.config_manager = ConfigManager()
        self.config_manager.action_executor = ActionExecutor(self.config_manager)

        # 三个 QML 根：桌面小窗、启动台编辑窗口、设置窗口。后两个按需创建。
        self.compact: RinUIWindow | None = None
        self.editor: RinUIWindow | None = None
        self.settings: RinUIWindow | None = None
        self.recovery: RinUIWindow | None = None
        self.tray = TrayIcon(ICON_FILE)
        self.hotkey = GlobalHotkey()
        # 系统控制（音量 / Wi-Fi / 移动热点），小窗底部那排卡片用。
        self.system_controls = SystemControls()
        # GitHub Releases 更新检查 / 下载 / 安装。
        self.update_manager = UpdateManager(self.config_manager)
        # 按键序列编辑器用：全局录制键盘输入（QML 侧名字是 KeyRecorder）。
        self.key_recorder = KeyRecorder()
        # 单实例消息服务端（见 start_single_instance_server）。
        self._single_server: SingleInstanceServer | None = None
        self._tray_wired = False
        # 安全模式：不装全局热键钩子、不跑系统状态轮询与配置监听。
        self.launch_mode = self.config_manager.getLaunchMode()

        self._wire_config()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------
    def _wire_config(self) -> None:
        """Re-apply the OS-level settings whenever they change in the UI."""
        settings = self.config_manager.config["settings"]
        self.config_manager.hotkeyChanged.connect(self.apply_hotkey)
        self.config_manager.trayEnabledChanged.connect(self.apply_tray)
        # QML 里的页面够不到窗口对象，页面级请求统一从后端转上来。
        self.config_manager.pageRequested.connect(self.show_page)
        # 托盘气泡是「通知」的一个渠道，由 ConfigManager 按类别分发；
        # 直接把 showToast 转发给托盘会让每条提示都多出一份气泡。
        self.config_manager.attachTraySink(
            lambda message, _severity: self.tray.show_message("Rin Launcher", message))
        # 系统控制与更新器的提示走各自的通知类别。
        self.system_controls.notify.connect(
            lambda message, severity: self.config_manager.notifyEvent(
                "system", message, severity))
        self.update_manager.notify.connect(
            lambda message, severity: self.config_manager.notifyEvent(
                "update", message, severity))

        # 热键与托盘放到小窗首帧之后：pynput 的全局键盘钩子和 QSystemTrayIcon
        # 都要跟系统打交道，没必要挡在「小窗可见」这条关键路径上。
        if self.safe_mode:
            logger.warning("安全模式：跳过热键注册与系统状态轮询")
        else:
            QTimer.singleShot(120, lambda: self.apply_hotkey(
                str(settings.get("globalHotkey", ""))))
        QTimer.singleShot(120, lambda: self.apply_tray(
            bool(settings.get("showTray", True))))

    @property
    def safe_mode(self) -> bool:
        return self.launch_mode == "safe"

    @property
    def diagnostic_mode(self) -> bool:
        return self.launch_mode == "diagnostic"

    def _wire_tray(self) -> None:
        # 托盘可以在设置里反复开关，重复连接会让一次点击触发多次。
        if self._tray_wired:
            return
        self._tray_wired = True
        self.tray.toggleLauncherRequested.connect(self.toggle_compact)
        self.tray.showLauncherRequested.connect(self.show_compact)
        self.tray.hideLauncherRequested.connect(self.hide_compact)
        self.tray.openPageRequested.connect(self.handle_tray_page)
        self.tray.openConfigFolderRequested.connect(self.config_manager.openConfigFolder)
        self.tray.reloadConfigRequested.connect(self.config_manager.reloadConfig)
        self.tray.quitRequested.connect(self.quit)

    # ------------------------------------------------------------------
    # Window creation
    # ------------------------------------------------------------------
    def _create_window(self, entry: Path) -> RinUIWindow | None:
        """创建一个独立 QML 引擎的窗口，并注入所有后端对象。"""
        if not entry.is_file():
            logger.error("QML entry point is missing: %s", entry)
            return None

        window = RinUIWindow(shared_engine=False)
        context = window.engine.rootContext()
        context.setContextProperty("ConfigManager", self.config_manager)
        context.setContextProperty("KeyRecorder", self.key_recorder)
        context.setContextProperty("SystemControls", self.system_controls)
        context.setContextProperty("UpdateManager", self.update_manager)
        window.load(entry)

        if window.root_window is None:
            logger.error("Failed to load %s", entry)
            return None
        if ICON_FILE.is_file():
            window.setIcon(ICON_FILE)
        return window

    def create_compact_window(self) -> bool:
        window = self._create_window(COMPACT_ENTRY)
        if window is None:
            return False

        self.compact = window
        root = window.root_window
        # 小窗是独立的 QML 根，跨窗口的请求统一走信号回到这里。
        root.openMainRequested.connect(self.show_page)
        root.hideRequested.connect(self.hide_compact)
        root.quitRequested.connect(self.quit)

        # 小窗不是 RinUI 的 FluentWindow，需要手动把 hwnd 注册给 ThemeManager，
        # 之后才能用和完整窗口同一套云母 / 增强云母。
        window.theme_manager.set_window(root)

        # 桌面挂件：沉底、不抢焦点，窗口本体按 Win11 的 8px 圆角裁切。
        effects.apply_no_focus_tool_window(root)
        effects.apply_bottom_layer(root)
        effects.apply_win11_round_corners(root)
        self.apply_backdrop(window)
        return True

    def create_editor_window(self) -> bool:
        window = self._create_window(EDITOR_ENTRY)
        if window is None:
            return False
        self.editor = window
        window.root_window.closeRequested.connect(
            lambda: self._close_window(window))
        self.apply_backdrop(window)
        return True

    def create_settings_window(self) -> bool:
        window = self._create_window(SETTINGS_ENTRY)
        if window is None:
            return False
        self.settings = window
        window.root_window.closeRequested.connect(
            lambda: self._close_window(window))
        self.apply_backdrop(window)
        return True

    def ensure_editor_window(self) -> bool:
        if self.editor is not None:
            return True
        if not self.create_editor_window():
            self.tray.show_message("Rin Launcher", "启动台编辑窗口加载失败，可以看看日志")
            return False
        return True

    def ensure_settings_window(self) -> bool:
        if self.settings is not None:
            return True
        if not self.create_settings_window():
            self.tray.show_message("Rin Launcher", "设置窗口加载失败，可以看看日志")
            return False
        return True

    def create_recovery_window(self) -> bool:
        window = self._create_window(RECOVERY_ENTRY)
        if window is None:
            return False
        self.recovery = window
        if window.root_window is not None:
            window.root_window.closeRequested.connect(
                lambda: self._close_window(window))
        self.apply_backdrop(window)
        return True

    def ensure_recovery_window(self) -> bool:
        if self.recovery is not None:
            return True
        if not self.create_recovery_window():
            self.tray.show_message("Rin Launcher", "恢复模式窗口加载失败，可以看看日志")
            return False
        return True

    def show_recovery(self) -> None:
        if not self.ensure_recovery_window():
            return
        root = self.recovery.root_window
        if root is None:
            return
        root.show()
        root.raise_()
        root.requestActivate()

    def start_single_instance_server(self) -> None:
        """守着单实例的本地套接字：第二个进程请求「亮出小窗」时照办。"""
        self._single_server = SingleInstanceServer(self.app)
        self._single_server.showRequested.connect(self.show_compact)

    # ------------------------------------------------------------------
    # OS integration
    # ------------------------------------------------------------------
    def apply_hotkey(self, sequence: str) -> None:
        if not self.hotkey.register(sequence):
            logger.info("No global hotkey registered (configured value: %r)", sequence)

    def apply_backdrop(self, target: RinUIWindow | None = None) -> None:
        """给窗口上云母背景（默认三个窗口全部）。

        新建窗口时只给它自己上材质；对已有窗口重复调用只是白跑一次
        DwmSetWindowAttribute，代价很低。Win10 没有云母，直接退回不透明，
        而不是把文字铺在桌面上。
        """
        if not is_windows():
            return
        effect = BACKDROP_EFFECT if is_win11() else BackdropEffect.None_
        targets = (target,) if target is not None else (
            self.compact, self.editor, self.settings, self.recovery)
        for window in targets:
            if window is None or window.root_window is None:
                continue
            try:
                status = window.theme_manager.apply_backdrop_effect(effect.value)
                if window is self.compact:
                    window.root_window.setProperty(
                        "backdropActive",
                        status == 0 and effect != BackdropEffect.None_)
            except Exception:
                logger.exception("Failed to apply backdrop effect")

    def apply_tray(self, enabled: bool) -> None:
        if enabled:
            if self.tray.start():
                self._wire_tray()
        else:
            self.tray.stop()

    # ------------------------------------------------------------------
    # Window operations (also invoked from the tray)
    # ------------------------------------------------------------------
    @staticmethod
    def _visible(window: RinUIWindow | None) -> bool:
        return (
            window is not None
            and window.root_window is not None
            and window.root_window.isVisible()
        )

    def show_compact(self) -> None:
        if self.compact is None or self.compact.root_window is None:
            return
        root = self.compact.root_window
        root.show()
        # 小窗可见时才需要系统状态轮询；隐藏期间不碰 WinRT。
        if not self.safe_mode:
            self.system_controls.setActive(True)
        # 小窗带 WindowDoesNotAcceptFocus，requestActivate() 是无效调用（Qt 会打一条
        # 警告）。置底窗口不能 raise_()（那会把它翻到别的窗口上面），显示完再向
        # 系统兜一次底，防止刚显示时被抬到前台。
        effects.apply_bottom_layer(root)

    def hide_compact(self) -> None:
        if self.compact is not None and self.compact.root_window is not None:
            self.compact.root_window.hide()
            self.system_controls.setActive(False)

    def toggle_compact(self) -> None:
        if self._visible(self.compact):
            self.hide_compact()
        else:
            self.show_compact()

    def show_editor(self) -> None:
        if not self.ensure_editor_window():
            return
        root = self.editor.root_window
        if root is None:
            return
        root.show()
        root.raise_()
        root.requestActivate()

    def show_settings(self, section: str = "") -> None:
        if not self.ensure_settings_window():
            return
        root = self.settings.root_window
        if root is None:
            return
        root.show()
        root.raise_()
        root.requestActivate()
        if section:
            # 新窗口的 QML 连接可能还没建好，稍等一拍再滚到目标分组。
            QTimer.singleShot(
                180, lambda: self.config_manager.requestSettingsSection(section))

    def show_page(self, page: str) -> None:
        """兼容旧路由：launcher 开编辑窗口，about 进设置分类，其余都进设置窗口。"""
        if page == "launcher":
            self.show_editor()
        elif page == "compact":
            self.show_compact()
        elif page == "recovery":
            self.show_recovery()
        elif page == "about":
            self.show_settings("about")
        else:
            self.show_settings()

    def handle_tray_page(self, page: str) -> None:
        """托盘菜单：启动台设置 → 编辑窗口，设置 / 关于 → 设置窗口。"""
        self.show_page(page)

    def _close_window(self, window: RinUIWindow) -> None:
        """编辑 / 设置窗口的关闭按钮只收起自己 —— 小窗还在，程序不退出。"""
        if window.root_window is not None:
            window.root_window.hide()
        if (not self.tray.started and not self._visible(self.compact)
                and not self._visible(self.editor) and not self._visible(self.settings)
                and not self._visible(self.recovery)):
            self.quit()

    def _auto_check_updates(self) -> None:
        if self.config_manager.config["settings"].get("autoCheckUpdates", True):
            self.update_manager.checkSilently()

    def log_startup_notes(self) -> None:
        """把上次更新的结论写进日志（日志初始化在这之后，所以单独调）。"""
        note = self.update_manager.takeStartupNote()
        if not note:
            return
        if "失败" in note:
            logger.warning("%s", note)
        else:
            logger.info("%s", note)

    def quit(self) -> None:
        self.hotkey.unregister()
        self.tray.stop()
        self.system_controls.stop()
        self.update_manager.stop()
        self.config_manager.stopWatching()
        self.app.quit()

    def run(self) -> int:
        # 安全模式 / 诊断模式直接开恢复窗口，让小窗先靠边站。
        if self.launch_mode in ("safe", "diagnostic"):
            self.show_recovery()
        elif not self.config_manager.config["settings"].get("startMinimized", False):
            self.show_compact()
        # 这些都不是「小窗可见」的必要条件，推迟到首帧之后：
        #   * watchdog 的导入与文件监听（几十毫秒）；
        #   * schtasks 子进程查任务计划状态；
        #   * 静默更新检查（本来就在 5 秒后）。
        if not self.safe_mode:
            QTimer.singleShot(1200, self.config_manager.startWatching)
            QTimer.singleShot(4000, self.config_manager._start_startup_prefetch)
            QTimer.singleShot(5000, self._auto_check_updates)

        try:
            return self.app.exec()
        finally:
            self.quit()


def main() -> int:
    # 隐藏的辅助入口：三态启动方式里的任务计划重活在提权进程里干完就退，
    # 完全不进 Qt、不抢单实例锁（见 rin_launcher/autostart.py）。
    for arg in sys.argv[1:]:
        if arg.startswith("--set-startup-mode="):
            from rin_launcher.autostart import apply_startup_mode

            mode = arg.split("=", 1)[1].strip()
            return 0 if apply_startup_mode(mode) else 1

    app = QApplication(sys.argv)
    app.setApplicationName("Rin Launcher")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("RinLauncher")
    app.setQuitOnLastWindowClosed(False)  # the tray keeps the app alive

    # 单实例：已经有实例在跑就把「亮出小窗」交给它，本进程直接退出。
    # 安全 / 诊断模式是救命通道，不抢锁也不被旧实例拦截。
    recovery_mode = any(arg in ("--safe-mode", "--diagnostic") for arg in sys.argv[1:])
    if not recovery_mode:
        guard = acquire_single_instance()
        if guard is None:
            notify_running_instance()
            return 0

    launcher = Launcher(app)
    _setup_logging(launcher.config_manager)
    launcher.log_startup_notes()

    # 小窗总是先建好（恢复模式下只建不显示）：恢复窗口的「继续使用」要直接
    # 把小窗亮出来，不能到了那儿才发现它根本没建。
    if not launcher.create_compact_window():
        return 1
    if not recovery_mode:
        launcher.start_single_instance_server()
        launcher.hotkey.activated.connect(launcher.toggle_compact)
    return launcher.run()


if __name__ == "__main__":
    sys.exit(main())
