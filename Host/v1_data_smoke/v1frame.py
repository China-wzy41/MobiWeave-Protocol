"""DATA frame codec for the unfrozen MobiWeave V1 draft.

Field layout follows docs/protocol/protocol-v1.md on main.
This module does not implement ACK, retry, cache, or deduplication.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

MAGIC = b"\xA5\x5A"
VERSION = 1
FRAME_DATA = 1
FRAME_ACK = 2
MAX_BODY = 160
MAX_FRAME = 8 + MAX_BODY
DATA_HEAD = 28
MAX_PAYLOAD = 132
# Tool experiment only. The draft says the parse timeout is not frozen.
TOOL_IDLE_TIMEOUT_S = 1.0

PRIORITY_OK = {0, 1, 2}
PAYLOAD_TEXT = 1


def crc16_ibm3740(data: bytes) -> int:
    """CRC-16/IBM-3740, also called CRC-16/CCITT-FALSE."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def _address_ok(value: int) -> bool:
    return 1 <= value <= 65534


@dataclass(frozen=True)
class DataFields:
    sender_id: int
    receiver_id: int
    source_id: int
    destination_id: int
    boot_counter: int
    sequence: int
    priority: int
    age_ms: int
    lifetime_ms: int
    hop_count: int
    hop_limit: int
    payload_type: int
    payload: bytes

    @property
    def crc_covered_body(self) -> bytes:
        return struct.pack(
            "<HHHHIIBIIBBB",
            self.sender_id,
            self.receiver_id,
            self.source_id,
            self.destination_id,
            self.boot_counter,
            self.sequence,
            self.priority,
            self.age_ms,
            self.lifetime_ms,
            self.hop_count,
            self.hop_limit,
            self.payload_type,
        ) + self.payload


def encode_data(fields: DataFields, *, bad_crc: bool = False) -> bytes:
    body = fields.crc_covered_body
    if not 28 <= len(body) <= MAX_BODY:
        raise ValueError("DATA body length out of range")
    covered = struct.pack("<BBH", VERSION, FRAME_DATA, len(body)) + body
    crc = crc16_ibm3740(covered)
    if bad_crc:
        crc ^= 0x00FF
    return MAGIC + covered + struct.pack("<H", crc)


def two_node_text(
    local_id: int,
    peer_id: int,
    sequence: int,
    text: str,
    *,
    boot_counter: int = 1,
    bad_crc: bool = False,
) -> bytes:
    """Direct delivery: source is local, next hop and final dest are the peer."""
    payload = text.encode("utf-8")
    if len(payload) > MAX_PAYLOAD:
        raise ValueError("UTF-8 payload longer than 132 bytes")
    fields = DataFields(
        sender_id=local_id,
        receiver_id=peer_id,
        source_id=local_id,
        destination_id=peer_id,
        boot_counter=boot_counter,
        sequence=sequence,
        priority=0,
        age_ms=0,
        lifetime_ms=60000,
        hop_count=1,
        hop_limit=1,
        payload_type=PAYLOAD_TEXT,
        payload=payload,
    )
    return encode_data(fields, bad_crc=bad_crc)


@dataclass(frozen=True)
class FrameEvent:
    kind: str
    frame: bytes
    reason: str
    fields: DataFields | None = None
    crc: int | None = None
    text: str | None = None


