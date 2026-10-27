"""Windows 原生 Toast。调用失败（未注册 AUMID、缺少 winrt 组件）时静默返回 False。"""

from __future__ import annotations

import logging
import sys
from xml.sax.saxutils import escape

logger = logging.getLogger(__name__)


def show(title: str, message: str, app_id: str = "Rin Launcher") -> bool:
    if sys.platform != "win32":
        return False
    try:
        from winrt.windows.data.xml.dom import XmlDocument
        from winrt.windows.ui.notifications import (
            ToastNotification,
            ToastNotificationManager,
        )

        payload = (
            '<toast><visual><binding template="ToastGeneric">'
            f"<text>{escape(title)}</text><text>{escape(message)}</text>"
            "</binding></visual></toast>"
        )
        document = XmlDocument()
        document.load_xml(payload)
        notifier = ToastNotificationManager.create_toast_notifier(app_id)
        notifier.show(ToastNotification(document))
        return True
    except Exception:  # pragma: no cover - 未注册 AUMID 时很常见
        logger.debug("Windows toast unavailable", exc_info=True)
        return False
