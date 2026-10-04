"""启动方式：注册表 Run 值（登录时启动）与任务计划（管理员自启动）的统一管理。

「管理员自启动」要在任务计划程序里建一条最高权限的登录触发任务，创建 / 删除
都需要提权 —— 界面线程不直接干这事，而是把活交给本程序的无界面辅助分支：

    RinLauncher.exe --set-startup-mode=admin|normal|off

由 ``spawn_apply_elevated`` 用 runas 拉起来（会弹一次 UAC）。界面在稍后通过
``rin_launcher.autostart.startup_state`` 回查系统里的真实状态。
"""

from __future__ import annotations

import logging
import subprocess
import sys
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

#: 任务计划里那条目的名称（任务计划程序里看到的就是它）。
TASK_NAME = "Rin Launcher"
#: 别再闪黑窗：schtasks 的调用全部隐藏控制台。
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# 任务状态的读缓存：schtasks 一次要 70~200ms，界面路径（设置页打开 / 轮询）
# 绝不能同步等它 —— 启动时在后台预热，之后读取走缓存、刷新走异步线程。
_TASK_CACHE_TTL = 30.0
_task_cache: tuple[float, bool] | None = None
_task_lock = threading.Lock()


def _schtasks(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["schtasks", *args],
        capture_output=True, text=True, check=False, creationflags=_NO_WINDOW)


def _query_task_exists() -> bool:
    return _schtasks(["/Query", "/TN", TASK_NAME]).returncode == 0


def _store_task_cache(value: bool) -> None:
    global _task_cache
    with _task_lock:
        _task_cache = (time.monotonic(), value)


def task_exists(force: bool = False) -> bool:
    """任务计划里有没有我们那条「管理员自启动」任务。

    走 30 秒缓存（避免界面路径反复起 schtasks 子进程）；切换启动方式这种要
    下判断的地方传 ``force=True`` 拿新鲜值。
    """
    if not force:
        with _task_lock:
            cached = _task_cache
        if cached is not None and (time.monotonic() - cached[0]) < _TASK_CACHE_TTL:
            return cached[1]
    value = _query_task_exists()
    _store_task_cache(value)
    return value


def task_exists_cached() -> bool:
    """只读缓存（还没探测过时先当 False）；绝不阻塞界面线程。"""
    with _task_lock:
        return _task_cache[1] if _task_cache else False


def refresh_task_exists_async(on_done=None) -> None:
    """后台线程刷一遍任务状态；完成后调 ``on_done(值)``（回调里发 Qt 信号回主线程）。"""
    def work() -> None:
        value = _query_task_exists()
        _store_task_cache(value)
        if on_done is not None:
            try:
                on_done(value)
            except Exception:
                logger.exception("task-state refresh callback failed")

    threading.Thread(target=work, name="task-state-refresh", daemon=True).start()


def _app_command() -> str:
    """写进任务的启动命令：打包后是 exe 自身，源码运行时用 pythonw + 入口脚本。"""
    if getattr(sys, "frozen", False):
        return sys.executable
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    runner = pythonw if pythonw.exists() else Path(sys.executable)
    return f'{runner} "{Path(sys.argv[0]).resolve()}"'


def create_task() -> bool:
    """创建 / 覆盖「管理员自启动」任务（登录触发 + 最高权限）。需要管理员。"""
    result = _schtasks([
        "/Create", "/F", "/TN", TASK_NAME, "/TR", _app_command(),
        "/SC", "ONLOGON", "/RL", "HIGHEST",
    ])
    if result.returncode != 0:
        logger.error("创建任务计划失败: %s", (result.stderr or result.stdout).strip())
        return False
    _store_task_cache(True)
    return True


def delete_task() -> bool:
    """删掉任务；本来就不存在算成功。需要管理员（任务以最高权限注册）。"""
    if not task_exists(force=True):
        _store_task_cache(False)
        return True
    result = _schtasks(["/Delete", "/F", "/TN", TASK_NAME])
    if result.returncode != 0:
        logger.error("删除任务计划失败: %s", (result.stderr or result.stdout).strip())
        return False
    _store_task_cache(False)
    return True


def startup_state() -> str:
    """系统里的真实启动方式：admin（任务在）/ normal（注册表在）/ off。

    只读缓存、不起子进程 —— 界面路径永不阻塞；缓存由启动预热和
    ``refresh_task_exists_async`` 更新。
    """
    if sys.platform != "win32":
        return "off"
    from rin_launcher.elevation import run_on_startup_enabled

    if task_exists_cached():
        return "admin"
    return "normal" if run_on_startup_enabled() else "off"


def apply_startup_mode(mode: str) -> bool:
    """把系统的启动项调成 ``mode``；注册表与任务计划二选一，永远互斥。

    这个函数会在提权后的辅助进程里被调用（注册 / 删除最高权限任务需要管理员）。
    """
    from rin_launcher.elevation import set_run_on_startup

    if mode == "admin":
        # 开管理员自启动时顺手撤掉注册表项，避免登录时启两遍。
        set_run_on_startup(False)
        return create_task()
    if mode == "normal":
        if not delete_task():
            return False
        return set_run_on_startup(True)
    # off：两边都收拾干净。
    if not delete_task():
        return False
    return set_run_on_startup(False)


def spawn_apply_elevated(mode: str) -> bool:
    """以管理员身份拉起本程序的无界面辅助分支去调启动项（会弹一次 UAC）。"""
    from rin_launcher.elevation import run_elevated

    if getattr(sys, "frozen", False):
        return run_elevated(sys.executable, f"--set-startup-mode={mode}")
    return run_elevated(
        sys.executable,
        f'"{Path(sys.argv[0]).resolve()}" --set-startup-mode={mode}')
