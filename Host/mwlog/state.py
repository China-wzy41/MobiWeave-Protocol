"""把 V1 记录聚合成界面要看的三张表：节点、消息、链路。

这一层仍然**不碰界面**（不 import tkinter），所以自检脚本可以在没有显示器的环境里
把同样的聚合逻辑跑一遍。界面只负责把这里算出来的东西摆到屏幕上。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .records import LoadResult, Record

# ---------------------------------------------------------------- 常量

STATUS_UNKNOWN = "未知"
STATUS_OK = "正常"
STATUS_DOWN_CONFIRMED = "断开（已确认）"
STATUS_DOWN_INFERRED = "断开（推断）"

# 这些事件是"本跳确实通了"的观测证据（规范 §3.1「正常」那一行）。
SUCCESS_EVENTS = {"HOP_CONFIRMED", "LINK_UP", "DATA_RX", "ACK_RX"}
# 这些事件是"明确失败"的观测证据。
FAIL_EVENTS = {"LINK_DOWN", "TRANSFER_FAILED"}

# 默认推断阈值；界面上可改，并在报告里写明用了多少。
DEFAULT_T_DOWN_MS = 30_000


@dataclass
class LinkView:
    node_id: int
    peer_id: int
    channel: str
    status: str = STATUS_UNKNOWN
    evidence: str = ""              # 让人看得懂"凭什么这么判"
    last_success_ms: Optional[int] = None
    last_fail_ms: Optional[int] = None
    frames: int = 0

    @property
    def key(self) -> str:
        return f"{self.node_id} <-> {self.peer_id} ({self.channel})"


@dataclass
class NodeView:
    node_id: int
    records: int = 0
    sessions: set = field(default_factory=set)
    runs: set = field(default_factory=set)
    last_event: str = ""
    last_ms: Optional[int] = None
    sources: set = field(default_factory=set)

    @property
    def source_text(self) -> str:
        return "/".join(sorted(self.sources))


@dataclass
class TimelineRow:
    """消息时间线上的一行：一条原始事件。"""

    ms: int
    line_no: int
    event: str
    result: str
    reason: Optional[str]
    channel: Optional[str]
    node_id: int
    source_kind: str
    detail_text: str


@dataclass
class MessageView:
    run_id: str
    mid: str
    source_kind: str
    destination: Optional[int] = None
    created_ms: Optional[int] = None
    attempts: int = 0
    tx_count: int = 0
    hop_confirmed: List[str] = field(default_factory=list)
    last_ack: Optional[str] = None
    delivered: bool = False
    expired: bool = False
    dropped: bool = False
    failed: bool = False
    rejected: bool = False
    cached_storage: Optional[str] = None
    timeline: List[TimelineRow] = field(default_factory=list)

    @property
    def state(self) -> str:
        """只写日志能证明的状态。顺序即优先级，别随手调整。"""
        if self.delivered:
            return "已送达"
        if self.expired:
            return "已过期"
        if self.dropped:
            return "已丢弃"
        if self.hop_confirmed:
            return "本跳已确认"
        if self.failed and not self.hop_confirmed:
            return "本轮失败"
        if self.tx_count:
            return "已发出，等确认"
        if self.rejected:
            return "存在被拒帧"
        if self.created_ms is not None:
            return "已创建"
        return "未知"

    @property
    def hop_text(self) -> str:
        return "、".join(self.hop_confirmed) if self.hop_confirmed else "-"


@dataclass
class ViewState:
    path: str = ""
    nodes: List[NodeView] = field(default_factory=list)
    messages: List[MessageView] = field(default_factory=list)
    links: List[LinkView] = field(default_factory=list)
    issues: list = field(default_factory=list)
    records: List[Record] = field(default_factory=list)
    total_lines: int = 0
    bad_lines: int = 0
    t_down_ms: int = DEFAULT_T_DOWN_MS

    # ---- 给界面用的汇总文案

    @property
    def sources(self) -> List[str]:
        return sorted({r.source_kind for r in self.records})

    @property
    def simulated(self) -> bool:
        """只要出现 SIM/ESTIMATED，就必须在界面上标"模拟数据"。"""
        return any(s in ("SIM", "ESTIMATED") for s in self.sources)

    @property
    def banner(self) -> str:
        kinds = self.sources
        if not kinds:
            return ""
        if kinds == ["REAL"]:
            return ""
        label = "/".join(kinds)
        if "SIM" in kinds:
            return (f"模拟数据：这份日志的来源是 {label}，不是真实无线链路的观测。"
                    "界面上任何「已送达」只证明解析与显示正确，不证明空口链路可用。")
        return (f"估计数据：来源 {label}，其中含推断/估计值，不能当作实测证据。")

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if getattr(i, "level", "") == "错误")

    @property
    def hint_count(self) -> int:
        return sum(1 for i in self.issues if getattr(i, "level", "") == "提示")


# ---------------------------------------------------------------- 聚合


def _fmt_details(details: Dict[str, Any]) -> str:
    if not details:
        return "{}"
    parts = []
    for key, value in details.items():
        parts.append(f"{key}={value}")
    return ", ".join(parts)


def build(loaded: LoadResult, t_down_ms: int = DEFAULT_T_DOWN_MS) -> ViewState:
    state = ViewState(
        path=loaded.path,
        issues=list(loaded.issues),
        records=list(loaded.records),
        total_lines=loaded.total_lines,
        bad_lines=loaded.bad_lines,
        t_down_ms=t_down_ms,
    )

    nodes: Dict[int, NodeView] = {}
    messages: Dict[Tuple[str, str], MessageView] = {}
    links: Dict[Tuple[int, int, str], LinkView] = {}
    # 每个节点在文件里的"当前时刻"：用该节点最大的 monotonic_ms 近似。
    node_now: Dict[int, int] = {}

    for rec in loaded.records:
        # ---- 节点
        node = nodes.get(rec.node_id)
        if node is None:
            node = nodes[rec.node_id] = NodeView(node_id=rec.node_id)
        node.records += 1
        node.sessions.add(rec.session_id)
        node.runs.add(rec.run_id)
        node.sources.add(rec.source_kind)
        if node.last_ms is None or rec.monotonic_ms >= node.last_ms:
            node.last_ms = rec.monotonic_ms
            node.last_event = rec.event
        node_now[rec.node_id] = max(node_now.get(rec.node_id, 0), rec.monotonic_ms)

        # ---- 消息
        key = rec.message_key
        if key is not None:
            msg = messages.get(key)
            if msg is None:
                msg = messages[key] = MessageView(
                    run_id=rec.run_id, mid=rec.message_id.text, source_kind=rec.source_kind)
            msg.timeline.append(TimelineRow(
                ms=rec.monotonic_ms, line_no=rec.line_no, event=rec.event,
                result=rec.result, reason=rec.reason, channel=rec.channel,
                node_id=rec.node_id, source_kind=rec.source_kind,
                detail_text=_fmt_details(rec.details)))

            if rec.event == "MESSAGE_CREATED":
                msg.created_ms = rec.monotonic_ms
                msg.destination = rec.destination_id
            elif rec.event == "APP_DELIVERED":
                msg.delivered = True
            elif rec.event == "DATA_TX":
                msg.tx_count += 1
                attempt = rec.details.get("attempt")
                if isinstance(attempt, int):
                    msg.attempts = max(msg.attempts, attempt)
            elif rec.event in ("RETRY_SCHEDULED", "MESSAGE_FORWARDED"):
                attempt = rec.details.get("attempt")
                if isinstance(attempt, int):
                    msg.attempts = max(msg.attempts, attempt)
            elif rec.event == "HOP_CONFIRMED":
                peer = rec.peer_id
                tag = f"{peer}" if peer is not None else "?"
                if tag not in msg.hop_confirmed:
                    msg.hop_confirmed.append(tag)
                msg.last_ack = str(rec.details.get("ack_status"))
            elif rec.event == "ACK_RX":
                msg.last_ack = str(rec.details.get("ack_status"))
            elif rec.event == "MESSAGE_CACHED":
                msg.cached_storage = str(rec.details.get("storage"))
            elif rec.event == "MESSAGE_EXPIRED":
                msg.expired = True
            elif rec.event == "MESSAGE_DROPPED":
                msg.dropped = True
            elif rec.event == "TRANSFER_FAILED":
                msg.failed = True
            elif rec.event == "FRAME_REJECTED":
                msg.rejected = True

        # ---- 链路（本跳推断）
        peer = rec.peer_id
        if peer is not None:
            channel = rec.channel or "-"
            lkey = (rec.node_id, peer, channel)
            link = links.get(lkey)
            if link is None:
                link = links[lkey] = LinkView(node_id=rec.node_id, peer_id=peer, channel=channel)
            if rec.event in ("DATA_TX", "DATA_RX", "ACK_TX", "ACK_RX",
                             "HOP_CONFIRMED", "MESSAGE_FORWARDED"):
                link.frames += 1
            if rec.event in SUCCESS_EVENTS:
                if link.last_success_ms is None or rec.monotonic_ms >= link.last_success_ms:
                    link.last_success_ms = rec.monotonic_ms
            if rec.event in FAIL_EVENTS:
                if link.last_fail_ms is None or rec.monotonic_ms >= link.last_fail_ms:
                    link.last_fail_ms = rec.monotonic_ms

    # ---- 判定链路四态（规范 §3.1）
    for link in links.values():
        now = node_now.get(link.node_id, 0)
        if link.last_success_ms is None and link.last_fail_ms is None:
            link.status = STATUS_UNKNOWN
            link.evidence = "没有可用证据（只有收发帧，没有确认或失败）"
        elif link.last_fail_ms is not None and (
                link.last_success_ms is None or link.last_fail_ms >= link.last_success_ms):
            link.status = STATUS_DOWN_CONFIRMED
            link.evidence = f"最后一条是失败事件（{link.last_fail_ms} ms）"
        elif link.last_success_ms is not None and (now - link.last_success_ms) > t_down_ms:
            link.status = STATUS_DOWN_INFERRED
            link.evidence = f"最近一次成功在 {link.last_success_ms} ms，已超过 {t_down_ms} ms 无新证据"
        elif link.last_success_ms is not None:
            link.status = STATUS_OK
            link.evidence = f"最近一次成功在 {link.last_success_ms} ms"
        else:
            link.status = STATUS_UNKNOWN
            link.evidence = "没有成功证据"

    # ---- 排序：节点按编号，消息按创建时间（没有创建时间的排最后），链路按编号
    state.nodes = sorted(nodes.values(), key=lambda n: n.node_id)
    state.messages = sorted(
        messages.values(),
        key=lambda m: (m.created_ms is None, m.created_ms if m.created_ms is not None else 0, m.mid))
    # 时间线本身按（时间，行号）稳定排序，跨会话时以文件顺序兜底
    for msg in state.messages:
        msg.timeline.sort(key=lambda row: (row.ms, row.line_no))
    state.links = sorted(links.values(), key=lambda l: (l.node_id, l.peer_id, l.channel))
    return state
