"""更新器与备份：版本解析、安装脚本、Release 列表与自动备份策略。"""

from __future__ import annotations

import ast
import codecs
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

import rin_launcher.config_manager as cm
from rin_launcher import __version__, powershell
from rin_launcher.updater import (
    UpdateManager,
    clean_release_notes,
    parse_release_notes,
    parse_releases,
    release_label,
    version_tuple,
)

ROOT = Path(__file__).resolve().parent.parent


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
    # 回滚机制已下线：脚本不再打包 old.zip。
    assert "old.zip" not in script
    assert "Compress-Archive" not in script
    script.encode("ascii")  # 脚本内容保持 ASCII，避开 PowerShell 的编码坑


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


def test_mirror_url_and_auto_selection(qapp, tmp_path):
    manager = cm.ConfigManager(config_dir=tmp_path)
    updater = UpdateManager(manager)
    try:
        updater.setMirror("ghfast")
        assert updater._mirror_url("https://github.com/a/b") == (
            "https://ghfast.top/https://github.com/a/b")
        updater.setMirror("github")
        assert updater._mirror_url("https://github.com/a/b") == "https://github.com/a/b"

        updater._apply_speed_results([
            {"name": "github", "label": "GitHub", "ms": 300, "ok": True},
            {"name": "ghfast", "label": "ghfast", "ms": 100, "ok": True},
            {"name": "ghproxy", "label": "ghproxy", "ms": -1, "ok": False},
        ])
        assert manager.getSettings()["updateMirror"] == "ghfast"
        assert updater.mirror == "ghfast"
    finally:
        manager.stopWatching()


def test_install_archive_rejects_zip_slip(qapp, tmp_path):
    import zipfile

    manager = cm.ConfigManager(config_dir=tmp_path)
    updater = UpdateManager(manager)
    errors: list[str] = []
    updater.notify.connect(lambda message, _severity: errors.append(message))
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("../evil.exe", "x")
    try:
        updater._install_archive(archive)
    finally:
        manager.stopWatching()
    assert any("非法路径" in message for message in errors), errors


# ----------------------------------------------------------------------
# Release 列表
# ----------------------------------------------------------------------
def _release_payload() -> list[dict]:
    return [
        {
            "tag_name": "v1.1.8-pre",
            "name": "1.1.8-pre",
            "prerelease": True,
            "published_at": "2026-10-27T12:36:00Z",
            "html_url": "https://example.com/1.1.8-pre",
            "body": "## 1.1.8-pre\n\n- 修复",
            "assets": [{
                "name": "RinLauncher.zip",
                "browser_download_url": "https://example.com/a.zip",
                "digest": "sha256:abc",
            }],
        },
        {
            "tag_name": "v1.1.7-pre",
            "name": "1.1.7-pre",
            "prerelease": True,
            "published_at": "2026-10-27T01:00:00Z",
            "html_url": "https://example.com/1.1.7-pre",
            "assets": [],
        },
        {"tag_name": "v1.1.9", "draft": True, "assets": []},
        {"tag_name": ""},
        "not-a-dict",
    ]


def test_parse_releases_skips_drafts_and_sorts_newest_first():
    items = parse_releases(_release_payload())
    assert [item["version"] for item in items] == ["1.1.8-pre", "1.1.7-pre"]
    first = items[0]
    assert first["downloadUrl"] == "https://example.com/a.zip"
    assert first["digest"] == "sha256:abc"
    assert first["prerelease"] is True
    assert first["published"] == "2026-10-27"
    assert first["current"] is False
    # 没有更新包的版本也要保留：界面会标出来，引导用户去 Release 页手动下载。
    assert items[1]["downloadUrl"] == ""


def test_parse_releases_marks_current_version():
    payload = [{"tag_name": f"v{__version__}", "assets": [], "published_at": "2026-10-28"}]
    assert parse_releases(payload)[0]["current"] is True


def test_parse_releases_tolerates_garbage_and_limit():
    assert parse_releases(None) == []
    assert parse_releases({"message": "Not Found"}) == []
    many = [{"tag_name": f"v1.0.{index}"} for index in range(50)]
    assert len(parse_releases(many, limit=5)) == 5


def test_release_label_marks_current_and_missing_asset():
    label = release_label({"version": "1.1.8-pre", "current": True, "prerelease": True,
                           "published": "2026-10-27", "downloadUrl": ""})
    assert "v1.1.8-pre" in label
    assert "当前" in label
    assert "预发布" in label
    assert "无更新包" in label


def test_selecting_release_updates_notes_and_url(qapp, tmp_path):
    manager = cm.ConfigManager(config_dir=tmp_path)
    updater = UpdateManager(manager)
    try:
        updater._apply_releases(parse_releases(_release_payload()))
        assert updater.selectedIndex == 0
        assert updater.selectedRelease["version"] == "1.1.8-pre"
        assert updater.releaseUrl.endswith("1.1.8-pre")

        updater.selectRelease(1)
        assert updater.selectedIndex == 1
        assert updater.selectedRelease["version"] == "1.1.7-pre"
        assert updater.releaseUrl.endswith("1.1.7-pre")
        # 选中的版本没有更新包，就不该允许下载
        assert updater.canDownload is False
    finally:
        manager.stopWatching()


