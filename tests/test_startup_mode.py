"""三态启动方式：注册表 / 任务计划的互斥切换与提权分流。"""

from __future__ import annotations

import rin_launcher.autostart as autostart
import rin_launcher.config_manager as cm


def test_startup_state_prefers_task(monkeypatch):
    monkeypatch.setattr(autostart, "task_exists_cached", lambda: True)
    monkeypatch.setattr("rin_launcher.elevation.run_on_startup_enabled", lambda: True)
    assert autostart.startup_state() == "admin"


def test_startup_state_registry_only(monkeypatch):
    monkeypatch.setattr(autostart, "task_exists_cached", lambda: False)
    monkeypatch.setattr("rin_launcher.elevation.run_on_startup_enabled", lambda: True)
    assert autostart.startup_state() == "normal"


def test_startup_state_nothing(monkeypatch):
    monkeypatch.setattr(autostart, "task_exists_cached", lambda: False)
    monkeypatch.setattr("rin_launcher.elevation.run_on_startup_enabled", lambda: False)
    assert autostart.startup_state() == "off"


def test_task_exists_uses_cache(monkeypatch):
    calls = []
    monkeypatch.setattr(autostart, "_query_task_exists",
                        lambda: calls.append(1) or True)
    autostart._store_task_cache(False)
    # 缓存命中：不启子进程；force=True 才重新探测。
    assert autostart.task_exists() is False
    assert autostart.task_exists(force=True) is True
    assert len(calls) == 1


def test_apply_off_cleans_both(monkeypatch):
    calls = []
    monkeypatch.setattr(autostart, "delete_task", lambda: calls.append("delete") or True)
    monkeypatch.setattr("rin_launcher.elevation.set_run_on_startup",
                        lambda flag: calls.append(("registry", flag)) or True)
    assert autostart.apply_startup_mode("off") is True
    assert calls == ["delete", ("registry", False)]


def test_apply_admin_sets_task_first(monkeypatch):
    calls = []
    monkeypatch.setattr(autostart, "create_task", lambda: calls.append("create") or True)
    monkeypatch.setattr("rin_launcher.elevation.set_run_on_startup",
                        lambda flag: calls.append(("registry", flag)) or True)
    assert autostart.apply_startup_mode("admin") is True
    # 注册表先撤掉，再登记任务 —— 两者永远互斥。
    assert calls == [("registry", False), "create"]


def test_apply_normal_switches_back(monkeypatch):
    calls = []
    monkeypatch.setattr(autostart, "delete_task", lambda: calls.append("delete") or True)
    monkeypatch.setattr("rin_launcher.elevation.set_run_on_startup",
                        lambda flag: calls.append(("registry", flag)) or True)
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
