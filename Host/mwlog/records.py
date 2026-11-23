"""日志 V1 的逐行解析与字段校验（纯逻辑，不依赖界面）。

对应规范：docs/protocol/log-v1.md（分支 Yanis0118-patch-1，2026-11-23 冻结版）。
设计原则只有一条：**解析器不做任何猜测**。字段缺失、越界、事件未知，都记成一条
`Issue` 交给界面显示，而不是丢掉整行或补一个默认值——补默认值等于伪造证据。
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

# ---------------------------------------------------------------- 常量

FORMAT_VERSION = 1
MAX_LINE_BYTES = 4096

SOURCE_KINDS = {"REAL", "SIM", "ESTIMATED"}
CLOCK_BASES = {"node_session", "simulation_run"}
RESULTS = {"OK", "REJECTED", "RETRY", "FAILED", "INFO"}

ACK_STATUSES = {"ACCEPTED", "ALREADY_HAVE", "BUSY", "EXPIRED"}
FRAME_TYPES = {"DATA", "ACK", "UNKNOWN"}
STORAGES = {"RAM", "FLASH"}

# 事件 → (该类事件允许的 result, 出现在界面上时的中文名)
EVENT_RESULTS: Dict[str, set] = {
    "BOOT": {"INFO"},
    "MESSAGE_CREATED": {"OK"},
    "DATA_TX": {"OK"},
    "DATA_RX": {"OK"},
    "MESSAGE_CACHED": {"OK"},
    "ACK_TX": {"OK"},
    "ACK_RX": {"OK"},
    "HOP_CONFIRMED": {"OK"},
    "RETRY_SCHEDULED": {"RETRY"},
    "MESSAGE_FORWARDED": {"OK"},
    "APP_DELIVERED": {"OK"},
    "MESSAGE_EXPIRED": {"REJECTED"},
    "MESSAGE_DROPPED": {"REJECTED"},
    "TRANSFER_FAILED": {"FAILED"},
    "FRAME_REJECTED": {"REJECTED"},
    "STREAM_TIMEOUT": {"REJECTED"},
    "LINK_UP": {"OK"},
    "LINK_DOWN": {"FAILED"},
}
KNOWN_EVENTS = set(EVENT_RESULTS)

# 这些事件的 channel 必填（规范 §2 表格末行交代）。
CHANNEL_REQUIRED = {
    "DATA_TX", "ACK_TX", "MESSAGE_FORWARDED", "DATA_RX", "ACK_RX",
    "FRAME_REJECTED", "STREAM_TIMEOUT", "LINK_UP", "LINK_DOWN",
}

# 这些事件允许 message_id 为 null（链路事件不对应具体消息）。
MESSAGE_ID_OPTIONAL = {
    "BOOT", "FRAME_REJECTED", "STREAM_TIMEOUT", "LINK_UP", "LINK_DOWN",
}

# 规范 §3 建议原因码。未知码不报错，只提示——读取端不得自行解释为成功。
KNOWN_REASONS = {
    "BAD_MAGIC", "BAD_LENGTH", "BAD_CRC", "UNSUPPORTED_VERSION", "UNSUPPORTED_TYPE",
    "INVALID_ADDRESS", "INVALID_MESSAGE_ID", "INVALID_PRIORITY", "INVALID_PAYLOAD_TYPE",
    "INVALID_UTF8", "HOP_LIMIT", "ACK_TIMEOUT", "ACK_MISMATCH", "UNKNOWN_ACK_STATUS",
    "BUFFER_FULL", "EXPIRED", "DUPLICATE", "ID_CONFLICT", "RETRY_LIMIT",
    "STREAM_IDLE_TIMEOUT", "IO_ERROR",
}

RUN_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


# ---------------------------------------------------------------- 数据结构


class LogError(Exception):
    """单行无法构成有效记录。code 用于界面上的错误分类。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Issue:
    """一条导入问题。raw 保留原始行，界面可以让人看到"到底哪行坏了"。"""

    line_no: int
    level: str          # "错误" / "提示"
    code: str
    message: str
    raw: str

    def as_row(self) -> Tuple[str, str, str, str]:
        return (f"L{self.line_no}", self.level, self.message, self.raw[:200])


