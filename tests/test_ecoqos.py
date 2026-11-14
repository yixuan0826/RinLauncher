"""EcoQoS：只验证掩码与失败降级，不真的修改当前进程的调度策略。"""

from __future__ import annotations

import pytest

from rin_launcher import ecoqos


class _FakeKernel32:
    def __init__(self, result: bool = True):
        self.result = result
        self.calls: list[tuple[int, int, object]] = []

    def GetCurrentThread(self) -> int:  # noqa: N802 - Win32 命名
        return 1234

    def GetCurrentProcess(self) -> int:  # noqa: N802
        return 5678

    def SetThreadInformation(self, handle, info_class, pointer, size):  # noqa: N802
        state = pointer._obj  # ctypes.byref 指向的结构体
        self.calls.append((info_class, state.ControlMask, state.StateMask))
        return self.result

    def SetProcessInformation(self, handle, info_class, pointer, size):  # noqa: N802
        state = pointer._obj
        self.calls.append((info_class, state.ControlMask, state.StateMask))
        return self.result


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setattr(ecoqos, "sys", type("S", (), {"platform": "win32"}))
    monkeypatch.setattr(ecoqos, "_enabled", True)
    monkeypatch.setattr(ecoqos, "_thread_supported", None)
    monkeypatch.setattr(ecoqos, "_process_supported", None)
    yield


def _install(monkeypatch, fake):
    monkeypatch.setattr(ecoqos, "_api", (fake,))


def test_thread_masks(monkeypatch):
    fake = _FakeKernel32(True)
    _install(monkeypatch, fake)
    assert ecoqos.enable_current_thread() is True
    assert ecoqos.disable_current_thread() is True
    assert ecoqos.reset_current_thread() is True
    assert fake.calls == [
        (ecoqos._THREAD_POWER_THROTTLING, 1, 1),
        (ecoqos._THREAD_POWER_THROTTLING, 1, 0),
        (ecoqos._THREAD_POWER_THROTTLING, 0, 0),
    ]


def test_failure_returns_false_and_degrades(monkeypatch):
    fake = _FakeKernel32(False)
    _install(monkeypatch, fake)
    assert ecoqos.enable_current_thread() is False
    assert ecoqos._thread_supported is False


def test_disabled_switch_short_circuits(monkeypatch):
    fake = _FakeKernel32(True)
    _install(monkeypatch, fake)
    ecoqos.set_enabled(False)
    try:
        assert ecoqos.enable_current_thread() is False
        assert fake.calls == []
    finally:
        ecoqos.set_enabled(True)


def test_non_windows_is_noop(monkeypatch):
    monkeypatch.setattr(ecoqos, "sys", type("S", (), {"platform": "linux"}))
    assert ecoqos.enable_current_thread() is False
    assert ecoqos.enable_process() is False
    assert ecoqos.available() is False


def test_struct_size_and_version():
    state = ecoqos._PowerThrottlingState()
    assert state.Version == 0
    state.Version = 1
    assert state.Version == 1
