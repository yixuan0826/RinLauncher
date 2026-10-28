"""GitHub Releases 更新检查、下载与安装。

1.1.9 起不再是「自动挑一个最新版下载」，而是把 **Release 列表**整张交给界面：
用户在下拉里选一个版本（可新可旧，回滚就是这么做的）→ 下载 → 手动点安装。

安装仍是：写一个隐藏的 PowerShell 脚本，等主进程退出后把解压好的文件覆盖
到安装目录并重新启动。区别是：

* 脚本用 ``powershell.write_script`` 落盘（绕开冻结包里的 ``utf-8-sig`` 编码
  缺失）；
* 脚本自己写结果文件（OK / FAIL + 原因），下次启动时读回来显示在更新页；
* 复制带重试，失败也会把旧版本拉起来，不会把用户晾在那儿；
* 只有确认辅助进程真的起来了，主进程才退出。

**没有 old.zip 回滚了**：回滚 = 在列表里选一个旧版本重装。
"""

from __future__ import annotations

import hashlib
import html
import json
import logging
import os
import re
import shutil
import sys
import threading
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QCoreApplication, QObject, QTimer, Signal, Slot
from PySide6.QtWidgets import QFileDialog

from rin_launcher import __version__ as APP_VERSION
from rin_launcher import powershell
from rin_launcher.config_manager import ConfigManager

logger = logging.getLogger(__name__)

REPO = "yixuan0826/RinLauncher"
API_ROOT = f"https://api.github.com/repos/{REPO}/releases"
ASSET_NAME = "rinlauncher.zip"
USER_AGENT = f"RinLauncher/{APP_VERSION}"

MIRRORS: dict[str, str] = {
    "ghfast": "https://ghfast.top/",
    "ghproxy": "https://ghproxy.net/",
}
MIRROR_LABELS = {"github": "GitHub", "ghfast": "ghfast", "ghproxy": "ghproxy"}
SPEED_URLS = {
    "github": f"https://api.github.com/repos/{REPO}/releases/latest",
    "ghfast": f"https://ghfast.top/https://raw.githubusercontent.com/{REPO}/main/README.md",
    "ghproxy": f"https://ghproxy.net/https://raw.githubusercontent.com/{REPO}/main/README.md",
}

STATE_IDLE = "idle"
STATE_CHECKING = "checking"
STATE_UP_TO_DATE = "up-to-date"
STATE_DOWNLOADING = "downloading"
STATE_READY = "ready"
STATE_INSTALLING = "installing"
STATE_ERROR = "error"


def version_tuple(tag: str) -> tuple[int, ...]:
    """把 ``v1.2.3-beta`` 这类 tag 变成可比较的数字元组。"""
    numbers = [int(part) for part in re.findall(r"\d+", str(tag))[:4]]
    return tuple(numbers) if numbers else (0,)


_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_HTML_BREAK = re.compile(r"<br\s*/?>", re.IGNORECASE)


def clean_release_notes(body: str) -> str:
    """GitHub Release 正文的最小清洗：丢掉 HTML 注释、把 ``<br>`` 换成换行。"""
    text = _HTML_COMMENT.sub("", str(body or ""))
    text = _HTML_BREAK.sub("\n", text)
    return text.strip()


# ── Release 列表 ────────────────────────────────────────────────────
#
# 更新页不再是「有新版就自动下载」，而是把整张 Release 列表交给用户挑。
# 这样「回滚」就是选一个旧版本重装，不需要 old.zip 那套备份/还原。

RELEASE_LIST_LIMIT = 30


def parse_releases(payload: Any, *,
                   limit: int = RELEASE_LIST_LIMIT) -> list[dict[str, Any]]:
    """把 GitHub ``/releases`` 的响应整理成界面能直接用的列表。

    纯函数（不碰网络 / Qt），方便测试。跳过草稿与没有 tag 的条目，按版本号
    从新到旧排序；每条带上下载地址、SHA-256 digest（GitHub 没给时为空串）
    以及 ``current`` 标记（就是当前运行的版本）。
    """
    if not isinstance(payload, list):
        return []
    items: list[dict[str, Any]] = []
    for raw in payload:
        if not isinstance(raw, dict) or raw.get("draft"):
            continue
        tag = str(raw.get("tag_name") or "").strip()
        if not tag:
            continue
        # 历史上的 tag 写法不统一（v1.1.0 / v.1.1.2），统一成纯版本号
        version = tag.lstrip("vV").lstrip(".")
        if not version:
            continue
        assets = raw.get("assets") if isinstance(raw.get("assets"), list) else []
        asset = next(
            (item for item in assets
             if isinstance(item, dict)
             and str(item.get("name") or "").lower() == ASSET_NAME),
            None,
        )
        items.append({
            "tag": tag,
            "version": version,
            "name": str(raw.get("name") or tag),
            "prerelease": bool(raw.get("prerelease")),
            "published": str(raw.get("published_at") or "")[:10],
            "url": str(raw.get("html_url") or ""),
            "downloadUrl": str((asset or {}).get("browser_download_url") or ""),
            "digest": str((asset or {}).get("digest") or ""),
            "assetName": str((asset or {}).get("name") or ""),
            "current": version == APP_VERSION,
            "notes": clean_release_notes(str(raw.get("body") or "")),
        })
    items.sort(key=lambda item: version_tuple(item["version"]), reverse=True)
    return items[:max(1, limit)]