# ----------------------------------------------------------------------
# 脚本落盘（1.1.6~1.1.8 的崩溃点）
# ----------------------------------------------------------------------
def test_write_script_does_not_use_dynamic_codec(tmp_path):
    path = tmp_path / "apply.ps1"
    powershell.write_script(path, "Write-Host '中文'\n")
    assert path.read_bytes().startswith(codecs.BOM_UTF8)
    assert powershell.read_text(path) == "Write-Host '中文'\n"


def test_no_utf8_sig_encoding_anywhere_in_package():
    """utf-8-sig 在冻结包里会抛 LookupError —— 源代码里不许再出现。"""
    offenders: list[str] = []
    for path in (ROOT / "rin_launcher").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if (keyword.arg == "encoding"
                        and isinstance(keyword.value, ast.Constant)
                        and keyword.value.value == "utf-8-sig"):
                    offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == [], offenders


def test_old_zip_api_is_gone():
    assert not hasattr(UpdateManager, "rollbackUpdate")
    assert not hasattr(UpdateManager, "canRollback")
    assert not hasattr(cm.ConfigManager, "deleteOldVersion")


# ----------------------------------------------------------------------
# 真实安装脚本（只在 Windows 上跑）
# ----------------------------------------------------------------------
@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell 安装脚本只在 Windows 可用")
def test_install_script_replaces_files_and_reports_ok(tmp_path):
    target = tmp_path / "target"
    payload = tmp_path / "payload"
    logs = tmp_path / "logs"
    target.mkdir()
    payload.mkdir()
    logs.mkdir()

    # 旧版本
    (target / "RinLauncher.cmd").write_text("@echo old> marker.txt\r\n", encoding="ascii")
    (target / "keep.txt").write_text("old", encoding="ascii")
    (target / "data").mkdir()
    (target / "data" / "config.yaml").write_text("keep-me", encoding="ascii")
    # 新版本（payload 里的 data 不能被拷过去）
    (payload / "RinLauncher.cmd").write_text("@echo new> marker.txt\r\n", encoding="ascii")
    (payload / "keep.txt").write_text("new", encoding="ascii")
    (payload / "extra.txt").write_text("extra", encoding="ascii")
    (payload / "data").mkdir()
    (payload / "data" / "config.yaml").write_text("should-not-copy", encoding="ascii")

    result = logs / "update-apply.txt"
    script = powershell.write_script(tmp_path / "apply-update.ps1",
                                     UpdateManager._install_script())
    fake_pid = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.2)"])
    try:
        proc = powershell.spawn_hidden(script, [
            "-TargetPid", str(fake_pid.pid),
            "-Payload", str(payload),
            "-Target", str(target),
            "-Exe", "RinLauncher.cmd",
            "-LogFile", str(result),
        ])
        assert proc.wait(timeout=90) == 0
    finally:
        fake_pid.wait(timeout=30)

    assert (target / "extra.txt").read_text(encoding="ascii") == "extra"
    assert (target / "keep.txt").read_text(encoding="ascii") == "new"
    # 数据目录永远不跟随更新包覆盖
    assert (target / "data" / "config.yaml").read_text(encoding="ascii") == "keep-me"
    # 不再生成 old.zip
    assert not (target / "old.zip").exists()

    text = powershell.read_text(result)
    assert "copied" in text
    assert "OK" in text

    # 新程序被拉起来了（.cmd 会在工作目录里写 marker.txt）
    marker = target / "marker.txt"
    for _ in range(100):
        if marker.exists():
            break
        time.sleep(0.1)
    assert marker.exists()
    assert marker.read_text(encoding="ascii").strip() == "new"


# ----------------------------------------------------------------------
# 上次安装结果回显 / 遗留清理
# ----------------------------------------------------------------------
def test_startup_reports_last_failed_install(qapp, tmp_path):
    manager = cm.ConfigManager(config_dir=tmp_path)
    result = manager.log_dir / "update-apply.txt"
    result.write_bytes(codecs.BOM_UTF8 + b"start\ncopy-retry 1\nFAIL files still locked\n")

    updater = UpdateManager(manager)
    assert "上次更新失败" in updater.lastError
    assert "files still locked" in updater.lastError
    # 读过的结果会改名归档，避免每次启动重复提示
    assert not result.exists()
    assert list(manager.log_dir.glob("update-apply-*.txt"))
    assert "上次更新失败" in updater.takeStartupNote()
    assert updater.takeStartupNote() == ""


def test_startup_cleans_legacy_update_residue(qapp, tmp_path):
    manager = cm.ConfigManager(config_dir=tmp_path)
    updates = manager.config_dir / "updates"
    (updates / "staging-1").mkdir(parents=True)
    (updates / "staging-1" / "a.bin").write_bytes(b"0")
    (updates / "rollback-123.zip").write_bytes(b"0")

    UpdateManager(manager)
    assert not (updates / "staging-1").exists()
    assert not (updates / "rollback-123.zip").exists()
