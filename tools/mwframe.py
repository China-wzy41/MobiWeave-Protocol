#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MobiWeave 协议 V1 参考实现（PC 端）。

用途有三：
1. 作为 Arduino 板端之外的独立实现，核对 docs/protocol/protocol-v1.md 的样例；
2. 解析板子通过 USB 串口打印出来的十六进制日志；
3. 给上位机/仿真当共用的编解码底座。

只依赖标准库。示例：
    python tools/mwframe.py --selftest
    python tools/mwframe.py --hex "A5 5A 01 01 1F 00 ... BA D0"
    python tools/mwframe.py --log capture.txt
    python tools/mwframe.py --port COM5 --baud 115200   # 需要 pyserial

本实现按 protocol-v1.md 编写，尚未经过团队评审，也没在实机上验证。
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Tuple

MAGIC = b"\xA5\x5A"
VERSION = 1
FRAME_DATA = 1
FRAME_ACK = 2

DATA_FIXED = 28          # DATA 正文中除 payload 外的固定部分
DATA_BODY_MIN = 28
DATA_BODY_MAX = 160
ACK_BODY_LEN = 15
FRAME_OVERHEAD = 8       # magic2 + version1 + type1 + len2 + crc2

ACK_STATUS = {
    0: "ACCEPTED",
    1: "ALREADY_HAVE",
    2: "BUSY",
    3: "EXPIRED",
}

PAYLOAD_TYPE = {1: "UTF-8"}


# --------------------------------------------------------------------------
# CRC-16/IBM-3740（即 CRC-16/CCITT-FALSE）
# poly=0x1021 init=0xFFFF refin=false refout=false xorout=0x0000
# --------------------------------------------------------------------------
def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


class ProtocolError(Exception):
    """帧不合法。message 是给人看的原因，stage 指明在哪一步失败。"""

    def __init__(self, reason: str, stage: str = "parse"):
        super().__init__(reason)
        self.reason = reason
        self.stage = stage


@dataclass
class Frame:
    frame_type: int
    body: bytes
    raw: bytes
    data: dict = field(default_factory=dict)

    @property
    def message_key(self) -> Optional[Tuple[int, int, int]]:
        """去重键：(source_id, boot_counter, sequence)。"""
        if self.frame_type == FRAME_DATA:
            return (self.data["source_id"], self.data["boot_counter"],
                    self.data["sequence"])
        if self.frame_type == FRAME_ACK:
            return (self.data["source_id"], self.data["boot_counter"],
                    self.data["sequence"])
        return None

    def __str__(self) -> str:
        d = self.data
        if self.frame_type == FRAME_DATA:
            return (
                "DATA {src}->{dst} via {snd}->{rcv} #({src},{boot},{seq}) "
                "pri={pri} age={age}ms life={life}ms hop={hop}/{limit} "
                "type={ptype} payload={payload!r}".format(
                    src=d["source_id"], dst=d["destination_id"],
                    snd=d["sender_id"], rcv=d["receiver_id"],
                    boot=d["boot_counter"], seq=d["sequence"],
                    pri=d["priority"], age=d["age_ms"],
                    life=d["lifetime_ms"], hop=d["hop_count"],
                    limit=d["hop_limit"], ptype=d["payload_type"],
                    payload=d["payload_text"],
                )
            )
        return (
            "ACK {snd}->{rcv} #({src},{boot},{seq}) status={status}".format(
                snd=d["sender_id"], rcv=d["receiver_id"], src=d["source_id"],
                boot=d["boot_counter"], seq=d["sequence"],
                status=d["status_name"],
            )
        )


def _u16(buf: bytes, off: int) -> int:
    return buf[off] | (buf[off + 1] << 8)


def _u32(buf: bytes, off: int) -> int:
    return (buf[off] | (buf[off + 1] << 8)
            | (buf[off + 2] << 16) | (buf[off + 3] << 24))


def _put16(value: int) -> bytes:
    return int(value).to_bytes(2, "little", signed=False)


