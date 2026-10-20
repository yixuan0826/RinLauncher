"""输入法兼容的注入：东亚布局下可打印字符走 Unicode，其余走虚拟键码。"""

from __future__ import annotations

import ctypes

from rin_launcher import ime


class _FakeUser32:
    """记录 SendInput 的输入事件，并提供布局查询。"""

    def __init__(self, layout=0x0804, layouts=None, delivered=None):
        self.layouts = list(layouts) if layouts is not None else [layout]
        self.delivered = delivered
        self.count = 0
        self.size = 0
        self.events: list[tuple] = []

    def GetKeyboardLayoutList(self, count, pointer):
        if count <= 0:
            return len(self.layouts)
        for index in range(min(count, len(self.layouts))):
            pointer[index] = self.layouts[index]
        return min(count, len(self.layouts))

    def SendInput(self, count, events, size):
        self.count = count
        self.size = size
        self.events = [(event.ki.wScan, event.ki.dwFlags) for event in events]
        return count if self.delivered is None else self.delivered


def _install(monkeypatch, user32):
    monkeypatch.setattr(ime, "_user32", user32)
    monkeypatch.setattr(ime, "available", lambda: True)
    # 布局检测有 1 秒缓存；测试里每次重置。
    monkeypatch.setattr(ime, "_layout_checked_at", 0.0)
    monkeypatch.setattr(ime, "_layout_active", False)
    return user32


def test_input_struct_matches_win32_size():
    # x64 上 INPUT 必须是 40 字节，否则 SendInput 会直接失败
    expected = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
    assert ctypes.sizeof(ime.INPUT) == expected


def test_send_text_emits_down_and_up(monkeypatch):
    fake = _install(monkeypatch, _FakeUser32())

    assert ime.send_text("ab") is True
    assert fake.size == ctypes.sizeof(ime.INPUT)
    assert fake.count == 4
    assert fake.events == [
        (ord("a"), ime.KEYEVENTF_UNICODE),
        (ord("a"), ime.KEYEVENTF_UNICODE | ime.KEYEVENTF_KEYUP),
        (ord("b"), ime.KEYEVENTF_UNICODE),
        (ord("b"), ime.KEYEVENTF_UNICODE | ime.KEYEVENTF_KEYUP),
    ]


def test_send_text_reports_partial_delivery(monkeypatch):
    _install(monkeypatch, _FakeUser32(delivered=1))

    assert ime.send_text("ab") is False


def test_send_text_splits_surrogate_pairs(monkeypatch):
    fake = _install(monkeypatch, _FakeUser32())

    assert ime.send_text("😀") is True
    assert len(fake.events) == 4
    assert fake.events[0][0] != fake.events[2][0]  # 高低代理各一个


def test_send_text_noop_when_unavailable(monkeypatch):
    monkeypatch.setattr(ime, "available", lambda: False)

    assert ime.send_text("a") is False
    assert ime.send_text("") is False


def test_east_asian_layouts_are_detected(monkeypatch):
    for layout in (0x0804, 0x0411, 0x0412):  # 中 / 日 / 韩
        _install(monkeypatch, _FakeUser32(layout=layout))
        assert ime.east_asian_ime_active() is True


def test_latin_layout_is_not_treated_as_ime(monkeypatch):
    _install(monkeypatch, _FakeUser32(layout=0x0409))

    assert ime.east_asian_ime_active() is False


def test_no_layouts_means_no_ime(monkeypatch):
    _install(monkeypatch, _FakeUser32(layouts=[]))

    assert ime.east_asian_ime_active() is False

