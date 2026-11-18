"""Bounded cache, dedup, and this-hop ACK for the unfrozen V1 draft.

Timeout, retry count, and backoff are experimental defaults.
The draft still marks those three as undecided.
This module does not forward frames and does not treat a this-hop ACK
as end-to-end delivery.
"""

from __future__ import annotations

import os
from collections import OrderedDict
from dataclasses import dataclass, field

from v1frame import (
    STATUS_ACCEPTED,
    STATUS_ALREADY_HAVE,
    STATUS_BUSY,
    STATUS_EXPIRED,
    STATUS_NAME,
    AckFields,
    DataFields,
    FrameEvent,
    _address_ok,
    encode_ack,
    encode_data,
)

UINT32_MAX = 0xFFFFFFFF


@dataclass(frozen=True)
class ExperimentLimits:
    """Not frozen protocol values. Change them only as an experiment."""

    ack_timeout_ms: int = 3000
    max_retries: int = 2
    retry_backoff_ms: int = 1000
    busy_backoff_ms: int = 2000
    cache_limit: int = 16
    lifetime_ms: int = 60000
    hop_limit: int = 1


LIMITS = ExperimentLimits()


class IdentityError(Exception):
    """Boot counter could not be persisted. No new message id was issued."""


def saturate(left: int, right: int) -> int:
    if right < 0 or left < 0:
        raise ValueError("age is negative")
    if left > UINT32_MAX or right > UINT32_MAX - left:
        return UINT32_MAX
    return left + right


def age_at(anchor_age: int, anchor_ms: int, now_ms: int) -> int:
    if now_ms <= anchor_ms:
        return anchor_age
    return saturate(anchor_age, now_ms - anchor_ms)


