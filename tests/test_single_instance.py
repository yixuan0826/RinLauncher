"""单实例消息：show / quit 命令的解析与发送。"""

from __future__ import annotations

import time
import uuid

import pytest

import rin_launcher.single_instance as si


class _FakeSocket:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def readAll(self):
        return self._payload


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setattr(si, "SERVICE_NAME", f"RinLauncher.test.{uuid.uuid4().hex}")
    instance = si.SingleInstanceServer()
    yield instance
    instance._server.close()


def test_quit_is_preferred_over_show(server):
    events: list[str] = []
    server.showRequested.connect(lambda: events.append("show"))
    server.quitRequested.connect(lambda: events.append("quit"))

    server._read(_FakeSocket(b"show\nquit\n"))

    assert events == ["quit"]


def test_unknown_payload_is_ignored(server):
    events: list[str] = []
    server.showRequested.connect(lambda: events.append("show"))
    server.quitRequested.connect(lambda: events.append("quit"))

    server._read(_FakeSocket(b"reload\n"))

    assert events == []


def test_show_round_trip(server, qapp):
    events: list[str] = []
    server.showRequested.connect(lambda: events.append("show"))

    assert si.notify_running_instance() is True
    deadline = time.monotonic() + 1.0
    while not events and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)

    assert events == ["show"]


def test_notify_rejects_unknown_command():
    with pytest.raises(ValueError):
        si.notify_running_instance("reload")