def release_label(item: dict[str, Any]) -> str:
    """下拉菜单里的一行文本，例如 ``v1.1.8-pre · 预发布 · 当前``。"""
    parts = [f"v{item.get('version') or item.get('tag') or '?'}"]
    if item.get("current"):
        parts.append("当前")
    if item.get("prerelease"):
        parts.append("预发布")
    if item.get("published"):
        parts.append(str(item["published"]))
    if not item.get("downloadUrl"):
        parts.append("无更新包")
    return " · ".join(parts)



# ── Markdown → 结构化块 ──────────────────────────────────────────────
#
# 为什么不直接在 QML 里用 ``Text.MarkdownText``：Qt 6.12 的 QQuickText 在
# 「先空文本、后填 Markdown」这条路径上会按默认字号排版、按 Markdown 字号绘制，
# 标题行距被压扁甚至重叠。改成后端把正文拆成块、QML 一块一个 Text 之后，
# 每个块都是「创建时就有内容」，行距稳定，也顺手拿到了可控的字号与间距。

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_BULLET = re.compile(r"^[-*+]\s+(.+)$")
_ORDERED = re.compile(r"^(\d{1,3})[.)]\s+(.+)$")
_RULE = re.compile(r"^(?:-{3,}|\*{3,}|_{3,})$")

_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_STRIKE = re.compile(r"~~(.+?)~~")
_ITALIC_STAR = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
_ITALIC_UNDER = re.compile(r"(?<!_)_([^_\n]+)_(?!_)")


def _inline_markdown(text: str) -> str:
    """把行内 Markdown 变成 RichText 片段。

    先整体转义 HTML，再把代码、链接这些「里面的内容不该再解析」的部分暂存成
    占位符，最后统一还原 —— 免得代码里的星号被当成斜体。
    """
    tokens: list[str] = []

    def stash(fragment: str) -> str:
        tokens.append(fragment)
        return f"\x00{len(tokens) - 1}\x00"

    escaped = html.escape(text, quote=False)
    escaped = _INLINE_CODE.sub(
        lambda match: stash(f"<code>{match.group(1)}</code>"), escaped)
    escaped = _LINK.sub(
        lambda match: stash(
            f'<a href="{html.escape(match.group(2), quote=True)}">{match.group(1)}</a>'),
        escaped)
    escaped = _BOLD.sub(r"<b>\1</b>", escaped)
    escaped = _STRIKE.sub(r"<s>\1</s>", escaped)
    escaped = _ITALIC_STAR.sub(r"<i>\1</i>", escaped)
    escaped = _ITALIC_UNDER.sub(r"<i>\1</i>", escaped)

    for index, fragment in enumerate(tokens):
        escaped = escaped.replace(f"\x00{index}\x00", fragment)
    return escaped


