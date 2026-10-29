# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build script — run with ``pyinstaller build.spec``.

产物是单文件 ``dist/RinLauncher.exe``（console=False）。构建时的取舍：

* **体积**：PySide6 的 hook 会把整套 Qt 运行库都带上（其中 WebEngine 内核就有
  ~194MB），这里做两层过滤：``EXCLUDES`` 排掉用不到的 Python 绑定，分析完再
  按名字把用不到的 Qt DLL / QML 模块从 binaries、datas 里剔出去（见
  ``_drop_qt_binaries`` / ``_drop_qt_datas``）。原则是「拿不准就保留」——
  宁可多带几 MB，也不能运行期缺 DLL。
* **资源**：qml/、RinUI/、assets/ 都不是 Python 模块，必须显式带进 datas，
  漏掉任何一个都会在运行期找不到资源。

产物有两种形态：

* 默认 **onedir** —— ``dist/RinLauncher/`` 目录（入口是 RinLauncher.exe）：
  不用解压、启动快，是正式发布的形态；``data/`` 数据目录就落在 exe 同级。
* **onefile** —— ``set RIN_ONEFILE=1`` 后再构建，产物是单个
  ``dist/RinLauncher.exe``，拷贝方便但每次启动先解压，只作应急用。
"""

import os
from pathlib import Path

ROOT = Path(SPECPATH)
ICON = ROOT / "assets" / "icon.ico"

# 用不到的模块：整包剔掉。Qt 侧只用 Core / Gui / Widgets / Qml / Quick /
# QuickControls2 / Svg（RinUI 的 Lawnicons 渲染需要 Svg；Qt5Compat 被 RinUI
# 组件引用，必须保留）。
EXCLUDES = [
    # 大块头 Qt 模块
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel", "PySide6.QtWebSockets", "PySide6.QtWebView",
    "PySide6.Qt3DAnimation", "PySide6.Qt3DCore", "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput", "PySide6.Qt3DLogic", "PySide6.Qt3DRender",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs",
    "PySide6.QtQuick3D", "PySide6.QtQuick3DAssetImport", "PySide6.QtQuick3DRuntimeRender",
    "PySide6.QtQuick3DUtils", "PySide6.QtQuickWidgets",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtSpatialAudio",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    # 设备与外设：桌面启动台用不到
    "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtSensors", "PySide6.QtSerialPort",
    "PySide6.QtPositioning", "PySide6.QtTextToSpeech", "PySide6.QtRemoteObjects",
    "PySide6.QtScxml", "PySide6.QtStateMachine", "PySide6.QtNetworkAuth",
    # 工具链与开发用模块
    "PySide6.QtHelp", "PySide6.QtDesigner", "PySide6.QtUiTools", "PySide6.QtTest",
    "PySide6.QtSql", "PySide6.QtSvgWidgets", "PySide6.QtOpenGLWidgets",
    # 纯 Python 侧的大包（有的会被环境里的其它东西顺带勾进来）
    "tkinter", "matplotlib", "numpy", "pandas", "scipy", "PIL", "cv2", "IPython", "pytest",
]

# 运行库层面的深度瘦身：前缀命中即删。都是桌面上明确不会加载的模块 ——
# WebEngine / WebView 系、3D 与 Quick3D 系、图表系、多媒体系、虚拟键盘、
# 开发工具（Designer/Test/Sql/Help）……
DROP_QT_DLL_PREFIXES = (
    "Qt6WebEngine", "Qt6WebView", "Qt6WebChannel", "Qt6WebSockets",
    "Qt63D", "Qt6Quick3D",
    "Qt6Charts", "Qt6DataVisualization", "Qt6Graphs",
    "Qt6Multimedia", "Qt6SpatialAudio", "Qt6Pdf", "Qt6VirtualKeyboard",
    "Qt6TextToSpeech", "Qt6Sensors", "Qt6Positioning", "Qt6Location",
    "Qt6RemoteObjects", "Qt6Scxml", "Qt6StateMachine", "Qt6Sql", "Qt6Test",
    "Qt6QuickTest", "Qt6Designer", "Qt6Help",
    # Qt Quick Controls 的默认 style 解析会依次尝试 Windows / Fusion，这两个
    # 必须留着；RinUI 组件显式 import Basic，FluentWinUI3 是当前观感基准。
    # Imagine / Material / Universal 三套（~8MB）用不到，可以剔掉。
    "Qt6QuickControls2Imagine", "Qt6QuickControls2Material",
    "Qt6QuickControls2Universal",
)
# 对应的 QML 模块目录（dest 以 PySide6/qml/ 开头）。
DROP_QML_DIRS = (
    "QtQuick3D", "Qt3D", "QtCharts", "QtDataVisualization", "QtGraphs",
    "QtMultimedia", "QtWebEngine", "QtWebView", "QtWebChannel",
    "QtVirtualKeyboard", "QtTextToSpeech", "QtSensors", "QtPositioning",
    "QtLocation", "QtRemoteObjects", "QtScxml", "QtStateMachine", "QtSql", "QtTest",
)
# QtQuick/Controls 下的样式子目录，与上面 DLL 一一对应。
DROP_CONTROLS_STYLES: tuple[str, ...] = ("Imagine", "Material", "Universal")

# 运行期用不到的插件目录：qmltooling 是 QML 调试器后端，networkinformation 只服务于
# Qt Network 的网络状态查询，两者都不会被加载。
DROP_PLUGIN_DIRS = ("qmltooling", "networkinformation")
# 不会用到的图片格式（图标只用 png / ico / svg / jpeg / webp / gif）。
DROP_PLUGIN_FILES = ("qtiff.dll", "qicns.dll", "qtga.dll", "qwbmp.dll")


def _basename(path: str) -> str:
    return path.replace("\\", "/").rsplit("/", 1)[-1]


def _drop_qt_binaries(binaries):
    kept = []
    for entry in binaries:
        name = _basename(entry[0])
        norm = entry[0].replace("\\", "/")
        if name.startswith(DROP_QT_DLL_PREFIXES):
            continue
        if "/plugins/" in norm:
            plugin_dir = norm.split("/plugins/", 1)[1].split("/", 1)[0]
            if plugin_dir in DROP_PLUGIN_DIRS or name in DROP_PLUGIN_FILES:
                continue
        kept.append(entry)
    print(f"[spec] Qt DLL: {len(binaries)} -> {len(kept)}")
    return kept


def _drop_qt_datas(datas):
    def unwanted(dest: str) -> bool:
        norm = dest.replace("\\", "/")
        if norm.startswith("PySide6/translations/"):
            # 本项目不做 i18n；Qt 自己的翻译只留简体中文（标准文件对话框的
            # 按钮文字靠它）。其余语言全部剔掉，一次省 8MB。
            return not norm.rsplit("/", 1)[-1].endswith("_zh_CN.qm")
        if not norm.startswith("PySide6/qml/"):
            return False
        rest = norm[len("PySide6/qml/"):]
        parts = rest.split("/")
        if parts[0] in DROP_QML_DIRS:
            return True
        # QtQuick/Controls/<Style>：样式目录不在第一层，需要单独匹配。
        if len(parts) >= 3 and parts[0] == "QtQuick" and parts[1] == "Controls":
            return parts[2] in DROP_CONTROLS_STYLES
        return False

    kept = [entry for entry in datas if not unwanted(entry[0])]
    print(f"[spec] QML datas: {len(datas)} -> {len(kept)}")
    return kept


a = Analysis(
    [str(ROOT / "rin_launcher" / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / "qml"), "qml"),
        # RinUI 是内联的普通目录，QML/字体/主题都不是 Python 模块，必须显式带上。
        (str(ROOT / "RinUI"), "RinUI"),
        # QML 里用相对路径引用 Lawnicons，图标与 icon.ico 都在 assets 下。
        (str(ROOT / "assets"), "assets"),
    ],
    # PyInstaller's PySide6 hook already pulls in the Qt modules, so only the
    # plain-Python dependencies have to be listed here.
    hiddenimports=[
        "yaml", "pynput", "watchdog", "ctypes.wintypes",
        # watchdog 在 startWatching() 里才导入，显式列出子模块更稳。
        "watchdog.events", "watchdog.observers",
        # 小窗系统控制：音量（pycaw）与 WinRT 投影。这些导入都在函数里延迟加载，
        # 静态分析可能漏掉子模块，这里逐个点名。
        "pycaw", "pycaw.pycaw", "comtypes", "comtypes.client",
        "winrt", "winrt.runtime",
        "winrt.windows.devices.radios",
        "winrt.windows.foundation",
        "winrt.windows.foundation.collections",
        "winrt.windows.networking.connectivity",
        "winrt.windows.networking.networkoperators",
        # Windows 原生通知（rin_launcher/toast.py）。
        "winrt.windows.data.xml.dom",
        "winrt.windows.ui.notifications",
        # 启动台搜索的拼音匹配（rin_launcher/search.py，缺失时自动退化）。
        "pypinyin",
        # 冻结包里按名字动态查找的编码器不会被静态收集；1.1.6~1.1.8 的
        # “unknown encoding: utf-8-sig” 就是这么来的。这里显式点名两个会用到的。
        "encodings.utf_8_sig",
        "encodings.utf_8",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)

# 深度瘦身放在分析之后：hook 已经把 DLL 全收集完，这里只做减法。
a.binaries = _drop_qt_binaries(a.binaries)
a.datas = _drop_qt_datas(a.datas)

pyz = PYZ(a.pure)

# 正式发布形态是 onedir：目录形式启动不用先解压，冷启动快得多。
# 万一需要单文件（比如临时拷给别的机器），设 RIN_ONEFILE=1 再构建。
ONEDIR = os.environ.get("RIN_ONEFILE") != "1"

if ONEDIR:
    # 目录形态：不打包成一个文件，启动时不用解压。
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="RinLauncher",
        debug=False,
        strip=False,
        upx=True,
        console=False,
        icon=str(ICON) if ICON.exists() else None,
    )
    COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=True,
        name="RinLauncher",
    )
else:
    # 单文件形态（默认）：dist/RinLauncher.exe。
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="RinLauncher",
        debug=False,
        strip=False,
        upx=True,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=str(ICON) if ICON.exists() else None,
    )
