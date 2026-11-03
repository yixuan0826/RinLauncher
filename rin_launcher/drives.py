"""磁盘枚举与卷标读取。

``ConfigManager`` 原来把这一整套内联在文件里（约 160 行），既和配置读写无关，
也被小窗的存储卡片、设置页的磁盘选择器、U 盘槽位三处共用。这里只放纯函数：
不持有 Qt 对象、不发信号、不读写配置，方便单独测试。

Windows 上用 ``kernel32`` 直接问系统；其它平台返回一个根分区占位，
让开发环境下的界面仍然能跑通。
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_USB_NAME_CACHE: tuple[float, dict[str, str]] | None = None
_USB_NAME_TTL = 5.0

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


# IOCTL_STORAGE_QUERY_PROPERTY + StorageDeviceProperty：拿 USB 设备的
# VendorId / ProductId，不启动子进程。
_IOCTL_STORAGE_QUERY_PROPERTY = 0x002D1400
_FILE_SHARE_READ = 0x00000001
_FILE_SHARE_WRITE = 0x00000002
_OPEN_EXISTING = 3
_INVALID_HANDLE_VALUE = -1


def _device_name_native(root: str) -> str:
    """盘根 → 硬件型号（如 ``TransMemory``）；读不到返回空串。"""
    if sys.platform != "win32" or not root:
        return ""
    try:
        import ctypes
        from ctypes import wintypes

        class STORAGE_PROPERTY_QUERY(ctypes.Structure):
            _fields_ = [("PropertyId", ctypes.c_uint32),
                        ("QueryType", ctypes.c_uint32),
                        ("AdditionalParameters", ctypes.c_ubyte * 1)]

        kernel32 = ctypes.windll.kernel32
        kernel32.CreateFileW.restype = wintypes.HANDLE
        handle = kernel32.CreateFileW(
            ctypes.c_wchar_p("\\\\.\\" + root.rstrip("\\")),
            0, _FILE_SHARE_READ | _FILE_SHARE_WRITE, None,
            _OPEN_EXISTING, 0, None)
        if handle == _INVALID_HANDLE_VALUE or not handle:
            return ""
        try:
            query = STORAGE_PROPERTY_QUERY(0, 0)  # StorageDeviceProperty, PropertyStandardQuery
            buffer = ctypes.create_string_buffer(1024)
            returned = wintypes.DWORD(0)
            ok = kernel32.DeviceIoControl(
                handle, _IOCTL_STORAGE_QUERY_PROPERTY,
                ctypes.byref(query), ctypes.sizeof(query),
                buffer, ctypes.sizeof(buffer),
                ctypes.byref(returned), None)
            if not ok or returned.value < 32:
                return ""

            def text_at(offset: int) -> str:
                if offset <= 0 or offset >= returned.value:
                    return ""
                return ctypes.string_at(ctypes.addressof(buffer) + offset).decode(
                    "mbcs", errors="replace").strip()

            vendor_offset = ctypes.c_uint32.from_buffer(buffer, 12).value
            product_offset = ctypes.c_uint32.from_buffer(buffer, 16).value
            vendor = text_at(vendor_offset)
            product = text_at(product_offset)
            return " ".join(part for part in (vendor, product) if part).strip()
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        logger.debug("原生 USB 型号读取失败: %s", root, exc_info=True)
        return ""


def _native_usb_names() -> dict[str, str]:
    """枚举当前可移动盘符并直接读型号。"""
    names: dict[str, str] = {}
    if sys.platform != "win32":
        return names
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        mask = kernel32.GetLogicalDrives()
    except Exception:
        return names
    for index in range(26):
        if not mask & (1 << index):
            continue
        root = f"{chr(ord('A') + index)}:\\"
        try:
            if kernel32.GetDriveTypeW(ctypes.c_wchar_p(root)) != 2:
                continue
        except Exception:
            continue
        name = _device_name_native(root)
        if name:
            names[root.rstrip("\\").upper()] = name
    return names


def _run_powershell(script: str, timeout: float = 6.0) -> str:
    if sys.platform != "win32":
        return ""
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return (completed.stdout or b"").decode("utf-8", errors="replace")
    except Exception:
        logger.debug("USB device query failed", exc_info=True)
        return ""


def usb_device_names() -> dict[str, str]:
    """盘符（``E:``）→ USB 设备型号（如 ``TransMemory``）。

    卷标是用户给分区起的名字，多分区 U 盘会各不相同；设备型号才是硬件本身。
    读不到时返回空表，调用方回退到卷标。
    """
    global _USB_NAME_CACHE
    if sys.platform != "win32":
        return {}
    now = time.monotonic()
    if _USB_NAME_CACHE and now - _USB_NAME_CACHE[0] < _USB_NAME_TTL:
        return dict(_USB_NAME_CACHE[1])
    # 先走原生 IOCTL（毫秒级）；个别驱动不实现 StorageDeviceProperty 时才回退
    # 到 PowerShell/CIM。
    native = _native_usb_names()
    if native:
        _USB_NAME_CACHE = (now, native)
        return dict(native)
    script = (
        "$rows = Get-CimInstance Win32_DiskDrive | "
        "Where-Object { $_.InterfaceType -eq 'USB' } | ForEach-Object { "
        "$disk = $_; $letters = @(); "
        "Get-CimAssociatedInstance -InputObject $disk -ResultClassName Win32_DiskPartition | "
        "ForEach-Object { $part = $_; "
        "Get-CimAssociatedInstance -InputObject $part -ResultClassName Win32_LogicalDisk | "
        "ForEach-Object { $letters += $_.DeviceID } }; "
        "[pscustomobject]@{ model = $disk.Model; letters = $letters } }; "
        "$rows | ConvertTo-Json -Compress"
    )
    output = _run_powershell(script)
    names: dict[str, str] = {}
    if output.strip():
        try:
            payload = json.loads(output)
        except json.JSONDecodeError:
            payload = []
        if isinstance(payload, dict):
            payload = [payload]
        for item in payload if isinstance(payload, list) else []:
            if not isinstance(item, dict):
                continue
            model = str(item.get("model") or "").strip()
            letters = item.get("letters") or []
            if isinstance(letters, str):
                letters = [letters]
            for letter in letters:
                key = str(letter or "").strip().rstrip("\\").upper()
                if key and model:
                    names[key] = model
    _USB_NAME_CACHE = (now, names)
    return dict(names)


def _partition_info(root: str) -> dict[str, Any] | None:
    try:
        import ctypes

        free = ctypes.c_ulonglong(0)
        total = ctypes.c_ulonglong(0)
        if not ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                ctypes.c_wchar_p(root), ctypes.byref(free),
                ctypes.byref(total), None) or not total.value:
            return None
        return {
            "path": root,
            "label": volume_label(root) or root,
            "free": human_size(free.value),
            "total": human_size(total.value),
            "freeBytes": int(free.value),
            "totalBytes": int(total.value),
            "percent": round((total.value - free.value) / total.value * 100),
        }
    except Exception:
        logger.debug("Cannot read free space of %s", root, exc_info=True)
        return None


def removable_devices() -> list[dict[str, Any]]:
    """按「物理设备」聚合可移动磁盘；多分区合并容量，并保留分区列表。"""
    if sys.platform != "win32":
        return []
    names = usb_device_names()
    groups: dict[str, dict[str, Any]] = {}
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        mask = kernel32.GetLogicalDrives()
    except Exception:
        logger.exception("Failed to enumerate removable drives")
        return []
    for index in range(26):
        if not mask & (1 << index):
            continue
        root = f"{chr(ord('A') + index)}:\\"
        if kernel32.GetDriveTypeW(ctypes.c_wchar_p(root)) != 2:  # DRIVE_REMOVABLE
            continue
        partition = _partition_info(root)
        if partition is None:
            # 读不到容量（刚拔出 / 未格式化）也保留盘符，不让入口凭空消失。
            partition = {
                "path": root, "label": volume_label(root) or root,
                "free": "", "total": "", "freeBytes": 0,
                "totalBytes": 0, "percent": 0,
            }
        key = names.get(root.rstrip("\\").upper()) or partition["label"] or root
        group = groups.setdefault(key, {
            "name": key,
            "device": names.get(root.rstrip("\\").upper(), ""),
            "partitions": [],
            "freeBytes": 0,
            "totalBytes": 0,
        })
        group["partitions"].append(partition)
        group["freeBytes"] += int(partition.get("freeBytes") or 0)
        group["totalBytes"] += int(partition.get("totalBytes") or 0)
    devices = list(groups.values())
    for device in devices:
        total = int(device.pop("totalBytes") or 0)
        free = int(device.pop("freeBytes") or 0)
        device["total"] = human_size(total) if total else ""
        device["free"] = human_size(free) if total else ""
        device["percent"] = round((total - free) / total * 100) if total else 0
        device["paths"] = [part["path"] for part in device["partitions"]]
        device["path"] = device["paths"][0] if device["paths"] else ""
    return devices


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
