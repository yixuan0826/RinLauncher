"""三态启动方式：注册表 / 任务计划的互斥切换与提权分流。"""

from __future__ import annotations

import rin_launcher.autostart as autostart
import rin_launcher.config_manager as cm
from rin_launcher.startup_command import commands_match


def test_startup_state_prefers_task(monkeypatch):
    monkeypatch.setattr(autostart, "task_is_current", lambda force=False: True)
    monkeypatch.setattr("rin_launcher.elevation.run_on_startup_current",
                        lambda command=None: True)
    assert autostart.startup_state() == "admin"


def test_startup_state_registry_only(monkeypatch):
    monkeypatch.setattr(autostart, "task_is_current", lambda force=False: False)
    monkeypatch.setattr(autostart, "_launcher_is_current", lambda: True)
    monkeypatch.setattr("rin_launcher.elevation.run_on_startup_current",
                        lambda command=None: True)
    assert autostart.startup_state() == "normal"


def test_startup_state_nothing(monkeypatch):
    monkeypatch.setattr(autostart, "task_is_current", lambda force=False: False)
    monkeypatch.setattr("rin_launcher.elevation.run_on_startup_current",
                        lambda command=None: False)
    assert autostart.startup_state() == "off"


def test_task_exists_uses_cache(monkeypatch):
    calls = []
    monkeypatch.setattr(autostart, "_query_task_status",
                        lambda: calls.append(1) or (True, True))
    autostart._store_task_cache(False)
    # 缓存命中：不启子进程；force=True 才重新探测。
    assert autostart.task_exists() is False
    assert autostart.task_exists(force=True) is True
    assert len(calls) == 1


def test_apply_off_cleans_both(monkeypatch):
    calls = []
    monkeypatch.setattr(autostart, "delete_task", lambda: calls.append("delete") or True)
    monkeypatch.setattr("rin_launcher.elevation.set_run_on_startup",
                        lambda flag, command=None: calls.append(("registry", flag)) or True)
    assert autostart.apply_startup_mode("off") is True
    assert calls == ["delete", ("registry", False)]


def test_apply_admin_sets_task_first(monkeypatch):
    calls = []
    monkeypatch.setattr(autostart, "create_task", lambda: calls.append("create") or True)
    monkeypatch.setattr("rin_launcher.elevation.set_run_on_startup",
                        lambda flag, command=None: calls.append(("registry", flag)) or True)
    assert autostart.apply_startup_mode("admin") is True
    # 注册表先撤掉，再登记任务 —— 两者永远互斥。
    assert calls == [("registry", False), "create"]


def test_apply_normal_switches_back(monkeypatch):
    calls = []
    monkeypatch.setattr(autostart, "delete_task", lambda: calls.append("delete") or True)
    monkeypatch.setattr("rin_launcher.elevation.set_run_on_startup",
                        lambda flag, command=None: calls.append(("registry", flag)) or True)
    assert autostart.apply_startup_mode("normal") is True
    assert calls == ["delete", ("registry", True)]


def test_set_startup_mode_spawns_helper_when_admin_needed(qapp, tmp_path, monkeypatch):
    manager = cm.ConfigManager(config_dir=tmp_path)
    spawned = []
    monkeypatch.setattr(cm, "is_admin", lambda: False)
    # 无论目标是 admin 还是已有任务要拆，都得走提权辅助进程。
    monkeypatch.setattr(autostart, "task_exists", lambda force=False: True)
    monkeypatch.setattr(autostart, "spawn_apply_elevated",
                        lambda mode: spawned.append(mode) or True)
    monkeypatch.setattr(autostart, "startup_state", lambda: "normal")

    result = manager.setStartupMode("admin")
    assert result["pending"] is True
    assert spawned == ["admin"]
    assert manager.config["settings"]["startupMode"] == "admin"


def test_set_startup_mode_applies_directly_without_admin(qapp, tmp_path, monkeypatch):
    manager = cm.ConfigManager(config_dir=tmp_path)
    applied = []
    monkeypatch.setattr(cm, "is_admin", lambda: False)
    monkeypatch.setattr(autostart, "task_exists", lambda force=False: False)
    monkeypatch.setattr(autostart, "apply_startup_mode",
                        lambda mode: applied.append(mode) or True)
    monkeypatch.setattr(autostart, "startup_state", lambda: "normal")

    result = manager.setStartupMode("normal")
    assert result == {"mode": "normal", "state": "normal", "pending": False}
    assert applied == ["normal"]


def test_parse_task_command_reads_exec_action():
    xml = """<?xml version="1.0" encoding="UTF-16"?>
    <Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
      <Actions Context="Author">
        <Exec>
          <Command>"C:\\Apps\\RinLauncher.exe"</Command>
          <Arguments>--recovery</Arguments>
        </Exec>
      </Actions>
    </Task>"""
    command = autostart.parse_task_command(xml)
    assert command == '"C:\\Apps\\RinLauncher.exe" --recovery'


def test_parse_task_command_handles_bad_xml():
    assert autostart.parse_task_command("") == ""
    assert autostart.parse_task_command("<not-a-task>") == ""


def test_cached_task_status_keeps_current_flag():
    autostart._store_task_cache(True, False)
    assert autostart.task_exists_cached() is True
    assert autostart.task_is_current() is False
    autostart._store_task_cache(True, True)
    assert autostart.task_is_current() is True


def test_commands_match_ignores_quotes_and_slashes():
    assert commands_match('"C:\\Apps\\RinLauncher.exe"',
                          "c:/apps/rinlauncher.exe")
    assert not commands_match('"C:\\Apps\\RinLauncher.exe"',
                              '"C:\\Other\\RinLauncher.exe"')


def test_source_launcher_must_point_at_current_bundle(tmp_path, monkeypatch):
    monkeypatch.setenv("RINLAUNCHER_CONFIG_DIR", str(tmp_path))
    launcher = autostart._source_launcher_path()
    launcher.write_text("# moved repo\n", encoding="utf-8")
    assert autostart._launcher_is_current() is False

    assert autostart._write_source_launcher()
    assert autostart._launcher_is_current() is True
