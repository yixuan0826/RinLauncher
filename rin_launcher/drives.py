"""磁盘枚举与卷标读取。

``ConfigManager`` 原来把这一整套内联在文件里（约 160 行），既和配置读写无关，
也被小窗的存储卡片、设置页的磁盘选择器、U 盘槽位三处共用。这里只放纯函数：
不持有 Qt 对象、不发信号、不读写配置，方便单独测试。

Windows 上用 ``kernel32`` 直接问系统；其它平台返回一个根分区占位，
让开发环境下的界面仍然能跑通。
"""

from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DRIVE_KIND_LABELS: dict[str, str] = {
    "removable": "可移动磁盘", "fixed": "本地磁盘", "network": "网络位置",
    "cdrom": "光驱", "ramdisk": "内存盘",
}


def human_size(size: int) -> str:
    """把字节数写成 32.78GB 这种一眼能读的形式。"""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f}{unit}" if unit == "B" else f"{value:.2f}{unit}"
        value /= 1024
    return f"{value:.2f}TB"


def drive_kind(code: int) -> str:
    return {2: "removable", 3: "fixed", 4: "network", 5: "cdrom", 6: "ramdisk"}.get(code, "")


def volume_label(root: str) -> str:
    """读盘根的卷标（如 ``课件``）；没有卷标或读不到时返回空串。"""
    if sys.platform != "win32" or not root:
        return ""
    try:
        import ctypes

        buffer = ctypes.create_unicode_buffer(261)
        if ctypes.windll.kernel32.GetVolumeInformationW(
                ctypes.c_wchar_p(root), buffer, 261, None, None, None, None, 0):
            return buffer.value.strip()
    except Exception:
        logger.debug("Cannot read volume label of %s", root, exc_info=True)
    return ""


def drive_details(path: Path) -> dict[str, Any]:
    """路径是盘根时返回卷标 / 类型；普通文件夹返回空字典。

    小窗的存储卡片要显示「课件」而不是「E:\\」：盘符对用户没有意义，卷标才是
    他自己起的名字。普通文件夹仍然用目录名。
    """
    root = str(path.anchor or "")
    if not root or str(path) != root:
        return {}
    kind = ""
    if sys.platform == "win32":
        try:
            import ctypes

            kind = drive_kind(ctypes.windll.kernel32.GetDriveTypeW(
                ctypes.c_wchar_p(root)))
        except Exception:
            logger.debug("Cannot read drive type of %s", root, exc_info=True)
    return {
        "root": root,
        "label": volume_label(root),
        "kind": kind,
        "kindLabel": DRIVE_KIND_LABELS.get(kind, ""),
    }


def find_removable_drive() -> str:
    """返回第一个可移动磁盘的根路径（如 ``E:\\``）；找不到或非 Windows 返回空串。"""
    if sys.platform != "win32":
        return ""
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        mask = kernel32.GetLogicalDrives()
    except Exception:
        logger.exception("Failed to enumerate drives")
        return ""

    for index in range(26):
        if not mask & (1 << index):
            continue
        root = f"{chr(ord('A') + index)}:\\"
        if kernel32.GetDriveTypeW(ctypes.c_wchar_p(root)) == 2:  # DRIVE_REMOVABLE
            return root
    return ""


def list_drives() -> list[dict[str, Any]]:
    """枚举本机磁盘，给「磁盘」槽位的选择器用。

    非 Windows 上只给一个根分区 —— 开发环境（Linux/macOS）里界面照样能跑通，
    不至于整块功能消失。
    """
    if sys.platform != "win32":
        try:
            usage = shutil.disk_usage("/")
        except OSError:
            return []
        return [{
            "path": "/",
            "label": "根目录",
            "kind": "fixed",
            "kindLabel": "本地磁盘",
            "free": human_size(usage.free),
            "total": human_size(usage.total),
            "percent": round(usage.used / usage.total * 100) if usage.total else 0,
        }]

    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        mask = kernel32.GetLogicalDrives()
    except Exception:
        logger.exception("Failed to enumerate drives")
        return []

    drives: list[dict[str, Any]] = []
    for index in range(26):
        if not mask & (1 << index):
            continue
        root = f"{chr(ord('A') + index)}:\\"
        kind = drive_kind(kernel32.GetDriveTypeW(ctypes.c_wchar_p(root)))
        if not kind:
            continue

        label = ""
        try:
            buffer = ctypes.create_unicode_buffer(261)
            if kernel32.GetVolumeInformationW(
                    ctypes.c_wchar_p(root), buffer, 261, None, None, None, None, 0):
                label = buffer.value
        except Exception:
            logger.debug("Cannot read volume label of %s", root)

        free_text = total_text = ""
        percent = 0
        # 光驱／网络盘没插介质时读容量会卡住，直接跳过。
        if kind in ("fixed", "removable", "ramdisk"):
            try:
                free = ctypes.c_ulonglong(0)
                total = ctypes.c_ulonglong(0)
                if kernel32.GetDiskFreeSpaceExW(
                        ctypes.c_wchar_p(root), ctypes.byref(free),
                        ctypes.byref(total), None) and total.value:
                    free_text = human_size(free.value)
                    total_text = human_size(total.value)
                    percent = round((total.value - free.value) / total.value * 100)
            except Exception:
                logger.debug("Cannot read free space of %s", root)

        drives.append({
            "path": root,
            "label": label or root,
            "kind": kind,
            "kindLabel": DRIVE_KIND_LABELS.get(kind, kind),
            "free": free_text,
            "total": total_text,
            "percent": percent,
        })
    return drives
