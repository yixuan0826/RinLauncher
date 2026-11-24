"""运行期路径语义：源码、PyInstaller 与 Nuitka 三种形态共用一套判断。

Nuitka 不会设置 ``sys.frozen``，而是在每个编译过的模块里注入 ``__compiled__``。
如果继续直接判断 ``sys.frozen``，Nuitka 包会误以为自己跑在源码树里：

* QML / assets 去开发机路径找，构建时漏收资源也“看起来能跑”；
* ``data/`` 写回仓库，而不是 exe 同级。

这里把“是否冻结”“资源在哪”“安装目录在哪”收成三个函数，业务代码不再各写
一套。注意资源根与安装目录是两件事：

* PyInstaller onefile 的资源解压在 ``sys._MEIPASS``，数据仍应写在 exe 同级；
* onedir / Nuitka standalone 两者都指向 exe 同级。
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

#: 进程刚启动时的 ``sys.executable``。Nuitka standalone 默认把它设成
#: ``<安装目录>\\python.exe``（构建时 Python 的文件名），而不是 RinLauncher.exe。
ORIGINAL_EXECUTABLE = sys.executable


def _is_compiled() -> bool:
    """Nuitka 编译标记；单独拆出来方便测试模拟。"""
    return "__compiled__" in globals()


def is_frozen() -> bool:
    """是否运行在打包产物里（PyInstaller 或 Nuitka）。"""
    return bool(getattr(sys, "frozen", False)) or _is_compiled()


def bundle_root() -> Path:
    """只读资源根：qml/、assets/ 以及随包数据都从这里加载。"""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent.parent


def app_dir() -> Path:
    """安装目录：冻结包是 exe 同级，源码运行是仓库根。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return bundle_root()


def process_image() -> Path | None:
    """当前进程的映像路径（Windows）。

    ``sys.executable`` 不一定是进程映像：Nuitka standalone 在 Python 3.8+
    上是拿启动时的 ``argv[0]`` 填的，从中文快捷方式 / 8.3 短路径 / 改名副本
    启动时会留下一个「看起来像 Python」的旧路径。诊断和兜底都需要真实映像。
    """
    if sys.platform != "win32":
        return None
    try:
        from ctypes import create_unicode_buffer, windll

        buffer = create_unicode_buffer(32768)
        length = windll.kernel32.GetModuleFileNameW(None, buffer, len(buffer))
        if length:
            return Path(buffer.value)
    except Exception:
        logger.debug("无法读取进程映像路径", exc_info=True)
    return None


def launch_target() -> Path:
    """当前安装里应该被 Windows 拉起的 exe。

    冻结包永远优先安装目录下的 ``RinLauncher.exe``。Nuitka standalone 默认把
    ``sys.executable`` 设成 ``<安装目录>\\python.exe``（构建时 Python 的
    basename），这个文件并不存在；从改名副本 / 8.3 短路径启动时还可能指向
    别处。自启动、重启、更新覆盖和通知注册都必须指回真正存在的入口。
    """
    if not is_frozen():
        return Path(sys.executable)
    current = Path(sys.executable)
    candidates: list[Path] = []
    for base in (current.parent, bundle_root()):
        candidate = base / "RinLauncher.exe"
        if candidate not in candidates:
            candidates.append(candidate)
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate
        if resolved.is_file():
            return resolved
    if current.is_file():
        return current.resolve()
    image = process_image()
    if image is not None and image.is_file():
        return image.resolve()
    return current


def adopt_canonical_executable() -> tuple[str, str] | None:
    """冻结包从旧入口启动时，把 ``sys.executable`` 归一到 RinLauncher.exe。

    返回 ``(原值, 新值)``；没有改动时返回 ``None``。必须在任何「再启动一个
    自己」的操作（自启动、重启、更新、通知注册）之前调用，否则旧入口被删除
    后这些操作会全部指向一个不存在的文件。
    """
    if not is_frozen():
        return None
    target = launch_target()
    if not target.is_file():
        return None
    current = Path(sys.executable)
    try:
        current_resolved = current.resolve()
    except OSError:
        current_resolved = current
    if str(current) == str(target) and current_resolved == target:
        return None
    previous = str(current)
    sys.executable = str(target)
    return previous, str(target)


def describe() -> dict[str, str]:
    """运行期路径快照：写进日志 / 复制诊断信息时用。"""
    image = process_image()
    return {
        "frozen": str(is_frozen()),
        "executable": sys.executable,
        "rawExecutable": ORIGINAL_EXECUTABLE,
        "baseExecutable": str(getattr(sys, "_base_executable", "")),
        "argv0": sys.argv[0] if sys.argv else "",
        "processImage": str(image) if image is not None else "",
        "appDir": str(app_dir()),
        "bundleRoot": str(bundle_root()),
        "launchTarget": str(launch_target()),
        "meipass": str(getattr(sys, "_MEIPASS", "")),
    }
