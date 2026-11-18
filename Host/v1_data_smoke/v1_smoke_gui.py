"""Desktop DATA/CRC smoke tool. One short frame per click. No ACK or retry."""

from __future__ import annotations

import queue
import threading
import time
from datetime import datetime
from pathlib import Path

import serial
from serial.tools import list_ports
import tkinter as tk
from tkinter import ttk

from v1frame import (
    TOOL_IDLE_TIMEOUT_S,
    StreamParser,
    business_reject,
    payload_text,
    two_node_text,
)

BAUD = 115200


def _now() -> str:
    return datetime.now().isoformat(timespec="milliseconds")


class RunFiles:
    def __init__(self, root: Path, run_id: str, node_id: int) -> None:
        folder = root / run_id
        folder.mkdir(parents=True, exist_ok=True)
        self.folder = folder
        self.tx = (folder / f"node{node_id}-tx.bin").open("ab")
        self.rx = (folder / f"node{node_id}-rx.bin").open("ab")
        self.chunks = (folder / f"node{node_id}-rx-chunks.txt").open("a", encoding="utf-8")
        self.events = (folder / f"node{node_id}-events.txt").open("a", encoding="utf-8")
        self.events.write(
            f"{_now()} run_id={run_id} node={node_id} note=串口read块不是帧 无SNR 无单程延迟\n"
        )
        self.events.flush()

    def close(self) -> None:
        for handle in (self.tx, self.rx, self.chunks, self.events):
            handle.close()


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("DATA/CRC 冒烟测试（草案未冻结）")
        self.geometry("760x560")
        self.run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.sequence = 1
        self.serial: serial.Serial | None = None
        self.files: RunFiles | None = None
        self.parser = StreamParser(idle_s=TOOL_IDLE_TIMEOUT_S)
        self.inbox: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None
        self.stop = threading.Event()
        self._build()
        self.after(50, self._drain)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _build(self) -> None:
        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="串口").grid(row=0, column=0, sticky="w")
        self.port = ttk.Combobox(top, width=28, state="readonly")
        self.port.grid(row=0, column=1, padx=4)
        ttk.Button(top, text="刷新", command=self._refresh).grid(row=0, column=2)
        ttk.Label(top, text="115200 8N1").grid(row=0, column=3, padx=8)
        self.node = tk.IntVar(value=1)
        ttk.Radiobutton(top, text="节点 1", variable=self.node, value=1).grid(row=0, column=4)
        ttk.Radiobutton(top, text="节点 2", variable=self.node, value=2).grid(row=0, column=5)
        self.connect_button = ttk.Button(top, text="连接", command=self._toggle)
        self.connect_button.grid(row=0, column=6, padx=8)

        send = ttk.Frame(self, padding=8)
        send.pack(fill="x")
        self.message = ttk.Entry(send)
        self.message.pack(side="left", fill="x", expand=True)
        ttk.Button(send, text="发一条短消息", command=self._send_text).pack(side="left", padx=4)
        ttk.Button(send, text="发送坏 CRC 测试帧", command=self._send_bad).pack(side="left")

        self.status = ttk.Label(
            self,
            padding=8,
            text=(
                f"DATA/CRC 冒烟测试。协议草案未冻结，没有 ACK/重传。"
                f" run_id={self.run_id}。解析空闲 {TOOL_IDLE_TIMEOUT_S:.0f}s 只是本工具默认。"
            ),
        )
        self.status.pack(fill="x")
        self.log = tk.Text(self, height=24, wrap="word")
        self.log.pack(fill="both", expand=True, padx=8, pady=4)
        self._refresh()
        self._write_ui("本窗口没有本地回显。对方屏幕出现内容才算收到。")

    def _refresh(self) -> None:
        current = self.port.get()
        names = [item.device for item in list_ports.comports()]
        self.port["values"] = names
        if current in names:
            self.port.set(current)
        elif names:
            self.port.set(names[0])

    def _peer(self) -> int:
        return 2 if self.node.get() == 1 else 1

    def _toggle(self) -> None:
        if self.serial is None:
            self._connect()
        else:
            self._disconnect()

    def _connect(self) -> None:
        name = self.port.get().strip()
        if not name:
            self.status.configure(text="先刷新并选择串口。")
            return
        port = serial.Serial()
        port.port = name
        port.baudrate = BAUD
        port.timeout = 0
        port.write_timeout = 0
        port.dtr = False
        port.rts = False
        try:
            port.open()
            port.dtr = False
            port.rts = False
        except serial.SerialException as exc:
            self.status.configure(text=f"打开失败：{exc}")
            return
        self.serial = port
        self.parser = StreamParser(idle_s=TOOL_IDLE_TIMEOUT_S)
        self.files = RunFiles(Path(__file__).resolve().parent / "logs", self.run_id, self.node.get())
        self.stop.clear()
        self.worker = threading.Thread(target=self._read_loop, daemon=True)
        self.worker.start()
        self.connect_button.configure(text="断开")
        self.status.configure(
            text=(
                f"已连接 {name}，本机节点 {self.node.get()}，对端 {self._peer()}。"
                "已尽量拉低 DTR/RTS；有的板子仍可能在打开端口时重启。"
                "本工具不发送 AT，也不改射频。"
            )
        )

    def _disconnect(self) -> None:
        self.stop.set()
        port = self.serial
        self.serial = None
        if port is not None:
            try:
                port.close()
            except serial.SerialException:
                pass
        if self.files is not None:
            self.files.close()
            self.files = None
        self.connect_button.configure(text="连接")
        self.status.configure(text=f"已断开。日志在 logs/{self.run_id}。")

    def _read_loop(self) -> None:
        while not self.stop.is_set():
            port = self.serial
            if port is None:
                break
            try:
                chunk = port.read(256)
            except serial.SerialException as exc:
                self.inbox.put(("error", str(exc)))
                break
            now = time.monotonic()
            if chunk and self.files is not None:
                self.files.rx.write(chunk)
                self.files.rx.flush()
                self.files.chunks.write(
                    f"{_now()} bytes={len(chunk)} note=一次read不是一帧 hex={chunk.hex()}\n"
                )
                self.files.chunks.flush()
            events = self.parser.feed(chunk, now)
            if events:
                self.inbox.put(("events", events))
            time.sleep(0.02)

    def _send(self, frame: bytes, label: str) -> None:
        port = self.serial
        files = self.files
        if port is None or files is None:
            self.status.configure(text="还没有连接。")
            return
        try:
            port.write(frame)
        except serial.SerialException as exc:
            self.status.configure(text=f"发送失败：{exc}")
            return
        files.tx.write(frame)
        files.tx.flush()
        files.events.write(f"{_now()} TX {label} bytes={len(frame)} hex={frame.hex()}\n")
        files.events.flush()
        self._write_ui(f"已发送 {label}，{len(frame)} 字节。本机屏幕不会回显。")

    def _send_text(self) -> None:
        text = self.message.get()
        if text == "":
            self.status.configure(text="先输入一条短消息。")
            return
        try:
            encoded = text.encode("utf-8")
            frame = two_node_text(self.node.get(), self._peer(), self.sequence, text)
        except ValueError as exc:
            self.status.configure(text=str(exc))
            return
        if len(encoded) > 132:
            self.status.configure(text="UTF-8 超过 132 字节，没有发送。")
            return
        seq = self.sequence
        self.sequence += 1
        self._send(frame, f"DATA seq={seq}")

    def _send_bad(self) -> None:
        if self.serial is None:
            self.status.configure(text="还没有连接。")
            return
        seq = self.sequence
        self.sequence += 1
        frame = two_node_text(
            self.node.get(), self._peer(), seq, "BAD-CRC", bad_crc=True
        )
        self._send(frame, f"坏CRC测试 seq={seq}")

    def _drain(self) -> None:
        while True:
            try:
                kind, payload = self.inbox.get_nowait()
            except queue.Empty:
                break
            if kind == "error":
                self.status.configure(text=f"串口读失败：{payload}")
                self._disconnect()
                continue
            for event in payload:
                self._show_event(event)
        self.after(50, self._drain)

    def _show_event(self, event) -> None:
        files = self.files
        if event.kind == "crc_ok" and event.fields is not None:
            reason = business_reject(event.fields, self.node.get())
            if reason is None:
                line = (
                    f"有效帧 seq={event.fields.sequence} "
                    f"sender={event.fields.sender_id} receiver={event.fields.receiver_id} "
                    f"src={event.fields.source_id} dest={event.fields.destination_id} "
                    f"crc=0x{event.crc:04X} text={payload_text(event.fields)}"
                )
            else:
                line = f"拒收 {reason} seq={event.fields.sequence} crc=0x{event.crc:04X}"
        elif event.kind == "bad_crc":
            line = "拒收 坏 CRC"
        elif event.kind == "bad_length":
            line = f"拒收 {event.reason}"
        elif event.kind == "timeout":
            line = f"未收齐，已放弃：{event.reason}"
        elif event.kind == "ignored_ack":
            line = "收到 ACK 帧，本工具不处理确认"
        else:
            line = f"拒收 {event.reason}"
        self._write_ui(line)
        if files is not None:
            seq = event.fields.sequence if event.fields is not None else ""
            files.events.write(f"{_now()} RX {line} seq={seq}\n")
            files.events.flush()

    def _write_ui(self, line: str) -> None:
        self.log.insert("end", line + "\n")
        self.log.see("end")

    def _close(self) -> None:
        self._disconnect()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
