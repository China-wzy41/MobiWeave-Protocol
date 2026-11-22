#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MobiWeave 日志 V1 校验器。

用法：
    python tools/mwlog_check.py docs/protocol/examples/*.jsonl
    python tools/mwlog_check.py --strict capture.jsonl

校验 docs/protocol/log-v1.md 第 2、3 节的规定：必填字段、类型范围、事件与结果约束、
details 必填项、channel 归属、唯一键和单调时间。非 JSON 行按规范视为「非结构化调试行」，
默认只提示；加 --strict 视为错误。

退出码：0 全部通过；1 有错误。
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from collections import defaultdict
from typing import Any, Dict, List

MAX_EVENT_SEQ = 4294967295
MAX_COUNTER = 4294967295
MAX_MONOTONIC = 9007199254740991

RUN_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

SOURCE_KINDS = {"REAL", "SIM", "ESTIMATED"}
RESULTS = {"OK", "REJECTED", "RETRY", "FAILED", "INFO"}
CLOCK_BASIS = {"node_session", "simulation_run"}

# event -> (允许的 result 集合, details 必填键集合, 是否允许 message_id 为 null)
EVENTS: Dict[str, tuple] = {
    "BOOT": ({"INFO"}, set(), True),
    "MESSAGE_CREATED": ({"OK"}, {"destination_id"}, False),
    "DATA_TX": ({"OK"}, {"peer_id", "attempt", "frame_bytes", "tx_scope"}, False),
    "DATA_RX": ({"OK"}, {"peer_id", "frame_bytes"}, False),
    "MESSAGE_CACHED": ({"OK"}, {"storage"}, False),
    "ACK_TX": ({"OK"}, {"peer_id", "ack_status", "frame_bytes", "tx_scope"}, False),
    "ACK_RX": ({"OK"}, {"peer_id", "ack_status", "frame_bytes"}, False),
    "HOP_CONFIRMED": ({"OK"}, {"peer_id", "ack_status"}, False),
    "RETRY_SCHEDULED": ({"RETRY"}, {"peer_id", "attempt"}, False),
    "MESSAGE_FORWARDED": ({"OK"}, {"peer_id", "attempt", "frame_bytes", "tx_scope"}, False),
    "APP_DELIVERED": ({"OK"}, {"destination_id"}, False),
    "MESSAGE_EXPIRED": ({"REJECTED"}, {"age_ms", "lifetime_ms"}, False),
    "MESSAGE_DROPPED": ({"REJECTED"}, set(), False),
    "TRANSFER_FAILED": ({"FAILED"}, {"peer_id", "attempt"}, False),
    "FRAME_REJECTED": ({"REJECTED"}, {"frame_type"}, True),
    "STREAM_TIMEOUT": ({"REJECTED"}, {"pending_bytes"}, True),
    "LINK_UP": ({"OK"}, {"peer_id", "basis"}, True),
    "LINK_DOWN": ({"FAILED"}, {"peer_id", "basis", "consecutive_failures"}, True),
}

# 这些事件必须带顶层 channel
CHANNEL_REQUIRED = {
    "DATA_TX", "ACK_TX", "MESSAGE_FORWARDED", "DATA_RX", "ACK_RX",
    "FRAME_REJECTED", "STREAM_TIMEOUT", "LINK_UP", "LINK_DOWN",
}
CHANNELS = {"uart0", "uart1"}

ACK_STATUS = {"ACCEPTED", "ALREADY_HAVE", "BUSY", "EXPIRED"}
STORAGE = {"RAM", "FLASH"}
FRAME_TYPE = {"DATA", "ACK", "UNKNOWN"}
LINK_UP_BASIS = {"ack_ok", "data_rx"}
LINK_DOWN_BASIS = {"ack_timeout", "no_rx_timeout"}

REASONS = {
    "BAD_MAGIC", "BAD_LENGTH", "BAD_CRC", "UNSUPPORTED_VERSION", "UNSUPPORTED_TYPE",
    "INVALID_ADDRESS", "INVALID_MESSAGE_ID", "INVALID_PRIORITY", "INVALID_PAYLOAD_TYPE",
    "INVALID_UTF8", "HOP_LIMIT", "ACK_TIMEOUT", "ACK_MISMATCH", "UNKNOWN_ACK_STATUS",
    "BUFFER_FULL", "EXPIRED", "DUPLICATE", "ID_CONFLICT", "RETRY_LIMIT",
    "STREAM_IDLE_TIMEOUT", "IO_ERROR",
}

REQUIRED_KEYS = [
    "format_version", "run_id", "source_kind", "code_version", "config_version",
    "strategy_version", "node_id", "session_id", "event_seq", "monotonic_ms",
    "clock_basis", "message_id", "event", "result", "reason", "details",
]

ALLOWED_KEYS = set(REQUIRED_KEYS) | {"channel"}


def is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


class Report:
    def __init__(self) -> None:
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.lines = 0
        self.records = 0
        self.skipped = 0

    def error(self, where: str, message: str) -> None:
        self.errors.append(f"{where}: {message}")

    def warn(self, where: str, message: str) -> None:
        self.warnings.append(f"{where}: {message}")


def check_record(rec: Any, where: str, rep: Report) -> None:
    if not isinstance(rec, dict):
        rep.error(where, "不是 JSON 对象")
        return

    missing = [k for k in REQUIRED_KEYS if k not in rec]
    if missing:
        rep.error(where, "缺少必填字段 " + ", ".join(missing))
        return
    extra = set(rec) - ALLOWED_KEYS
    if extra:
        rep.warn(where, "出现未定义的附加字段 " + ", ".join(sorted(extra)))

    if rec["format_version"] != 1:
        rep.error(where, f"format_version 应为 1，实际 {rec['format_version']!r}")

    run_id = rec["run_id"]
    if not isinstance(run_id, str) or not RUN_ID_RE.match(run_id):
        rep.error(where, "run_id 必须是 1～64 个字母数字及 . _ -")

    source = rec["source_kind"]
    if source not in SOURCE_KINDS:
        rep.error(where, f"source_kind 非法：{source!r}")

    for key in ("code_version", "config_version", "strategy_version"):
        if not (rec[key] is None or isinstance(rec[key], str)):
            rep.error(where, f"{key} 必须是字符串或 null")

    node_id = rec["node_id"]
    if not is_int(node_id) or not (1 <= node_id <= 65534):
        rep.error(where, f"node_id 应为 1～65534，实际 {node_id!r}")

    session_id = rec["session_id"]
    if not isinstance(session_id, str) or not RUN_ID_RE.match(session_id):
        rep.error(where, "session_id 必须是 1～64 个字母数字及 . _ -")

    seq = rec["event_seq"]
    if not is_int(seq) or not (1 <= seq <= MAX_EVENT_SEQ):
        rep.error(where, f"event_seq 越界：{seq!r}")

    mono = rec["monotonic_ms"]
    if not is_int(mono) or not (0 <= mono <= MAX_MONOTONIC):
        rep.error(where, f"monotonic_ms 越界：{mono!r}")

    basis = rec["clock_basis"]
    if basis not in CLOCK_BASIS:
        rep.error(where, f"clock_basis 非法：{basis!r}")
    elif source == "REAL" and basis != "node_session":
        rep.error(where, "REAL 记录必须使用 clock_basis=node_session")
    elif source != "REAL" and basis != "simulation_run":
        rep.error(where, f"{source} 记录必须使用 clock_basis=simulation_run")

    event = rec["event"]
    if event not in EVENTS:
        rep.error(where, f"未知事件 {event!r}")
        return
    allowed_results, required_details, allows_null_mid = EVENTS[event]

    result = rec["result"]
    if result not in RESULTS:
        rep.error(where, f"result 非法：{result!r}")
    elif result not in allowed_results:
        rep.error(where, f"{event} 的 result 只能是 {sorted(allowed_results)}，实际 {result!r}")

    reason = rec["reason"]
    if result in ("OK", "INFO"):
        if reason is not None:
            rep.error(where, f"result={result} 时 reason 必须为 null，实际 {reason!r}")
    else:
        if not isinstance(reason, str):
            rep.error(where, f"result={result} 必须给出原因码")
        elif reason not in REASONS:
            rep.warn(where, f"原因码 {reason!r} 不在建议清单内")

    mid = rec["message_id"]
    if mid is None:
        if not allows_null_mid:
            rep.error(where, f"{event} 必须带 message_id")
    else:
        if not isinstance(mid, dict) or set(mid) != {"source_id", "boot_counter", "sequence"}:
            rep.error(where, "message_id 必须是 null 或 {source_id, boot_counter, sequence}")
        else:
            if not is_int(mid["source_id"]) or not (1 <= mid["source_id"] <= 65534):
                rep.error(where, f"message_id.source_id 越界：{mid['source_id']!r}")
            for key in ("boot_counter", "sequence"):
                if not is_int(mid[key]) or not (1 <= mid[key] <= MAX_COUNTER):
                    rep.error(where, f"message_id.{key} 越界：{mid[key]!r}")

    details = rec["details"]
    if not isinstance(details, dict):
        rep.error(where, "details 必须是对象")
        details = {}
    else:
        lacking = required_details - set(details)
        if lacking:
            rep.error(where, f"{event} 的 details 缺少 " + ", ".join(sorted(lacking)))

    channel = rec.get("channel")
    if event in CHANNEL_REQUIRED:
        if not isinstance(channel, str) or not channel:
            rep.error(where, f"{event} 必须带顶层 channel")
        elif channel not in CHANNELS:
            rep.warn(where, f"channel {channel!r} 不在已约定取值内")
    elif channel is not None and not isinstance(channel, str):
        rep.error(where, "channel 必须是字符串")

    # details 内部约束
    if "peer_id" in details and (not is_int(details["peer_id"])
                                 or not (1 <= details["peer_id"] <= 65534)):
        rep.error(where, f"peer_id 越界：{details['peer_id']!r}")
    if "destination_id" in details and (not is_int(details["destination_id"])
                                        or not (1 <= details["destination_id"] <= 65534)):
        rep.error(where, f"destination_id 越界：{details['destination_id']!r}")
    if "attempt" in details and (not is_int(details["attempt"]) or details["attempt"] < 1):
        rep.error(where, f"attempt 应为 ≥1 的整数，实际 {details['attempt']!r}")
    if "frame_bytes" in details:
        n = details["frame_bytes"]
        if not is_int(n):
            rep.error(where, "frame_bytes 必须是整数")
        elif event in ("ACK_TX", "ACK_RX") and n != 23:
            rep.error(where, f"ACK 的 frame_bytes 应为 23，实际 {n}")
        elif event in ("DATA_TX", "DATA_RX", "MESSAGE_FORWARDED") and not (36 <= n <= 168):
            rep.error(where, f"DATA 的 frame_bytes 应在 36～168，实际 {n}")
    if "tx_scope" in details and details["tx_scope"] != "local_uart_queued":
        rep.error(where, f"tx_scope 目前只允许 local_uart_queued，实际 {details['tx_scope']!r}")
    if "ack_status" in details and details["ack_status"] not in ACK_STATUS:
        rep.error(where, f"ack_status 非法：{details['ack_status']!r}")
    if "storage" in details and details["storage"] not in STORAGE:
        rep.error(where, f"storage 非法：{details['storage']!r}")
    if "frame_type" in details and details["frame_type"] not in FRAME_TYPE:
        rep.error(where, f"frame_type 非法：{details['frame_type']!r}")
    if "pending_bytes" in details and (not is_int(details["pending_bytes"])
                                       or details["pending_bytes"] < 0):
        rep.error(where, "pending_bytes 必须是非负整数")
    if event == "LINK_UP" and details.get("basis") not in LINK_UP_BASIS:
        rep.error(where, f"LINK_UP 的 basis 只能是 {sorted(LINK_UP_BASIS)}")
    if event == "LINK_DOWN":
        if details.get("basis") not in LINK_DOWN_BASIS:
            rep.error(where, f"LINK_DOWN 的 basis 只能是 {sorted(LINK_DOWN_BASIS)}")
        if not is_int(details.get("consecutive_failures")) or details["consecutive_failures"] < 1:
            rep.error(where, "consecutive_failures 应为 ≥1 的整数")
    if event == "MESSAGE_EXPIRED":
        age, life = details.get("age_ms"), details.get("lifetime_ms")
        if is_int(age) and is_int(life) and life > 0 and age < life:
            rep.error(where, f"age_ms={age} 小于 lifetime_ms={life}，不构成过期")


def check_file(path: str, rep: Report, strict: bool) -> None:
    seen = set()
    last_mono: Dict[tuple, int] = {}
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            rep.lines += 1
            line = raw.rstrip("\n").rstrip("\r")
            if not line.strip():
                continue
            where = f"{path}:{lineno}"
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                rep.skipped += 1
                if strict:
                    rep.error(
                        where,
                        f"不是合法 JSON（{exc.msg}）；--strict 下不接受非结构化调试行")
                continue

            rep.records += 1
            check_record(rec, where, rep)
            if not isinstance(rec, dict):
                continue

            key = (rec.get("run_id"), rec.get("source_kind"), rec.get("node_id"),
                   rec.get("session_id"), rec.get("event_seq"))
            if key in seen:
                rep.error(where, f"唯一键重复：{key}")
            seen.add(key)

            session = (rec.get("run_id"), rec.get("node_id"), rec.get("session_id"))
            mono = rec.get("monotonic_ms")
            if is_int(mono):
                if session in last_mono and mono < last_mono[session]:
                    rep.error(where, f"monotonic_ms 回退：{last_mono[session]} -> {mono}")
                last_mono[session] = max(mono, last_mono.get(session, mono))


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="MobiWeave 日志 V1 校验器")
    ap.add_argument("paths", nargs="+", help="JSONL 文件，支持通配符")
    ap.add_argument("--strict", action="store_true", help="把非 JSON 行也视为错误")
    args = ap.parse_args(argv)

    files: List[str] = []
    for pattern in args.paths:
        files.extend(sorted(glob.glob(pattern)))
    if not files:
        print("没有找到文件", file=sys.stderr)
        return 2

    rep = Report()
    for path in files:
        check_file(path, rep, args.strict)

    for warning in rep.warnings:
        print("WARN  " + warning)
    for error in rep.errors:
        print("ERROR " + error)

    print(f"\n{len(files)} 个文件、{rep.records} 条记录、{rep.skipped} 行非 JSON（已跳过），"
          f"{len(rep.errors)} 个错误、{len(rep.warnings)} 个警告")
    return 0 if not rep.errors else 1


if __name__ == "__main__":
    sys.exit(main())
