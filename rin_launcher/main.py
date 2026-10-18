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
QML_ENTRY = PROJECT_ROOT / "qml" / "LauncherWindow.qml"
COMPACT_ENTRY = PROJECT_ROOT / "qml" / "CompactWindow.qml"
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

from PySide6.QtWidgets import QApplication

# RinUI 导入期就要把 HiDPI 配好，必须早于任何 QApplication 的创建。
import RinUI  # noqa: F401
from rin_launcher import __version__, effects
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
from RinUI import RinUIWindow
from RinUI.core import BackdropEffect, is_windows

logger = logging.getLogger(__name__)

# 完整窗口的材质。小窗走亚克力（见 effects.py），不在这里选。
MATERIALS: dict[str, BackdropEffect] = {
    "tabbed": BackdropEffect.Tabbed,   # 增强云母
    "mica": BackdropEffect.Mica,       # 云母
    "none": BackdropEffect.None_,
}
DEFAULT_MATERIAL = "tabbed"



def _setup_logging(config_manager: ConfigManager) -> None:
    level_name = str(config_manager.config["settings"].get("logLevel", "INFO")).upper()
    handlers: list[logging.Handler] = [
        logging.FileHandler(config_manager.config_dir / "launcher.log", encoding="utf-8"),
    ]
    # 打包成无控制台的窗口程序后 stdout 是 None，加 StreamHandler 只会刷一堆
    # "no attribute 'write'"。
    if sys.stdout is not None:
        handlers.append(logging.StreamHandler(sys.stdout))

    logging.basicConfig(
        level=getattr(logging, level_name, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )


class Launcher:
    """Owns the windows plus the OS-level pieces (tray, hotkey, window flags)."""

    def __init__(self, app: QApplication):
        self.app = app
        self.config_manager = ConfigManager()
        self.config_manager.action_executor = ActionExecutor(self.config_manager)

        # 两个 QML 根：常驻桌面右下角的小窗（启动台本体）和完整窗口（启动台设置 / 设置 / 关于）。
        self.window: RinUIWindow | None = None
        self.compact: RinUIWindow | None = None
        self.tray = TrayIcon(ICON_FILE)
        self.hotkey = GlobalHotkey()
        # 系统控制（音量 / Wi-Fi / 移动热点），小窗底部那排卡片用。
        self.system_controls = SystemControls()
        # 按键序列编辑器用：全局录制键盘输入（QML 侧名字是 KeyRecorder）。
        self.key_recorder = KeyRecorder()
        # 单实例消息服务端（见 start_single_instance_server）。
        self._single_server: SingleInstanceServer | None = None
        self._tray_wired = False
        # 已经上过的小窗材质参数，避免每次设置改动都重上一次。
        self._acrylic_state: tuple[bool, bool] | None = None

        self._wire_config()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------
    def _wire_config(self) -> None:
        """Re-apply the OS-level settings whenever they change in the UI."""
        settings = self.config_manager.config["settings"]
        self.config_manager.hotkeyChanged.connect(self.apply_hotkey)
        self.config_manager.trayEnabledChanged.connect(self.apply_tray)
        self.config_manager.materialChanged.connect(self.apply_material)
        self.config_manager.settingsChanged.connect(self.apply_compact_acrylic)
        # QML 里的页面够不到窗口对象，页面级请求统一从后端转上来。
        self.config_manager.pageRequested.connect(self.show_main_page)
        self.config_manager.showToast.connect(
            lambda message, _severity: self.tray.show_message("Rin Launcher", message))
        # 系统控制的失败提示走和小窗同一条 toast 链路。
        self.system_controls.notify.connect(self.config_manager.notify)

        self.apply_hotkey(str(settings.get("globalHotkey", "")))
        self.apply_tray(bool(settings.get("showTray", True)))

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
    def create_main_window(self) -> bool:
        if not QML_ENTRY.is_file():
            logger.error("QML entry point is missing: %s", QML_ENTRY)
            return False

        # Inject the backend before loading, so the first binding already sees it.
        window = RinUIWindow()
        window.engine.rootContext().setContextProperty("ConfigManager", self.config_manager)
        window.engine.rootContext().setContextProperty("KeyRecorder", self.key_recorder)
        window.engine.rootContext().setContextProperty("SystemControls", self.system_controls)
        window.load(QML_ENTRY)

        if window.root_window is None:
            logger.error("Failed to load %s", QML_ENTRY)
            return False

        self.window = window
        if ICON_FILE.is_file():
            window.setIcon(ICON_FILE)
        self.apply_material(str(self.config_manager.config["settings"].get(
            "material", DEFAULT_MATERIAL)))

        # QML 的关闭按钮只发信号，由这里决定是收起还是真的退出。
        root = window.root_window
        if hasattr(root, "closeRequested"):
            root.closeRequested.connect(self.on_close_requested)
        # 双引擎的 ThemeManager 每次新建窗口后都要重钉一遍（后建的会顶掉先建的）。
        self._pin_theme_managers()
        return True

    def create_compact_window(self) -> bool:
        if not COMPACT_ENTRY.is_file():
            logger.error("Compact QML entry point is missing: %s", COMPACT_ENTRY)
            return False

        window = RinUIWindow()
        window.engine.rootContext().setContextProperty("ConfigManager", self.config_manager)
        window.engine.rootContext().setContextProperty("SystemControls", self.system_controls)
        window.load(COMPACT_ENTRY)

        if window.root_window is None:
            logger.error("Failed to load %s", COMPACT_ENTRY)
            return False

        self.compact = window
        root = window.root_window
        # 小窗是独立的 QML 根，够不到主窗口，跨窗口的请求统一走信号回到这里。
        root.openMainRequested.connect(self.show_main_page)
        root.hideRequested.connect(self.hide_compact)
        root.quitRequested.connect(self.quit)

        # ThemeManager 挂在共享的 rootContext 上，后建的窗口会把它顶掉：
        # 每个引擎都重钉回自己窗口那一份（懒建主窗后这里尤其重要）。
        self._pin_theme_managers()

        # 桌面挂件：沉底、不抢焦点 + 亚克力。材质要在窗口有原生句柄之后再上。
        effects.apply_no_focus_tool_window(root)
        effects.apply_bottom_layer(root)
        self.apply_compact_acrylic()
        return True

    def ensure_main_window(self) -> bool:
        """完整窗口按需创建：启动时只出小窗，第一次要打开时才构建。"""
        if self.window is not None:
            return True
        if not self.create_main_window():
            self.tray.show_message("Rin Launcher", "完整窗口加载失败，可以看看日志")
            return False
        return True

    def start_single_instance_server(self) -> None:
        """守着单实例的本地套接字：第二个进程请求「亮出小窗」时照办。"""
        self._single_server = SingleInstanceServer(self.app)
        self._single_server.showRequested.connect(self.show_compact)

    def _pin_theme_managers(self) -> None:
        """把每个引擎的 ThemeManager 都钉回自己窗口那一份。

        RinUI 的 ThemeManager 挂在各引擎的 rootContext 上，后建的窗口会把先建
        引擎里的绑定顶掉；谁后建都可能让另一个窗口主题错乱，所以每次新建窗口
        之后统一重钉一遍。
        """
        for window in (self.window, self.compact):
            if window is not None and window.root_window is not None:
                window.engine.rootContext().setContextProperty(
                    "ThemeManager", window.theme_manager)

    # ------------------------------------------------------------------
    # OS integration
    # ------------------------------------------------------------------
    def apply_hotkey(self, sequence: str) -> None:
        if not self.hotkey.register(sequence):
            logger.info("No global hotkey registered (configured value: %r)", sequence)

    def apply_material(self, material: str) -> None:
        """完整窗口的材质：默认「增强云母」。

        RinUI 的 backdrop 只管它自己注册过的窗口，小窗另有亚克力（见
        ``apply_compact_acrylic``）。非 Windows 上 RinUI 会直接抛错，所以先判断平台。
        """
        if self.window is None or not is_windows():
            return
        effect = MATERIALS.get(str(material), MATERIALS[DEFAULT_MATERIAL])
        try:
            self.window.setBackdropEffect(effect)
        except Exception:
            logger.exception("Failed to apply backdrop effect %r", material)

    def apply_compact_acrylic(self) -> None:
        """小窗的亚克力。QML 侧会根据 ``acrylicActive`` 决定卡片画多透明。"""
        if self.compact is None or self.compact.root_window is None:
            return
        root = self.compact.root_window
        enabled = bool(self.config_manager.config["settings"].get("compactAcrylic", True))
        dark = self._is_dark_theme()

        # 设置改动会频繁触发这里，参数没变就别重复问系统了。
        signature = (enabled, dark)
        if signature == self._acrylic_state:
            return
        self._acrylic_state = signature

        if not enabled:
            effects.clear_acrylic(root)
            root.setProperty("acrylicActive", False)
            return

        applied = effects.apply_acrylic(root, dark=dark)
        root.setProperty("acrylicActive", applied)
        if not applied:
            logger.info("Acrylic unavailable, falling back to a translucent card")

    def _is_dark_theme(self) -> bool:
        mode = str(self.config_manager.config["settings"].get("theme", "system")).lower()
        if mode == "dark":
            return True
        if mode == "light":
            return False
        try:  # 跟随系统
            return bool(self.app.styleHints().colorScheme().name == "Dark")
        except Exception:
            return False

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
        # 小窗带 WindowDoesNotAcceptFocus，requestActivate() 是无效调用（Qt 会打一条
        # 警告）。置底窗口不能 raise_()（那会把它翻到别的窗口上面），显示完再向
        # 系统兜一次底，防止刚显示时被抬到前台。
        effects.apply_bottom_layer(root)

    def hide_compact(self) -> None:
        if self.compact is not None and self.compact.root_window is not None:
            self.compact.root_window.hide()

    def toggle_compact(self) -> None:
        if self._visible(self.compact):
            self.hide_compact()
        else:
            self.show_compact()

    def show_main_page(self, page: str) -> None:
        """打开完整窗口并切到指定页（小窗的编辑按钮也走这里）。"""
        if not self.ensure_main_window():
            return
        root = self.window.root_window
        if root is None:
            return
        root.show()
        root.raise_()
        root.requestActivate()
        root.setProperty("requestedPage", page)

    def hide_main(self) -> None:
        if self.window is not None and self.window.root_window is not None:
            self.window.root_window.hide()

    def handle_tray_page(self, page: str) -> None:
        """托盘菜单里的「启动台」指常驻小窗，设置 / 关于才开完整窗口。"""
        if page == "launcher":
            self.show_compact()
        else:
            self.show_main_page(page)

    def on_close_requested(self) -> None:
        """完整窗口的关闭按钮只收起自己 —— 常驻小窗还在，程序不该跟着退出。"""
        self.hide_main()
        if not self.tray.started and not self._visible(self.compact):
            # 没有托盘、小窗也没显示：再没有任何入口能把它叫回来了。
            self.quit()

    def quit(self) -> None:
        self.hotkey.unregister()
        self.tray.stop()
        self.system_controls.stop()
        self.config_manager.stopWatching()
        self.app.quit()

    def run(self) -> int:
        self.config_manager.startWatching()
        if not self.config_manager.config["settings"].get("startMinimized", False):
            self.show_compact()

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
    guard = acquire_single_instance()
    if guard is None:
        notify_running_instance()
        return 0

    launcher = Launcher(app)
    _setup_logging(launcher.config_manager)

    # 启动只出小窗；完整窗口第一次要打开时才建（懒建，启动更快）。
    if not launcher.create_compact_window():
        return 1
    launcher.start_single_instance_server()
    launcher.hotkey.activated.connect(launcher.toggle_compact)
    return launcher.run()


if __name__ == "__main__":
    sys.exit(main())
