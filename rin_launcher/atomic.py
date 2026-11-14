"""小文件的原子写入。

配置、启动标记、更新状态这类文件一旦被截断，下一次启动就会读到半截内容
（``config.yaml`` 会回退默认值，``rin_ui.json`` 会让 RinUI 直接抛异常）。
这里统一用「同目录临时文件 → flush + fsync → os.replace」的写法，保证磁盘上
要么是旧文件，要么是新文件，不会出现第三种状态。

保留原文件的权限；``os.replace`` 在 Windows 上覆盖已存在文件是原子的。
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> bool:
    """把 *text* 原子地写到 *path*；失败时返回 False（旧文件保持不变）。"""
    target = Path(path)
    directory = target.parent
    try:
        directory.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            mode="w", encoding=encoding, newline="",
            dir=str(directory), prefix=f".{target.name}.", suffix=".tmp",
            delete=False)
        temporary = Path(handle.name)
        try:
            with handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
            return True
        except BaseException:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise
    except OSError:
        logger.exception("Failed to atomically write %s", target)
        return False


def atomic_write_bytes(path: Path, data: bytes) -> bool:
    """二进制版本（图标、清单等小文件）。"""
    target = Path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            mode="wb", dir=str(target.parent), prefix=f".{target.name}.",
            suffix=".tmp", delete=False)
        temporary = Path(handle.name)
        try:
            with handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
            return True
        except BaseException:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise
    except OSError:
        logger.exception("Failed to atomically write %s", target)
        return False
