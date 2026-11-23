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

import sys
from pathlib import Path


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
