"""GitHub Releases 更新检查与安装。

通道：
* 稳定版 —— ``releases/latest``（即 GitHub 上的 Latest）
* 测试版 —— 发布列表里第一个 ``prerelease == true`` 的 Release

更新包固定叫 ``RinLauncher.zip``。下载在后台线程完成；安装时写一个隐藏的
PowerShell 脚本，等主进程退出后解压覆盖安装目录并重新启动。
"""

from __future__ import annotations

import hashlib
import html
import json
import logging
import os
import re
import subprocess
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
    _releaseReady = Signal(str, str, str)
    _downloadStart = Signal(str, str, str)
    _progressReady = Signal(float)
    _downloadFinished = Signal(bool, str)
    _speedReady = Signal(list)

    def __init__(self, config_manager: ConfigManager, parent: QObject | None = None):
        super().__init__(parent)
        self._config = config_manager
        self._state = STATE_IDLE
        self._message = "尚未检查更新"
        self._latest_version = ""
        self._release_blocks: list[dict[str, Any]] = []
        self._release_url = ""
        self._download_url = ""
        self._progress = 0.0
        self._silent = False
        self._thread: threading.Thread | None = None
        self._mirror_speeds: list[dict[str, Any]] = []
        self._speed_testing = False

        self._stateReady.connect(self._apply_state)
        self._releaseReady.connect(self._apply_release)
        self._downloadStart.connect(self._apply_download_start)
        self._progressReady.connect(self._apply_progress)
        self._downloadFinished.connect(self._apply_download)
        self._speedReady.connect(self._apply_speed_results)

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
        return self._latest_version

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
        return self._state == STATE_READY and bool(getattr(sys, "frozen", False))

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
            if self.channel == "prerelease":
                releases = self._api_get(f"{API_ROOT}?per_page=30")
                release = next(
                    (item for item in releases
                     if item.get("prerelease") and not item.get("draft")),
                    None,
                )
                if release is None:
                    self._stateReady.emit(
                        STATE_UP_TO_DATE, "测试通道暂时没有预发布版本")
                    return
            else:
                release = self._api_get(f"{API_ROOT}/latest")

            tag = str(release.get("tag_name") or "")
            latest = tag.lstrip("vV")
            if not tag:
                self._stateReady.emit(STATE_ERROR, "Release 缺少版本号")
                return

            # 不管有没有新版本，都先把 Release 的版本号 / 更新说明 / 页面地址交给界面：
            # 设置页要在「已是最新」时也能看到当前版本的发布说明。
            self._releaseReady.emit(
                latest,
                clean_release_notes(str(release.get("body") or "")),
                str(release.get("html_url") or ""),
            )

            if version_tuple(latest) <= version_tuple(APP_VERSION):
                self._stateReady.emit(
                    STATE_UP_TO_DATE, f"已是最新版本 v{APP_VERSION}")
                return

            assets = release.get("assets") or []
            asset = next(
                (item for item in assets
                 if str(item.get("name") or "").lower() == ASSET_NAME),
                None,
            )
            if asset is None:
                self._stateReady.emit(
                    STATE_ERROR,
                    f"v{latest} 没有找到 {ASSET_NAME} 更新包",
                )
                return

            digest = str(asset.get("digest") or "")
            download_url = str(asset.get("browser_download_url") or "")
            self._downloadStart.emit(
                self._mirror_url(download_url) if download_url else "", latest, digest)
        except urllib.error.HTTPError as exc:
            self._stateReady.emit(STATE_ERROR, f"检查更新失败：HTTP {exc.code}")
        except Exception as exc:
            logger.exception("Update check failed")
            self._stateReady.emit(STATE_ERROR, f"检查更新失败：{exc}")

    # ------------------------------------------------------------------
    # 下载
    # ------------------------------------------------------------------
    def _apply_release(self, latest: str, notes: str, release_url: str) -> None:
        """Release 元数据：版本号、更新说明、页面地址。不触发下载。"""
        self._latest_version = latest
        self._release_blocks = parse_release_notes(notes)
        self._release_url = release_url
        self.changed.emit()

    def _apply_download_start(self, download_url: str, latest: str, digest: str) -> None:
        self._download_url = download_url
        self._progress = 0.0
        self._state = STATE_DOWNLOADING
        self._message = f"正在下载 v{latest}…"
        self.changed.emit()
        self.notify.emit(f"发现新版本 v{latest}，正在下载…", "info")
        threading.Thread(
            target=self._download_worker, args=(download_url, latest, digest),
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

    def _download_worker(self, url: str, latest: str, digest: str) -> None:
        target_dir = self._config.config_dir / "updates"
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / f"RinLauncher-{latest}.zip"
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            digest_hash = hashlib.sha256()
            with urllib.request.urlopen(request, timeout=60) as response, \
                    open(target, "wb") as handle:
                total = int(response.headers.get("Content-Length") or 0)
                read = 0
                while True:
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
                    digest_hash.update(chunk)
                    read += len(chunk)
                    if total > 0:
                        self._progressReady.emit(read / total)
            if digest.startswith("sha256:"):
                expected = digest.split(":", 1)[1].strip().lower()
                if expected and digest_hash.hexdigest().lower() != expected:
                    target.unlink(missing_ok=True)
                    self._downloadFinished.emit(False, "更新包校验失败，请重试")
                    return
            self._downloadFinished.emit(True, str(target))
        except Exception as exc:
            logger.exception("Update download failed")
            self._downloadFinished.emit(False, f"下载更新失败：{exc}")

    def _apply_download(self, ok: bool, detail: str) -> None:
        if ok:
            self._state = STATE_READY
            self._message = f"v{self._latest_version} 已下载，点击安装并重启"
            self._progress = 1.0
            self.changed.emit()
            self.notify.emit(
                f"新版本 v{self._latest_version} 已下载，可在设置里安装", "success")
        else:
            self._state = STATE_ERROR
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
        if self._state != STATE_READY:
            return
        archive = self._config.config_dir / "updates" / f"RinLauncher-{self._latest_version}.zip"
        if not archive.is_file():
            self.notify.emit("更新包不存在，请重新检查更新", "error")
            return
        self._install_archive(archive)

    @Slot()
    def installFromFile(self) -> None:
        """离线更新：用户自己下载的 RinLauncher.zip。"""
        if not getattr(sys, "frozen", False):
            self.notify.emit("源码模式不支持安装更新", "warning")
            return
        folder = self._config.config_dir / "updates"
        folder.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getOpenFileName(
            None, "选择更新包", str(folder), "更新包 (*.zip);;所有文件 (*)")
        if path:
            self._install_archive(Path(path))

    def _install_archive(self, archive: Path) -> None:
        """校验并安装一个 zip；在线下载与离线选择共用这一条路径。"""
        try:
            if not archive.is_file() or archive.stat().st_size == 0:
                self.notify.emit("更新包不存在或为空", "error")
                return
            staging = self._config.config_dir / "updates" / f"staging-{int(time.time())}"
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
                self.notify.emit("更新包里没有 RinLauncher.exe", "error")
                return
            payload = exe.parent
            target = Path(sys.executable).resolve().parent
            script = self._config.config_dir / "updates" / "apply-update.ps1"
            script.write_text(self._install_script(), encoding="utf-8-sig")
            subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-WindowStyle", "Hidden", "-File", str(script),
                 "-TargetPid", str(os.getpid()),
                 "-Payload", str(payload),
                 "-Target", str(target),
                 "-Exe", exe.name],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            self._state = STATE_INSTALLING
            self._message = "正在退出并安装更新…"
            self.changed.emit()
            QTimer.singleShot(250, QCoreApplication.quit)
        except Exception as exc:
            logger.exception("Installing update failed")
            self.notify.emit(f"安装更新失败：{exc}", "error")

    @staticmethod
    def _install_script() -> str:
        return "\n".join([
            "param(",
            "  [int]$TargetPid,",
            "  [string]$Payload,",
            "  [string]$Target,",
            "  [string]$Exe",
            ")",
            "try { Wait-Process -Id $TargetPid -Timeout 60 -ErrorAction SilentlyContinue } catch {}",
            "Start-Sleep -Milliseconds 1200",
            "# 数据目录（配置、日志、图标）永远保留，不跟随更新包覆盖。",
            "$data = Join-Path $Payload 'data'",
            "if (Test-Path -LiteralPath $data) {",
            "  Remove-Item -LiteralPath $data -Recurse -Force -ErrorAction SilentlyContinue",
            "}",
            "Copy-Item -Path (Join-Path $Payload '*') -Destination $Target -Recurse -Force",
            "Start-Process -FilePath (Join-Path $Target $Exe)",
            "Remove-Item -LiteralPath $Payload -Recurse -Force -ErrorAction SilentlyContinue",
        ])

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

        folder = self._config.config_dir / "updates"
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _reset(self) -> None:
        self._state = STATE_IDLE
        self._message = "尚未检查更新"
        self._latest_version = ""
        self._release_blocks = []
        self._release_url = ""
        self._download_url = ""
        self._progress = 0.0

    def stop(self) -> None:
        """占位：线程都是 daemon，退出时不需要额外等待。"""
