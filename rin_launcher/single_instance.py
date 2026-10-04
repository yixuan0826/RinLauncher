"""单实例保护：第二个进程把「亮出小窗」交给已在运行的主实例，然后自己退出。

机制是 QSharedMemory 占位锁 + QLocalServer/QLocalSocket 的本地消息：

* 第一个进程 ``acquire_single_instance()`` 抢到共享内存并起一个本地服务端；
* 后来的进程发现锁被占，发一条 ``show`` 消息（运行中的实例会亮出小窗）后退出，
  不会再起第二份托盘 / 热键 / 配置监听。
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QSharedMemory, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

logger = logging.getLogger(__name__)

#: 本地套接字名（Windows 上就是命名管道的名字）。
SERVICE_NAME = "RinLauncher.instance"
#: 共享内存键（判重用的占位锁）。
SHARED_KEY = "RinLauncher-single-instance"


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


def notify_running_instance(timeout_ms: int = 800) -> bool:
    """给已在运行的实例发一条「亮出小窗」的消息；连不上返回 False。"""
    socket = QLocalSocket()
    socket.connectToServer(SERVICE_NAME)
    if not socket.waitForConnected(timeout_ms):
        return False
    socket.write(b"show\n")
    socket.flush()
    socket.waitForBytesWritten(timeout_ms)
    socket.disconnectFromServer()
    return True


class SingleInstanceServer(QObject):
    """主实例里的消息服务端：收到 ``show`` 就发 ``showRequested``。"""

    showRequested = Signal()

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
        socket.disconnected.connect(socket.deleteLater)
        # 连接建立时数据一般已经到了，先读一次；没到就等 readyRead。
        self._read(socket)

    def _read(self, socket: QLocalSocket) -> None:
        payload = bytes(socket.readAll()).decode("utf-8", "replace").strip()
        if "show" in payload:
            self.showRequested.emit()
