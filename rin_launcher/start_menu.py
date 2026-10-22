"""开始菜单应用扫描：传统 .lnk、UWP / WSA（AUMID）与 WSL 发行版。

只负责「列出能启动什么」并定位条目图标（UWP 读包清单、WSA 读快捷方式
``IconLocation``）；图标入库与动作落盘交给 ConfigManager。结果短缓存，避免每次
打开选择器都重新解析几百个快捷方式。
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CACHE_TTL = 30.0
_cache: tuple[float, list[dict[str, Any]]] | None = None

_START_MENU_DIRS = (
    Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    Path(os.environ.get("PROGRAMDATA", "C:/ProgramData"))
    / "Microsoft" / "Windows" / "Start Menu" / "Programs",
)
_SKIP_WORDS = ("uninstall", "卸载", "unins")
# 快捷方式自己的 IconLocation 是图片时可以直接拿来预览（WSA 的安卓应用就是
# 这样：一个普通的 .lnk，图标放在 LocalState 里的 .ico）。
_IMAGE_ICON_SUFFIXES = (".ico", ".png", ".svg", ".jpg", ".jpeg", ".bmp")

# UWP 的图标不在快捷方式里：每个应用的 ``uap:VisualElements`` 写在包清单
# AppxManifest.xml 的 ``Square44x44Logo`` / ``Square150x150Logo`` 上，清单在
# 包的安装目录里。安装目录可以从 HKCU 的 AppModel 包仓库一次全部读出来，
# 比逐个跑 Get-AppxPackage 快一个数量级。
_PACKAGE_REPOSITORY = (
    r"Software\Classes\Local Settings\Software\Microsoft\Windows"
    r"\CurrentVersion\AppModel\Repository\Packages"
)
_package_roots: dict[str, Path] | None = None
# AUMID 的图标只在第一次扫描时解析；之后开选择器直接用缓存。
_uwp_icon_cache: dict[str, str] = {}


def _clean_icon_location(raw: str) -> str:
    """``"C:\\x\\app.ico,0"`` / ``"%windir%\\system32\\imageres.dll,-114"`` → 文件路径。

    只认真实存在的文件；``,0`` 这种资源索引会被丢掉（Qt 这边不按索引取图标）。
    """
    text = str(raw or "").strip()
    if not text:
        return ""
    if "," in text:
        text = text.rsplit(",", 1)[0]
    text = os.path.expandvars(text.strip().strip('"'))
    return text if text and Path(text).is_file() else ""


def _is_wsa(target: str, arguments: str) -> bool:
    """WSA 安卓应用的快捷方式，目标都是 WsaClient.exe + wsa:// 参数。"""
    lowered = f"{target} {arguments}".lower()
    return ("wsaclient.exe" in lowered
            or "windowssubsystemforandroid" in lowered
            or "wsa://" in lowered)



def _decode(raw: bytes) -> str:
    for encoding in ("utf-8", "utf-16-le", "mbcs", "latin-1"):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def _run(command: list[str], timeout: float = 8.0) -> str:
    if sys.platform != "win32":
        return ""
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return _decode(completed.stdout or b"")
    except Exception:
        logger.debug("Command failed: %s", command, exc_info=True)
        return ""


def _should_skip(name: str, target: str) -> bool:
    lowered = f"{name} {target}".lower()
    return any(word in lowered for word in _SKIP_WORDS)


def _load_package_roots() -> dict[str, Path]:
    """包族名 → 安装目录。读 HKCU 的 AppModel 包仓库，整表只读一次。"""
    global _package_roots
    if _package_roots is not None:
        return _package_roots
    roots: dict[str, Path] = {}
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _PACKAGE_REPOSITORY) as key:
                index = 0
                while True:
                    try:
                        full_name = winreg.EnumKey(key, index)
                    except OSError:
                        break
                    index += 1
                    # 键名是 PackageFullName：Name_Version_Arch_ResourceId_PublisherId，
                    # 包族名只保留 Name 与 PublisherId。
                    parts = full_name.split("_")
                    if len(parts) < 2:
                        continue
                    try:
                        with winreg.OpenKey(key, full_name) as entry:
                            root = winreg.QueryValueEx(entry, "PackageRootFolder")[0]
                    except OSError:
                        continue
                    roots[f"{parts[0]}_{parts[-1]}".lower()] = Path(str(root))
        except OSError:
            logger.debug("Cannot read the AppModel package repository", exc_info=True)
    _package_roots = roots
    return roots


