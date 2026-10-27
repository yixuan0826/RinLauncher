"""按天切分的日志文件，以及把最近日志打包导出。

日志落在 ``<数据目录>/logs/log-<年月日>.txt``（例如 ``log-261026.txt``），
超过 ``KEEP_DAYS`` 天的文件在启动、跨天切文件时清掉。导出会把最近 N 天的
日志压成一个 zip 放在数据目录下，用户拖走一个文件就能发反馈。
"""

from __future__ import annotations

import logging
import sys
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

LOG_DIR_NAME = "logs"
KEEP_DAYS = 30
FILE_GLOB = "log-*.txt"
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def log_dir(config_dir: Path | str) -> Path:
    """数据目录下的 logs 文件夹。"""
    return Path(config_dir) / LOG_DIR_NAME


def file_for(directory: Path | str, day: date | None = None) -> Path:
    """某一天的日志文件路径（默认今天）。"""
    day = day or date.today()
    return Path(directory) / f"log-{day:%y%m%d}.txt"


def _parse_day(path: Path) -> date | None:
    """从 ``log-261026.txt`` 里读回日期；不是这个命名就返回 None。"""
    stem = path.stem
    if not stem.startswith("log-") or len(stem) != 10:
        return None
    try:
        return datetime.strptime(stem[4:], "%y%m%d").date()
    except ValueError:
        return None


def cleanup(directory: Path | str, keep_days: int = KEEP_DAYS) -> int:
    """删除超过保留期的日志文件，返回删除数量。"""
    directory = Path(directory)
    if not directory.is_dir():
        return 0
    cutoff = date.today() - timedelta(days=max(1, int(keep_days)))
    removed = 0
    for path in directory.glob(FILE_GLOB):
        day = _parse_day(path)
        if day is None or day >= cutoff:
            continue
        try:
            path.unlink()
            removed += 1
        except OSError:
            logging.getLogger(__name__).debug("无法删除旧日志 %s", path, exc_info=True)
    return removed


class DailyFileHandler(logging.Handler):
    """按日期写文件；日期一变就换到新文件，并顺手清理过期日志。"""

    def __init__(self, directory: Path | str, keep_days: int = KEEP_DAYS):
        super().__init__()
        self.directory = Path(directory)
        self.keep_days = keep_days
        self._stream = None
        self._day: date | None = None

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._ensure_stream()
            if self._stream is not None:
                self._stream.write(self.format(record) + "\n")
                self._stream.flush()
        except Exception:  # pragma: no cover - 日志失败不能带走程序
            self.handleError(record)

    def _ensure_stream(self) -> None:
        today = date.today()
        if self._stream is not None and self._day == today:
            return
        self._close_stream()
        self.directory.mkdir(parents=True, exist_ok=True)
        self._stream = open(file_for(self.directory, today), "a", encoding="utf-8")
        self._day = today
        cleanup(self.directory, self.keep_days)

    def _close_stream(self) -> None:
        if self._stream is not None:
            try:
                self._stream.close()
            finally:
                self._stream = None

    def close(self) -> None:
        self._close_stream()
        super().close()


def setup(config_dir: Path | str, level: str = "INFO", *, console: bool = True) -> Path:
    """初始化根 logger，返回今天的日志文件路径。"""
    directory = log_dir(config_dir)
    directory.mkdir(parents=True, exist_ok=True)
    file_handler = DailyFileHandler(directory)
    formatter = logging.Formatter(LOG_FORMAT)
    file_handler.setFormatter(formatter)

    handlers: list[logging.Handler] = [file_handler]
    if console and sys.stdout is not None:
        stream = logging.StreamHandler()
        stream.setFormatter(formatter)
        handlers.append(stream)

    logging.basicConfig(
        level=getattr(logging, str(level).upper(), logging.INFO),
        handlers=handlers,
        force=True,
    )
    return file_for(directory)


def collect(config_dir: Path | str, days: int = KEEP_DAYS) -> list[Path]:
    """最近 ``days`` 天内的日志文件（按名称排序）。"""
    directory = log_dir(config_dir)
    if not directory.is_dir():
        return []
    cutoff = date.today() - timedelta(days=max(1, int(days)))
    files: list[Path] = []
    for path in sorted(directory.glob(FILE_GLOB)):
        day = _parse_day(path)
        if day is None or day >= cutoff:
            files.append(path)
    return files


def export(config_dir: Path | str, days: int = KEEP_DAYS) -> Path | None:
    """把最近 ``days`` 天的日志压成 zip；没有日志时返回 None。"""
    files = collect(config_dir, days)
    if not files:
        return None
    target = Path(config_dir) / f"RinLauncher-logs-{datetime.now():%y%m%d-%H%M%S}.zip"
    try:
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in files:
                archive.write(path, arcname=path.name)
    except OSError:
        logging.getLogger(__name__).exception("导出日志失败: %s", target)
        return None
    return target
