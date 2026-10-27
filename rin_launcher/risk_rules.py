"""风险行为库：系统关键路径、危险命令与提权动作的预警规则。

只做「提示」不做「拦截」：编辑器会把命中的原因显示给用户，二次确认后
仍然允许添加。规则尽量保守，误报的代价只是多一次确认。
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

HIGH = "high"
MEDIUM = "medium"

# (正则, 原因)。命令串 = target + arguments。
DANGEROUS_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bformat\s+[a-z]:", re.I), "格式化磁盘"),
    (re.compile(r"\bdiskpart\b", re.I), "磁盘分区工具"),
    (re.compile(r"\bbcdedit\b", re.I), "修改启动配置"),
    (re.compile(r"\bbootrec\b", re.I), "改写启动记录"),
    (re.compile(r"\breg\s+delete\b", re.I), "删除注册表项"),
    (re.compile(r"\breg\s+add\b.*\\run\b", re.I), "写入开机启动注册表"),
    (re.compile(r"\bshutdown\b.*(/s|/r|/p)", re.I), "关机或重启系统"),
    (re.compile(r"\b(vssadmin|wbadmin)\b.*\bdelete\b", re.I), "删除系统备份"),
    (re.compile(r"\bcipher\s+/w", re.I), "擦除磁盘空闲空间"),
    (re.compile(r"\bnet\s+user\b", re.I), "修改本地账户"),
    (re.compile(r"\b(sc|net)\s+delete\b", re.I), "删除系统服务"),
    (re.compile(r"\bicacls\b.*\bgrant\b", re.I), "修改文件权限"),
    (re.compile(r"\btakeown\b", re.I), "接管文件所有权"),
    (re.compile(r"(remove-item|del|rd|rmdir)\b.*(-recurse|-r\b).*(c:\\|/s|/q)", re.I),
     "递归删除磁盘内容"),
    (re.compile(r"\brm\s+-rf\s+/(\s|$)", re.I), "递归删除根目录"),
    (re.compile(r"(powershell|pwsh).*(-enc|-encodedcommand|invoke-expression|\biex\b)", re.I),
     "执行动态 PowerShell"),
    (re.compile(r"\bset-executionpolicy\b.*unrestricted", re.I), "放开脚本执行策略"),
)

HIGH_REASONS = frozenset({
    "格式化磁盘", "修改启动配置", "删除注册表项", "写入开机启动注册表",
    "删除系统服务", "递归删除磁盘内容", "递归删除根目录", "系统关键文件",
    "删除系统备份",
})

SYSTEM_DIRS = tuple(
    value for value in (
        os.environ.get("WINDIR"),
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("ProgramData"),
    ) if value
)

STARTUP_HINTS = ("\\start menu\\programs\\startup", "\\startup\\")
CRITICAL_NAMES = frozenset({
    "pagefile.sys", "hiberfil.sys", "bootmgr", "ntldr", "user32.dll", "kernel32.dll",
})


def _action(slot: dict[str, Any]) -> dict[str, Any]:
    action = slot.get("action")
    return action if isinstance(action, dict) else slot


def check(slot: Any) -> dict[str, Any]:
    """返回 ``{"level": high|medium|"", "reasons": [...]}``。"""
    if not isinstance(slot, dict):
        return {"level": "", "reasons": []}
    action = _action(slot)
    target = str(action.get("target") or "")
    arguments = str(action.get("arguments") or "")
    workdir = str(action.get("working_dir") or "")
    command = f"{target} {arguments}".strip()
    reasons: list[str] = []

    for pattern, label in DANGEROUS_PATTERNS:
        if pattern.search(command):
            reasons.append(label)

    path_text = (target + " " + workdir).lower().replace("/", "\\")
    if any(directory.lower() in path_text for directory in SYSTEM_DIRS):
        reasons.append("位于系统目录")
    if any(hint in path_text for hint in STARTUP_HINTS):
        reasons.append("位于开机启动目录")
    if Path(target).name.lower() in CRITICAL_NAMES:
        reasons.append("系统关键文件")
    if str(action.get("run_as") or "") == "admin":
        reasons.append("需要管理员权限")

    reasons = list(dict.fromkeys(reasons))
    if any(reason in HIGH_REASONS for reason in reasons):
        level = HIGH
    elif reasons:
        level = MEDIUM
    else:
        level = ""
    return {"level": level, "reasons": reasons}
