"""Keeps one running QuickConvert: later launches (e.g. from "Send to") hand their file over.

Messages are a single JSON line {"open": "<path>"}. The receiver only ever loads the
path as an input file; nothing received is executed.
"""

from __future__ import annotations

import getpass
import json
import logging
import re
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

log = logging.getLogger("quickconvert.instance")
MAX_MESSAGE = 64 * 1024


def server_name() -> str:
    user = re.sub(r"[^A-Za-z0-9_-]", "_", getpass.getuser() or "user")
    return f"QuickConvert-{user}"


def send_to_running(path: Path | None, name: str | None = None, timeout_ms: int = 1000) -> bool:
    """Ask an already-running instance to open `path` (or just come to front). True if it answered."""
    socket = QLocalSocket()
    socket.connectToServer(name or server_name())
    if not socket.waitForConnected(timeout_ms):
        return False
    payload = {"open": str(Path(path).resolve())} if path else {"show": True}
    socket.write((json.dumps(payload) + "\n").encode("utf-8"))
    ok = socket.waitForBytesWritten(timeout_ms)
    socket.disconnectFromServer()
    return ok


class InstanceServer(QObject):
    open_requested = Signal(Path)
    show_requested = Signal()

    def __init__(self, name: str | None = None, parent: QObject | None = None):
        super().__init__(parent)
        self.name = name or server_name()
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self._on_connection)

    def listen(self) -> bool:
        if self.server.listen(self.name):
            return True
        # A crashed instance can leave a stale socket on Unix; harmless on Windows.
        QLocalServer.removeServer(self.name)
        return self.server.listen(self.name)

    def close(self) -> None:
        self.server.close()

    def _on_connection(self) -> None:
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            socket.readyRead.connect(lambda s=socket: self._read(s))
            socket.disconnected.connect(socket.deleteLater)

    def _read(self, socket: QLocalSocket) -> None:
        if not socket.canReadLine():
            if socket.bytesAvailable() > MAX_MESSAGE:
                socket.abort()
            return
        line = bytes(socket.readLine(MAX_MESSAGE)).decode("utf-8", errors="replace")
        try:
            message = json.loads(line)
        except ValueError:
            log.warning("ignored malformed instance message")
            return
        if isinstance(message, dict) and isinstance(message.get("open"), str):
            self.open_requested.emit(Path(message["open"]))
        elif isinstance(message, dict) and message.get("show"):
            self.show_requested.emit()
