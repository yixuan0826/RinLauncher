"""配置备份的纯文件操作。

原来的实现散在 ``ConfigManager`` 里：轮转、创建、列举、清理各占一段，还和
``self._config`` / 信号 / toast 缠在一起。这里只负责「文件系统上的备份」，
返回值是路径或数据；是否弹提示、发哪个信号仍然由调用方决定。
"""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 自动备份 7 天一次，保留最近 8 份；手动备份不自动删。
AUTO_INTERVAL_DAYS = 7
AUTO_KEEP = 8
AUTO_PREFIX = "config-auto-"
MANUAL_PREFIX = "config-manual-"
ALL_PREFIX = "config-"


def files(backup_dir: Path, prefix: str) -> list[Path]:
    """按修改时间升序返回某类备份（最新的一份在最后）。"""
    try:
        matched = list(backup_dir.glob(f"{prefix}*.yaml"))
    except OSError:
        return []
    entries: list[tuple[float, Path]] = []
    for path in matched:
        try:
            entries.append((path.stat().st_mtime, path))
        except OSError:
            continue
    entries.sort(key=lambda item: item[0])
    return [path for _stamp, path in entries]


def rotate(backup_dir: Path, config_file: Path, keep: int = 10) -> None:
    """写盘前留一份 ``config.yaml.bak.<时间戳>``，只保留最近 *keep* 份。"""
    try:
        shutil.copy2(config_file, backup_dir / f"config.yaml.bak.{int(time.time())}")
    except OSError:
        logger.exception("Failed to rotate config backups in %s", backup_dir)
        return
    for stale in sorted(backup_dir.glob("config.yaml.bak.*"))[:-keep]:
        stale.unlink(missing_ok=True)


def create(backup_dir: Path, config_file: Path, *, manual: bool) -> Path | None:
    """复制一份备份，返回新文件路径；源文件不存在或写失败时返回 None。"""
    if not config_file.is_file():
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S")
    prefix = MANUAL_PREFIX if manual else AUTO_PREFIX
    target = backup_dir / f"{prefix}{stamp}.yaml"
    suffix = 1
    while target.exists():
        target = backup_dir / f"{prefix}{stamp}-{suffix}.yaml"
        suffix += 1
    try:
        # 不要用 copy2：它会保留源文件的 mtime，7 天自动备份的判断会失真。
        shutil.copyfile(config_file, target)
    except OSError:
        logger.exception("Failed to create backup %s", target)
        return None
    return target


def prune_auto(backup_dir: Path, keep: int) -> None:
    """自动备份只保留最近 *keep* 份；手动备份不动。"""
    for stale in files(backup_dir, AUTO_PREFIX)[:-max(1, keep)]:
        stale.unlink(missing_ok=True)


def describe(backup_dir: Path) -> dict[str, Any]:
    """自动 / 手动两类备份的数量与最新一份的时间、文件名。"""
    auto = files(backup_dir, AUTO_PREFIX)
    manual = files(backup_dir, MANUAL_PREFIX)

    def latest(paths: list[Path]) -> tuple[str, str]:
        if not paths:
            return "", ""
        path = paths[-1]
        try:
            stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(path.stat().st_mtime))
        except OSError:
            stamp = ""
        return stamp, path.name

    auto_time, auto_name = latest(auto)
    manual_time, manual_name = latest(manual)
    return {
        "autoCount": len(auto),
        "manualCount": len(manual),
        "autoTime": auto_time,
        "manualTime": manual_time,
        "autoName": auto_name,
        "manualName": manual_name,
    }


def list_entries(backup_dir: Path) -> list[dict[str, Any]]:
    """最近的备份（手动 + 自动），按时间倒序，供设置页与恢复窗口列表用。"""
    entries: list[dict[str, Any]] = []
    for path in files(backup_dir, ALL_PREFIX):
        try:
            stat = path.stat()
        except OSError:
            continue
        entries.append({
            "name": path.name,
            "manual": path.name.startswith(MANUAL_PREFIX),
            "size": stat.st_size,
            "mtime": stat.st_mtime,
            "time": time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime)),
        })
    entries.sort(key=lambda item: item["mtime"], reverse=True)
    return entries


def clear(backup_dir: Path) -> int:
    """删除全部配置备份，返回删掉了几份。"""
    removed = 0
    for path in files(backup_dir, ALL_PREFIX):
        try:
            path.unlink()
            removed += 1
        except OSError:
            logger.debug("无法删除备份 %s", path, exc_info=True)
    return removed


def newest_age_seconds(backup_dir: Path) -> float | None:
    """最新一份自动备份距今多少秒；没有自动备份时返回 None。"""
    auto = files(backup_dir, AUTO_PREFIX)
    if not auto:
        return None
    try:
        return time.time() - auto[-1].stat().st_mtime
    except OSError:
        return None