class StreamParser:
    """Byte-stream parser. One read() chunk is not a frame boundary."""

    def __init__(self, idle_s: float = TOOL_IDLE_TIMEOUT_S) -> None:
        self.idle_s = idle_s
        self.buf = bytearray()
        self._last_data_at: float | None = None

    def feed(self, data: bytes, now: float) -> list[FrameEvent]:
        if data:
            self.buf.extend(data)
            self._last_data_at = now
        events: list[FrameEvent] = []
        self._expire(now, events)
        while self._step(events):
            pass
        if len(self.buf) > MAX_FRAME:
            self.buf = self.buf[-1:]
        return events

    def _expire(self, now: float, events: list[FrameEvent]) -> None:
        if not self.buf.startswith(MAGIC) or self._last_data_at is None:
            return
        if now - self._last_data_at < self.idle_s:
            return
        if len(self.buf) >= 6:
            body_length = struct.unpack_from("<H", self.buf, 4)[0]
            if body_length <= MAX_BODY and len(self.buf) >= 8 + body_length:
                return
        events.append(
            FrameEvent("timeout", bytes(self.buf[:1]), "工具默认空闲超时，不是冻结的协议超时")
        )
        del self.buf[0]

    def _step(self, events: list[FrameEvent]) -> bool:
        if not self.buf:
            return False
        index = self.buf.find(MAGIC)
        if index < 0:
            if self.buf[-1] == MAGIC[0]:
                if len(self.buf) > 1:
                    del self.buf[:-1]
                    return True
                return False
            self.buf.clear()
            return False
        if index > 0:
            del self.buf[:index]
            return True
        if len(self.buf) < 6:
            return False
        version = self.buf[2]
        frame_type = self.buf[3]
        body_length = struct.unpack_from("<H", self.buf, 4)[0]
        if version != VERSION or frame_type not in (FRAME_DATA, FRAME_ACK) or body_length > MAX_BODY:
            events.append(FrameEvent("bad_length", bytes(self.buf[:6]), "版本、类型或正文长度非法"))
            del self.buf[0]
            return True
        need = 8 + body_length
        if len(self.buf) < need:
            return False
        frame = bytes(self.buf[:need])
        covered = frame[2:-2]
        expect = struct.unpack_from("<H", frame, need - 2)[0]
        actual = crc16_ibm3740(covered)
        if actual != expect:
            events.append(FrameEvent("bad_crc", frame, "CRC 不符", crc=actual))
            del self.buf[0]
            return True
        del self.buf[:need]
        if frame_type == FRAME_ACK:
            events.append(FrameEvent("ignored_ack", frame, "收到 ACK，本工具不处理确认", crc=actual))
            return True
        fields = _parse_data_body(frame[6:-2])
        if isinstance(fields, str):
            events.append(FrameEvent("bad_length", frame, fields, crc=actual))
            return True
        events.append(FrameEvent("crc_ok", frame, "CRC 通过", fields=fields, crc=actual))
        return True


def _parse_data_body(body: bytes) -> DataFields | str:
    if not DATA_HEAD <= len(body) <= MAX_BODY:
        return "DATA 正文长度不在 28～160"
    head = struct.unpack_from("<HHHHIIBIIBBB", body)
    payload = body[DATA_HEAD:]
    if len(payload) > MAX_PAYLOAD:
        return "载荷超过 132 字节"
    return DataFields(
        sender_id=head[0],
        receiver_id=head[1],
        source_id=head[2],
        destination_id=head[3],
        boot_counter=head[4],
        sequence=head[5],
        priority=head[6],
        age_ms=head[7],
        lifetime_ms=head[8],
        hop_count=head[9],
        hop_limit=head[10],
        payload_type=head[11],
        payload=payload,
    )


def business_reject(fields: DataFields, local_id: int) -> str | None:
    """Return a rejection reason, or None when the DATA frame can be shown."""
    for value in (
        fields.sender_id,
        fields.receiver_id,
        fields.source_id,
        fields.destination_id,
    ):
        if not _address_ok(value):
            return "地址非法"
    if fields.receiver_id != local_id:
        return "本跳地址不是本节点"
    if fields.destination_id != local_id:
        return "最终目的不是本节点，本工具只做直达"
    if fields.source_id == 0 or fields.boot_counter == 0 or fields.sequence == 0:
        return "消息编号字段为 0"
    if fields.priority not in PRIORITY_OK:
        return "优先级不支持"
    if fields.payload_type != PAYLOAD_TEXT:
        return "载荷类型不是 UTF-8 文本"
    if fields.lifetime_ms == 0 or fields.age_ms >= fields.lifetime_ms:
        return "有效期不满足"
    if not (1 <= fields.hop_count <= fields.hop_limit):
        return "跳数不满足"
    try:
        fields.payload.decode("utf-8")
    except UnicodeDecodeError:
        return "不是合法 UTF-8"
    return None


def payload_text(fields: DataFields) -> str:
    return fields.payload.decode("utf-8")


DOC_SOS_FRAME = bytes.fromhex(
    "A55A01011F000100020001000300070000000C000000020000000060EA0000010301534F53BAD0"
)
