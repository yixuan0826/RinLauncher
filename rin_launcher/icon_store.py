"""图标库：导入图片、从程序/快捷方式里抽图标、列出已装图标。

这部分原来内联在 ``ConfigManager`` 里（约 180 行），只和文件、Qt 图标提供器
打交道，和配置读写没有关系。抽成独立类之后 ``ConfigManager`` 只保留 QML
入口，图标相关的异常与落盘逻辑集中在这里。
"""

from __future__ import annotations

import logging
import shutil
import uuid
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QFileInfo
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QFileDialog, QFileIconProvider

from rin_launcher import start_menu
from rin_launcher.drives import human_size

logger = logging.getLogger(__name__)

# 这些后缀是「图片」，走导入；其余（exe/dll/lnk…）走系统图标提取。
IMAGE_ICON_SUFFIXES: tuple[str, ...] = (".svg", ".png", ".ico", ".jpg", ".jpeg", ".bmp")


def icon_key(path: Path) -> str:
    """图标在配置里的写法：``file:<绝对路径>``。"""
    return f"file:{path}"


class IconStore:
    """一个落盘目录 + 一个可选的提示回调，负责所有图标文件操作。"""

    def __init__(
        self,
        icon_dir: Path,
        bundled_dir: Path,
        notify: Callable[[str, str], None] | None = None,
    ):
        self.icon_dir = Path(icon_dir)
        self.bundled_dir = Path(bundled_dir)
        self._notify = notify
        self._provider = QFileIconProvider()

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------
    def bundled(self) -> list[str]:
        """随包附带的 Lawnicons 名称（不带扩展名）。"""
        if not self.bundled_dir.is_dir():
            return []
        return sorted(path.stem for path in self.bundled_dir.glob("*.svg"))

    def custom(self) -> list[dict]:
        """用户自己的图标库：导入的位图/矢量 + 从程序里抽出来的。"""
        if not self.icon_dir.is_dir():
            return []
        items = []
        for path in sorted(self.icon_dir.iterdir(),
                           key=lambda item: item.stat().st_mtime, reverse=True):
            if path.suffix.lower() not in IMAGE_ICON_SUFFIXES:
                continue
            items.append({
                "name": path.stem,
                "key": icon_key(path),
                "size": human_size(path.stat().st_size),
            })
        return items

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------
    def _toast(self, message: str, severity: str) -> None:
        if self._notify is not None:
            self._notify(message, severity)

    def import_file(self, path: str, notify: bool = True) -> str:
        """把一张图片（svg / png / ico / …）复制进图标库，返回它的 icon key。"""
        source = Path(path)
        if not source.is_file():
            return ""
        target = self.icon_dir / f"{uuid.uuid4().hex[:8]}{source.suffix.lower()}"
        try:
            shutil.copy2(source, target)
        except OSError:
            logger.exception("Failed to copy icon %s", source)
            if notify:
                self._toast("图标复制失败", "error")
            return ""
        if notify:
            self._toast(f"已添加图标：{source.name}", "success")
        return icon_key(target)

    @staticmethod
    def shortcut_target(path: str | Path) -> Path | None:
        """快捷方式（.lnk）指向的目标；不是快捷方式或解析不出来时返回 None。"""
        source = Path(path)
        if source.suffix.lower() != ".lnk":
            return None
        target = QFileInfo(str(source)).symLinkTarget()
        if not target:
            return None
        candidate = Path(target)
        return candidate if candidate.exists() else None

    def from_path(self, source: Path, notify: bool) -> str:
        """从一个具体文件取图标；取不到返回空串。"""
        if not source.is_file():
            return ""
        suffix = source.suffix.lower()
        if suffix in IMAGE_ICON_SUFFIXES:
            if suffix != ".ico":
                return self.import_file(str(source), notify=notify)
            # .ico 可能是多尺寸的：转成 256 的 PNG 再入库，小窗放大时不糊。
            icon = QIcon(str(source))
            pixmap = icon.pixmap(256, 256) if not icon.isNull() else None
            if pixmap is None or pixmap.isNull():
                return ""
            target = self.icon_dir / f"{uuid.uuid4().hex[:8]}.png"
            return icon_key(target) if pixmap.save(str(target), "PNG") else ""

        icon = self._provider.icon(QFileInfo(str(source)))
        if icon.isNull():
            return ""
        # 取最大的一档，通常在 32~256 之间。
        pixmap = icon.pixmap(256, 256)
        if pixmap.isNull():
            return ""
        target = self.icon_dir / f"{uuid.uuid4().hex[:8]}.png"
        if not pixmap.save(str(target), "PNG"):
            return ""
        return icon_key(target)

    def extract(self, path: str, notify: bool = True) -> str:
        """从程序 / 快捷方式 / DLL 里抽出图标，落成文件存进图标库。

        快捷方式按「自己的 IconLocation → 快捷方式本身 → 目标」的顺序找：
        WSA 安卓应用的正确图标只在 IconLocation 里（LocalState 下的 .ico），
        直接跟随目标只会拿到 WsaClient.exe 的通用图标。普通程序没有
        IconLocation 时再退回目标，行为与旧版一致。

        ``notify=False`` 用于保存槽位时的自动补图标：静默失败，不打扰用户。
        """
        # 没有 QApplication（裸脚本／无 GUI 环境）时 QFileIconProvider 会直接
        # 把进程干掉（原生访问冲突，Python 捕不住），先挡一道。
        if QApplication.instance() is None:
            logger.warning("No QApplication instance, skipping icon extraction")
            return ""
        source = Path(path)
        candidates: list[Path] = []
        if source.suffix.lower() == ".lnk":
            icon_path = start_menu.shortcut_icon_path(source)
            if icon_path:
                candidates.append(Path(icon_path))
            # 快捷方式自身的 shell 图标；IconLocation 读不到时的兜底。
            candidates.append(source)
            target = self.shortcut_target(source)
            if target is not None:
                candidates.append(target)
        else:
            candidates.append(source)

        for candidate in candidates:
            key = self.from_path(candidate, notify)
            if key:
                if notify:
                    self._toast(f"已提取图标：{candidate.name}", "success")
                return key
        if notify:
            self._toast("这个文件里没有取到图标", "warning")
        return ""

    def acquire(self, path: str) -> str:
        """「从文件获取图标」的统一入口：程序走提取，图片走导入。"""
        if not path:
            path = self.pick_source()
        if not path:
            return ""
        if Path(path).suffix.lower() in IMAGE_ICON_SUFFIXES:
            return self.import_file(path)
        return self.extract(path)

    @staticmethod
    def pick_source() -> str:
        """挑一个「图标来源」文件：程序、快捷方式或图片都行。"""
        path, _ = QFileDialog.getOpenFileName(
            None, "选择程序、快捷方式或图片", str(Path.home()),
            "程序与图标 (*.exe *.dll *.lnk *.ico *.svg *.png *.jpg *.jpeg *.bmp)"
            ";;程序与库 (*.exe *.dll *.lnk)"
            ";;图标图片 (*.ico *.svg *.png *.jpg *.jpeg *.bmp)"
            ";;所有文件 (*)")
        return path or ""

    @staticmethod
    def pick_image() -> str:
        path, _ = QFileDialog.getOpenFileName(
            None, "添加图标", str(Path.home()),
            "图标 (*.svg *.png *.ico *.jpg *.jpeg *.bmp);;所有文件 (*)")
        return path or ""

    def delete(self, key: str) -> bool:
        """删掉图标库里的一张图；配置里还在引用它的地方会退回默认图标。"""
        target = Path(key.removeprefix("file:"))
        # 只允许删图标库里的东西，免得被误导着删掉别处的文件。
        if target.parent.resolve() != self.icon_dir.resolve() or not target.is_file():
            return False
        try:
            target.unlink()
        except OSError:
            logger.exception("Failed to delete icon %s", target)
            return False
        self._toast("图标已删除", "success")
        return True