def _put32(value: int) -> bytes:
    return int(value).to_bytes(4, "little", signed=False)


def build_frame(frame_type: int, body: bytes, version: int = VERSION) -> bytes:
    """按公共帧格式拼出完整帧（含 magic 和 CRC）。"""
    core = bytes([version, frame_type]) + _put16(len(body)) + body
    return MAGIC + core + _put16(crc16(core))


def encode_data(sender_id: int, receiver_id: int, source_id: int,
                destination_id: int, boot_counter: int, sequence: int,
                priority: int, age_ms: int, lifetime_ms: int,
                hop_count: int, hop_limit: int, payload: bytes,
                payload_type: int = 1) -> bytes:
    body = (
        _put16(sender_id) + _put16(receiver_id)
        + _put16(source_id) + _put16(destination_id)
        + _put32(boot_counter) + _put32(sequence)
        + bytes([priority])
        + _put32(age_ms) + _put32(lifetime_ms)
        + bytes([hop_count, hop_limit, payload_type])
        + payload
    )
    return build_frame(FRAME_DATA, body)


def encode_ack(sender_id: int, receiver_id: int, source_id: int,
               boot_counter: int, sequence: int, status: int) -> bytes:
    body = (_put16(sender_id) + _put16(receiver_id) + _put16(source_id)
            + _put32(boot_counter) + _put32(sequence) + bytes([status]))
    return build_frame(FRAME_ACK, body)


def decode_frame(raw: bytes) -> Frame:
    """解析一条已经定好边界的完整帧。边界不对就抛 ProtocolError。"""
    if len(raw) < FRAME_OVERHEAD:
        raise ProtocolError("帧短于最小长度 8", "length")
    if raw[0:2] != MAGIC:
        raise ProtocolError("帧头不是 A5 5A", "magic")

    version = raw[2]
    frame_type = raw[3]
    body_len = _u16(raw, 4)

    if version != VERSION:
        raise ProtocolError(f"不支持的版本 {version}", "version")
    if frame_type not in (FRAME_DATA, FRAME_ACK):
        raise ProtocolError(f"不支持的帧类型 {frame_type}", "type")
    if frame_type == FRAME_DATA and not (DATA_BODY_MIN <= body_len <= DATA_BODY_MAX):
        raise ProtocolError(f"DATA 正文长度 {body_len} 超出 28..160", "length")
    if frame_type == FRAME_ACK and body_len != ACK_BODY_LEN:
        raise ProtocolError(f"ACK 正文长度 {body_len} 应为 15", "length")
    if len(raw) != FRAME_OVERHEAD + body_len:
        raise ProtocolError(
            f"帧长 {len(raw)} 与声明 {FRAME_OVERHEAD + body_len} 不符", "length")

    got_crc = _u16(raw, len(raw) - 2)
    want_crc = crc16(raw[2:-2])
    if got_crc != want_crc:
        raise ProtocolError(
            f"CRC 不符：收到 0x{got_crc:04X} 算出 0x{want_crc:04X}", "crc")

    body = raw[6:6 + body_len]
    data = {}
    if frame_type == FRAME_DATA:
        data = {
            "sender_id": _u16(body, 0),
            "receiver_id": _u16(body, 2),
            "source_id": _u16(body, 4),
            "destination_id": _u16(body, 6),
            "boot_counter": _u32(body, 8),
            "sequence": _u32(body, 12),
            "priority": body[16],
            "age_ms": _u32(body, 17),
            "lifetime_ms": _u32(body, 21),
            "hop_count": body[25],
            "hop_limit": body[26],
            "payload_type": body[27],
            "payload": body[28:],
        }
        try:
            data["payload_text"] = data["payload"].decode("utf-8")
        except UnicodeDecodeError:
            data["payload_text"] = None
    else:
        status = body[14]
        data = {
            "sender_id": _u16(body, 0),
            "receiver_id": _u16(body, 2),
            "source_id": _u16(body, 4),
            "boot_counter": _u32(body, 6),
            "sequence": _u32(body, 10),
            "status": status,
            "status_name": ACK_STATUS.get(status, f"UNKNOWN({status})"),
        }
    return Frame(frame_type, body, raw, data)


