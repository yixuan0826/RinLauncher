"""``config.yaml`` 的外部改动监听。

单独成模块的理由：``watchdog`` 的导入链有几十毫秒成本，放进
``config_manager`` 会让冷启动多背一段；这里只在 ``startWatching`` 真正开启
监听时才导入 ``Observer``。
"""

from __future__ import annotations

import time
from collections.abc import Callable


class ConfigWatcher:
    """Debounced listener for edits made to the config file by other programs.

    不继承 ``watchdog.events.FileSystemEventHandler``：watchdog 只要求处理器有
    ``dispatch(event)``。这样模块导入时就不用把 watchdog 那一整条导入链拉起来。
    """

    def __init__(self, on_change: Callable[[], None]):
        self._on_change = on_change
        self._last_fired = 0.0

    def dispatch(self, event) -> None:
        self.on_modified(event)

    def on_modified(self, event) -> None:
        if event.is_directory or not event.src_path.endswith((".yaml", ".yml")):
            return
        now = time.monotonic()
        if now - self._last_fired > 0.5:
            self._last_fired = now
            self._on_change()
