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


def test_rejects_grayscale_and_zero():
    assert decode_accent_color(0x00000000) == ""
    assert decode_accent_color(0xFFFFFFFF) == ""


def test_rejects_unknown_byte_order():
    with pytest.raises(ValueError):
        decode_accent_color(0x12345678, "rgb")
