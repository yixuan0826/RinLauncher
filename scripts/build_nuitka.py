"""Build the Windows release payload with Nuitka.

Usage::

    python scripts/build_nuitka.py
    python scripts/build_nuitka.py --zig          # local machine without MSVC
    python scripts/build_nuitka.py --print-command

The result is the same layout as the old PyInstaller onedir build::

    dist/RinLauncher/RinLauncher.exe
    dist/RinLauncher/qml/...
    dist/RinLauncher/assets/...
    dist/RinLauncher/RinUI/...

Keeping that layout is important: ``RinLauncher.zip`` is the self-update
payload, and the installer/updater both expect the exe at the zip root.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
TARGET = DIST / "RinLauncher"
STAGE = ROOT / "build" / "nuitka"
MAIN = ROOT / "rin_launcher" / "main.py"
ICON = ROOT / "assets" / "icon.ico"

# 只有 Nuitka 的静态分析容易漏掉、且运行期确实需要的模块。
HIDDEN_MODULES = (
    "encodings.utf_8_sig",
    "encodings.utf_8",
    "comtypes.client",
    "win32com.client",
    "win32com.propsys.propsys",
    "win32com.propsys.pscon",
    "winrt.runtime",
    "winrt.windows.data.xml.dom",
    "winrt.windows.devices.radios",
    "winrt.windows.foundation",
    "winrt.windows.foundation.collections",
    "winrt.windows.networking.connectivity",
    "winrt.windows.networking.networkoperators",
    "winrt.windows.storage.streams",
    "winrt.windows.ui",
    "winrt.windows.ui.notifications",
    "winrt.windows.ui.viewmanagement",
    "watchdog.events",
    "watchdog.observers",
)

# 明确用不到的大包：不让 Nuitka 顺着偶然的导入把它们收进来。
NOFOLLOW = (
    "tkinter",
    "matplotlib",
    "numpy",
    "pandas",
    "scipy",
    "PIL",
    "cv2",
    "IPython",
    "pytest",
)

# Nuitka 的 pyside6 插件会把整棵 QML 模块树和它依赖的 Qt DLL 都收进来。
# 这些模块本项目明确不用，构建后按文件名 / QML 目录裁掉；保留清单与
# 旧 PyInstaller 发布配置的裁剪规则一致，原则仍是「拿不准就保留」。
DROP_QT_DLL_PREFIXES = (
    "qt6webengine", "qt6webview", "qt6webchannel", "qt6websockets",
    "qt63d", "qt6quick3d",
    "qt6charts", "qt6datavisualization", "qt6graphs",
    "qt6multimedia", "qt6spatialaudio", "qt6pdf", "qt6virtualkeyboard",
    "qt6texttospeech", "qt6sensors", "qt6positioning", "qt6location",
    "qt6remoteobjects", "qt6scxml", "qt6statemachine", "qt6sql", "qt6test",
    "qt6quicktest", "qt6designer", "qt6help",
    "qt6quickcontrols2imagine", "qt6quickcontrols2material",
    "qt6quickcontrols2universal",
    # QtQuick 在 Windows 上会 import PySide6.QtOpenGL；软件 OpenGL 兜底
    # opengl32sw.dll（约 20 MB）不参与正常的 D3D11 路径。
    "qt6openglwidgets", "opengl32sw",
    # QtQuick.Controls 的默认样式解析仍会试 Windows / Fusion / NativeStyle，
    # 这三套必须保留；只裁 Imagine / Material / Universal。
    "qt6quickparticles", "qt6quicktimeline", "qt6quickvectorimage",
    "qt6quickdialogs2", "qt6quickcontrols2native",
    "qt6qmldesignsupport", "qt6qmllocalstorage", "qt6qmlnetwork",
    "qt6qmlxmllistmodel", "qt6concurrent",
    "qt6labsanimation", "qt6labsfolderlistmodel", "qt6labsplatform",
    "qt6labsqmlmodels", "qt6labssettings", "qt6labssharedimage",
    "qt6labssynchronizer", "qt6labswavefrontmesh",
)
DROP_QML_DIRS = (
    "QtWebEngine", "QtWebView", "QtWebChannel", "QtWebSockets",
    "Qt3D", "QtQuick3D", "QtCharts", "QtDataVisualization", "QtGraphs",
    "QtMultimedia", "QtLocation", "QtPositioning", "QtSensors",
    "QtTextToSpeech", "QtRemoteObjects", "QtScxml", "QtTest",
)
DROP_QML_SUBDIRS = (
    "QtQuick/VirtualKeyboard", "QtQuick/Dialogs", "QtQuick/Particles",
    "QtQuick/Timeline", "QtQuick/VectorImage", "QtQuick/LocalStorage",
    "QtQuick/Scene2D", "QtQuick/Scene3D", "QtQuick/tooling",
    "QtQuick/Pdf", "QtQuick/Controls/designer",
)
DROP_CONTROLS_STYLES = ("Imagine", "Material", "Universal")
# QtQuick 会 import PySide6.QtOpenGL，不能删；QtOpenGLWidgets 本项目不用。
DROP_PYSIDE_FILES = ("qtopenglwidgets.pyd",)


def read_version() -> str:
    text = (ROOT / "rin_launcher" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if match is None:
        raise SystemExit("cannot read __version__ from rin_launcher/__init__.py")
    return match.group(1)


def numeric_version(version: str) -> str:
    """Turn ``1.2.4-pre`` into the four-part Windows version ``1.2.4.0``."""
    parts = [int(item) for item in re.findall(r"\d+", version)[:4]]
    while len(parts) < 4:
        parts.append(0)
    return ".".join(str(item) for item in parts)


def build_command(*, zig: bool, report: bool) -> list[str]:
    version = read_version()
    quad = numeric_version(version)
    command = [
        sys.executable,
        "-m",
        "nuitka",
        "--mode=standalone",
        "--enable-plugin=pyside6",
        # RinUI 的 QML 组件会从 PySide6/qml 下解析 QtQuick / Controls 模块。
        "--include-qt-plugins=qml",
        "--assume-yes-for-downloads",
        f"--output-dir={STAGE}",
        "--output-filename=RinLauncher.exe",
        "--windows-console-mode=disable",
        f"--windows-icon-from-ico={ICON}",
        "--company-name=RinLauncher",
        "--product-name=Rin Launcher",
        "--file-description=Rin Launcher",
        f"--file-version={quad}",
        f"--product-version={quad}",
        # 应用自己的资源：zed / QML / 字体都在这些目录里。
        f"--include-data-dir={ROOT / 'qml'}=qml",
        f"--include-data-dir={ROOT / 'assets'}=assets",
        f"--include-data-file={ROOT / 'scripts' / 'repair.ps1'}=repair.ps1",
        # pip 包里的非 Python 文件（RinUI 的 QML/字体/主题、WinRT 投影表、
        # pypinyin 词库）不会自动进入 standalone 目录。
        "--include-package-data=RinUI",
        "--include-package-data=winrt",
        "--include-package-data=pypinyin",
        "--include-package=RinUI",
        "--include-package=rin_launcher",
        f"--nofollow-import-to={','.join(NOFOLLOW)}",
        str(MAIN),
    ]
    for module in HIDDEN_MODULES:
        command.insert(-1, f"--include-module={module}")
    if report:
        command.insert(-1, f"--report={STAGE / 'report.xml'}")
    if zig:
        command.insert(-2, "--zig")
    else:
        # Zig 0.17.1 的 LTO 链接会缺 fdiml/nanl 符号；本地绕开，CI 的 MSVC 用 LTO。
        command.insert(-1, "--lto=yes")
    return command


def _stage_dist() -> Path:
    candidates = sorted(STAGE.glob("*.dist"))
    if len(candidates) != 1:
        names = ", ".join(path.name for path in candidates) or "none"
        raise SystemExit(f"expected exactly one Nuitka .dist directory, got: {names}")
    return candidates[0]


def _trim_payload(target: Path) -> None:
    """Delete Qt modules the launcher never loads (same policy as the old PyInstaller release config)."""
    removed = 0
    for path in sorted(target.rglob("*"), reverse=True):
        if not path.is_file():
            continue
        name = path.name.lower()
        norm = path.relative_to(target).as_posix()
        drop = name.startswith(DROP_QT_DLL_PREFIXES) or name in DROP_PYSIDE_FILES
        if not drop and norm.startswith("PySide6/qml/"):
            rest = norm[len("PySide6/qml/"):]
            first = rest.split("/", 1)[0]
            drop = (
                first in DROP_QML_DIRS
                or any(rest == sub or rest.startswith(sub + "/")
                       for sub in DROP_QML_SUBDIRS)
                or (rest.startswith("QtQuick/Controls/")
                    and rest.split("/")[2] in DROP_CONTROLS_STYLES)
                # .qmltypes / .metainfo 只服务 qmllint / 设计器，运行期不加载。
                or name.endswith((".qmltypes", ".metainfo"))
            )
        if not drop and norm.startswith("RinUI/") and name.endswith(".ts"):
            # 翻译源文件；运行期只读 .qm。
            drop = True
        plugin_root = next(
            (prefix for prefix in ("PySide6/qt-plugins/", "PySide6/plugins/")
             if norm.startswith(prefix)),
            None,
        )
        if not drop and plugin_root is not None:
            rest = norm[len(plugin_root):]
            plugin_dir = rest.split("/", 1)[0]
            drop = plugin_dir in ("qmltooling", "networkinformation", "tls", "generic")
            if not drop:
                drop = name in (
                    "qtiff.dll", "qicns.dll", "qtga.dll", "qwbmp.dll",
                    "qdirect2d.dll", "qminimal.dll", "qoffscreen.dll",
                )
        if drop:
            path.unlink()
            removed += 1
    # 删掉空目录，避免 zip 里留一堆空壳。
    for path in sorted(target.rglob("*"), reverse=True):
        if path.is_dir():
            try:
                path.rmdir()
            except OSError:
                pass
    print(f"[nuitka] trimmed {removed} unused Qt files")


def _check_payload(target: Path) -> None:
    required = (
        target / "RinLauncher.exe",
        target / "qml" / "CompactWindow.qml",
        target / "assets" / "icon.ico",
        target / "repair.ps1",
    )
    missing = [str(path.relative_to(target)) for path in required if not path.exists()]
    if missing:
        raise SystemExit("payload is missing: " + ", ".join(missing))
    rinui = list(target.rglob("*.qml"))
    if not any("RinUI" in path.parts for path in rinui):
        raise SystemExit("payload has no RinUI QML data (check --include-package-data=RinUI)")
    pywinrt = list(target.rglob("*.pywinrt"))
    if not pywinrt:
        raise SystemExit("payload has no WinRT projection tables (*.pywinrt)")


def _size_mb(path: Path) -> float:
    total = sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
    return total / (1024 * 1024)


def find_upx() -> str | None:
    """Locate UPX; winget's Links directory is not always in the current PATH."""
    found = shutil.which("upx")
    if found:
        return found
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        candidate = Path(local) / "Microsoft" / "WinGet" / "Links" / "upx.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def compress_exe(target: Path, upx: str, *, required: bool) -> None:
    """UPX the launcher exe only.

    A/B on 2026-11-23: compressing Qt DLLs/pyds more than doubled frozen cold
    start (1133 -> 2200 ms), so only the main exe is packed.  ``--best`` (NRV)
    keeps startup at ~1.24 s; ``--lzma`` was slower to decompress.  The zip
    still shrinks from 53.9 MB to ~51.8 MB.
    """
    exe = target / "RinLauncher.exe"
    before = exe.stat().st_size
    result = subprocess.run(
        [upx, "--best", "--no-progress", "-q", str(exe)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        if required:
            raise SystemExit(f"UPX failed for {exe}: {detail}")
        print(f"[nuitka] WARNING: UPX skipped: {detail}")
        return
    after = exe.stat().st_size
    print(f"[nuitka] UPX exe: {before / 1048576:.1f} -> {after / 1048576:.1f} MB")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zig", action="store_true",
                        help="use Nuitka's bundled Zig instead of MSVC (local experiments)")
    parser.add_argument("--print-command", action="store_true",
                        help="print the Nuitka command and exit")
    parser.add_argument("--no-report", action="store_true",
                        help="skip the Nuitka XML report")
    upx_group = parser.add_mutually_exclusive_group()
    upx_group.add_argument("--upx", dest="upx", action="store_true",
                           help="require UPX and compress the main exe")
    upx_group.add_argument("--no-upx", dest="upx", action="store_false",
                           help="do not compress with UPX")
    parser.set_defaults(upx=None)
    args = parser.parse_args(argv)

    upx = find_upx()
    if args.upx is True and upx is None:
        raise SystemExit("--upx requested but upx.exe was not found in PATH")
    if args.upx is False:
        upx = None

    command = build_command(zig=args.zig, report=not args.no_report)
    if args.print_command:
        print(subprocess.list2cmdline(command))
        return 0

    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    print(f"[nuitka] building {read_version()} -> {TARGET}", flush=True)
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode != 0:
        return result.returncode

    produced = _stage_dist()
    if TARGET.exists():
        shutil.rmtree(TARGET)
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(produced), str(TARGET))
    _trim_payload(TARGET)
    # 构建目录里还剩 C 源码 / obj；留着方便排查，CI 的 build/ 不会进包。
    _check_payload(TARGET)
    if upx is not None:
        compress_exe(TARGET, upx, required=args.upx is True)
    elapsed = time.monotonic() - started
    print(f"[nuitka] done in {elapsed:.1f}s, payload {_size_mb(TARGET):.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