def validate_data(frame: Frame, my_id: Optional[int] = None) -> List[str]:
    """对照 protocol-v1.md 第五轮第 6 节做正文合法性检查。

    返回问题列表，空列表表示通过。这些规则板端目前还没实现。
    """
    if frame.frame_type != FRAME_DATA:
        return ["不是 DATA 帧"]
    d = frame.data
    problems = []
    if my_id is not None and d["receiver_id"] != my_id:
        problems.append(f"本跳接收地址 {d['receiver_id']} 不是本节点 {my_id}")
    if d["source_id"] == 0 or d["sequence"] == 0 or d["boot_counter"] == 0:
        problems.append("消息编号字段含 0")
    if d["priority"] not in (0, 1, 2):
        problems.append(f"不支持的优先级 {d['priority']}")
    if d["payload_type"] not in PAYLOAD_TYPE:
        problems.append(f"不支持的载荷类型 {d['payload_type']}")
    if d["lifetime_ms"] == 0:
        problems.append("lifetime_ms 为 0")
    if d["age_ms"] >= d["lifetime_ms"]:
        problems.append("消息已过期")
    if not (1 <= d["hop_limit"]):
        problems.append("hop_limit 必须大于 0")
    if d["hop_count"] == 0 or d["hop_count"] > d["hop_limit"]:
        problems.append(f"hop_count {d['hop_count']} 不在 1..{d['hop_limit']}")
    if d["payload_text"] is None:
        problems.append("payload 不是合法 UTF-8")
    return problems


class FrameStream:
    """按字节流分帧：可能半帧、可能粘包、帧头可能出现在正文里。

    与板端 processStreamBuffer 的逻辑一致，额外记录被丢弃的坏帧原因，
    方便在日志里定位“为什么这一帧没解析出来”。
    """

    def __init__(self, max_body: int = DATA_BODY_MAX):
        self.buf = bytearray()
        self.max_body = max_body
        self.rejected: List[Tuple[str, str]] = []   # (stage, reason)

    def feed(self, chunk: bytes) -> List[Frame]:
        self.buf.extend(chunk)
        frames = []
        while True:
            start = self.buf.find(MAGIC)
            if start < 0:
                # 末尾单独的 A5 可能是下一帧帧头的前半，留着
                keep = b"\xA5" if self.buf.endswith(b"\xA5") else b""
                self.buf = bytearray(keep)
                return frames
            if start:
                del self.buf[:start]
            if len(self.buf) < 6:
                return frames

            body_len = _u16(self.buf, 4)
            frame_type = self.buf[3]
            version = self.buf[2]
            limit = self.max_body if frame_type == FRAME_DATA else ACK_BODY_LEN
            header_ok = (version == VERSION
                         and frame_type in (FRAME_DATA, FRAME_ACK)
                         and (limit == ACK_BODY_LEN and frame_type == FRAME_ACK
                              and body_len == limit
                              or frame_type == FRAME_DATA
                              and DATA_BODY_MIN <= body_len <= self.max_body))
            if not header_ok:
                self.rejected.append(("header", f"v={version} t={frame_type} len={body_len}"))
                del self.buf[:1]
                continue

            total = FRAME_OVERHEAD + body_len
            if len(self.buf) < total:
                return frames

            candidate = bytes(self.buf[:total])
            try:
                frames.append(decode_frame(candidate))
            except ProtocolError as exc:
                self.rejected.append((exc.stage, exc.reason))
                del self.buf[:1]
                continue
            del self.buf[:total]

    def flush(self) -> bytes:
        """把残留的半帧取出来（超时后调用）。"""
        leftover = bytes(self.buf)
        self.buf.clear()
        return leftover