def _asset_rank(path: Path) -> tuple[int, int, int]:
    """图标变体的优先级：普通版优先，尺寸越大越靠前。"""
    name = path.stem.lower()
    # 高对比度与浅色（单色）变体不适合当应用图标，排在后面。
    plain = 1 if ("contrast" in name or "altform" in name) else 0
    target = re.search(r"targetsize-(\d+)", name)
    if target:
        return (plain, 0, -int(target.group(1)))
    scale = re.search(r"scale-(\d+)", name)
    if scale:
        return (plain, 1, -int(scale.group(1)))
    return (plain, 2, 0)


def _xml_attr(node: Any, name: str) -> str:
    """按本地名取属性：清单里偶有 ``uap:Square44x44Logo`` 这种带命名空间的写法。"""
    for key, value in node.attrib.items():
        if key.split("}")[-1] == name and value:
            return str(value)
    return ""


def _resolve_uwp_logo(root: Path, logo: str) -> Path | None:
    """把清单里的 Logo 属性解析成实际图片文件（含 scale / targetsize 变体）。"""
    text = str(logo or "").strip()
    if not text:
        return None
    if text.lower().startswith("ms-resource:"):
        # ms-resource:///Files/Assets/Logo.png → Assets\\Logo.png
        tail = text.split(":", 1)[1].replace("/", "\\").lstrip("\\")
        marker = "files\\"
        index = tail.lower().find(marker)
        text = tail[index + len(marker):] if index >= 0 else tail
    path = root / text.replace("/", "\\")
    if path.suffix.lower() not in _IMAGE_ICON_SUFFIXES:
        return None
    directory = path.parent
    if not directory.is_dir():
        return None
    # 清单只写基名，磁盘上是 Base.scale-200.png / Base.targetsize-48.png 这类变体。
    try:
        candidates = [
            item for item in directory.iterdir()
            if item.is_file()
            and item.suffix.lower() == path.suffix.lower()
            and (item.stem == path.stem or item.stem.startswith(path.stem + "."))
        ]
    except OSError:
        # 个别包目录有 ACL 限制：读不到变体就用清单里的原始路径兜底。
        return path if path.is_file() else None
    if not candidates:
        return path if path.is_file() else None
    return min(candidates, key=_asset_rank)


def _uwp_icon(app_id: str) -> str:
    """AUMID → ``file:<图标路径>``；取不到时返回空串（界面退回占位字形）。"""
    key = app_id.lower()
    if key in _uwp_icon_cache:
        return _uwp_icon_cache[key]
    icon = ""
    family, _, application = app_id.partition("!")
    root = _load_package_roots().get(family.lower())
    if root is not None and application:
        logo = ""
        try:
            import xml.etree.ElementTree as ET

            tree = ET.parse(root / "AppxManifest.xml")
            first = ""
            for node in tree.iter():
                if node.tag.split("}")[-1] != "Application":
                    continue
                visual = next(
                    (child for child in node.iter()
                     if child.tag.split("}")[-1] == "VisualElements"),
                    None,
                )
                if visual is None:
                    continue
                current = (_xml_attr(visual, "Square44x44Logo")
                           or _xml_attr(visual, "Square150x150Logo")
                           or _xml_attr(visual, "Logo"))
                if node.get("Id", "").lower() == application.lower():
                    logo = current
                    break
                if not first:
                    first = current
            logo = logo or first
        except Exception:
            logger.debug("Cannot read the manifest of %s", root, exc_info=True)
        if logo:
            asset = _resolve_uwp_logo(root, logo)
            if asset is not None:
                icon = f"file:{asset}"
    _uwp_icon_cache[key] = icon
    return icon


def _parse_lnk(shell: Any, path: Path) -> dict[str, Any] | None:
    try:
        shortcut = shell.CreateShortcut(str(path))
        target = os.path.expandvars(str(shortcut.TargetPath or "").strip())
        if not target:
            return None
        arguments = str(shortcut.Arguments or "").strip()
        working_dir = os.path.expandvars(str(shortcut.WorkingDirectory or "").strip())
        name = str(shortcut.Description or "").strip() or path.stem
        if _should_skip(name, target):
            return None
        # WSA 安卓应用不是 UWP：它们只是普通的 .lnk（目标 WsaClient.exe），
        # 正确的应用图标写在快捷方式自己的 IconLocation 里。跟随 target 去抽
        # 只会拿到 WsaClient 的通用图标，所以这里把 IconLocation 一起带出去。
        try:
            icon_location = _clean_icon_location(str(shortcut.IconLocation or ""))
        except Exception:
            icon_location = ""
        icon = ""
        if (icon_location
                and Path(icon_location).suffix.lower() in _IMAGE_ICON_SUFFIXES):
            icon = f"file:{icon_location}"
        return {
            "kind": "wsa" if _is_wsa(target, arguments) else "lnk",
            "name": name,
            "target": target,
            "arguments": arguments,
            "working_dir": working_dir,
            "icon": icon,
            "icon_location": icon_location,
            "source": str(path),
        }
    except Exception:
        logger.debug("Cannot parse shortcut %s", path, exc_info=True)
        return None


