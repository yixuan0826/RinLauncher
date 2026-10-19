"""系统控制：依赖缺失 / 非 Windows 时必须安静降级，不能阻断启动。"""

from __future__ import annotations

import types


def test_system_controls_degrade_gracefully(qapp):
    from rin_launcher.system_controls import SystemControls

    controls = SystemControls()
    # 属性始终可读，QML 不需要判断后端是否存在。
    assert 0.0 <= controls.volume <= 1.0
    assert isinstance(controls.muted, bool)
    assert isinstance(controls.wifiAvailable, bool)
    assert isinstance(controls.wifiEnabled, bool)
    assert isinstance(controls.hotspotAvailable, bool)
    assert isinstance(controls.hotspotEnabled, bool)
    controls.stop()


class _FakeConfiguration:
    def __init__(self):
        self.ssid = ""
        self.passphrase = ""
        self.authentication_kind = None


class _AsyncAction:
    """WinRT 的 IAsyncAction：get() 返回 None，没有 result.status。"""

    def get(self):
        return None


class _FakeManager:
    def __init__(self, *, apply_configuration: bool = True):
        self._current = _FakeConfiguration()
        self._apply = apply_configuration
        self.configured = []

    def configure_access_point_async(self, configuration):
        self.configured.append(configuration)
        if self._apply:
            self._current = configuration
        return _AsyncAction()

    def get_current_access_point_configuration(self):
        return self._current


def _prepare_configuration(monkeypatch):
    """把只在 Windows 上导入的类型换成可控的假实现。"""
    from rin_launcher import system_controls as module

    monkeypatch.setattr(
        module, "NetworkOperatorTetheringAccessPointConfiguration",
        _FakeConfiguration, raising=False)
    monkeypatch.setattr(
        module, "TetheringWiFiAuthenticationKind",
        types.SimpleNamespace(WPA2=0), raising=False)


def test_configure_hotspot_handles_async_action_without_result(qapp, monkeypatch):
    """回归：ConfigureAccessPointAsync 是 IAsyncAction，get() 返回 None。"""
    from rin_launcher import system_controls as module

    _prepare_configuration(monkeypatch)
    controls = module.SystemControls()
    try:
        manager = _FakeManager()
        assert controls._configure_hotspot(manager) == (True, "")
        assert manager.configured[0].ssid == module.HOTSPOT_SSID
        assert manager.configured[0].passphrase == module.HOTSPOT_PASSWORD
    finally:
        controls.stop()


def test_configure_hotspot_detects_configuration_not_applied(qapp, monkeypatch):
    from rin_launcher import system_controls as module

    _prepare_configuration(monkeypatch)
    controls = module.SystemControls()
    try:
        ok, message = controls._configure_hotspot(_FakeManager(apply_configuration=False))
        assert not ok
        assert "SSID" in message
    finally:
        controls.stop()