@dataclass
class MessageId:
    source_id: int
    boot_counter: int
    sequence: int

    @property
    def text(self) -> str:
        return f"{self.source_id}-{self.boot_counter}-{self.sequence}"


@dataclass
class Record:
    """一行业务记录。字段按规范原样保存，界面只读不造。"""

    line_no: int
    raw: str
    run_id: str
    source_kind: str
    node_id: int
    session_id: str
    event_seq: int
    monotonic_ms: int
    clock_basis: str
    event: str
    result: str
    reason: Optional[str]
    details: Dict[str, Any]
    channel: Optional[str]
    message_id: Optional[MessageId]
    code_version: Optional[str] = None
    config_version: Optional[str] = None
    strategy_version: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    # ---- 便捷读取（界面用，不改变语义）

    @property
    def known_event(self) -> bool:
        return self.event in KNOWN_EVENTS

    @property
    def dedup_key(self) -> Tuple[Any, ...]:
        """日志唯一键；去重只能按这个，不能按 message_id。"""
        return (self.run_id, self.source_kind, self.node_id, self.session_id, self.event_seq)

    @property
    def message_key(self) -> Optional[Tuple[str, str]]:
        """消息归属。同一编号跨 run 不合并——正常与重试是两次实验。"""
        if self.message_id is None:
            return None
        return (self.run_id, self.message_id.text)

    @property
    def peer_id(self) -> Optional[int]:
        value = self.details.get("peer_id")
        return value if isinstance(value, int) else None

    @property
    def destination_id(self) -> Optional[int]:
        value = self.details.get("destination_id")
        return value if isinstance(value, int) else None


@dataclass
class LoadResult:
    path: str
    records: List[Record] = field(default_factory=list)
    issues: List[Issue] = field(default_factory=list)
    total_lines: int = 0
    bad_lines: int = 0

    @property
    def errors(self) -> List[Issue]:
        return [i for i in self.issues if i.level == "错误"]

    @property
    def hints(self) -> List[Issue]:
        return [i for i in self.issues if i.level == "提示"]


# ---------------------------------------------------------------- 校验工具


