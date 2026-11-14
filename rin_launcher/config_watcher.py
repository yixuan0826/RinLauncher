"""``config.yaml`` 的外部改动监听。

单独成模块的理由：``watchdog`` 的导入链有几十毫秒成本，放进
``config_manager`` 会让冷启动多背一段；这里只在 ``startWatching`` 真正开启
监听时才导入 ``Observer``。

事件处理有三个容易踩的坑：

* 编辑器常用「写临时文件 → rename」保存，watchdog 发的是 ``FileMovedEvent``，
  只盯 ``src_path`` 会漏掉；
* modified 事件可能发生在文件还没写完时，必须防抖而不是节流；
* 回调运行在 watchdog 线程，不能直接读配置、改 Qt 对象 —— 这里只负责在
  安静 0.5 秒后触发一次回调，由调用方用队列信号切回 GUI 线程。
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)

# 只认真正的配置文件；config.yaml.broken-* / 临时文件不触发重载。
_CONFIG_NAMES = {"config.yaml", "config.yml"}
_DEBOUNCE_SECONDS = 0.5


class ConfigWatcher:
    """Debounced listener for edits made to the config file by other programs.

    不继承 ``watchdog.events.FileSystemEventHandler``：watchdog 只要求处理器有
    ``dispatch(event)``。这样模块导入时就不用把 watchdog 那一整条导入链拉起来。
    """

    def __init__(self, on_change: Callable[[], None],
                 delay: float = _DEBOUNCE_SECONDS):
        self._on_change = on_change
        self._delay = delay
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None

    @staticmethod
    def _touches_config(event) -> bool:
        if getattr(event, "is_directory", False):
            return False
        # 删除不是「外部编辑」：重载会把缺失的 config.yaml 当成首次运行，
        # 立刻又生成一份默认配置，反而把用户想删掉的文件复活。
        if str(getattr(event, "event_type", "")) == "deleted":
            return False
        paths = []
        for attribute in ("dest_path", "src_path"):
            value = getattr(event, attribute, "")
            if value:
                paths.append(str(value))
        return any(Path(path).name in _CONFIG_NAMES for path in paths)

    def dispatch(self, event) -> None:
        # created / modified / moved 都走这里：只要最终落点是 config.yaml
        # 就排一次防抖；重复事件会重置计时器。
        if not self._touches_config(event):
            return
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            timer = threading.Timer(self._delay, self._fire)
            timer.daemon = True
            self._timer = timer
            timer.start()

    def _fire(self) -> None:
        with self._lock:
            self._timer = None
        try:
            self._on_change()
        except Exception:
            logger.exception("Config change callback failed")

    def cancel(self) -> None:
        """停止待触发的防抖计时器（退出 / 停止监听时调用）。"""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
