"""appmodset.conf 与首次运行 / 窗口新设置的回归。"""

from __future__ import annotations

from rin_launcher import app_mode, drives


def test_parse_is_strict_about_booleans_and_unknown_keys():
    values, problems = app_mode.parse(
        "# comment\n"
        "first-run==false\n"
        "normal-boot==yes\n"
        "channel==beta\n"
        "debug==TRUE\n"
        "mystery==true\n")
    assert values["first-run"] is False
    assert values["debug"] is True
    # 写坏的项保留默认值，并给出可读诊断。
    assert values["normal-boot"] is True
    assert values["channel"] == "stable"
    assert len(problems) == 3


def test_channel_txt_migrates_once_and_keeps_legacy_file(tmp_path):
    (tmp_path / "channel.txt").write_text("Pre-Release", encoding="utf-8")
    values, problems, path = app_mode.load(tmp_path)
    assert problems == []
    assert values["channel"] == "prerelease"
    assert path.is_file()
    assert (tmp_path / "channel.txt").is_file()


def test_update_preserves_comments_and_unknown_lines(tmp_path):
    path = tmp_path / "appmodset.conf"
    path.write_text("# my note\nfirst-run==true\nextra-line\n", encoding="utf-8")
    assert app_mode.update(tmp_path, {"first-run": False, "debug": True})
    text = path.read_text(encoding="utf-8")
    assert "# my note" in text
    assert "extra-line" in text
    assert "first-run==false" in text
    assert "debug==true" in text


def test_effective_mode_priority():
    mode = app_mode.effective_mode({
        "first-run": True, "failsafe": True, "recovery": True, "debug": True,
    })
    assert mode.launch_mode == "safe"
    assert mode.recovery_only is True
    assert mode.safe_mode is True
    assert mode.debug is True

    mode = app_mode.effective_mode({"recovery": True, "first-run": True})
    assert mode.launch_mode == "recovery"
    assert mode.recovery_only is True

    mode = app_mode.effective_mode({"first-run": True, "debug": True})
    assert mode.launch_mode == "normal"
    assert mode.first_run is True
    assert mode.debug is True


def test_complete_oobe_writes_first_run_false(qapp, tmp_path):
    from rin_launcher.config_manager import ConfigManager

    manager = ConfigManager(config_dir=tmp_path, app_mode_root=tmp_path)
    try:
        assert manager.isFirstRun() is True
        assert manager.completeOobe({"theme": "dark"})
        assert manager.isFirstRun() is False
        assert manager.getSettings()["theme"] == "dark"
        text = (tmp_path / "appmodset.conf").read_text(encoding="utf-8")
        assert "first-run==false" in text
    finally:
        manager.stopWatching()


def test_window_settings_are_normalized(qapp, tmp_path):
    from rin_launcher.config_manager import ConfigManager

    manager = ConfigManager(config_dir=tmp_path, app_mode_root=tmp_path)
    try:
        manager.updateSettings({
            "compactMode": "floating",
            "windowCorner": "left-top",
            "windowOffsetX": 99999,
            "compactTransparency": -5,
            "miniTransparency": 999,
            "backdropMode": "glass",
        })
        # 归一化在写盘 / 读盘时发生：重新读一遍才能看到夹紧后的值。
        manager._config = manager._normalize(manager._config)
        settings = manager.getSettings()
        # 悬浮球已下线：旧配置里的 floating 迁移为 mini。
        assert settings["compactMode"] == "mini"
        assert settings["windowCorner"] == "bottom-right"
        assert settings["windowOffsetX"] == 2000
        assert settings["compactTransparency"] == 0
        assert settings["miniTransparency"] == 90
        assert settings["backdropMode"] == "auto"
    finally:
        manager.stopWatching()


def test_usb_names_parse_powershell_payload(monkeypatch):
    payload = (
        '[{"model":"TransMemory","letters":["E:","F:"]},'
        '{"model":"USB DISK","letters":"G:"}]'
    )
    monkeypatch.setattr(drives, "_native_usb_names", lambda: {})
    monkeypatch.setattr(drives, "_run_powershell", lambda *_a, **_k: payload)
    monkeypatch.setattr(drives, "_USB_NAME_CACHE", None)
    names = drives.usb_device_names()
    assert names == {"E:": "TransMemory", "F:": "TransMemory", "G:": "USB DISK"}
    # 第二次走缓存，不再启动 PowerShell。
    assert drives.usb_device_names() == names
