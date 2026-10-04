"""Global hotkey support.

Uses ``pynput``'s listener (already a dependency for keyboard actions) rather
than Windows' ``RegisterHotKey`` so the same code path works everywhere.  The
listener runs on its own thread, so activation is re-emitted as a Qt signal and
Qt queues it back onto the GUI thread.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)

# "Ctrl+Space" style token -> pynput's ``<token>`` syntax.
_MODIFIERS = {
    "ctrl": "<ctrl>",
    "control": "<ctrl>",
    "alt": "<alt>",
    "shift": "<shift>",
    "win": "<cmd>",
    "cmd": "<cmd>",
    "super": "<cmd>",
    "meta": "<cmd>",
}

_KEYS = {
    "space": "<space>",
    "enter": "<enter>",
    "return": "<enter>",
    "tab": "<tab>",
    "esc": "<esc>",
    "escape": "<esc>",
    "backspace": "<backspace>",
    "delete": "<delete>",
    "insert": "<insert>",
    "home": "<home>",
    "end": "<end>",
    "pageup": "<page_up>",
    "pagedown": "<page_down>",
    "up": "<up>",
    "down": "<down>",
    "left": "<left>",
    "right": "<right>",
    "printscreen": "<print_screen>",
    "pause": "<pause>",
    "menu": "<menu>",
    "numlock": "<num_lock>",
    "capslock": "<caps_lock>",
    "scrolllock": "<scroll_lock>",
    **{f"f{index}": f"<f{index}>" for index in range(1, 25)},
}


def to_pynput_spec(sequence: str) -> str | None:
    """Translate ``Ctrl+Space`` into pynput's ``<ctrl>+<space>``; None if unusable."""
    tokens = [token.strip().lower() for token in sequence.replace(" ", "").split("+")]
    tokens = [token for token in tokens if token]
    if len(tokens) < 2:  # a bare key would swallow normal typing
        return None

    converted = []
    for token in tokens:
        if token in _MODIFIERS:
            converted.append(_MODIFIERS[token])
        elif token in _KEYS:
            converted.append(_KEYS[token])
        elif len(token) == 1:
            converted.append(token)
        else:
            return None
    return "+".join(converted)


class GlobalHotkey(QObject):
    """Registers one system-wide hotkey and reports presses via ``activated``."""

    activated = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._listener = None
        self._sequence = ""

    @property
    def sequence(self) -> str:
        return self._sequence

    def register(self, sequence: str) -> bool:
        """(Re)register *sequence*. Returns whether the hotkey is now active."""
        self.unregister()

        spec = to_pynput_spec(sequence or "")
        if spec is None:
            logger.info("Hotkey %r is empty or not supported", sequence)
            return False

        try:
            from pynput import keyboard
        except Exception:
            logger.exception("pynput is unavailable, global hotkey disabled")
            return False

        try:
            listener = keyboard.GlobalHotKeys({spec: self.activated.emit})
            listener.daemon = True
            listener.start()
        except Exception:
            logger.exception("Failed to register the global hotkey %r", sequence)
            return False

        self._listener = listener
        self._sequence = sequence
        logger.info("Global hotkey active: %s (%s)", sequence, spec)
        return True

    def unregister(self) -> None:
        if self._listener is None:
            return
        try:
            self._listener.stop()
        except Exception:
            logger.debug("Ignoring listener shutdown error", exc_info=True)
        self._listener = None
        self._sequence = ""
