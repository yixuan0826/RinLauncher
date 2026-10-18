"""系统控制：依赖缺失 / 非 Windows 时必须安静降级，不能阻断启动。"""

from __future__ import annotations


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