def parse_release_notes(body: str) -> list[dict[str, Any]]:
    """把 Release 正文拆成 QML 能直接渲染的块列表。

    每块带 ``kind`` / ``html`` / ``spaceBefore``，标题额外带 ``level``。
    只覆盖 GitHub Release 里常见的语法：标题、段落、无序/有序列表、引用、
    围栏代码块、分隔线；表格与图片按普通段落处理。
    """
    blocks: list[dict[str, Any]] = []
    paragraph: list[str] = []
    code_lines: list[str] = []
    in_code = False

    def flush_paragraph() -> None:
        if not paragraph:
            return
        blocks.append({
            "kind": "paragraph",
            "html": _inline_markdown(" ".join(paragraph)),
            "spaceBefore": 8 if blocks else 0,
        })
        paragraph.clear()

    for raw_line in clean_release_notes(body).splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if in_code:
            if stripped.startswith("```"):
                blocks.append({
                    "kind": "code",
                    "html": html.escape("\n".join(code_lines), quote=False),
                    "spaceBefore": 10,
                })
                code_lines = []
                in_code = False
            else:
                code_lines.append(line)
            continue

        if stripped.startswith("```"):
            flush_paragraph()
            in_code = True
            continue

        if not stripped:
            flush_paragraph()
            continue

        heading = _HEADING.match(stripped)
        if heading:
            flush_paragraph()
            level = len(heading.group(1))
            blocks.append({
                "kind": "heading",
                "level": level,
                "html": _inline_markdown(heading.group(2)),
                "spaceBefore": 16 if level == 1 else 12 if level == 2 else 10,
            })
            continue

        if _RULE.match(stripped):
            flush_paragraph()
            blocks.append({"kind": "rule", "html": "", "spaceBefore": 12})
            continue

        bullet = _BULLET.match(stripped)
        if bullet:
            flush_paragraph()
            blocks.append({
                "kind": "bullet",
                "html": "• " + _inline_markdown(bullet.group(1)),
                "spaceBefore": 4 if blocks else 0,
            })
            continue

        ordered = _ORDERED.match(stripped)
        if ordered:
            flush_paragraph()
            blocks.append({
                "kind": "ordered",
                "html": f"{ordered.group(1)}. " + _inline_markdown(ordered.group(2)),
                "spaceBefore": 4 if blocks else 0,
            })
            continue

        if stripped.startswith(">"):
            flush_paragraph()
            blocks.append({
                "kind": "quote",
                "html": _inline_markdown(stripped.lstrip(">").strip()),
                "spaceBefore": 10,
            })
            continue

        paragraph.append(stripped)

    if in_code and code_lines:
        blocks.append({
            "kind": "code",
            "html": html.escape("\n".join(code_lines), quote=False),
            "spaceBefore": 10,
        })
    flush_paragraph()
    return blocks