def _req_int(obj: Dict[str, Any], key: str, lo: int, hi: int) -> int:
    if key not in obj:
        raise LogError("MISSING_FIELD", f"缺少必填字段 {key}")
    value = obj[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise LogError("BAD_TYPE", f"{key} 必须是整数，实际是 {type(value).__name__}")
    if not (lo <= value <= hi):
        raise LogError("OUT_OF_RANGE", f"{key}={value} 超出 {lo}～{hi}")
    return value


def _req_str(obj: Dict[str, Any], key: str) -> str:
    if key not in obj:
        raise LogError("MISSING_FIELD", f"缺少必填字段 {key}")
    value = obj[key]
    if not isinstance(value, str):
        raise LogError("BAD_TYPE", f"{key} 必须是字符串，实际是 {type(value).__name__}")
    return value


def _opt_str(obj: Dict[str, Any], key: str) -> Optional[str]:
    value = obj.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise LogError("BAD_TYPE", f"{key} 必须是字符串或 null")
    return value


def _need(details: Dict[str, Any], key: str, event: str) -> Any:
    if key not in details:
        raise LogError("MISSING_DETAIL", f"{event} 的 details 缺少 {key}")
    return details[key]


def _need_int(details: Dict[str, Any], key: str, event: str, lo: int, hi: int) -> int:
    value = _need(details, key, event)
    if isinstance(value, bool) or not isinstance(value, int):
        raise LogError("BAD_DETAIL_TYPE", f"{event}.{key} 必须是整数")
    if not (lo <= value <= hi):
        raise LogError("DETAIL_OUT_OF_RANGE", f"{event}.{key}={value} 超出 {lo}～{hi}")
    return value


# ---------------------------------------------------------------- 事件细则


def _check_details(rec: Record) -> None:
    """逐事件校验 details 必填项。规范 §3 那张表就是这段代码。"""
    d = rec.details
    e = rec.event

    if e == "MESSAGE_CREATED" or e == "APP_DELIVERED":
        _need_int(d, "destination_id", e, 1, 65534)
    elif e in ("DATA_TX", "ACK_TX", "DATA_RX", "ACK_RX", "MESSAGE_FORWARDED"):
        _need_int(d, "peer_id", e, 1, 65534)
        _need_int(d, "frame_bytes", e, 1, 4096)
        if "tx_scope" in d and d["tx_scope"] != "local_uart_queued":
            raise LogError("BAD_TX_SCOPE", "tx_scope 规范固定为 local_uart_queued")
        if e in ("DATA_TX", "ACK_TX", "MESSAGE_FORWARDED"):
            _need(d, "tx_scope", e)
        if e == "DATA_TX" or e == "MESSAGE_FORWARDED":
            _need_int(d, "attempt", e, 1, 65535)
        if e in ("ACK_TX", "ACK_RX", "HOP_CONFIRMED"):
            status = _need(d, "ack_status", e)
            if status not in ACK_STATUSES:
                raise LogError("BAD_ACK_STATUS", f"ACK 状态 {status!r} 不在规范取值内")
        if e == "HOP_CONFIRMED" and d.get("ack_status") not in ("ACCEPTED", "ALREADY_HAVE"):
            raise LogError("BAD_HOP", "HOP_CONFIRMED 只允许 ACCEPTED / ALREADY_HAVE")
    elif e == "MESSAGE_CACHED":
        storage = _need(d, "storage", e)
        if storage not in STORAGES:
            raise LogError("BAD_STORAGE", f"storage={storage!r} 只能是 RAM / FLASH")
    elif e == "RETRY_SCHEDULED":
        _need_int(d, "peer_id", e, 1, 65534)
        _need_int(d, "attempt", e, 1, 65535)
    elif e == "MESSAGE_EXPIRED":
        _need_int(d, "age_ms", e, 0, 2 ** 53 - 1)
        _need_int(d, "lifetime_ms", e, 0, 2 ** 53 - 1)
    elif e == "TRANSFER_FAILED":
        _need_int(d, "peer_id", e, 1, 65534)
        _need_int(d, "attempt", e, 1, 65535)
    elif e == "FRAME_REJECTED":
        frame_type = _need(d, "frame_type", e)
        if frame_type not in FRAME_TYPES:
            raise LogError("BAD_FRAME_TYPE", f"frame_type={frame_type!r} 只能是 DATA/ACK/UNKNOWN")
    elif e == "STREAM_TIMEOUT":
        _need_int(d, "pending_bytes", e, 0, 2 ** 31 - 1)
    elif e == "LINK_UP":
        _need_int(d, "peer_id", e, 1, 65534)
        basis = _need(d, "basis", e)
        if basis not in ("ack_ok", "data_rx"):
            raise LogError("BAD_BASIS", f"LINK_UP.basis={basis!r} 只能是 ack_ok / data_rx")
    elif e == "LINK_DOWN":
        _need_int(d, "peer_id", e, 1, 65534)
        basis = _need(d, "basis", e)
        if basis not in ("ack_timeout", "no_rx_timeout"):
            raise LogError("BAD_BASIS", f"LINK_DOWN.basis={basis!r} 只能是 ack_timeout / no_rx_timeout")
        _need_int(d, "consecutive_failures", e, 1, 65535)


# ---------------------------------------------------------------- 单行解析


def parse_line(line: str, line_no: int) -> Tuple[Optional[Record], List[Issue]]:
    """解析一行。返回 (记录或 None, 问题列表)。

    能构成记录就返回记录；字段层面的"提示"会一起带出来，不阻断显示。
    """
    raw = line.rstrip("\r\n")
    issues: List[Issue] = []

    def hint(code: str, message: str) -> None:
        issues.append(Issue(line_no, "提示", code, message, raw))

    if not raw.strip():
        issues.append(Issue(line_no, "错误", "EMPTY_LINE", "空行不是合法记录（规范 §1）", raw))
        return None, issues

    if len(raw.encode("utf-8")) > MAX_LINE_BYTES:
        issues.append(Issue(line_no, "错误", "LINE_TOO_LONG",
                            f"行长超过 {MAX_LINE_BYTES} 字节，不能截断后当有效 JSON", raw))
        return None, issues

    if raw.startswith("\ufeff"):
        raw = raw.lstrip("\ufeff")
        hint("BOM", "该行带 BOM，已按规范忽略；写日志的一侧应去掉 BOM")

    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        issues.append(Issue(line_no, "错误", "NOT_JSON",
                            f"不是完整 JSON（{exc.msg}，第 {exc.colno} 列）：可能是半行或串口调试文本", raw))
        return None, issues

    if not isinstance(obj, dict):
        issues.append(Issue(line_no, "错误", "NOT_OBJECT", "顶层必须是 JSON 对象", raw))
        return None, issues

    try:
        fmt = _req_int(obj, "format_version", 1, 1 << 30)
        if fmt != FORMAT_VERSION:
            raise LogError("UNSUPPORTED_VERSION", f"format_version={fmt} 不是本读取端支持的 V1")

        run_id = _req_str(obj, "run_id")
        if not RUN_ID_RE.match(run_id):
            raise LogError("BAD_RUN_ID", "run_id 只能由字母数字与 . _ - 组成，长度 1～64")

        source_kind = _req_str(obj, "source_kind")
        if source_kind not in SOURCE_KINDS:
            raise LogError("BAD_SOURCE_KIND", f"source_kind={source_kind!r} 只能是 REAL/SIM/ESTIMATED")

        node_id = _req_int(obj, "node_id", 1, 65534)
        session_id = _req_str(obj, "session_id")
        if not (1 <= len(session_id) <= 64):
            raise LogError("BAD_SESSION_ID", "session_id 长度应为 1～64")
        event_seq = _req_int(obj, "event_seq", 1, 4294967295)
        monotonic_ms = _req_int(obj, "monotonic_ms", 0, 9007199254740991)

        clock_basis = _req_str(obj, "clock_basis")
        if clock_basis not in CLOCK_BASES:
            raise LogError("BAD_CLOCK_BASIS", "clock_basis 只能是 node_session / simulation_run")
        if source_kind == "REAL" and clock_basis != "node_session":
            raise LogError("CLOCK_MISMATCH", "REAL 记录必须用 node_session")
        if source_kind == "SIM" and clock_basis != "simulation_run":
            raise LogError("CLOCK_MISMATCH", "SIM 记录必须用 simulation_run")

        event = _req_str(obj, "event")
        result = _req_str(obj, "result")
        if result not in RESULTS:
            raise LogError("BAD_RESULT", f"result={result!r} 不在 OK/REJECTED/RETRY/FAILED/INFO 内")

        reason = _opt_str(obj, "reason")
        if result == "OK" and reason is not None:
            raise LogError("REASON_ON_OK", "result=OK 时 reason 必须为 null（规范 §2）")
        if result in ("REJECTED", "RETRY", "FAILED") and reason is None:
            raise LogError("MISSING_REASON", f"result={result} 必须带原因码")
        if result == "INFO" and reason is not None:
            raise LogError("REASON_ON_INFO", "result=INFO 时 reason 必须为 null")

        details = obj.get("details", {})
        if not isinstance(details, dict):
            raise LogError("BAD_DETAILS", "details 必须是对象（无附加信息用 {}）")

        channel = _opt_str(obj, "channel")

        message_id: Optional[MessageId] = None
        raw_mid = obj.get("message_id")
        if raw_mid is not None:
            if not isinstance(raw_mid, dict):
                raise LogError("BAD_MESSAGE_ID", "message_id 必须是对象或 null")
            message_id = MessageId(
                source_id=_req_int(raw_mid, "source_id", 1, 65534),
                boot_counter=_req_int(raw_mid, "boot_counter", 1, 4294967295),
                sequence=_req_int(raw_mid, "sequence", 1, 4294967295),
            )

        rec = Record(
            line_no=line_no, raw=raw, run_id=run_id, source_kind=source_kind,
            node_id=node_id, session_id=session_id, event_seq=event_seq,
            monotonic_ms=monotonic_ms, clock_basis=clock_basis, event=event,
            result=result, reason=reason, details=details, channel=channel,
            message_id=message_id,
            code_version=_opt_str(obj, "code_version"),
            config_version=_opt_str(obj, "config_version"),
            strategy_version=_opt_str(obj, "strategy_version"),
        )
    except LogError as exc:
        issues.append(Issue(line_no, "错误", exc.code, exc.message, raw))
        return None, issues

    # ---- 以下是"能读但不合规"的软问题：保留记录，标提示。

    if event not in KNOWN_EVENTS:
        hint("UNKNOWN_EVENT", f"未知事件 {event}：只展示原文，不参与指标计算")
    else:
        allowed = EVENT_RESULTS[event]
        if result not in allowed:
            hint("RESULT_MISMATCH",
                 f"{event} 的 result 应为 {'/'.join(sorted(allowed))}，实际是 {result}")

    if rec.message_id is None and event not in MESSAGE_ID_OPTIONAL:
        hint("MESSAGE_ID_MISSING", f"{event} 应有 message_id，实际为 null")
    if rec.message_id is not None and event in MESSAGE_ID_OPTIONAL:
        hint("MESSAGE_ID_UNEXPECTED", f"{event} 不对应具体消息，message_id 通常为 null")

    if event in CHANNEL_REQUIRED and not rec.channel:
        hint("CHANNEL_MISSING", f"{event} 的 channel 必填（uart0 调试口 / uart1 LoRa 口）")

    if rec.reason and rec.reason not in KNOWN_REASONS:
        hint("UNKNOWN_REASON", f"未知原因码 {rec.reason}：展示原文，不解释为成功")

    try:
        _check_details(rec)
    except LogError as exc:
        hint(exc.code, f"details 不合规：{exc.message}")

    return rec, issues


# ---------------------------------------------------------------- 文件入口


def read_lines(path: str) -> Tuple[List[str], Optional[Issue]]:
    """按字节读全文再切行：读取端要能处理"最后一行没换行"（半行）。"""
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except FileNotFoundError:
        return [], Issue(0, "错误", "FILE_NOT_FOUND", f"文件不存在：{path}", "")
    except IsADirectoryError:
        return [], Issue(0, "错误", "IS_DIRECTORY", f"这是目录不是文件：{path}", "")
    except OSError as exc:
        return [], Issue(0, "错误", "READ_FAILED", f"读取失败：{exc}", "")

    if not data:
        return [], Issue(0, "提示", "EMPTY_FILE", "文件是空的", "")

    for encoding in ("utf-8", "utf-8-sig"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        return [], Issue(0, "错误", "NOT_UTF8", "文件不是 UTF-8 文本，按规范拒绝导入", "")

    return text.split("\n"), None


def load_file(path: str) -> LoadResult:
    result = LoadResult(path=os.fspath(path))
    lines, fatal = read_lines(path)
    if fatal is not None:
        result.issues.append(fatal)
        return result

    seen: Dict[Tuple[Any, ...], int] = {}
    for index, line in enumerate(lines, start=1):
        if index == len(lines) and line == "":
            break  # 文件尾部的换行，不是记录
        result.total_lines += 1
        rec, issues = parse_line(line, index)
        if rec is None:
            result.bad_lines += 1
            result.issues.extend(issues)
            continue
        key = rec.dedup_key
        if key in seen:
            result.issues.append(Issue(
                index, "提示", "DUPLICATE_KEY",
                f"与第 {seen[key]} 行是同一个唯一键（run/来源/节点/会话/序号），已跳过", rec.raw))
            continue
        seen[key] = index
        result.records.append(rec)
        result.issues.extend(issues)
    return result


def load_lines(paths: Iterable[str]) -> LoadResult:
    """把多个文件当成一份日志读（多串口 / 多节点分别落盘时用）。"""
    merged: Optional[LoadResult] = None
    for path in paths:
        part = load_file(path)
        if merged is None:
            merged = LoadResult(path=os.fspath(path))
        merged.records.extend(part.records)
        merged.issues.extend(part.issues)
        merged.total_lines += part.total_lines
        merged.bad_lines += part.bad_lines
    return merged or LoadResult(path="")
