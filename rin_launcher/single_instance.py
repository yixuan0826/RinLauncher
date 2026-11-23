"""单实例保护：第二个进程把「亮出小窗」交给已在运行的主实例，然后自己退出。

机制是 QSharedMemory 占位锁 + QLocalServer/QLocalSocket 的本地消息：

* 第一个进程 ``acquire_single_instance()`` 抢到共享内存并起一个本地服务端；
* 后来的进程发现锁被占，发一条 ``show`` 消息（运行中的实例会亮出小窗）后退出，
  不会再起第二份托盘 / 热键 / 配置监听。
"""

from __future__ import annotations

import logging
import os
import time

from PySide6.QtCore import QCoreApplication, QObject, QSharedMemory, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

logger = logging.getLogger(__name__)

# 源码 UI 验收 / 便携多开测试时给实例名加后缀；正常用户不设这个环境变量。
_SUFFIX = os.environ.get("RINLAUNCHER_INSTANCE_SUFFIX", "").strip()
#: 本地套接字名（Windows 上就是命名管道的名字）。
SERVICE_NAME = f"RinLauncher.instance{_SUFFIX}"
#: 共享内存键（判重用的占位锁）。
SHARED_KEY = f"RinLauncher-single-instance{_SUFFIX}"


def acquire_single_instance() -> QSharedMemory | None:
    """抢单实例锁：抢到返回需要保活的内存对象，已有实例在跑则返回 None。"""
    memory = QSharedMemory(SHARED_KEY)
    if memory.create(1):
        return memory
    # create 失败：要么真有实例在跑，要么上次异常退出留了残骸；
    # 能 attach 就说明锁还在（残骸在 Windows 上会随进程退出自动清掉）。
    if memory.attach():
        memory.detach()
    return None


_COMMANDS = ("show", "quit")


def notify_running_instance(command: str = "show", timeout_ms: int = 800) -> bool:
    """给已在运行的实例发一条命令；没有实例或连不上时返回 False。

    ``show`` 亮出小窗，``quit`` 要求主实例正常退出（安装 / 升级 / 卸载前用）。
    命令只认这两个值，避免把任意文本塞进主进程。
    """
    command = str(command or "").strip().lower()
    if command not in _COMMANDS:
        raise ValueError(f"unsupported single-instance command: {command!r}")
    socket = QLocalSocket()
    socket.connectToServer(SERVICE_NAME)
    if not socket.waitForConnected(timeout_ms):
        return False
    socket.write(command.encode("ascii") + b"\n")
    socket.flush()
    # QLocalSocket 在 Windows 上把数据交给命名管道前仍需要一个事件循环节拍：
    # 只调 waitForBytesWritten() 时它可能一直报 false，随后的 disconnect 会把
    # 缓冲里的命令一起丢掉。这里小步泵事件，最多等到 timeout_ms。
    deadline = time.monotonic() + timeout_ms / 1000.0
    while socket.bytesToWrite() > 0 and time.monotonic() < deadline:
        socket.waitForBytesWritten(50)
        QCoreApplication.processEvents()
    written = socket.bytesToWrite() == 0
    socket.disconnectFromServer()
    return written


class SingleInstanceServer(QObject):
    """主实例里的消息服务端：收到 ``show`` / ``quit`` 就发对应信号。"""

    showRequested = Signal()
    quitRequested = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        # 上个进程崩溃可能留下孤立的套接字名，先清一遍再监听。
        QLocalServer.removeServer(SERVICE_NAME)
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_connection)
        if not self._server.listen(SERVICE_NAME):
            logger.warning("单实例套接字监听失败：%s", self._server.errorString())

    def _on_connection(self) -> None:
        socket = self._server.nextPendingConnection()
        if socket is None:
            return
        socket.readyRead.connect(lambda s=socket: self._read(s))
        # 第二个进程发完命令就断开；短命连接有时来不及触发 readyRead，
        # 在 disconnected 时再读一次，避免 show / quit 被吞掉。
        socket.disconnected.connect(lambda s=socket: self._read(s))
        socket.disconnected.connect(socket.deleteLater)
        # 连接建立时数据一般已经到了，先读一次；没到就等 readyRead。
        self._read(socket)

    def _read(self, socket: QLocalSocket) -> None:
        try:
            payload = bytes(socket.readAll()).decode("utf-8", "replace").strip()
        except RuntimeError:
            # disconnected 与 deleteLater 的先后顺序不保证；对象已销毁时忽略。
            return
        commands = {line.strip().lower() for line in payload.splitlines()}
        # quit 优先：同一批数据里既要求退出又要求显示时，退出不能被 show 吃掉。
        if "quit" in commands:
            self.quitRequested.emit()
        elif "show" in commands:
            self.showRequested.emit()