class UpdateManager(QObject):
    changed = Signal()
    notify = Signal(str, str)

    _stateReady = Signal(str, str)
    _releasesReady = Signal(list)
    _downloadStart = Signal(str, str, str)
    _progressReady = Signal(float)
    _downloadFinished = Signal(bool, str, bool, str)
    _speedReady = Signal(list)

    def __init__(self, config_manager: ConfigManager, parent: QObject | None = None):
        super().__init__(parent)
        self._config = config_manager
        self._state = STATE_IDLE
        self._message = "尚未检查更新"
        self._latest_version = ""
        self._releases: list[dict[str, Any]] = []
        self._selected = -1
        self._downloaded_version = ""
        self._release_blocks: list[dict[str, Any]] = []
        self._release_url = ""
        self._download_url = ""
        self._progress = 0.0
        self._silent = False
        self._digest_verified = False
        self._last_error = ""
        self._startup_note = ""
        self._stopped = False
        self._pending_proc: Any = None
        self._thread: threading.Thread | None = None
        self._mirror_speeds: list[dict[str, Any]] = []
        self._speed_testing = False

        self._stateReady.connect(self._apply_state)
        self._releasesReady.connect(self._apply_releases)
        self._downloadStart.connect(self._apply_download_start)
        self._progressReady.connect(self._apply_progress)
        self._downloadFinished.connect(self._apply_download)
        self._speedReady.connect(self._apply_speed_results)

        self._cleanup_legacy()
        self._read_last_result()

    # ------------------------------------------------------------------
    # QML 属性
    # ------------------------------------------------------------------
    @Property(str, notify=changed)
    def state(self) -> str:
        return self._state

    @Property(str, notify=changed)
    def message(self) -> str:
        return self._message

    @Property(str, constant=True)
    def currentVersion(self) -> str:
        return APP_VERSION

    @Property(str, notify=changed)
    def latestVersion(self) -> str:
        """列表里最新的版本号（不代表一定比当前新）。"""
        return self._latest_version

    @Property(str, notify=changed)
    def downloadedVersion(self) -> str:
        return self._downloaded_version

    @Property(str, notify=changed)
    def lastError(self) -> str:
        """最近一次失败的原因（下载 / 安装 / 上次更新遗留）。"""
        return self._last_error

    @Property("QVariantList", notify=changed)
    def releases(self) -> list[dict[str, Any]]:
        """Release 列表（不含正文，正文只在选中时解析）。"""
        return [{key: value for key, value in item.items() if key != "notes"}
                for item in self._releases]

    @Property("QStringList", notify=changed)
    def releaseLabels(self) -> list[str]:
        return [release_label(item) for item in self._releases]

    @Property(int, notify=changed)
    def selectedIndex(self) -> int:
        return self._selected

    @Property("QVariantMap", notify=changed)
    def selectedRelease(self) -> dict[str, Any]:
        item = self._current_release()
        if item is None:
            return {}
        return {key: value for key, value in item.items() if key != "notes"}

    @Property("QVariantList", notify=changed)
    def releaseNoteBlocks(self) -> list[dict[str, Any]]:
        return self._release_blocks

    @Property(str, notify=changed)
    def releaseUrl(self) -> str:
        return self._release_url

    @Property(float, notify=changed)
    def progress(self) -> float:
        return self._progress

    @Property(bool, notify=changed)
    def busy(self) -> bool:
        return self._state in (STATE_CHECKING, STATE_DOWNLOADING, STATE_INSTALLING)

    @Property(bool, notify=changed)
    def canInstall(self) -> bool:
        """已下载好、且当前是打包运行，才允许点「安装」。"""
        return (self._state == STATE_READY
                and bool(getattr(sys, "frozen", False))
                and bool(self._downloaded_version)
                and self._archive_path(self._downloaded_version).is_file())

    @Property(bool, notify=changed)
    def digestVerified(self) -> bool:
        """下载包是否通过 GitHub API 提供的 sha256 校验（未提供值时为 False）。"""
        return self._digest_verified

    @Property(bool, notify=changed)
    def canDownload(self) -> bool:
        item = self._current_release()
        return bool(item and item.get("downloadUrl")) and not self.busy

    @Property(str, notify=changed)
    def channel(self) -> str:
        channel = str(self._config.config["settings"].get("updateChannel", "stable"))
        return channel if channel in ("stable", "prerelease") else "stable"

    @Property(bool, notify=changed)
    def autoCheck(self) -> bool:
        return bool(self._config.config["settings"].get("autoCheckUpdates", True))

    @Property(str, notify=changed)
    def mirror(self) -> str:
        value = str(self._config.config["settings"].get("updateMirror", "github"))
        return value if value in MIRROR_LABELS else "github"

    @Property(bool, notify=changed)
    def mirrorAuto(self) -> bool:
        return bool(self._config.config["settings"].get("updateMirrorAuto", True))

    @Property("QVariantList", notify=changed)
    def mirrorSpeeds(self) -> list[dict[str, Any]]:
        return self._mirror_speeds

    @Property(bool, notify=changed)
    def speedTesting(self) -> bool:
        return self._speed_testing

    @Slot(str)
    def setChannel(self, channel: str) -> None:
        self._config.setUpdateChannel(channel)
        self._reset()
        self.changed.emit()

    @Slot(bool)
    def setAutoCheck(self, enabled: bool) -> None:
        self._config.setAutoCheckUpdates(enabled)
        self.changed.emit()

    @Slot(str)
    def setMirror(self, mirror: str) -> None:
        self._config.setUpdateMirror(mirror)
        self.changed.emit()

    @Slot(bool)
    def setMirrorAuto(self, enabled: bool) -> None:
        self._config.setUpdateMirrorAuto(enabled)
        self.changed.emit()

    def _mirror_url(self, url: str) -> str:
        base = MIRRORS.get(self.mirror)
        return f"{base.rstrip('/')}/{url}" if base else url

    @Slot()
    def testMirrors(self) -> None:
        """并行测速三个下载源；自动模式会切到最快且可用的那个。"""
        if self._speed_testing:
            return
        self._speed_testing = True
        self.changed.emit()
        threading.Thread(target=self._speed_worker, name="rin-mirror-speed",
                         daemon=True).start()

    @staticmethod
    def _measure(url: str) -> int:
        started = time.monotonic()
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=6) as response:
            response.read(4096)
        return int((time.monotonic() - started) * 1000)

    def _speed_worker(self) -> None:
        results: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {
                pool.submit(self._measure, url): name
                for name, url in SPEED_URLS.items()
            }
            for future, name in futures.items():
                try:
                    ms = future.result()
                    results.append({"name": name, "label": MIRROR_LABELS[name],
                                    "ms": ms, "ok": True})
                except Exception:
                    results.append({"name": name, "label": MIRROR_LABELS[name],
                                    "ms": -1, "ok": False})
        order = {name: index for index, name in enumerate(MIRROR_LABELS)}
        results.sort(key=lambda item: order.get(item["name"], 99))
        self._speedReady.emit(results)

    def _apply_speed_results(self, results: list[dict[str, Any]]) -> None:
        self._mirror_speeds = results
        self._speed_testing = False
        best = min((item for item in results if item.get("ok")),
                   key=lambda item: item["ms"], default=None)
        if best is not None and self.mirrorAuto:
            self._config.setUpdateMirror(best["name"])
        self.changed.emit()

    # ------------------------------------------------------------------
    # 检查
    # ------------------------------------------------------------------
    @Slot()
    def checkForUpdates(self) -> None:
        self.check(silent=False)

    @Slot()
    def checkSilently(self) -> None:
        self.check(silent=True)

    def check(self, *, silent: bool = False) -> None:
        if self.busy:
            return
        if silent and not self.autoCheck:
            return
        self._silent = silent
        self._state = STATE_CHECKING
        self._message = "正在检查更新…"
        self.changed.emit()
        self._thread = threading.Thread(
            target=self._check_worker, name="rin-update-check", daemon=True)
        self._thread.start()

    def _api_request(self, url: str, timeout: float = 8.0) -> Any:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/vnd.github+json",
            },
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _api_get(self, path: str) -> Any:
        """先直连；镜像模式下再试一次镜像前缀（是否支持 API 取决于镜像）。"""
        sources = [path]
        if self.mirror != "github":
            sources.append(self._mirror_url(path))
        last_error: Exception | None = None
        for index, url in enumerate(sources):
            try:
                return self._api_request(url, 8.0 if index == 0 else 15.0)
            except Exception as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        return None

    def _check_worker(self) -> None:
        try:
            payload = self._api_get(f"{API_ROOT}?per_page={RELEASE_LIST_LIMIT + 10}")
            items = parse_releases(payload)
            if not items:
                self._safe_emit(self._stateReady, STATE_ERROR,
                                "没有拿到任何 Release，请检查网络或仓库地址")
                return
            self._safe_emit(self._releasesReady, items)
        except urllib.error.HTTPError as exc:
            self._safe_emit(self._stateReady, STATE_ERROR,
                            f"检查更新失败：HTTP {exc.code}")
        except Exception as exc:
            logger.exception("Update check failed")
            self._safe_emit(self._stateReady, STATE_ERROR, f"检查更新失败：{exc}")

    # ------------------------------------------------------------------
    # 版本列表
    # ------------------------------------------------------------------
    def _apply_releases(self, items: list) -> None:
        self._releases = [dict(item) for item in items if isinstance(item, dict)]
        if not self._releases:
            self._state = STATE_ERROR
            self._message = "没有拿到任何 Release"
            self._last_error = self._message
            self.changed.emit()
            return

        self._latest_version = str(self._releases[0].get("version") or "")
        # 默认选中「比当前新的最新一个」；没有更新的就选最新那个（选旧版就是回滚）。
        default_index = next(
            (index for index, item in enumerate(self._releases)
             if version_tuple(str(item.get("version") or ""))
             > version_tuple(APP_VERSION)),
            0,
        )
        self._select(default_index, announce=False)

        # 自动检查只提醒、不下载；通道决定「预发布要不要提醒」。
        candidate = next(
            (item for item in self._releases
             if self.channel == "prerelease" or not item.get("prerelease")),
            None,
        )
        newer = (candidate is not None and version_tuple(
            str(candidate.get("version") or "")) > version_tuple(APP_VERSION))
        if newer:
            self._state = STATE_IDLE
            self._message = f"发现新版本 v{candidate['version']}，选择版本后点「下载」"
            self.notify.emit(
                f"发现新版本 v{candidate['version']}，可在设置 → 更新里下载", "info")
        else:
            self._state = STATE_UP_TO_DATE
            self._message = f"已是最新版本 v{APP_VERSION}"
        self.changed.emit()

    def _select(self, index: int, *, announce: bool = True) -> None:
        if not 0 <= index < len(self._releases):
            return
        self._selected = index
        item = self._releases[index]
        self._release_blocks = parse_release_notes(str(item.get("notes") or ""))
        self._release_url = str(item.get("url") or "")
        if announce and self._state not in (
                STATE_CHECKING, STATE_DOWNLOADING, STATE_INSTALLING):
            self._state = STATE_IDLE
            self._message = f"已选择 v{item.get('version')}，点「下载」开始"
        self.changed.emit()

    def _current_release(self) -> dict[str, Any] | None:
        if 0 <= self._selected < len(self._releases):
            return self._releases[self._selected]
        return None

    @Slot(int)
    def selectRelease(self, index: int) -> None:
        self._select(int(index))

    @Slot()
    def downloadSelected(self) -> None:
        """下载下拉里选中的版本；下载完停在「已下载」，等用户点安装。"""
        if self.busy:
            return
        item = self._current_release()
        if item is None:
            self.notify.emit("版本列表还没加载，先点「检查更新」", "warning")
            return
        version = str(item.get("version") or "")
        url = str(item.get("downloadUrl") or "")
        if not url:
            self.notify.emit(f"v{version} 没有 {ASSET_NAME} 更新包，请到 Release 页面手动下载",
                             "warning")
            return
        if version == APP_VERSION:
            self.notify.emit("这就是当前版本，不用重新下载", "info")
            return
        self._downloadStart.emit(self._mirror_url(url), version, str(item.get("digest") or ""))

    # ------------------------------------------------------------------
    # 下载
    # ------------------------------------------------------------------
    def _apply_download_start(self, download_url: str, version: str, digest: str) -> None:
        self._download_url = download_url
        self._progress = 0.0
        self._last_error = ""
        self._state = STATE_DOWNLOADING
        self._message = f"正在下载 v{version}…"
        self.changed.emit()
        threading.Thread(
            target=self._download_worker, args=(download_url, version, digest),
            name="rin-update-download", daemon=True).start()

    def _apply_state(self, state: str, message: str) -> None:
        self._state = state
        self._message = message
        self.changed.emit()
        if state == STATE_ERROR and not self._silent:
            self.notify.emit(message, "error")

    def _apply_progress(self, progress: float) -> None:
        self._progress = max(0.0, min(1.0, progress))
        self.changed.emit()

    def _download_worker(self, url: str, version: str, digest: str) -> None:
        try:
            target_dir = self._updates_dir()
            target_dir.mkdir(parents=True, exist_ok=True)
            target = self._archive_path(version)
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            digest_hash = hashlib.sha256()
            with urllib.request.urlopen(request, timeout=60) as response, \
                    open(target, "wb") as handle:
                total = int(response.headers.get("Content-Length") or 0)
                read = 0
                while True:
                    if self._stopped:
                        raise RuntimeError("应用正在退出，下载已中止")
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
                    digest_hash.update(chunk)
                    read += len(chunk)
                    if total > 0:
                        self._safe_emit(self._progressReady, read / total)
            verified = False
            if digest.startswith("sha256:"):
                expected = digest.split(":", 1)[1].strip().lower()
                if expected:
                    if digest_hash.hexdigest().lower() != expected:
                        target.unlink(missing_ok=True)
                        self._safe_emit(self._downloadFinished, False,
                                        "更新包校验失败，请重试", False, version)
                        return
                    verified = True
            self._safe_emit(self._downloadFinished, True, str(target), verified, version)
        except Exception as exc:
            logger.exception("Update download failed")
            self._safe_emit(self._downloadFinished, False,
                            f"下载更新失败：{exc}", False, version)

    def _apply_download(self, ok: bool, detail: str, verified: bool,
                        version: str) -> None:
        self._digest_verified = bool(ok and verified)
        if ok:
            self._downloaded_version = version
            self._state = STATE_READY
            suffix = "已校验" if verified else "未提供校验值"
            self._message = f"v{version} 已下载（{suffix}），点「安装」退出并替换"
            self._progress = 1.0
            self.changed.emit()
            self.notify.emit(f"v{version} 已下载，可在更新页安装", "success")
        else:
            self._state = STATE_ERROR
            self._last_error = detail
            self._message = detail
            self.changed.emit()
            self.notify.emit(detail, "error")

    # ------------------------------------------------------------------
    # 安装
    # ------------------------------------------------------------------
    @Slot()
    def installUpdate(self) -> None:
        if not getattr(sys, "frozen", False):
            self.notify.emit("源码模式不支持自动安装更新", "warning")
            return
        if self._state != STATE_READY or not self._downloaded_version:
            return
        archive = self._archive_path(self._downloaded_version)
        if not archive.is_file():
            self._fail("更新包不存在，请重新下载")
            return
        self._install_archive(archive)

    @Slot()
    def installFromFile(self) -> None:
        """高级用法：手动选一个 RinLauncher.zip（不推荐，仅作备份手段）。"""
        if not getattr(sys, "frozen", False):
            self.notify.emit("源码模式不支持安装更新", "warning")
            return
        folder = self._updates_dir()
        folder.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getOpenFileName(
            None, "选择更新包", str(folder), "更新包 (*.zip);;所有文件 (*)")
        if path:
            self._install_archive(Path(path))

    def _install_archive(self, archive: Path) -> None:
        """校验并安装一个 zip；在线下载与「从文件安装」共用这一条路径。"""
        try:
            if not archive.is_file() or archive.stat().st_size == 0:
                self._fail("更新包不存在或为空")
                return
            staging = self._updates_dir() / f"staging-{int(time.time())}"
            with zipfile.ZipFile(archive) as bundle:
                # 防 Zip Slip：所有条目必须落在 staging 目录内。
                root = staging.resolve()
                for member in bundle.infolist():
                    destination = (staging / member.filename).resolve()
                    if root != destination and root not in destination.parents:
                        raise RuntimeError("更新包里包含非法路径")
                bundle.extractall(staging)
            exe = next(staging.rglob("RinLauncher.exe"), None)
            if exe is None:
                self._fail("更新包里没有 RinLauncher.exe")
                return
            payload = exe.parent
            target = Path(sys.executable).resolve().parent
            script = self._updates_dir() / "apply-update.ps1"
            result = self._result_file()
            try:
                result.unlink(missing_ok=True)
            except OSError:
                logger.debug("无法删除旧的安装结果文件", exc_info=True)

            powershell.write_script(script, self._install_script())
            proc = powershell.spawn_hidden(script, [
                "-TargetPid", str(os.getpid()),
                "-Payload", str(payload),
                "-Target", str(target),
                "-Exe", exe.name,
                "-LogFile", str(result),
            ], cwd=target)
            logger.info(
                "Update helper started: pid=%s payload=%s target=%s",
                proc.pid, payload, target)
            self._pending_proc = proc
            self._state = STATE_INSTALLING
            self._message = "正在退出并安装更新…"
            self.changed.emit()
            # 700ms 后再确认辅助进程还活着：脚本立刻退出说明它根本没跑起来
            # （解析失败 / 被策略拦下），这时候绝不能把主程序关掉。
            QTimer.singleShot(700, self._confirm_install_started)
        except Exception as exc:
            logger.exception("Installing update failed")
            self._fail(f"安装更新失败：{exc}")

    def _confirm_install_started(self) -> None:
        proc = self._pending_proc
        self._pending_proc = None
        if proc is None:
            return
        code = proc.poll()
        if code is None:
            logger.info("Update helper is alive; quitting for install")
            QCoreApplication.quit()
            return
        detail = self._result_tail() or f"辅助进程退出码 {code}"
        logger.error("Update helper exited early: %s", detail)
        self._fail(f"更新脚本没能启动（{detail}）。程序未退出，可以打开下载目录手动替换。")

    def _fail(self, message: str) -> None:
        """统一的失败出口：留在程序里、把原因显示在更新页。"""
        self._state = STATE_ERROR
        self._last_error = message
        self._message = message
        self.changed.emit()
        self.notify.emit(message, "error")

    @staticmethod
    def _install_script() -> str:
        """等主进程退出 → 覆盖程序文件 → 重新启动，并把每一步写进结果文件。

        脚本内容必须保持 **ASCII**：它由 ``powershell.write_script`` 以带 BOM 的
        UTF-8 落盘，PowerShell 5.1 能正确解析；但日志与异常信息由系统语言环境
        决定，Python 侧读回来时按 UTF-8 容错解码。
        """
        return "\n".join([
            "param(",
            "  [int]$TargetPid,",
            "  [string]$Payload,",
            "  [string]$Target,",
            "  [string]$Exe,",
            "  [string]$LogFile",
            ")",
            "$ErrorActionPreference = 'Stop'",
            "function Write-Result([string]$Text) {",
            "  try {",
            "    Add-Content -LiteralPath $LogFile -Value $Text -Encoding UTF8",
            "  } catch {",
            "  }",
            "}",
            "try {",
            "  Write-Result 'start'",
            "  try { Wait-Process -Id $TargetPid -Timeout 60 -ErrorAction SilentlyContinue } catch {",
            "  }",
            "  Start-Sleep -Milliseconds 1200",
            "  $payloadExe = Join-Path $Payload $Exe",
            "  if (-not (Test-Path -LiteralPath $payloadExe)) {",
            "    throw 'payload has no RinLauncher.exe'",
            "  }",
            "  # data/ (config, logs, icons) must never be overwritten by the payload.",
            "  $payloadData = Join-Path $Payload 'data'",
            "  if (Test-Path -LiteralPath $payloadData) {",
            "    Remove-Item -LiteralPath $payloadData -Recurse -Force -ErrorAction SilentlyContinue",
            "  }",
            "  $copied = $false",
            "  for ($i = 1; $i -le 10; $i++) {",
            "    try {",
            "      Copy-Item -Path (Join-Path $Payload '*') -Destination $Target -Recurse -Force -ErrorAction Stop",
            "      $copied = $true",
            "      break",
            "    } catch {",
            "      Write-Result ('copy-retry ' + $i + ': ' + $_.Exception.Message)",
            "      Start-Sleep -Milliseconds 800",
            "    }",
            "  }",
            "  if (-not $copied) { throw 'copy failed (files still locked)' }",
            "  $src = Get-Item -LiteralPath $payloadExe",
            "  $dst = Get-Item -LiteralPath (Join-Path $Target $Exe)",
            "  if ($src.Length -ne $dst.Length) {",
            "    throw ('exe size mismatch: ' + $src.Length + ' != ' + $dst.Length)",
            "  }",
            "  Write-Result 'copied'",
            "  Start-Process -FilePath (Join-Path $Target $Exe) -WorkingDirectory $Target",
            "  Write-Result 'started'",
            "  Remove-Item -LiteralPath $Payload -Recurse -Force -ErrorAction SilentlyContinue",
            "  Write-Result 'OK'",
            "} catch {",
            "  Write-Result ('FAIL ' + $_.Exception.Message)",
            "  # On failure relaunch the old build so the user is not left with nothing.",
            "  try {",
            "    Start-Process -FilePath (Join-Path $Target $Exe) -WorkingDirectory $Target",
            "  } catch {",
            "  }",
            "  exit 1",
            "}",
        ])

    # ------------------------------------------------------------------
    # 路径与清理
    # ------------------------------------------------------------------
    def _updates_dir(self) -> Path:
        return self._config.config_dir / "updates"

    def _archive_path(self, version: str) -> Path:
        safe = re.sub(r"[^0-9A-Za-z._-]", "_", str(version or "unknown"))
        return self._updates_dir() / f"RinLauncher-{safe}.zip"

    def _result_file(self) -> Path:
        return self._config.log_dir / "update-apply.txt"

    def _result_tail(self, lines: int = 6) -> str:
        path = self._result_file()
        if not path.is_file():
            return ""
        try:
            text = powershell.read_text(path)
        except OSError:
            logger.debug("读取安装结果失败", exc_info=True)
            return ""
        rows = [row.strip() for row in text.splitlines() if row.strip()]
        return "\n".join(rows[-lines:])

    def _cleanup_legacy(self) -> None:
        """清掉 1.1.8 及以前留下的回滚产物与解包残留。

        ``old.zip`` 那套备份 / 还原已经整体下线（回滚改成「下载一个旧版本」），
        留着只是白占几十 MB。
        """
        removed: list[str] = []
        targets: list[Path] = [self._app_root() / "old.zip"]
        updates = self._updates_dir()
        if updates.is_dir():
            targets.extend(updates.glob("staging-*"))
            targets.extend(updates.glob("rollback-*.zip"))
        for path in targets:
            try:
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                elif path.exists():
                    path.unlink()
                else:
                    continue
                removed.append(path.name)
            except OSError:
                logger.debug("无法清理旧的更新残留 %s", path, exc_info=True)
        if removed:
            logger.info("已清理旧的更新残留：%s", ", ".join(removed))

    @staticmethod
    def _app_root() -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent
        return Path(__file__).resolve().parent.parent

    def _read_last_result(self) -> None:
        """读上一次安装脚本留下的结果：失败原因直接摆到更新页上。"""
        path = self._result_file()
        if not path.is_file():
            return
        try:
            text = powershell.read_text(path)
        except OSError:
            return
        rows = [row.strip() for row in text.splitlines() if row.strip()]
        failure = next((row for row in reversed(rows) if "FAIL" in row), "")
        if failure:
            reason = failure.partition("FAIL")[2].strip() or "安装脚本报告失败"
            self._last_error = f"上次更新失败：{reason}"
            self._message = self._last_error
            self._state = STATE_ERROR
            self._startup_note = f"更新器：{self._last_error}\n{chr(10).join(rows[-6:])}"
        elif rows:
            self._startup_note = f"更新器：上次安装结果 {rows[-1]}"
        # 见过一次就把文件改名归档，避免每次启动都重复提示。
        try:
            suffix = time.strftime("%Y%m%d-%H%M%S")
            path.rename(path.with_name(f"update-apply-{suffix}.txt"))
        except OSError:
            logger.debug("无法归档安装结果文件", exc_info=True)

    @Slot(result=str)
    def takeStartupNote(self) -> str:
        """启动时取走「上次更新」的结论（读一次就清空）。"""
        note = self._startup_note
        self._startup_note = ""
        return note

    @Slot()
    def clearLastError(self) -> None:
        self._last_error = ""
        if self._state == STATE_ERROR:
            self._state = STATE_IDLE
            self._message = "尚未检查更新"
        self.changed.emit()

    @staticmethod
    def _safe_emit(signal: Any, *args: Any) -> None:
        """后台线程发信号：对象已销毁时 Qt 会抛 RuntimeError，这里吞掉。"""
        try:
            signal.emit(*args)
        except RuntimeError:
            logger.debug("Update signal dropped: receiver already deleted")

    @Slot()
    def openReleasePage(self) -> None:
        if self._release_url:
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices

            QDesktopServices.openUrl(QUrl(self._release_url))

    @Slot()
    def openDownloadFolder(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        folder = self._updates_dir()
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _reset(self) -> None:
        self._state = STATE_IDLE
        self._message = "尚未检查更新"
        self._latest_version = ""
        self._releases = []
        self._selected = -1
        self._downloaded_version = ""
        self._release_blocks = []
        self._release_url = ""
        self._download_url = ""
        self._progress = 0.0
        self._digest_verified = False
        self._last_error = ""

    def stop(self) -> None:
        """标记退出：后台下载线程下一轮循环就会自己收手。"""
        self._stopped = True