class BootStore:
    """Persistent boot counter. Sequence stays in memory for that boot."""

    def __init__(self, directory) -> None:
        self.directory = directory
        self.file = directory / "boot"
        self.marker = directory / "initialized"

    def open_boot(self) -> int:
        self.directory.mkdir(parents=True, exist_ok=True)
        if not self.file.exists():
            if self.marker.exists():
                raise IdentityError("启动计数文件丢失，拒绝从旧编号重新开始")
            value = 1
        else:
            value = self._read()
            if value >= UINT32_MAX:
                raise IdentityError("启动计数已满，停止创建新消息")
            value += 1
        self._write(value)
        try:
            self.marker.write_bytes(b"1\n")
        except OSError as exc:
            raise IdentityError(f"写启动标记失败：{exc}") from exc
        if self._read() != value:
            raise IdentityError("启动计数写后读回不一致")
        return value

    def _read(self) -> int:
        try:
            raw = self.file.read_text(encoding="ascii")
        except OSError as exc:
            raise IdentityError(f"读启动计数失败：{exc}") from exc
        body = raw[:-1] if raw.endswith("\n") else ""
        if not raw.endswith("\n") or not body.isdigit() or str(int(body)) != body:
            raise IdentityError("启动计数文件损坏，拒绝创建新消息")
        value = int(body)
        if not 1 <= value <= UINT32_MAX:
            raise IdentityError("启动计数超出范围")
        return value

    def _write(self, value: int) -> None:
        temporary = self.directory / "boot.tmp"
        data = f"{value}\n".encode("ascii")
        try:
            with temporary.open("wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.file)
        except OSError as exc:
            raise IdentityError(f"写启动计数失败：{exc}") from exc


@dataclass
class SendRequest:
    message_id: tuple[int, int, int]
    frame: bytes
    label: str


@dataclass
class RxResult:
    lines: list[str] = field(default_factory=list)
    ack: bytes | None = None
    ack_label: str = "ACK"


@dataclass
class _Outbound:
    source_id: int
    boot_counter: int
    sequence: int
    destination_id: int
    payload: bytes
    anchor_ms: int
    wire_hop: int
    sends: int = 0
    state: str = "queued"
    deadline: int | None = None
    full_write_ms: int | None = None
    rtt_ms: int | None = None

    @property
    def message_id(self) -> tuple[int, int, int]:
        return (self.source_id, self.boot_counter, self.sequence)


@dataclass
class _Held:
    message_id: tuple[int, int, int]
    destination_id: int
    priority: int
    lifetime_ms: int
    hop_limit: int
    payload_type: int
    payload: bytes
    anchor_age: int
    anchor_ms: int
    delivered: bool = False

    def expired(self, now_ms: int) -> bool:
        return age_at(self.anchor_age, self.anchor_ms, now_ms) >= self.lifetime_ms


def _immutable(fields: DataFields) -> tuple:
    return (
        fields.destination_id,
        fields.priority,
        fields.lifetime_ms,
        fields.hop_limit,
        fields.payload_type,
        fields.payload,
    )


class NodeEngine:
    def __init__(
        self,
        local_id: int,
        peer_id: int,
        boot_counter: int,
        limits: ExperimentLimits = LIMITS,
    ) -> None:
        if boot_counter < 1 or boot_counter > UINT32_MAX:
            raise IdentityError("启动计数不可用")
        self.local_id = local_id
        self.peer_id = peer_id
        self.boot_counter = boot_counter
        self.limits = limits
        self.sequence = 0
        self.outbound: list[_Outbound] = []
        self.held: dict[tuple[int, int, int], _Held] = {}
        self.accepted_ids: list[tuple[int, int, int]] = []
        self.recent_writes: OrderedDict[tuple[int, int, int], int | None] = OrderedDict()
        self.duplicates = 0
        self.bad_crc = 0
        self.bad_length = 0
        self.intentional_bad = 0
        self.rtt_ms: list[tuple[tuple[int, int, int], int]] = []
        self.closed = False
        self.lines: list[str] = []

    def submit_text(self, text: str, now_ms: int) -> SendRequest | None:
        message = self._new_outbound(text, now_ms, reliable=True)
        self.outbound.append(message)
        return self._take_send(now_ms)

    def submit_smoke(self, text: str, now_ms: int) -> SendRequest:
        message = self._new_outbound(text, now_ms, reliable=False)
        frame = self._encode(message, now_ms)
        self._remember_write(message.message_id, None)
        return SendRequest(message.message_id, frame, self._data_label(message, "单次DATA"))

    def submit_bad_crc(self, text: str, now_ms: int) -> SendRequest:
        message = self._new_outbound(text, now_ms, reliable=False)
        self.intentional_bad += 1
        frame = self._encode(message, now_ms, bad_crc=True)
        return SendRequest(message.message_id, frame, self._data_label(message, "坏CRC测试"))

    def take_lines(self) -> list[str]:
        lines = self.lines
        self.lines = []
        return lines

    def note_write(self, request: SendRequest, accepted: int, complete: bool, error: str | None, now_ms: int) -> list[str]:
        if request.message_id in self.recent_writes and not any(
            item.message_id == request.message_id and item.state == "armed" for item in self.outbound
        ):
            if complete:
                self.recent_writes[request.message_id] = now_ms
                self.recent_writes.move_to_end(request.message_id)
                return [f"单次发送已完整写出 {request.message_id}，不等待重传。端到端未知。"]
            self.recent_writes.pop(request.message_id, None)
            return [
                f"短写或异常 id={request.message_id} accepted={accepted} complete=no "
                f"error={error or ''}。不回收编号，不记为整帧已发出。"
            ]
        message = self._find(request.message_id)
        if message is None or message.state != "armed":
            return []
        message.sends += 1
        if not complete:
            return self._fail_or_backoff(
                message,
                now_ms,
                f"短写或异常 accepted={accepted} complete=no error={error or ''}。不记为整帧已发出。",
            )
        message.full_write_ms = now_ms
        message.state = "waiting"
        message.deadline = now_ms + self.limits.ack_timeout_ms
        return [f"已完整写出 {self._data_label(message, 'DATA')}，等待本跳 ACK。端到端未知。"]

    def poll(self, now_ms: int) -> list[SendRequest]:
        if self.closed:
            return []
        self._purge(now_ms)
        waiting = [item for item in self.outbound if item.state == "waiting"]
        if waiting:
            message = waiting[0]
            if message.deadline is not None and now_ms >= message.deadline:
                self._on_timeout(message, now_ms)
            else:
                return []
        for message in self.outbound:
            if message.state in ("backoff", "busy_wait") and message.deadline is not None and now_ms >= message.deadline:
                message.state = "queued"
        return self._take_all_ready(now_ms)

    def cancel(self) -> None:
        self.closed = True
        for message in self.outbound:
            if message.state in ("queued", "armed", "waiting", "backoff", "busy_wait"):
                message.state = "cancelled"
                message.deadline = None

    def resume(self) -> None:
        self.closed = False

    def on_event(self, event: FrameEvent, now_ms: int) -> RxResult:
        if event.kind == "bad_crc":
            self.bad_crc += 1
            return RxResult(["拒收 坏 CRC。不回复 ACK，不计入唯一收包。"])
        if event.kind == "bad_length":
            self.bad_length += 1
            return RxResult([f"拒收 {event.reason}。不回复 ACK。"])
        if event.kind == "timeout":
            return RxResult([f"未收齐，已放弃：{event.reason}"])
        if event.kind == "ack" and event.ack is not None:
            return RxResult(self._on_ack(event.ack, now_ms))
        if event.kind == "crc_ok" and event.fields is not None:
            return self._on_data(event.fields, now_ms)
        if event.kind == "ignored_ack":
            return RxResult(["收到 ACK，但没有解析出状态。不作为成功。"])
        return RxResult([f"拒收 {event.reason}。不回复 ACK。"])

    def summary(self) -> str:
        holes = self.sequence_holes()
        hole_text = "无" if not holes else ",".join(
            f"{source}-{boot}-{seq}" for (source, boot), seq in holes
        )
        rtt_text = "无" if not self.rtt_ms else ",".join(str(item[1]) for item in self.rtt_ms)
        return (
            f"唯一收下 {len(self.accepted_ids)}。"
            f"同一 source+boot 的序号空洞：{hole_text}（不是无线丢包，不含坏 CRC，不跨 boot）。"
            f"重复 {self.duplicates}。"
            f"本机时钟本跳 RTT ms：{rtt_text}（不是单程，不用对端时间）。"
        )

    def sequence_holes(self) -> list[tuple[tuple[int, int], int]]:
        groups: dict[tuple[int, int], set[int]] = {}
        for source, boot, seq in self.accepted_ids:
            groups.setdefault((source, boot), set()).add(seq)
        holes: list[tuple[tuple[int, int], int]] = []
        for key, seqs in groups.items():
            for seq in range(min(seqs), max(seqs) + 1):
                if seq not in seqs:
                    holes.append((key, seq))
        return holes

    def _new_outbound(self, text: str, now_ms: int, *, reliable: bool) -> _Outbound:
        payload = text.encode("utf-8")
        if len(payload) > 132:
            raise ValueError("UTF-8 payload longer than 132 bytes")
        if reliable:
            active = [
                item for item in self.outbound
                if item.state in ("queued", "armed", "waiting", "backoff", "busy_wait")
            ]
            if len(active) >= self.limits.cache_limit:
                raise ValueError("待发队列已满，没有创建新编号")
        if self.sequence >= UINT32_MAX:
            raise IdentityError("序号已满，停止创建新消息")
        self.sequence += 1
        return _Outbound(
            source_id=self.local_id,
            boot_counter=self.boot_counter,
            sequence=self.sequence,
            destination_id=self.peer_id,
            payload=payload,
            anchor_ms=now_ms,
            wire_hop=1,
        )

    def _encode(self, message: _Outbound, now_ms: int, *, bad_crc: bool = False) -> bytes:
        age = age_at(0, message.anchor_ms, now_ms)
        if message.wire_hop != 1:
            raise RuntimeError("同一跳重传不能增加 hop")
        fields = DataFields(
            sender_id=self.local_id,
            receiver_id=self.peer_id,
            source_id=message.source_id,
            destination_id=message.destination_id,
            boot_counter=message.boot_counter,
            sequence=message.sequence,
            priority=0,
            age_ms=age,
            lifetime_ms=self.limits.lifetime_ms,
            hop_count=message.wire_hop,
            hop_limit=self.limits.hop_limit,
            payload_type=1,
            payload=message.payload,
        )
        return encode_data(fields, bad_crc=bad_crc)

    def _data_label(self, message: _Outbound, kind: str) -> str:
        return (
            f"{kind} id={message.source_id}-{message.boot_counter}-{message.sequence} "
            f"hop={message.wire_hop}"
        )

    def _take_send(self, now_ms: int) -> SendRequest | None:
        ready = self._take_all_ready(now_ms)
        return ready[0] if ready else None

    def _take_all_ready(self, now_ms: int) -> list[SendRequest]:
        if self.closed or any(item.state in ("waiting", "armed") for item in self.outbound):
            return []
        for message in self.outbound:
            if message.state != "queued":
                continue
            age = age_at(0, message.anchor_ms, now_ms)
            if age >= self.limits.lifetime_ms or message.wire_hop > self.limits.hop_limit:
                message.state = "failed"
                self.lines.append(f"本地已过期或跳数用尽 id={message.message_id}。不再发送，不是送达。")
                continue
            frame = self._encode(message, now_ms)
            message.state = "armed"
            return [SendRequest(message.message_id, frame, self._data_label(message, "DATA"))]
        return []

    def _on_timeout(self, message: _Outbound, now_ms: int) -> None:
        if message.sends >= 1 + self.limits.max_retries:
            message.state = "failed"
            message.deadline = None
            self.lines.append(
                f"有限重试结束 id={message.message_id}。本跳未确认。端到端未知。"
            )
            return
        message.state = "backoff"
        message.deadline = now_ms + self.limits.retry_backoff_ms
        self.lines.append(f"ACK 超时，稍后重传原编号 id={message.message_id}，hop 不增加。")

    def _fail_or_backoff(self, message: _Outbound, now_ms: int, line: str) -> list[str]:
        if message.sends >= 1 + self.limits.max_retries:
            message.state = "failed"
            message.deadline = None
            return [line + " 有限重试结束。端到端未知。"]
        message.state = "backoff"
        message.deadline = now_ms + self.limits.retry_backoff_ms
        return [line + " 稍后重传原编号。"]

    def _find(self, message_id: tuple[int, int, int]) -> _Outbound | None:
        for message in self.outbound:
            if message.message_id == message_id:
                return message
        return None

    def _remember_write(self, message_id: tuple[int, int, int], when: int | None) -> None:
        self.recent_writes[message_id] = when
        self.recent_writes.move_to_end(message_id)
        while len(self.recent_writes) > self.limits.cache_limit:
            self.recent_writes.popitem(last=False)

    def _trim_history(self) -> None:
        limit = self.limits.cache_limit
        if len(self.rtt_ms) > limit:
            del self.rtt_ms[: len(self.rtt_ms) - limit]
        cap = limit * 4
        if len(self.accepted_ids) > cap:
            del self.accepted_ids[: len(self.accepted_ids) - cap]
        active_states = {"queued", "armed", "waiting", "backoff", "busy_wait"}
        if len(self.outbound) <= limit:
            return
        active = [item for item in self.outbound if item.state in active_states]
        done = [item for item in self.outbound if item.state not in active_states]
        room = max(limit - len(active), 0)
        self.outbound = done[-room:] + active

    def _purge(self, now_ms: int) -> None:
        expired = [key for key, item in self.held.items() if item.expired(now_ms)]
        for key in expired:
            del self.held[key]

    def _on_ack(self, ack: AckFields, now_ms: int) -> list[str]:
        if ack.sender_id != self.peer_id or ack.receiver_id != self.local_id:
            return ["ACK 不是预期对端发给本节点。不作为成功。端到端未知。"]
        if ack.source_id == 0 or ack.boot_counter == 0 or ack.sequence == 0:
            return ["ACK 编号字段为 0。不作为成功。"]
        message_id = (ack.source_id, ack.boot_counter, ack.sequence)
        if ack.status not in STATUS_NAME:
            return [f"未知 ACK status={ack.status} id={message_id}。不作为成功。端到端未知。"]
        message = self._find(message_id)
        if message is not None and message.state in ("waiting", "backoff", "busy_wait", "queued"):
            return self._apply_status(message, ack.status, now_ms)
        written = self.recent_writes.get(message_id)
        if written is not None and ack.status in (STATUS_ACCEPTED, STATUS_ALREADY_HAVE):
            rtt = now_ms - written
            self.rtt_ms.append((message_id, rtt))
            self._trim_history()
            name = STATUS_NAME[ack.status]
            return [
                f"本跳缓存确认 {name} id={message_id} 本机RTT={rtt}ms。端到端未知。"
            ]
        return [f"ACK {STATUS_NAME[ack.status]} id={message_id} 没有匹配的等待。不作为成功。"]

    def _apply_status(self, message: _Outbound, status: int, now_ms: int) -> list[str]:
        name = STATUS_NAME[status]
        message_id = message.message_id
        if status in (STATUS_ACCEPTED, STATUS_ALREADY_HAVE):
            message.state = "hop_cached"
            message.deadline = None
            if message.full_write_ms is not None:
                message.rtt_ms = now_ms - message.full_write_ms
                self.rtt_ms.append((message_id, message.rtt_ms))
                self._trim_history()
            rtt = "无" if message.rtt_ms is None else str(message.rtt_ms)
            return [
                f"本跳缓存确认 {name} id={message_id} 本机RTT={rtt}ms。端到端未知。"
            ]
        if status == STATUS_BUSY:
            if message.sends >= 1 + self.limits.max_retries:
                message.state = "peer_busy"
                message.deadline = None
                return ["对端 BUSY，缓存未接纳。本轮不再立即重试。端到端未知。"]
            message.state = "busy_wait"
            message.deadline = now_ms + self.limits.busy_backoff_ms
            return ["对端 BUSY，缓存未接纳。结束立即重试，保留消息等待后续机会。端到端未知。"]
        message.state = "peer_expired"
        message.deadline = None
        return ["对端 EXPIRED，拒绝接收。不能记为送达。端到端未知。"]

    def _on_data(self, fields: DataFields, now_ms: int) -> RxResult:
        self._purge(now_ms)
        reason = self._reject_data(fields)
        if reason is not None:
            return RxResult([f"{reason}。不回复成功 ACK。"])
        message_id = (fields.source_id, fields.boot_counter, fields.sequence)
        if fields.age_ms >= fields.lifetime_ms and message_id not in self.held:
            return RxResult(["EXPIRED 消息已过期。不缓存。"], self._ack(fields, STATUS_EXPIRED), "ACK EXPIRED")
        current = self.held.get(message_id)
        if current is not None:
            if _immutable(fields) != (
                current.destination_id,
                current.priority,
                current.lifetime_ms,
                current.hop_limit,
                current.payload_type,
                current.payload,
            ):
                return RxResult([f"编号冲突 id={message_id}。不回复成功 ACK，不替换已有内容。"])
            self.duplicates += 1
            return RxResult(
                [f"ALREADY_HAVE id={message_id}。不重复入队，不重复显示。"],
                self._ack(fields, STATUS_ALREADY_HAVE),
                "ACK ALREADY_HAVE",
            )
        if len(self.held) >= self.limits.cache_limit:
            return RxResult(
                ["BUSY 缓存已满。未记录为成功接收。"],
                self._ack(fields, STATUS_BUSY),
                "ACK BUSY",
            )
        text = fields.payload.decode("utf-8")
        self.held[message_id] = _Held(
            message_id=message_id,
            destination_id=fields.destination_id,
            priority=fields.priority,
            lifetime_ms=fields.lifetime_ms,
            hop_limit=fields.hop_limit,
            payload_type=fields.payload_type,
            payload=fields.payload,
            anchor_age=fields.age_ms,
            anchor_ms=now_ms,
            delivered=True,
        )
        self.accepted_ids.append(message_id)
        self._trim_history()
        return RxResult(
            [f"当地应用交付 id={message_id} text={text}。这不是端到端确认。"],
            self._ack(fields, STATUS_ACCEPTED),
            "ACK ACCEPTED",
        )

    def _reject_data(self, fields: DataFields) -> str | None:
        for value in (
            fields.sender_id,
            fields.receiver_id,
            fields.source_id,
            fields.destination_id,
        ):
            if not _address_ok(value):
                return "地址非法"
        if fields.receiver_id != self.local_id:
            return "本跳地址不是本节点"
        if fields.sender_id != self.peer_id:
            return "不是预期对端"
        if fields.destination_id != self.local_id:
            return "最终目的不是本节点，本程序不转发"
        if fields.source_id == 0 or fields.boot_counter == 0 or fields.sequence == 0:
            return "消息编号字段为 0"
        if fields.priority not in (0, 1, 2):
            return "优先级不支持"
        if fields.payload_type != 1:
            return "载荷类型不是 UTF-8 文本"
        if fields.lifetime_ms == 0:
            return "有效期不满足"
        if not (1 <= fields.hop_count <= fields.hop_limit):
            return "跳数不满足"
        try:
            fields.payload.decode("utf-8")
        except UnicodeDecodeError:
            return "不是合法 UTF-8"
        return None

    def _ack(self, fields: DataFields, status: int) -> bytes:
        return encode_ack(
            AckFields(
                sender_id=self.local_id,
                receiver_id=fields.sender_id,
                source_id=fields.source_id,
                boot_counter=fields.boot_counter,
                sequence=fields.sequence,
                status=status,
            )
        )
