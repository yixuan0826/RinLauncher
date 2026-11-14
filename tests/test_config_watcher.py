"""config.yaml 外部监听：moved 事件、防抖、忽略无关文件。"""

from __future__ import annotations

import threading
import time

from rin_launcher.config_watcher import ConfigWatcher


class _Event:
    def __init__(self, src_path: str = "", dest_path: str = "",
                 is_directory: bool = False, event_type: str = "modified"):
        self.src_path = src_path
        self.dest_path = dest_path
        self.is_directory = is_directory
        self.event_type = event_type


def _collect(delay: float = 0.15) -> tuple[ConfigWatcher, list[float]]:
    calls: list[float] = []
    lock = threading.Lock()

    def on_change() -> None:
        with lock:
            calls.append(time.monotonic())

    return ConfigWatcher(on_change, delay=delay), calls


def test_moved_event_uses_destination():
    watcher, calls = _collect(0.05)
    watcher.dispatch(_Event(src_path="C:/cfg/.config.yaml.tmp",
                            dest_path="C:/cfg/config.yaml"))
    time.sleep(0.25)
    assert len(calls) == 1


def test_created_modified_same_path_debounced():
    watcher, calls = _collect(0.12)
    watcher.dispatch(_Event(src_path="C:/cfg/config.yaml"))
    time.sleep(0.03)
    watcher.dispatch(_Event(src_path="C:/cfg/config.yaml"))
    time.sleep(0.03)
    watcher.dispatch(_Event(src_path="C:/cfg/config.yaml"))
    time.sleep(0.3)
    assert len(calls) == 1


def test_broken_copy_and_directories_are_ignored():
    watcher, calls = _collect(0.05)
    watcher.dispatch(_Event(src_path="C:/cfg/config.yaml.broken-20261114"))
    watcher.dispatch(_Event(src_path="C:/cfg", is_directory=True))
    watcher.dispatch(_Event(src_path="C:/cfg/other.yaml"))
    time.sleep(0.2)
    assert calls == []


def test_deleted_config_does_not_reload():
    watcher, calls = _collect(0.05)
    watcher.dispatch(_Event(src_path="C:/cfg/config.yaml", event_type="deleted"))
    time.sleep(0.2)
    assert calls == []


def test_cancel_stops_pending_callback():
    watcher, calls = _collect(0.15)
    watcher.dispatch(_Event(src_path="C:/cfg/config.yaml"))
    watcher.cancel()
    time.sleep(0.3)
    assert calls == []
