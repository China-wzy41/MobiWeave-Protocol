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
)
from link import LinkSession, write_exact
from reliable import LIMITS, BootStore, IdentityError, NodeEngine

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
        self.session: LinkSession | None = None
        self.engine: NodeEngine | None = None
        self.engines: dict[int, NodeEngine] = {}
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
        ttk.Button(send, text="可靠发送", command=self._send_reliable).pack(side="left", padx=4)
        ttk.Button(send, text="发送坏 CRC 测试帧", command=self._send_bad).pack(side="left")

        self.status = ttk.Label(
            self,
            padding=8,
            text=(
                f"DATA/CRC 与本跳 ACK 实验。草案未冻结。"
                f" ACK 超时 {LIMITS.ack_timeout_ms} ms、最多再重试 {LIMITS.max_retries} 次、"
                f"退避 {LIMITS.retry_backoff_ms} ms 只是本工具默认。"
                f" run_id={self.run_id}。解析空闲 {TOOL_IDLE_TIMEOUT_S:.0f}s 也不是冻结超时。"
            ),
        )
        self.status.pack(fill="x")
        self.stats = ttk.Label(self, padding=(8, 0), text="尚未连接。统计不是无线丢包率。")
        self.stats.pack(fill="x")
        self.log = tk.Text(self, height=24, wrap="word")
        self.log.pack(fill="both", expand=True, padx=8, pady=4)
        self._refresh()
        self._write_ui("本窗口没有本地回显。当地应用交付只表示本机收下，不是端到端确认。")

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
        try:
            engine = self._engine_for(node_id)
        except IdentityError as exc:
            try:
                port.close()
            except serial.SerialException:
                pass
            self.status.configure(text=str(exc))
            return
        files = RunFiles(Path(__file__).resolve().parent / "logs", self.run_id, node_id)
        session = LinkSession(port, files, StreamParser(idle_s=TOOL_IDLE_TIMEOUT_S), node_id)
        self.session = session
        self.engine = engine
        session.start(self._read_loop)
        self._set_node_locked(True)
        self.connect_button.configure(text="断开")
        self.status.configure(
            text=(
                f"已连接 {name}，本机节点 {node_id}，对端 {self._peer()}，"
                f"boot={engine.boot_counter}。"
                "已尽量拉低 DTR/RTS；有的板子仍可能在打开端口时重启。"
                "本工具不发送 AT，也不改射频。本跳 ACK 不是端到端交付。"
            )
        )
        self._refresh_stats()

    def _engine_for(self, node_id: int) -> NodeEngine:
        engine = self.engines.get(node_id)
        if engine is None:
            store = BootStore(Path(__file__).resolve().parent / "state" / f"node-{node_id}")
            boot = store.open_boot()
            peer = 2 if node_id == 1 else 1
            engine = NodeEngine(node_id, peer, boot, LIMITS)
            self.engines[node_id] = engine
        engine.resume()
        return engine

    def _disconnect(self, because: str | None = None) -> None:
        if self.engine is not None:
            self.engine.cancel()
            self.engine = None
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

    def _send(self, frame: bytes, label: str):
        session = self.session
        if session is None:
            self.status.configure(text="还没有连接。")
            return None
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
            return outcome
        if outcome.complete:
            self._write_ui(f"已完整发送 {label}，{outcome.accepted} 字节。本机屏幕不会回显。")
            return outcome
        self._write_ui(
            f"发送不完整 {label}：只写出 {outcome.accepted}/{len(frame)} 字节。"
            f"{outcome.error or ''} 不能当成整帧已发出。"
        )
        self.status.configure(text="发送不完整，不能当成整帧已发出。")
        return outcome

    def _clock(self) -> int:
        return int(time.monotonic() * 1000)

    def _require_engine(self) -> NodeEngine | None:
        if self.session is None or self.engine is None:
            self.status.configure(text="还没有连接。")
            return None
        return self.engine

    def _emit(self, request, engine: NodeEngine) -> None:
        outcome = self._send(request.frame, request.label)
        if outcome is None:
            return
        now = self._clock()
        for line in engine.note_write(
            request, outcome.accepted, outcome.complete, outcome.error, now
        ):
            self._log_line(line)
        self._refresh_stats()

    def _send_text(self) -> None:
        engine = self._require_engine()
        if engine is None:
            return
        text = self.message.get()
        if text == "":
            self.status.configure(text="先输入一条短消息。")
            return
        try:
            request = engine.submit_smoke(text, self._clock())
        except (ValueError, IdentityError) as exc:
            self.status.configure(text=str(exc))
            return
        self._emit(request, engine)

    def _send_reliable(self) -> None:
        engine = self._require_engine()
        if engine is None:
            return
        text = self.message.get()
        if text == "":
            self.status.configure(text="先输入一条短消息。")
            return
        try:
            request = engine.submit_text(text, self._clock())
        except (ValueError, IdentityError) as exc:
            self.status.configure(text=str(exc))
            return
        if request is None:
            self._write_ui("已排队，等当前这一条的本跳确认或超时后再发。")
        else:
            self._emit(request, engine)
        self._flush_engine()

    def _send_bad(self) -> None:
        engine = self._require_engine()
        if engine is None:
            return
        try:
            request = engine.submit_bad_crc("BAD-CRC", self._clock())
        except (ValueError, IdentityError) as exc:
            self.status.configure(text=str(exc))
            return
        self._emit(request, engine)

    def _drain(self) -> None:
        session = self.session
        engine = self.engine
        if session is not None and engine is not None:
            for kind, payload in session.take():
                if kind == "error":
                    self.status.configure(text=f"串口读失败：{payload}")
                    self._disconnect(because=f"串口读失败：{payload}")
                    break
                for event in payload:
                    result = engine.on_event(event, self._clock())
                    for line in result.lines:
                        self._log_line(line)
                    if result.ack:
                        self._send(result.ack, result.ack_label)
            self._flush_engine()
        self.after(50, self._drain)

    def _flush_engine(self) -> None:
        session = self.session
        engine = self.engine
        if session is None or engine is None:
            return
        now = self._clock()
        for request in engine.poll(now):
            self._emit(request, engine)
        for line in engine.take_lines():
            self._log_line(line)
        self._refresh_stats()

    def _log_line(self, line: str) -> None:
        self._write_ui(line)
        session = self.session
        if session is None:
            return
        try:
            session.files.events.write(f"{_now()} {line}\n")
            session.files.events.flush()
        except OSError as exc:
            self.status.configure(text=f"日志写入失败：{exc}")

    def _refresh_stats(self) -> None:
        if self.engine is None:
            return
        self.stats.configure(text=self.engine.summary())

    def _write_ui(self, line: str) -> None:
        self.log.insert("end", line + "\n")
        end = int(self.log.index("end-1c").split(".")[0])
        if end > 200:
            self.log.delete("1.0", f"{end - 200}.0")
        self.log.see("end")

    def _close(self) -> None:
        self._disconnect()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
