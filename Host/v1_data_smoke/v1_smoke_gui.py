"""Desktop DATA/CRC smoke tool. One short frame per click. No ACK or retry."""

from __future__ import annotations

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
from link import LinkSession, write_exact

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
        errors: list[str] = []
        for handle in (self.tx, self.rx, self.chunks, self.events):
            try:
                handle.close()
            except OSError as exc:
                errors.append(str(exc))
        if errors:
            raise OSError("；".join(errors))


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("DATA/CRC 冒烟测试（草案未冻结）")
        self.geometry("760x560")
        self.run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.sequence = 1
        self.session: LinkSession | None = None
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
        self.node_1 = ttk.Radiobutton(top, text="节点 1", variable=self.node, value=1)
        self.node_2 = ttk.Radiobutton(top, text="节点 2", variable=self.node, value=2)
        self.node_1.grid(row=0, column=4)
        self.node_2.grid(row=0, column=5)
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

    def _set_node_locked(self, locked: bool) -> None:
        state = "disabled" if locked else "normal"
        self.node_1.configure(state=state)
        self.node_2.configure(state=state)

    def _peer(self) -> int:
        node_id = self.session.node_id if self.session is not None else self.node.get()
        return 2 if node_id == 1 else 1

    def _toggle(self) -> None:
        if self.session is None:
            self._connect()
        else:
            self._disconnect()

    def _connect(self) -> None:
        if self.session is not None:
            self._disconnect()
        name = self.port.get().strip()
        if not name:
            self.status.configure(text="先刷新并选择串口。")
            return
        node_id = self.node.get()
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
        files = RunFiles(Path(__file__).resolve().parent / "logs", self.run_id, node_id)
        session = LinkSession(port, files, StreamParser(idle_s=TOOL_IDLE_TIMEOUT_S), node_id)
        self.session = session
        session.start(self._read_loop)
        self._set_node_locked(True)
        self.connect_button.configure(text="断开")
        self.status.configure(
            text=(
                f"已连接 {name}，本机节点 {node_id}，对端 {self._peer()}。"
                "已尽量拉低 DTR/RTS；有的板子仍可能在打开端口时重启。"
                "本工具不发送 AT，也不改射频。boot_counter 固定为 1，不保证跨重启唯一。"
            )
        )

    def _disconnect(self, because: str | None = None) -> None:
        session = self.session
        self.session = None
        self._set_node_locked(False)
        note = None
        if session is not None:
            note = session.shutdown()
        text = because or "已断开。"
        if note:
            text = f"{text} {note}"
        text += f" 日志在 logs/{self.run_id}。"
        self.connect_button.configure(text="连接")
        self.status.configure(text=text)

    def _read_loop(self, session: LinkSession) -> None:
        port = session.port
        files = session.files
        parser = session.parser
        while not session.stop.is_set():
            try:
                chunk = port.read(256)
            except serial.SerialException as exc:
                session.push(("error", str(exc)))
                break
            except OSError as exc:
                session.push(("error", str(exc)))
                break
            now = time.monotonic()
            if chunk:
                try:
                    files.rx.write(chunk)
                    files.rx.flush()
                    files.chunks.write(
                        f"{_now()} bytes={len(chunk)} note=一次read不是一帧 hex={chunk.hex()}\n"
                    )
                    files.chunks.flush()
                except OSError as exc:
                    session.push(("error", f"写接收日志失败：{exc}"))
                    break
            events = parser.feed(chunk, now)
            if events:
                session.push(("events", events))
            time.sleep(0.02)

    def _send(self, frame: bytes, label: str) -> bool:
        session = self.session
        if session is None:
            self.status.configure(text="还没有连接。")
            return False
        outcome = write_exact(session.port.write, frame)
        accepted = frame[: outcome.accepted]
        files = session.files
        try:
            if accepted:
                files.tx.write(accepted)
                files.tx.flush()
            files.events.write(
                f"{_now()} TX {label} intended={len(frame)} accepted={outcome.accepted} "
                f"complete={'yes' if outcome.complete else 'no'} "
                f"error={outcome.error or ''} hex={accepted.hex()}\n"
            )
            files.events.flush()
        except OSError as exc:
            if outcome.complete:
                self.status.configure(
                    text=f"串口已接受全部 {outcome.accepted} 字节，但日志写入失败：{exc}"
                )
            else:
                self.status.configure(
                    text=f"发送不完整（{outcome.accepted}/{len(frame)}），且日志写入失败：{exc}"
                )
            return outcome.complete
        if outcome.complete:
            self._write_ui(f"已完整发送 {label}，{outcome.accepted} 字节。本机屏幕不会回显。")
            return True
        self._write_ui(
            f"发送不完整 {label}：只写出 {outcome.accepted}/{len(frame)} 字节。"
            f"{outcome.error or ''} 不能当成整帧已发出。"
        )
        self.status.configure(text="发送不完整，不能当成整帧已发出。")
        return False

    def _send_text(self) -> None:
        text = self.message.get()
        if text == "":
            self.status.configure(text="先输入一条短消息。")
            return
        session = self.session
        if session is None:
            self.status.configure(text="还没有连接。")
            return
        try:
            encoded = text.encode("utf-8")
            frame = two_node_text(session.node_id, self._peer(), self.sequence, text)
        except ValueError as exc:
            self.status.configure(text=str(exc))
            return
        if len(encoded) > 132:
            self.status.configure(text="UTF-8 超过 132 字节，没有发送。")
            return
        seq = self.sequence
        if self._send(frame, f"DATA seq={seq}"):
            self.sequence += 1

    def _send_bad(self) -> None:
        if self.session is None:
            self.status.configure(text="还没有连接。")
            return
        seq = self.sequence
        frame = two_node_text(
            self.session.node_id, self._peer(), seq, "BAD-CRC", bad_crc=True
        )
        if self._send(frame, f"坏CRC测试 seq={seq}"):
            self.sequence += 1

    def _drain(self) -> None:
        session = self.session
        if session is not None:
            for kind, payload in session.take():
                if kind == "error":
                    self.status.configure(text=f"串口读失败：{payload}")
                    self._disconnect(because=f"串口读失败：{payload}")
                    break
                for event in payload:
                    self._show_event(session, event)
        self.after(50, self._drain)

    def _show_event(self, session: LinkSession, event) -> None:
        files = session.files
        local_id = session.node_id
        if event.kind == "crc_ok" and event.fields is not None:
            reason = business_reject(event.fields, local_id)
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
