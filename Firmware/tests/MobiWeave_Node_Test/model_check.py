#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ACK / 重传 / 去重状态机的模型验证。

用途：
1. 本机策略禁止执行编译产物，用它先把逻辑跑通（C++ 版逻辑与此一一对应）；
2. C 的仿真器可以直接复用这份模型，不必重写一套确认流程。

对应实现：Firmware/tests/MobiWeave_Node_Test/mw_protocol.cpp
    python model_check.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

ACK_TIMEOUT_MS = 1000
MAX_ATTEMPTS = 3
CACHE_SLOTS = 8

ACCEPTED, ALREADY_HAVE, BUSY, EXPIRED = 0, 1, 2, 3

IDLE, WAITING, DONE, FAILED, DEFERRED, REJECTED = (
    "IDLE", "WAITING_ACK", "DONE", "FAILED", "DEFERRED", "REJECTED")


@dataclass(frozen=True)
class MessageId:
    source: int
    boot: int
    seq: int


@dataclass
class DataFrame:
    sender: int
    receiver: int
    id: MessageId
    destination: int
    age_ms: int = 0
    lifetime_ms: int = 60000


class ReceiverCache:
    def __init__(self, slots: int = CACHE_SLOTS) -> None:
        self.slots = slots
        self.entries = []          # [(id, stored_at, age_at_store, lifetime)]

    def admit(self, frame: DataFrame, now_ms: int) -> int:
        mid = frame.id
        if not (mid.source and mid.boot and mid.seq):
            return BUSY
        if frame.lifetime_ms == 0 or frame.age_ms >= frame.lifetime_ms:
            return EXPIRED
        if any(e[0] == mid for e in self.entries):
            return ALREADY_HAVE
        if len(self.entries) >= self.slots:
            return BUSY
        self.entries.append((mid, now_ms, frame.age_ms, frame.lifetime_ms))
        return ACCEPTED

    def holds(self, mid: MessageId) -> bool:
        return any(e[0] == mid for e in self.entries)

    def expired_count(self, now_ms: int) -> int:
        return sum(1 for (_, stored, age, life) in self.entries
                   if age + (now_ms - stored) >= life)


@dataclass
class OutboundTx:
    frame: DataFrame | None = None
    state: str = IDLE
    attempt: int = 0
    deadline_ms: int = 0

    def load(self, frame: DataFrame, now_ms: int) -> None:
        self.frame, self.state, self.attempt, self.deadline_ms = \
            frame, WAITING, 0, now_ms

    def active(self) -> bool:
        return self.state in (WAITING, DEFERRED)

    def poll(self, now_ms: int):
        """返回 True 表示此刻应当发送一帧。"""
        if self.state not in (WAITING, DEFERRED):
            return False
        if now_ms < self.deadline_ms:
            return False
        if self.attempt >= MAX_ATTEMPTS:
            self.state = FAILED
            return False
        self.attempt += 1
        self.state = WAITING
        self.deadline_ms = now_ms + ACK_TIMEOUT_MS
        return True

    def on_ack(self, ack: dict, now_ms: int) -> None:
        if self.state not in (WAITING, DEFERRED) or self.frame is None:
            return
        # 必须同时匹配：来自预期的本跳接收节点、发给本节点、编号一致
        if ack["sender"] != self.frame.receiver:
            return
        if ack["receiver"] != self.frame.sender:
            return
        if ack["id"] != self.frame.id:
            return
        status = ack["status"]
        if status in (ACCEPTED, ALREADY_HAVE):
            self.state = DONE
        elif status == BUSY:
            self.state = DEFERRED
            self.deadline_ms = now_ms + ACK_TIMEOUT_MS
        elif status == EXPIRED:
            self.state = REJECTED
        # 未知状态：不确认


# ------------------------------------------------------------------ 测试
PASS = FAIL = 0


def check(name: str, ok: bool) -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"PASS  {name}")
    else:
        FAIL += 1
        print(f"FAIL  {name}")


def frame(seq: int = 12, age: int = 0, life: int = 60000) -> DataFrame:
    return DataFrame(sender=1, receiver=2, id=MessageId(1, 7, seq),
                     destination=3, age_ms=age, lifetime_ms=life)


