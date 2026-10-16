"""动作执行器：参数拆分 / 变量替换 / 提权闸门 / 动作分发 / 键盘回放。

执行器直接碰系统（子进程、UAC、全局键盘），这里只测「决策逻辑」——
所有真正落下手的动作（Popen / run_elevated / webbrowser / pynput）都被
monkeypatch 替换，不产生任何实际系统调用。
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

import rin_launcher.action_executor as ae


class FakeManager:
    """只带执行器需要的接口：config / config_dir / notify。"""

    def __init__(self, settings=None):
        self.config = {"settings": dict(settings or {})}
        self.config_dir = Path("C:/fake/config")
        self.notifications: list[tuple[str, str]] = []

    def notify(self, text, level="info"):
        self.notifications.append((text, level))


@pytest.fixture
def manager():
    return FakeManager()


@pytest.fixture
def executor(manager):
    return ae.ActionExecutor(manager)


# ----------------------------------------------------------------------
# 参数拆分
# ----------------------------------------------------------------------
def test_split_args_empty():
    assert ae._split_args("") == []
    assert ae._split_args("   ") == []


def test_split_args_plain():
    assert ae._split_args("-a -b") == ["-a", "-b"]


def test_split_args_keeps_quoted_space():
    assert ae._split_args('--name "a b" --x') == ["--name", "a b", "--x"]


def test_split_args_single_quotes():
    assert ae._split_args("--path 'C:/a b/c'") == ["--path", "C:/a b/c"]


def test_split_args_unbalanced_quotes_fall_back():
    # 引号不配对：退回按空白拆，至少能把程序拉起来
    assert ae._split_args('a "b c') == ["a", '"b', "c"]


# ----------------------------------------------------------------------
# 变量替换
# ----------------------------------------------------------------------
def test_expand_empty_text(executor):
    assert executor._expand(None) == ""
    assert executor._expand("") == ""


def test_expand_env_and_placeholders(executor, monkeypatch):
    monkeypatch.setenv("RIN_TEST_VAR", "hello")
    assert executor._expand("%RIN_TEST_VAR%") == "hello"
    assert executor._expand("{configdir}") == str(Path("C:/fake/config"))
    assert executor._expand("{homedir}") == str(Path.home())


# ----------------------------------------------------------------------
# 提权闸门
# ----------------------------------------------------------------------
def test_elevation_allowed_by_default(executor):
    assert executor._elevation_blocked({}) is False
    assert executor._elevation_blocked({"name": "x"}) is False


def test_elevation_blocked_when_auto_elevate_off(executor, manager):
    manager.config["settings"]["adminAutoElevate"] = False
    assert executor._elevation_blocked({"name": "x"}) is True
    assert manager.notifications  # 拦下时必须提醒用户


def test_elevation_explicit_admin_bypasses_gate(executor, manager):
    # 右键「以管理员身份打开」是用户点名要的，不闸
    manager.config["settings"]["adminAutoElevate"] = False
    assert executor._elevation_blocked({"_explicit_admin": True}) is False


def test_elevation_missing_config_fails_open(executor, manager):
    manager.config = {}  # 配置缺 settings：视为放行，不误伤
    assert executor._elevation_blocked({}) is False


# ----------------------------------------------------------------------
# 动作分发
# ----------------------------------------------------------------------
def test_execute_unknown_type(executor):
    assert executor.execute({"type": "nope"}) is False


def test_execute_keymouse_maps_to_keyboard(manager, monkeypatch):
    # _handlers 在构造时绑定好方法，patch 必须在实例创建之前打在类上
    calls = []
    monkeypatch.setattr(ae.ActionExecutor, "_run_keyboard",
                        lambda self, action: calls.append(action) or True)
    executor = ae.ActionExecutor(manager)
    assert executor.execute({"type": "keymouse"}) is True
    assert len(calls) == 1


def test_execute_swallows_handler_errors(manager, monkeypatch):
    def boom(self, action):
        raise RuntimeError("boom")

    monkeypatch.setattr(ae.ActionExecutor, "_run_url", boom)
    executor = ae.ActionExecutor(manager)
    assert executor.execute({"type": "url", "target": "x"}) is False


# ----------------------------------------------------------------------
# url / file / cmd 分发
# ----------------------------------------------------------------------
def test_run_url_adds_https_scheme(executor, monkeypatch):
    opened = []
    monkeypatch.setattr(ae.webbrowser, "open", lambda url: opened.append(url) or True)
    assert executor._run_url({"target": "example.com"}) is True
    assert opened == ["https://example.com"]


def test_run_url_keeps_known_scheme(executor, monkeypatch):
    opened = []
    monkeypatch.setattr(ae.webbrowser, "open", lambda url: opened.append(url) or True)
    assert executor._run_url({"target": "mailto:a@b.c"}) is True
    assert opened == ["mailto:a@b.c"]


def test_run_file_missing_program(executor):
    assert executor._run_file({"target": "definitely-missing-rin-xyz.exe"}) is False


def test_run_file_spawns_with_expanded_args(executor, monkeypatch, tmp_path):
    dummy = tmp_path / "tool.bat"
    dummy.write_text("@echo off", encoding="utf-8")
    calls = []
    monkeypatch.setattr(
        executor, "_spawn",
        lambda program, args, cwd, elevated: calls.append(
            (program, args, cwd, elevated)) or True)
    assert executor._run_file({"target": str(dummy), "arguments": '--a "b c"'}) is True
    program, args, cwd, elevated = calls[0]
    assert Path(program) == dummy
    assert args == '--a "b c"'
    assert Path(cwd) == tmp_path
    assert elevated is False


def test_run_file_admin_elevates(executor, monkeypatch, tmp_path):
    dummy = tmp_path / "tool.exe"
    dummy.write_text("x", encoding="utf-8")
    elevated_calls = []
    monkeypatch.setattr(ae, "is_admin", lambda: False)
    monkeypatch.setattr(ae, "run_elevated",
                        lambda program, args, cwd: elevated_calls.append(program) or True)
    assert executor._run_file({"target": str(dummy), "run_as": "admin"}) is True
    assert elevated_calls == [str(dummy)]


def test_run_cmd_joins_command_and_args(executor, monkeypatch):
    calls = []
    monkeypatch.setattr(executor, "_spawn_shell",
                        lambda command, cwd: calls.append(command) or True)
    assert executor._run_cmd({"target": "echo", "arguments": "hi"}) is True
    assert calls == ["echo hi"]


def test_run_cmd_admin_blocked_when_gate_closed(executor, manager, monkeypatch):
    manager.config["settings"]["adminAutoElevate"] = False
    monkeypatch.setattr(ae, "is_admin", lambda: False)
    monkeypatch.setattr(ae, "run_elevated", lambda *args: pytest.fail("不应发起提权"))
    assert executor._run_cmd({"target": "whoami", "run_as": "admin"}) is False


def test_run_cmd_admin_elevates(executor, monkeypatch):
    calls = []
    monkeypatch.setattr(ae, "is_admin", lambda: False)
    monkeypatch.setattr(ae, "run_elevated",
                        lambda program, args, cwd: calls.append((program, args)) or True)
    assert executor._run_cmd({"target": "whoami", "run_as": "admin"}) is True
    assert calls == [("cmd.exe", "/c whoami")]


# ----------------------------------------------------------------------
# 进程启动
# ----------------------------------------------------------------------
def test_spawn_splits_quoted_args(executor, monkeypatch):
    calls = []
    monkeypatch.setattr(ae.subprocess, "Popen",
                        lambda cmd, **kwargs: calls.append(cmd))
    assert executor._spawn("tool.exe", '--a "b c"', "C:/tmp", elevated=False) is True
    assert calls == [["tool.exe", "--a", "b c"]]


def test_spawn_reports_oserror(executor, monkeypatch):
    def boom(cmd, **kwargs):
        raise OSError("nope")

    monkeypatch.setattr(ae.subprocess, "Popen", boom)
    assert executor._spawn("tool.exe", "--a", "C:/tmp", elevated=False) is False


# ----------------------------------------------------------------------
# 键盘回放（假 pynput，不碰真实键盘）
# ----------------------------------------------------------------------
class FakeKeyCode:
    def __init__(self, vk=None):
        self.vk = vk

    @classmethod
    def from_vk(cls, vk):
        return cls(vk=vk)


class FakeKey:
    ctrl = "Key.ctrl"
    shift = "Key.shift"
    esc = "Key.esc"
    space = "Key.space"
    f5 = "Key.f5"


@pytest.fixture
def key_events(monkeypatch):
    events: list[tuple[str, object]] = []

    class FakeController:
        def press(self, key):
            events.append(("press", key))

        def release(self, key):
            events.append(("release", key))

    keyboard = types.SimpleNamespace(
        Key=FakeKey, KeyCode=FakeKeyCode, Controller=FakeController)
    module = types.ModuleType("pynput")
    module.keyboard = keyboard
    monkeypatch.setitem(sys.modules, "pynput", module)
    monkeypatch.setitem(sys.modules, "pynput.keyboard", keyboard)
    return events


def test_keys_for_step_prefers_vk(executor, key_events):
    keys = executor._keys_for_step({"vk": 65})
    assert len(keys) == 1
    assert keys[0].vk == 65


def test_keys_for_step_parses_combo(executor, key_events):
    keys = executor._keys_for_step({"key": "Ctrl+Shift+Esc"})
    assert keys == [FakeKey.ctrl, FakeKey.shift, FakeKey.esc]


def test_keys_for_step_unknown_key(executor, key_events):
    assert executor._keys_for_step({"key": "definitely-not-a-key"}) == []


def test_run_keyboard_clicks_and_releases_held_keys(executor, key_events):
    action = {
        "type": "keyboard",
        "keyboard_steps": [
            {"type": "key", "key": "f5", "action": "click"},
            {"type": "wait", "duration": 0},
            {"type": "key", "key": "ctrl", "action": "press"},
        ],
    }
    assert executor._run_keyboard(action) is True
    # 单击 f5：先按后松
    assert key_events[0] == ("press", FakeKey.f5)
    assert key_events[1] == ("release", FakeKey.f5)
    # 「按住」的 ctrl 没有配对「释放」，序列结束后兜底松掉
    assert key_events[-1] == ("release", FakeKey.ctrl)


def test_run_keyboard_mouse_steps_ignored(executor, key_events):
    # 旧版 keymouse 步骤里的 mouse 条目被忽略，不产生任何按键事件
    action = {"keymouse_steps": [{"type": "mouse", "x": 1}]}
    assert executor._run_keyboard(action) is True
    assert key_events == []
