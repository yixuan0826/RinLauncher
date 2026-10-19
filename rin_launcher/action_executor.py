"""Executes launcher actions: file, cmd, url and keyboard sequences."""

from __future__ import annotations

import logging
import os
import shlex
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any

from rin_launcher import ime
from rin_launcher.elevation import is_admin, run_elevated

logger = logging.getLogger(__name__)

_URL_SCHEMES = ("http://", "https://", "ftp://", "file://", "mailto:")


def _split_args(text: str) -> list[str]:
    """把参数串拆成参数列表，并保留引号里的空格。

    ``shlex.split(posix=False)`` 在 Windows 上把 ``"a b"`` 当成一个 token，
    但引号本身会留着，这里再手工剥掉 —— 否则子进程会收到带引号的参数。
    拆不出来（引号不配对）时退回按空白拆，至少能把程序拉起来。
    """
    if not text.strip():
        return []
    try:
        parts = shlex.split(text, posix=False)
    except ValueError:
        logger.warning("Unbalanced quotes in arguments %r, splitting naively", text)
        return text.split()
    stripped: list[str] = []
    for part in parts:
        if len(part) >= 2 and part[0] == part[-1] and part[0] in "\"'":
            part = part[1:-1]
        stripped.append(part)
    return stripped

# Human-friendly key name -> pynput ``Key`` member.  Function keys are generated
# rather than listed, and single characters are handled before the lookup.
_SPECIAL_KEYS = {
    "ctrl": "ctrl", "alt": "alt", "shift": "shift", "win": "cmd", "cmd": "cmd",
    "super": "cmd", "space": "space", "enter": "enter", "return": "enter",
    "esc": "esc", "escape": "esc", "tab": "tab", "backspace": "backspace",
    "delete": "delete", "insert": "insert", "home": "home", "end": "end",
    "pageup": "page_up", "pagedown": "page_down", "up": "up", "down": "down",
    "left": "left", "right": "right", "numlock": "num_lock", "capslock": "caps_lock",
    "scrolllock": "scroll_lock", "printscreen": "print_screen", "pause": "pause",
    "menu": "menu",
    **{f"f{index}": f"f{index}" for index in range(1, 25)},
}


def _resolve_key(name: str):
    """Map a recorded key name to a pynput key, or None when unrecognised."""
    from pynput import keyboard

    name = (name or "").strip().lower()
    if not name:
        return None
    if len(name) == 1:
        return name
    return getattr(keyboard.Key, _SPECIAL_KEYS.get(name, name), None)