def ack(status: int, seq: int = 12, receiver: int = 1, sender: int = 2) -> dict:
    return {"sender": sender, "receiver": receiver,
            "id": MessageId(1, 7, seq), "status": status}


def test_sender() -> None:
    tx = OutboundTx()
    tx.load(frame(), 0)
    check("首次 poll 立即发送", tx.poll(0) and tx.attempt == 1)
    check("未到超时不重发", not tx.poll(999))
    tx.on_ack(ack(ACCEPTED), 1000)
    check("ACCEPTED → DONE", tx.state == DONE)
    check("DONE 后不再发送", not tx.poll(5000))

    tx = OutboundTx()
    tx.load(frame(), 0)
    tx.poll(0)
    check("1000ms 后第 2 次", tx.poll(1000) and tx.attempt == 2)
    check("2000ms 后第 3 次", tx.poll(2000) and tx.attempt == 3)
    check("用完置 FAILED", not tx.poll(3000) and tx.state == FAILED)

    tx = OutboundTx()
    tx.load(frame(), 0)
    tx.poll(0)
    tx.on_ack(ack(ALREADY_HAVE), 500)
    check("ALREADY_HAVE → DONE", tx.state == DONE)

    tx = OutboundTx()
    tx.load(frame(), 0)
    tx.poll(0)
    tx.on_ack(ack(BUSY), 400)
    check("BUSY → DEFERRED", tx.state == DEFERRED)
    check("DEFERRED 不立即重发", not tx.poll(900))
    check("延后到点重发", tx.poll(1400) and tx.attempt == 2)

    tx = OutboundTx()
    tx.load(frame(), 0)
    tx.poll(0)
    tx.on_ack(ack(EXPIRED), 300)
    check("EXPIRED → REJECTED", tx.state == REJECTED)

    tx = OutboundTx()
    tx.load(frame(), 0)
    tx.poll(0)
    tx.on_ack(ack(ACCEPTED, sender=9), 100)
    check("来源不对的 ACK 被忽略", tx.state == WAITING)
    tx.on_ack(ack(ACCEPTED, seq=13), 100)
    check("编号不对的 ACK 被忽略", tx.state == WAITING)
    tx.on_ack(ack(ACCEPTED, receiver=7), 100)
    check("发给他人的 ACK 被忽略", tx.state == WAITING)
    tx.on_ack(ack(9), 100)
    check("未知状态不确认", tx.state == WAITING)


def test_cache() -> None:
    cache = ReceiverCache()
    check("首次 ACCEPTED", cache.admit(frame(), 1000) == ACCEPTED)
    check("重复 ALREADY_HAVE", cache.admit(frame(), 1100) == ALREADY_HAVE)
    check("缓存计数 1", len(cache.entries) == 1)
    check("过期 EXPIRED", cache.admit(frame(seq=13, age=60000), 1200) == EXPIRED)
    check("编号非法不接收", cache.admit(frame(seq=0), 1300) != ACCEPTED)

    full = ReceiverCache()
    for i in range(CACHE_SLOTS):
        full.admit(frame(seq=100 + i), 2000)
    check("缓存满回 BUSY", full.admit(frame(seq=999), 2001) == BUSY)

    timed = ReceiverCache()
    timed.admit(frame(age=0, life=1000), 5000)
    check("本地计时到期可统计", timed.expired_count(6001) == 1)


def test_e2e() -> None:
    """A 发 → B 收 → B 回 ACK → A 结束本跳；重传时 B 回 ALREADY_HAVE。"""
    cache = ReceiverCache()
    tx = OutboundTx()
    tx.load(frame(), 0)
    check("A 发出首帧", tx.poll(0))

    status = cache.admit(tx.frame, 10)
    check("B 判定 ACCEPTED", status == ACCEPTED)
    tx.on_ack({"sender": 2, "receiver": 1, "id": tx.frame.id,
               "status": status}, 100)
    check("A 结束本跳", tx.state == DONE)

    again = cache.admit(tx.frame, 2010)
    check("重传时回 ALREADY_HAVE", again == ALREADY_HAVE)
    check("缓存没增加", len(cache.entries) == 1)


def main() -> int:
    print("=== ACK / 重传 / 去重 模型验证 ===\n")
    test_sender()
    test_cache()
    test_e2e()
    print(f"\n{PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
