"""全局热键：字符串 -> pynput 规格。"""

from __future__ import annotations

import pytest

from rin_launcher.hotkey import to_pynput_spec


@pytest.mark.parametrize(("sequence", "expected"), [
    ("Ctrl+Space", "<ctrl>+<space>"),
    ("ctrl + alt + l", "<ctrl>+<alt>+l"),
    ("WIN+Shift+S", "<cmd>+<shift>+s"),
    ("Ctrl+F12", "<ctrl>+<f12>"),
    ("Alt+PageDown", "<alt>+<page_down>"),
])
def test_supported(sequence, expected):
    assert to_pynput_spec(sequence) == expected


@pytest.mark.parametrize("sequence", [
    "",
    "   ",
    "Ctrl",           # 没有普通键，会吞掉正常输入
    "Ctrl+NoSuchKey",  # 未知键名
    "Ctrl+",          # 尾部空 token 被过滤后只剩修饰键
])
def test_rejected(sequence):
    assert to_pynput_spec(sequence) is None