# --------------------------------------------------------------------------
# 文档样例核对
# --------------------------------------------------------------------------
DOC_DATA = (
    "A5 5A 01 01 1F 00 01 00 02 00 01 00 03 00 07 00 00 00 0C 00 00 00 02 00 "
    "00 00 00 60 EA 00 00 01 03 01 53 4F 53 BA D0"
)
DOC_ACK = (
    "A5 5A 01 02 0F 00 02 00 01 00 01 00 07 00 00 00 0C 00 00 00 00 F0 82"
)


def _hex(text: str) -> bytes:
    return bytes.fromhex(re.sub(r"[^0-9A-Fa-f]", "", text))


def selftest() -> int:
    ok = 0
    fail = 0

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"PASS  {name}")
        else:
            fail += 1
            print(f"FAIL  {name} {detail}")

    check("CRC 标准向量 123456789 -> 0x29B1", crc16(b"123456789") == 0x29B1,
          f"得到 0x{crc16(b'123456789'):04X}")

    doc_data = _hex(DOC_DATA)
    doc_ack = _hex(DOC_ACK)

    mine_data = encode_data(1, 2, 1, 3, 7, 12, 2, 0, 60000, 1, 3, b"SOS")
    check("DATA 与文档样例逐字节一致", mine_data == doc_data,
          f"\n  自己 {mine_data.hex(' ').upper()}\n  文档 {DOC_DATA}")

    mine_ack = encode_ack(2, 1, 1, 7, 12, 0)
    check("ACK 与文档样例逐字节一致", mine_ack == doc_ack,
          f"\n  自己 {mine_ack.hex(' ').upper()}\n  文档 {DOC_ACK}")

    # 测试 A：完整帧
    f = decode_frame(doc_data)
    check("A 完整 DATA 解析", f.data["sender_id"] == 1 and f.data["payload_text"] == "SOS")
    check("A 正文长度 31 / 整帧 39", len(f.body) == 31 and len(f.raw) == 39)

    # 测试 B：分两次输入
    st = FrameStream()
    first = st.feed(doc_data[:10])
    second = st.feed(doc_data[10:])
    check("B 半帧不提前输出", first == [])
    check("B 补齐后输出一帧", len(second) == 1)

    # 测试 C：同一帧连续两次
    st = FrameStream()
    check("C 连发两帧解析出两条", len(st.feed(doc_data + doc_data)) == 2)

    # 测试 D：改载荷不改 CRC
    damaged = bytearray(doc_data)
    damaged[36] = 0x54
    st = FrameStream()
    got = st.feed(bytes(damaged))
    check("D 坏 CRC 被拒绝", got == [] and st.rejected and st.rejected[0][0] == "crc")

    # 测试 E：ACK 解析
    a = decode_frame(doc_ack)
    check("E ACK 解析", a.data["status"] == 0 and a.data["status_name"] == "ACCEPTED")
    check("E ACK 正文 15 / 整帧 23", len(a.body) == 15 and len(a.raw) == 23)

    # 额外的流式用例
    st = FrameStream()
    frames = []
    for i in range(len(doc_data)):
        frames += st.feed(doc_data[i:i + 1])
    check("逐字节最终得到一帧", len(frames) == 1)

    st = FrameStream()
    noise = bytes([0x00, 0xFF, 0xA5, 0x11, 0xA5])
    frames = st.feed(noise + doc_data)
    check("噪声后恢复", len(frames) == 1 and frames[0].data["payload_text"] == "SOS")

    st = FrameStream()
    frames = st.feed(bytes(damaged) + doc_data)
    check("坏帧后恢复", len(frames) == 1 and frames[0].data["payload_text"] == "SOS")

    # 正文里含帧头
    tricky = encode_data(1, 2, 1, 3, 7, 12, 2, 0, 60000, 1, 3, b"\xA5\x5A\xA5")
    st = FrameStream()
    frames = st.feed(tricky + doc_data)
    check("正文含 A5 5A 不误判", len(frames) == 2)

    # 长度边界
    big = encode_data(1, 2, 1, 3, 7, 1, 0, 0, 60000, 1, 3, bytes(132))
    check("最大载荷 132 可编码", len(big) == 168)
    check("最大帧可解析", decode_frame(big).data["payload"] == bytes(132))
    too_big = encode_data(1, 2, 1, 3, 7, 1, 0, 0, 60000, 1, 3, bytes(133))
    try:
        decode_frame(too_big)
        check("超长载荷被拒绝", False, "居然解析成功了")
    except ProtocolError as exc:
        check("超长载荷被拒绝", exc.stage == "length")

    # 合法性检查
    st = FrameStream()
    base = decode_frame(doc_data)
    check("合法帧无问题", validate_data(base) == [])
    check("目的地不匹配能发现",
          validate_data(base, my_id=9) and "不是本节点" in validate_data(base, my_id=9)[0])

    st = FrameStream()
    st.feed(doc_data[:10])
    check("flush 返回半帧", len(st.flush()) == 10)

    print(f"\n{ok} passed, {fail} failed")
    return 0 if fail == 0 else 1


