"""自启动命令的路径比较。

注册表和任务计划里存的是「一个字符串」，Windows 不保证它和当前进程的
``sys.executable`` 写法完全一致：可能带引号、用短路径（8.3）、大小写不同，
甚至指向已经被覆盖掉的旧版本。这里只做一件事：判断两条命令是不是同一个
可执行文件，供 ``autostart`` / ``elevation`` 共用。
"""

from __future__ import annotations

import os
import re


def first_token(command: str) -> str:
    """取出命令里的第一个参数（可执行文件），去掉外层引号。"""
    text = str(command or "").strip()
    if not text:
        return ""
    if text.startswith('"'):
        end = text.find('"', 1)
        return text[1:end] if end > 0 else text[1:]
    return text.split(None, 1)[0]


def normalize_command(command: str) -> str:
    """把命令压成可比较的形式：去引号、统一斜杠、折叠空白、小写。"""
    text = os.path.expandvars(str(command or "")).strip().lower()
    text = text.replace('"', "").replace("/", "\\")
    return re.sub(r"\s+", " ", text).strip()


def commands_match(left: str, right: str) -> bool:
    """两条自启动命令是否指向同一个可执行文件。

    先做字符串级比较；失败时再让 Windows 用 ``samefile`` 解析短路径 / 大小写。
    目标不存在时 ``samefile`` 会抛 ``OSError``，此时只能相信字符串比较。
    """
    if not left or not right:
        return False
    if normalize_command(left) == normalize_command(right):
        return True
    a = first_token(left)
    b = first_token(right)
    if not a or not b:
        return False
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False
