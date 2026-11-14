"""Windows PowerShell 脚本落盘与启动。

**为什么不用 ``encoding="utf-8-sig"``**：冻结后的 PyInstaller 包里，编码器是按
名字动态查找的；``encodings.utf_8_sig`` 没有被静态收集时，``open(..., encoding=
"utf-8-sig")`` 会直接抛 ``LookupError: unknown encoding: utf-8-sig``。

1.1.6 起更新装不上的根因就是这句（见 ``data/logs`` 里的真实堆栈）。这里改成
「``BOM_UTF8`` 常量 + ``str.encode("utf-8")``」——两者都是内置的，不经过动态
编码查找，冻结包里一样可靠；同时保留 BOM，让 Windows PowerShell 5.1 按 UTF-8
解析脚本里的非 ASCII 文本。
"""

from __future__ import annotations

import codecs
import os
import subprocess
from collections.abc import Iterable
from pathlib import Path

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _script_environment() -> dict[str, str]:
    """给 Windows PowerShell 5.1 准备一份能自动加载内置模块的 ModulePath。

    从 PowerShell 7 环境启动本程序时，``PSModulePath`` 会以
    ``Documents\\PowerShell\\Modules`` 开头；5.1 在某些机器上会先命中不兼容的
    模块目录，连 ``Get-FileHash`` / ``ConvertFrom-Json`` 都报「无法识别」。
    把 5.1 自己的模块目录放到最前面即可，其余用户路径保持不动。
    """
    env = os.environ.copy()
    if os.name != "nt":
        return env
    system_root = env.get("SystemRoot") or r"C:\Windows"
    builtin = os.path.join(
        system_root, "System32", "WindowsPowerShell", "v1.0", "Modules")
    parts = [part for part in env.get("PSModulePath", "").split(os.pathsep) if part]
    if not any(os.path.normcase(part) == os.path.normcase(builtin) for part in parts):
        parts.insert(0, builtin)
    else:
        parts.remove(next(part for part in parts
                          if os.path.normcase(part) == os.path.normcase(builtin)))
        parts.insert(0, builtin)
    env["PSModulePath"] = os.pathsep.join(parts)
    return env


def write_script(path: Path, text: str) -> Path:
    """把脚本文本写成「UTF-8 带 BOM」的字节流。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(codecs.BOM_UTF8 + text.encode("utf-8"))
    return path


def read_text(path: Path) -> str:
    """读回脚本 / 结果文件：去掉 BOM，解码失败用替换字符（不抛异常）。"""
    data = path.read_bytes()
    if data.startswith(codecs.BOM_UTF8):
        data = data[len(codecs.BOM_UTF8):]
    return data.decode("utf-8", errors="replace")


def spawn_hidden(script: Path, arguments: Iterable[str] = (),
                 cwd: str | Path | None = None) -> subprocess.Popen:
    """以隐藏窗口启动一个 .ps1；返回 Popen，调用方自己决定要不要等它。"""
    return subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-WindowStyle", "Hidden", "-File", str(script), *arguments],
        cwd=str(cwd) if cwd is not None else None,
        env=_script_environment(),
        creationflags=_CREATE_NO_WINDOW,
    )