# --------------------------------------------------------------------------
# 日志 / 串口
# --------------------------------------------------------------------------
HEX_RUN = re.compile(r"(?:\b[0-9A-Fa-f]{2}\b[\s,]*){8,}")
PURE_HEX = re.compile(r"^(?:[0-9A-Fa-f]{2}[\s,]*)+$")


def decode_log(path: str) -> int:
    """从板子打印的日志里抽出十六进制串并解析。

    兼容形如 `RX 39: A5 5A 01 ...` 或纯 hex 行的输出，
    也兼容串口监视器把长行自动折行的情况（续行接着上一行拼）。
    """
    total = 0
    pending_from = ""
    st = FrameStream()

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for lineno, line in enumerate(fh, 1):
            stripped = line.strip()
            if not stripped:
                continue

            runs = [m.group(0) for m in HEX_RUN.finditer(stripped)]
            if not runs:
                continue

            continuation = bool(PURE_HEX.match(stripped)) and bool(pending_from)
            if not continuation:
                pending_from = f"L{lineno}"
            data = _hex(stripped if continuation else runs[-1])
            for frame in st.feed(data):
                print(f"{pending_from}: {frame}")
                total += 1
            for stage, reason in st.rejected:
                print(f"{pending_from}: 丢弃（{stage}）{reason}")
            st.rejected.clear()

    leftover = st.flush()
    if leftover:
        print(f"{pending_from}: 末尾残留 {len(leftover)} 字节未成帧")
    print(f"\n共解析 {total} 帧")
    return 0


def read_port(port: str, baud: int) -> int:
    try:
        import serial  # type: ignore
    except ImportError:
        print("需要 pyserial：pip install pyserial", file=sys.stderr)
        return 2
    st = FrameStream()
    with serial.Serial(port, baud, timeout=0.2) as ser:
        print(f"监听 {port} @ {baud}，Ctrl+C 结束")
        try:
            while True:
                chunk = ser.read(256)
                if chunk:
                    for frame in st.feed(chunk):
                        print(frame, flush=True)
        except KeyboardInterrupt:
            print("\n结束")
    return 0


def main(argv: Optional[Iterable[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="MobiWeave 协议 V1 参考实现")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--selftest", action="store_true", help="跑文档样例与流式用例")
    group.add_argument("--hex", help='解析一条完整帧，例如 "A5 5A ..."')
    group.add_argument("--log", help="从日志文件里抽取十六进制并解析")
    group.add_argument("--port", help="直接读串口（需要 pyserial）")
    ap.add_argument("--baud", type=int, default=115200)
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.hex:
        try:
            frame = decode_frame(_hex(args.hex))
        except ProtocolError as exc:
            print(f"拒绝（{exc.stage}）：{exc.reason}")
            return 1
        print(frame)
        problems = validate_data(frame)
        print("正文检查：" + ("通过" if not problems else "；".join(problems)))
        return 0
    if args.log:
        return decode_log(args.log)
    return read_port(args.port, args.baud)


if __name__ == "__main__":
    sys.exit(main())