def _list_shortcuts() -> list[dict[str, Any]]:
    if sys.platform != "win32":
        return []
    try:
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        shell = win32com.client.Dispatch("WScript.Shell")
    except Exception:
        logger.debug("pywin32 shortcut parsing is unavailable", exc_info=True)
        return []

    apps: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for root in _START_MENU_DIRS:
        if not root.is_dir():
            continue
        for path in root.rglob("*.lnk"):
            app = _parse_lnk(shell, path)
            if app is None:
                continue
            key = (app["target"].lower(), app["arguments"])
            if key in seen:
                continue
            seen.add(key)
            apps.append(app)
    return apps


def _list_uwp() -> list[dict[str, Any]]:
    output = _run([
        "powershell.exe", "-NoProfile", "-Command",
        "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress",
    ])
    if not output.strip():
        return []
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        logger.debug("Cannot parse Get-StartApps output", exc_info=True)
        return []
    if isinstance(payload, dict):
        payload = [payload]
    apps: list[dict[str, Any]] = []
    for item in payload:
        app_id = str(item.get("AppID") or "").strip()
        name = str(item.get("Name") or "").strip()
        # AUMID 一定带包族名 + '!'；普通桌面程序的 AppID 不是我们要的。
        if not app_id or "!" not in app_id or not name:
            continue
        apps.append({
            "kind": "uwp",
            "name": name,
            "target": app_id,
            "arguments": "",
            "working_dir": "",
            # 包清单里的应用图标；解析不出来时为空，界面用类型占位图。
            "icon": _uwp_icon(app_id),
            "source": "shell:AppsFolder",
        })
    return apps


def _list_wsl() -> list[dict[str, Any]]:
    output = _run(["wsl.exe", "-l", "-q"])
    apps: list[dict[str, Any]] = []
    for line in output.splitlines():
        distro = line.strip().replace("\x00", "")
        if not distro or distro.lower().startswith("windows subsystem"):
            continue
        apps.append({
            "kind": "wsl",
            "name": f"{distro} (WSL)",
            "target": "wsl.exe",
            "arguments": f'-d "{distro}"',
            "working_dir": "",
            "icon": "",
            "source": "wsl",
        })
    return apps


def list_start_menu_apps(force: bool = False) -> list[dict[str, Any]]:
    """返回开始菜单里可添加的应用；结果缓存 30 秒。"""
    global _cache
    now = time.monotonic()
    if not force and _cache is not None and now - _cache[0] < _CACHE_TTL:
        return [dict(item) for item in _cache[1]]
    apps = _list_shortcuts() + _list_uwp() + _list_wsl()
    apps.sort(key=lambda item: str(item.get("name") or "").lower())
    _cache = (now, apps)
    return [dict(item) for item in apps]


def parse_shortcut(path: str) -> dict[str, Any] | None:
    """解析用户手动挑选的 .lnk（绕过缓存）。"""
    if sys.platform != "win32" or not path:
        return None
    try:
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        shell = win32com.client.Dispatch("WScript.Shell")
    except Exception:
        return None
    return _parse_lnk(shell, Path(path))


def shortcut_icon_path(path: str | Path) -> str:
    """只读快捷方式自己的 IconLocation；不存在或不是 .lnk 时返回空串。

    WSA 安卓应用把正确的应用图标写在这里（LocalState 目录下的 .ico），目标
    ``WsaClient.exe`` 只有一张通用图标 —— 抽图标时要先看这里。
    """
    if sys.platform != "win32":
        return ""
    source = Path(path)
    if source.suffix.lower() != ".lnk":
        return ""
    try:
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        shortcut = win32com.client.Dispatch("WScript.Shell").CreateShortcut(str(source))
        return _clean_icon_location(str(shortcut.IconLocation or ""))
    except Exception:
        logger.debug("Cannot read the icon location of %s", source, exc_info=True)
        return ""
