"""更新器与备份：版本解析、安装脚本保留数据、自动备份保留策略。"""

from __future__ import annotations

import tempfile
from pathlib import Path

import rin_launcher.config_manager as cm
from rin_launcher.updater import (
    UpdateManager,
    clean_release_notes,
    parse_release_notes,
    version_tuple,
)


def test_version_tuple_handles_tags():
    assert version_tuple("v1.2.3") == (1, 2, 3)
    assert version_tuple("1.2.3-beta.1") == (1, 2, 3, 1)
    assert version_tuple("v2") == (2,)
    assert version_tuple("") == (0,)


def test_release_notes_are_sanitized_for_markdown():
    body = "<!-- generated -->\n## 更新\n- 修复<br>问题\n"
    notes = clean_release_notes(body)
    assert "<!--" not in notes
    assert "<br>" not in notes
    assert notes.startswith("## 更新")
    assert "修复\n问题" in notes
    assert clean_release_notes(None) == ""


def test_parse_release_notes_builds_blocks():
    body = "\n".join([
        "# v1.1.0 更新说明",
        "",
        "正文里有 **加粗**、`code` 和 [链接](https://example.com)。",
        "",
        "## 新增",
        "- 第一项",
        "- 第二项",
        "",
        "1. 有序一",
        "2. 有序二",
        "",
        "> 引用",
        "",
        "```powershell",
        "RinLauncher.exe --version",
        "```",
        "",
        "---",
    ])
    blocks = parse_release_notes(body)
    assert [block["kind"] for block in blocks] == [
        "heading", "paragraph", "heading", "bullet", "bullet",
        "ordered", "ordered", "quote", "code", "rule",
    ]
    assert blocks[0]["level"] == 1
    assert blocks[2]["level"] == 2
    assert "<b>加粗</b>" in blocks[1]["html"]
    assert "<code>code</code>" in blocks[1]["html"]
    assert '<a href="https://example.com">链接</a>' in blocks[1]["html"]
    assert blocks[5]["html"].startswith("1. ")
    assert "RinLauncher.exe --version" in blocks[8]["html"]


def test_parse_release_notes_escapes_html():
    blocks = parse_release_notes("<script>alert(1)</script> & co")
    assert "<script>" not in blocks[0]["html"]
    assert "&lt;script&gt;" in blocks[0]["html"]


def test_parse_release_notes_handles_empty_body():
    assert parse_release_notes("") == []


def test_install_script_preserves_data():
    script = UpdateManager._install_script()
    assert "data" in script
    assert "Copy-Item" in script
    assert "Start-Process" in script


def test_auto_backups_keep_latest_eight_and_manual_is_kept(qapp):
    with tempfile.TemporaryDirectory() as raw:
        manager = cm.ConfigManager(config_dir=Path(raw))
        for _ in range(10):
            manager._create_backup(manual=False, silent=True)
        manager._create_backup(manual=True, silent=True)

        info = manager.getBackupInfo()
        assert info["autoCount"] == cm.AUTO_BACKUP_KEEP
        assert info["manualCount"] == 1
        assert info["autoKeep"] == 8
