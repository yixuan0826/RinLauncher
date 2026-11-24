"""启动项失效提示：设置里开了自启动、系统里却指向旧路径时要提醒一次。"""

from __future__ import annotations

from types import SimpleNamespace

from rin_launcher import autostart, main


class _Toast:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def emit(self, message: str, severity: str) -> None:
        self.calls.append((message, severity))


class _ConfigManager:
    def __init__(self, mode: str, first_run: bool = False):
        self.config = {"settings": {"startupMode": mode}}
        self.showToast = _Toast()
        self._first_run = first_run

    def isFirstRun(self) -> bool:
        return self._first_run


def _launcher(manager: _ConfigManager) -> SimpleNamespace:
    return SimpleNamespace(recovery_only=False, config_manager=manager)


def test_mismatch_emits_one_toast(monkeypatch):
    monkeypatch.setattr(autostart, "startup_state", lambda: "off")
    manager = _ConfigManager("admin")
    main.Launcher._check_startup_mismatch(_launcher(manager))

    assert len(manager.showToast.calls) == 1
    message, severity = manager.showToast.calls[0]
    assert "自启动" in message
    assert severity == "warning"


def test_matching_state_is_silent(monkeypatch):
    monkeypatch.setattr(autostart, "startup_state", lambda: "normal")
    manager = _ConfigManager("normal")
    main.Launcher._check_startup_mismatch(_launcher(manager))
    assert manager.showToast.calls == []


def test_off_mode_and_first_run_are_silent(monkeypatch):
    monkeypatch.setattr(autostart, "startup_state", lambda: "off")
    manager = _ConfigManager("off")
    main.Launcher._check_startup_mismatch(_launcher(manager))
    assert manager.showToast.calls == []

    first_run = _ConfigManager("admin", first_run=True)
    main.Launcher._check_startup_mismatch(_launcher(first_run))
    assert first_run.showToast.calls == []
