"""系统强调色：注册表 DWORD 的两种字节序解码。"""

from __future__ import annotations

import pytest

from rin_launcher.system_theme import decode_accent_color


def test_decodes_abgr():
    # Windows 11 的 AccentColor 是 ABGR：0xAABBGGRR -> #5175A1
    assert decode_accent_color(0xFFA17551, "abgr") == "#5175A1"


def test_decodes_argb():
    # ColorizationColor 是 ARGB：0xAARRGGBB -> #5175A1
    assert decode_accent_color(0x005175A1, "argb") == "#5175A1"


def test_keeps_grayscale_and_rejects_zero():
    # 黑 / 白 / 灰都是合法强调色，不能因为 R==G==B 就回退默认蓝色。
    assert decode_accent_color(0x00000000) == ""
    assert decode_accent_color(0xFF000000, "abgr") == "#000000"
    assert decode_accent_color(0xFFFFFFFF) == "#FFFFFF"
    assert decode_accent_color(0xFF808080) == "#808080"


def test_rejects_unknown_byte_order():
    with pytest.raises(ValueError):
        decode_accent_color(0x12345678, "rgb")


def test_ui_settings_is_preferred(monkeypatch):
    from rin_launcher import system_theme

    monkeypatch.setattr(system_theme, "_read_ui_settings", lambda: "#112233")
    monkeypatch.setattr(system_theme, "_read_registry", lambda: "#445566")
    monkeypatch.setattr(system_theme, "_cache", None)
    assert system_theme.read_system_accent_color(force=True) == "#112233"


def test_registry_fallback_and_cache(monkeypatch):
    from rin_launcher import system_theme

    calls = []

    def registry() -> str:
        calls.append(1)
        return "#778899"

    monkeypatch.setattr(system_theme, "_read_ui_settings", lambda: "")
    monkeypatch.setattr(system_theme, "_read_registry", registry)
    monkeypatch.setattr(system_theme, "_cache", None)
    assert system_theme.read_system_accent_color(force=True) == "#778899"
    assert system_theme.read_system_accent_color() == "#778899"
    assert len(calls) == 1