class ActionExecutor:
    """Runs one launcher action and reports whether it succeeded."""

    def __init__(self, config_manager):
        self.config_manager = config_manager
        self._handlers = {
            "file": self._run_file,
            "cmd": self._run_cmd,
            "url": self._run_url,
            "keyboard": self._run_keyboard,
            # 旧配置里可能还留着 keymouse；按键模拟接手，鼠标步骤会被忽略。
            "keymouse": self._run_keyboard,
        }

    def execute(self, action: dict[str, Any]) -> bool:
        kind = action.get("type", "file")
        handler = self._handlers.get(kind)
        if handler is None:
            logger.warning("Unknown action type: %r", kind)
            return False
        try:
            return handler(action)
        except Exception:
            logger.exception("Failed to execute action %r", action.get("name", "?"))
            return False

    # ------------------------------------------------------------------
    # Variable expansion
    # ------------------------------------------------------------------
    def _expand(self, text: str | None) -> str:
        """Expand ``%ENV%``/``~`` and the launcher's ``{placeholder}`` tokens."""
        if not text:
            return ""
        resolved = os.path.expanduser(os.path.expandvars(text))
        frozen = getattr(sys, "frozen", False)
        replacements = {
            "{appdir}": str(Path(sys.executable).parent if frozen else Path.cwd()),
            "{configdir}": str(self.config_manager.config_dir),
            "{homedir}": str(Path.home()),
            "{tempdir}": os.environ.get("TEMP", "/tmp"),
            "{desktop}": str(Path.home() / "Desktop"),
            "{documents}": str(Path.home() / "Documents"),
            "{downloads}": str(Path.home() / "Downloads"),
        }
        for token, value in replacements.items():
            resolved = resolved.replace(token, value)
        return resolved

    def _elevation_blocked(self, action: dict[str, Any]) -> bool:
        """「自动提权」关掉后，隐式提权动作直接拦下并提醒。

        显式提权（右键「以管理员身份打开」，payload 带 ``_explicit_admin``）
        是用户点名要的，不走这道闸。
        """
        if action.get("_explicit_admin"):
            return False
        manager = self.config_manager
        if manager is None:
            return False
        try:
            allowed = bool(manager.config["settings"].get("adminAutoElevate", True))
        except Exception:
            return False
        if allowed:
            return False
        logger.info("adminAutoElevate is off, skipping elevated action %r",
                    action.get("name", "?"))
        notify = getattr(manager, "notify", None)
        if callable(notify):
            notify("已在设置里关闭自动提权，这个动作没有执行", "warning")
        return True

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------
    def _run_file(self, action: dict[str, Any]) -> bool:
        target = self._expand(action.get("target"))
        if not target:
            return False
        # Accept an absolute/relative path or anything resolvable via PATH.
        program = target if Path(target).exists() else shutil.which(target)
        if not program:
            logger.error("File not found: %s", target)
            return False

        args = self._expand(action.get("arguments"))
        cwd = self._expand(action.get("working_dir")) or str(Path(program).parent)
        elevated = action.get("run_as") == "admin"
        if elevated and not is_admin() and self._elevation_blocked(action):
            return False
        return self._spawn(program, args, cwd, elevated=elevated)

    def _run_cmd(self, action: dict[str, Any]) -> bool:
        command = self._expand(action.get("target"))
        if not command:
            return False

        args = self._expand(action.get("arguments"))
        cwd = self._expand(action.get("working_dir")) or os.getcwd()
        shell_command = f"{command} {args}".strip()

        if action.get("run_as") == "admin" and not is_admin():
            if self._elevation_blocked(action):
                return False
            return run_elevated("cmd.exe", f"/c {shell_command}", cwd)
        return self._spawn_shell(shell_command, cwd)

    def _run_url(self, action: dict[str, Any]) -> bool:
        url = self._expand(action.get("target"))
        if not url:
            return False
        if not url.startswith(_URL_SCHEMES):
            url = f"https://{url}"
        try:
            return webbrowser.open(url)
        except Exception:
            logger.exception("Failed to open %s", url)
            return False

    def _run_keyboard(self, action: dict[str, Any]) -> bool:
        """按键模拟：按顺序回放按键 / 等待，语义照 SystemTools 的「模拟键盘」。

        每个步骤先等 ``duration`` 秒再执行（延迟前置，对应 SystemTools 的
        interval）；序列结束时兜底释放还按着的键 —— 否则「按住」忘了配
        「释放」会把系统按键一直卡住。
        """
        try:
            from pynput import keyboard
        except ImportError:
            logger.error("pynput is not installed, cannot run keyboard actions")
            return False

        steps = action.get("keyboard_steps")
        if steps is None:
            steps = action.get("keymouse_steps")  # 旧字段兜底
        controller = keyboard.Controller()
        pressed: list[Any] = []
        for step in steps or []:
            try:
                duration = max(0.0, float(step.get("duration") or 0))
            except (TypeError, ValueError):
                duration = 0.0
            if duration:
                time.sleep(duration)
            if step.get("type") == "key":
                self._send_key(controller, step, pressed)
            # wait 步骤：等待就是它本身，上面的 sleep 已经完成它的职责。
        while pressed:
            key = pressed.pop()
            try:
                controller.release(key)
            except Exception:
                logger.warning("Failed to release key %r after the sequence", key)
        return True

    # ------------------------------------------------------------------
    # Process launching
    # ------------------------------------------------------------------
    def _spawn(self, program: str, args: str, cwd: str, elevated: bool) -> bool:
        if elevated and not is_admin():
            return run_elevated(program, args, cwd)
        try:
            if args:
                subprocess.Popen([program, *_split_args(args)], cwd=cwd, start_new_session=True)
            elif sys.platform == "win32":
                os.startfile(program)  # lets the shell apply the file's default verb
            else:
                subprocess.Popen([program], cwd=cwd, start_new_session=True)
        except OSError:
            logger.exception("Failed to launch %s", program)
            return False
        return True

    @staticmethod
    def _spawn_shell(command: str, cwd: str) -> bool:
        try:
            subprocess.Popen(command, cwd=cwd, shell=True, start_new_session=True)
        except OSError:
            logger.exception("Failed to run command: %s", command)
            return False
        return True

    # ------------------------------------------------------------------
    # Input simulation
    # ------------------------------------------------------------------
    # 组合键里每个事件之间留一点空隙，系统才会把它当成一次组合；
    # SystemTools 的模拟键盘用的是 20ms，这里沿用。
    _KEY_EVENT_GAP = 0.02

    @classmethod
    def _send_key(cls, controller, step: dict[str, Any], pressed: list[Any]) -> None:
        """发送一步按键；「按住」的键登记进 ``pressed``，供序列结束后的兑底释放。"""
        keys = cls._keys_for_step(step)
        if not keys:
            logger.warning("Unknown key in keyboard step %r, skipping", step)
            return

        command = step.get("action", "click")
        if command == "click" and cls._send_as_text(step):
            return
        if command == "press":
            # 按住：全部按下并保持，等后面的步骤来释放。
            for key in keys:
                controller.press(key)
                pressed.append(key)
        elif command == "release":
            for key in reversed(keys):
                controller.release(key)
                cls._forget_pressed(pressed, key)
        else:
            # 点击：按顺序按下、再逆序释放（组合键只会在停顿期间同时成立）。
            # 空隙只插在事件之间：单键点击不留空隙，最后一个抬起后面也不再等。
            gap = cls._KEY_EVENT_GAP if len(keys) > 1 else 0
            for key in keys:
                controller.press(key)
                if gap:
                    time.sleep(gap)
            last = len(keys) - 1
            for index, key in enumerate(reversed(keys)):
                controller.release(key)
                if gap and index < last:
                    time.sleep(gap)

    @staticmethod
    def _printable_char(step: dict[str, Any]) -> str | None:
        """单字符步骤对应的文本；组合键、功能键返回 None。"""
        name = str(step.get("key") or "").strip()
        if len(name) != 1 or not name.isprintable():
            return None
        # 录制器把字母统一存成大写，但没带 Shift 的单击敲出来就是小写。
        return name.lower() if name.isascii() and name.isalpha() else name

    @classmethod
    def _send_as_text(cls, step: dict[str, Any]) -> bool:
        """挂着东亚输入法时，可打印字符改用 Unicode 注入。

        第三方输入法会把虚拟键码注入的字母拿去做拼音组词，目标程序什么都收不到；
        ``SendInput`` + ``KEYEVENTF_UNICODE`` 直接生成 ``WM_CHAR``，不过输入法。
        组合键、功能键不受影响，仍走原来的虚拟键码路径。
        """
        char = cls._printable_char(step)
        if not char or not ime.east_asian_ime_active():
            return False
        return ime.send_text(char)

    @staticmethod
    def _keys_for_step(step: dict[str, Any]) -> list[Any]:
        """一步按键 → pynput 能按下的键对象；认不出来返回空表。

        虚拟键码（``vk``）优先：编辑器录制出来的步骤都带着它，按码原样回放；
        没有键码时用 ``key`` 名称解析 —— 单键，或 ``Ctrl+Shift+Esc`` 组合。
        """
        from pynput import keyboard

        try:
            vk = int(step.get("vk") or 0)
        except (TypeError, ValueError):
            vk = 0
        if 0 < vk < 256:
            try:
                return [keyboard.KeyCode.from_vk(vk)]
            except Exception:
                logger.warning("Cannot use virtual key code %s, falling back to name", vk)
        names = [part.strip() for part in str(step.get("key") or "").split("+") if part.strip()]
        keys = [_resolve_key(name) for name in names]
        if not keys or any(key is None for key in keys):
            return []
        return keys

    @staticmethod
    def _forget_pressed(pressed: list[Any], key: Any) -> None:
        """把已释放的键从「仍按住」清单里摘掉（先精确相等，再比虚拟键码）。"""
        vk = getattr(key, "vk", None)
        for index, held in enumerate(pressed):
            if held == key or (vk is not None and getattr(held, "vk", None) == vk):
                del pressed[index]
                return
