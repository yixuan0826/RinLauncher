"""按天日志与导出归档。"""

from __future__ import annotations

import zipfile
from datetime import date, timedelta

from rin_launcher import logging_setup


def test_file_name_uses_short_date(tmp_path):
    path = logging_setup.file_for(tmp_path, date(2026, 10, 26))
    assert path.name == "log-261026.txt"


def test_export_bundles_recent_logs_only(tmp_path):
    directory = logging_setup.log_dir(tmp_path)
    directory.mkdir()
    today = logging_setup.file_for(directory, date.today())
    today.write_text("today", encoding="utf-8")
    stale = logging_setup.file_for(directory, date.today() - timedelta(days=60))
    stale.write_text("stale", encoding="utf-8")

    target = logging_setup.export(tmp_path, days=30)

    assert target is not None and target.is_file()
    with zipfile.ZipFile(target) as archive:
        names = archive.namelist()
    assert today.name in names
    assert stale.name not in names


def test_cleanup_removes_expired_logs(tmp_path):
    directory = logging_setup.log_dir(tmp_path)
    directory.mkdir()
    keep = logging_setup.file_for(directory, date.today())
    keep.write_text("keep", encoding="utf-8")
    stale = logging_setup.file_for(directory, date.today() - timedelta(days=31))
    stale.write_text("stale", encoding="utf-8")

    removed = logging_setup.cleanup(directory, keep_days=30)

    assert removed == 1
    assert keep.exists()
    assert not stale.exists()


def test_export_without_logs_returns_none(tmp_path):
    assert logging_setup.export(tmp_path) is None
