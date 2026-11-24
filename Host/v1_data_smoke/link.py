"""Port write and one link session. No GUI imports."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class WriteOutcome:
    accepted: int
    complete: bool
    error: str | None


def write_exact(write, payload: bytes) -> WriteOutcome:
    """Send every byte. A short write or exception is not a complete frame."""
    sent = 0
    try:
        while sent < len(payload):
            count = write(payload[sent:])
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                return WriteOutcome(sent, False, "write 返回值无效")
            if count == 0:
                return WriteOutcome(sent, False, "短写：端口未继续接受字节")
            if count > len(payload) - sent:
                return WriteOutcome(sent, False, "write 返回超过剩余长度")
            sent += count
    except Exception as exc:
        return WriteOutcome(sent, False, f"{type(exc).__name__}: {exc}")
    return WriteOutcome(sent, True, None)


class LinkSession:
    """One connection. The reader thread only uses this session's objects."""

    def __init__(self, port, files, parser, node_id: int) -> None:
        self.port = port
        self.files = files
        self.parser = parser
        self.node_id = node_id
        self.stop = threading.Event()
        self.inbox: list = []
        self._inbox_lock = threading.Lock()
        self.worker: threading.Thread | None = None

    def start(self, target) -> None:
        self.worker = threading.Thread(target=target, args=(self,), daemon=True)
        self.worker.start()

    def push(self, item) -> None:
        with self._inbox_lock:
            self.inbox.append(item)

    def take(self) -> list:
        with self._inbox_lock:
            items = self.inbox
            self.inbox = []
        return items

    def shutdown(self, join_s: float = 2.0) -> str | None:
        """Stop the reader, wait, then close the port and log files."""
        self.stop.set()
        worker = self.worker
        notes: list[str] = []
        if worker is not None and worker is not threading.current_thread():
            worker.join(join_s)
            if worker.is_alive():
                notes.append("读线程未在时限内退出")
        try:
            self.port.close()
        except Exception as exc:
            notes.append(f"关闭串口失败：{type(exc).__name__}: {exc}")
        if worker is not None and worker is not threading.current_thread() and worker.is_alive():
            worker.join(0.5)
            if worker.is_alive() and "读线程未在时限内退出" not in notes:
                notes.append("读线程未在时限内退出")
        try:
            self.files.close()
        except Exception as exc:
            notes.append(f"关闭日志失败：{type(exc).__name__}: {exc}")
        return "；".join(notes) if notes else None
