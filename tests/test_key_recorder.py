"""按键录制：原始事件 -> 可回放步骤的分类规则。"""

from __future__ import annotations

from rin_launcher.key_recorder import _build_steps


def _event(down: bool, name: str, gap: float = 0.0, vk: int = 0) -> dict:
    return {"down": down, "name": name, "vk": vk, "gap": gap}


def test_tap_becomes_click():
    steps = _build_steps([
        _event(True, "A", 0.0, 65),
        _event(False, "A", 0.08, 65),
    ])
    assert steps == [{
        "type": "key", "key": "A", "action": "click",
        "duration": 0.0, "vk": 65,
    }]


def test_hold_becomes_press_and_release():
    steps = _build_steps([
        _event(True, "Shift", 0.0, 16),
        _event(True, "A", 0.4, 65),
        _event(False, "A", 0.05, 65),
        _event(False, "Shift", 0.05, 16),
    ])
    # Shift 按下后不是立刻抬起 -> press；A 是点按；Shift 抬起 -> release。
    assert [step["action"] for step in steps] == ["press", "click", "release"]
    assert [step["key"] for step in steps] == ["Shift", "A", "Shift"]


def test_auto_repeat_is_dropped():
    steps = _build_steps([
        _event(True, "W", 0.0, 87),
        _event(True, "W", 0.03, 87),
        _event(True, "W", 0.03, 87),
        _event(False, "W", 0.05, 87),
    ])
    # 自动重复不单独成步；按住期间的抬起记成 release。
    assert [step["action"] for step in steps] == ["press", "release"]
    assert len(steps) == 2


def test_unmatched_release_is_ignored():
    steps = _build_steps([_event(False, "Ctrl", 0.0, 17)])
    assert steps == []
