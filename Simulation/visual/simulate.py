"""多场景仿真：隔离的通信孤岛 + 会走路的移动节点（存储-携带-转发）。

项目定位收窄到三个细分场景，这里是它们的「数据发生器」：

    hiking      户外徒步   —— 山谷把队伍切成几段，驴友互相捎话
    inspection  偏远巡检   —— 一条巡检线，几个打卡点，巡检员沿线走
    lab         高校实验   —— 两个实验室之间不能直连，同学拿板子跑一趟

三类业务（对应产品三个优先功能）：

    POS   共享位置     —— 经纬度 + 精度 + 时间戳
    TXT   短文字消息   —— UTF-8，≤120 字节
    MARK  离线地图标注 —— 经纬度 + 短标签，落在地图上

产出两份文件：

    trace.jsonl   每 5 秒一条位置快照（给地图用；不属于 V1 日志）
    log.jsonl     V1 日志（log-v1.md 那套字段），可直接喂给 logview 校验

为什么位置分到旁路文件：log-v1.md 的 16 个事件里没有「位置/移动」事件，
硬塞进日志会变成未知事件；这里轨迹走旁路、日志只记消息事件 + 位置附件。

跑：
    python visual\\simulate.py --scenario hiking --out sim
    python visual\\simulate.py --scenario inspection
    python visual\\simulate.py --scenario lab
"""

from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import dataclass, field

# ---------------- 通用常量 ----------------

BOOT_COUNTER = 7
DT_S = 5

LAT0, LON0 = 30.05, 103.00   # 示意位置（四川山区）；米 -> 度
M_PER_DEG_LAT = 111320.0

# 三个业务类型
KIND_POS = "POS"
KIND_TXT = "TXT"
KIND_MARK = "MARK"
KIND_TEXT = {KIND_POS: "共享位置", KIND_TXT: "短文字", KIND_MARK: "地图标注"}


def to_latlon(x: float, y: float) -> tuple[float, float]:
    lat = LAT0 + y / M_PER_DEG_LAT
    lon = LON0 + x / (M_PER_DEG_LAT * math.cos(math.radians(LAT0)))
    return round(lat, 6), round(lon, 6)


@dataclass
class Scenario:
    key: str
    title: str
    run_id: str
    duration_s: float
    range_m: float
    islands: list[dict]
    fixed: list[tuple[int, str, float, float, str]]
    carriers: list[dict]
    # (创建秒, 源, 目的, 优先级, 有效期, 业务类型, 内容)
    plan: list[tuple[float, int, int, int, float, str, str]]
    width_m: float = 1200.0
    height_m: float = 800.0


SCENARIOS: dict[str, Scenario] = {
    # ---------------------------------------------------------------- 徒步
    "hiking": Scenario(
        key="hiking",
        title="户外徒步：山谷把队伍切断，驴友互相捎话",
        run_id="sim-hiking-01",
        duration_s=900,
        range_m=160.0,
        islands=[
            {"id": "A", "name": "北岸营地", "x": 200.0, "y": 400.0, "radius": 120.0},
            {"id": "B", "name": "河谷垭口", "x": 600.0, "y": 400.0, "radius": 120.0},
            {"id": "C", "name": "南坡水源", "x": 1000.0, "y": 400.0, "radius": 120.0},
        ],
        fixed=[
            (1, "A", 235.0, 372.0, "营地电台"),
            (2, "A", 168.0, 428.0, "北岸中继"),
            (3, "B", 635.0, 372.0, "垭口电台"),
            (4, "B", 568.0, 428.0, "垭口中继"),
            (5, "C", 1035.0, 372.0, "水源电台"),
            (6, "C", 968.0, 428.0, "南坡中继"),
        ],
        carriers=[
            {"id": 7, "name": "驴友-甲", "speed": 3.0,
             "route": [(200.0, 400.0, 45), (600.0, 400.0, 45)]},
            {"id": 8, "name": "驴友-乙", "speed": 2.6,
             "route": [(600.0, 400.0, 30), (1000.0, 400.0, 40)]},
        ],
        plan=[
            (30, 1, 6, 2, 1800, KIND_TXT, "南坡有队员脚踝受伤，需要担架"),
            (75, 6, 1, 2, 1800, KIND_TXT, "已固定伤处，两人留守"),
            (150, 2, 4, 1, 1800, KIND_POS, "北岸中继当前位置"),
            (330, 3, 1, 2, 1800, KIND_MARK, "垭口断崖落石，勿靠近"),
            (520, 5, 2, 1, 1800, KIND_POS, "水源点坐标"),
            (640, 4, 5, 0, 1800, KIND_TXT, "夜里降温，注意保暖"),
            (760, 1, 5, 2, 1800, KIND_MARK, "营地可扎营，取水方便"),
        ],
    ),
    # ---------------------------------------------------------------- 巡检
    "inspection": Scenario(
        key="inspection",
        title="偏远巡检：一条巡检线，几个打卡点，巡检员沿线走",
        run_id="sim-inspection-01",
        duration_s=1200,
        range_m=150.0,
        islands=[
            {"id": "P1", "name": "1号塔基", "x": 200.0, "y": 250.0, "radius": 110.0},
            {"id": "P2", "name": "2号塔基", "x": 600.0, "y": 400.0, "radius": 110.0},
            {"id": "P3", "name": "3号变电站", "x": 1000.0, "y": 550.0, "radius": 110.0},
        ],
        fixed=[
            (1, "P1", 230.0, 220.0, "1号塔电台"),
            (2, "P1", 170.0, 285.0, "1号塔备份"),
            (3, "P2", 630.0, 370.0, "2号塔电台"),
            (4, "P3", 1030.0, 520.0, "变电站电台"),
            (5, "P3", 965.0, 585.0, "站内中继"),
        ],
        carriers=[
            {"id": 7, "name": "巡检员-甲", "speed": 2.2,
             "route": [(200.0, 250.0, 40), (600.0, 400.0, 30), (1000.0, 550.0, 50)]},
            {"id": 8, "name": "巡检员-乙", "speed": 2.0,
             "route": [(1000.0, 550.0, 40), (600.0, 400.0, 25), (200.0, 250.0, 30)]},
        ],
        plan=[
            (60, 1, 5, 1, 2400, KIND_POS, "1号塔基打卡：绝缘子完好"),
            (180, 3, 1, 2, 2400, KIND_TXT, "2号塔基线夹过热，需复测"),
            (300, 7, 4, 1, 2400, KIND_MARK, "沿线塌方点，注意绕行"),
            (480, 4, 2, 2, 2400, KIND_TXT, "变电站请求支援，工具不足"),
            (700, 2, 5, 1, 2400, KIND_POS, "2号塔基复测位置"),
            (900, 7, 5, 1, 2400, KIND_TXT, "全线索具已正常，收工"),
        ],
    ),
    # ---------------------------------------------------------------- 实验
    "lab": Scenario(
        key="lab",
        title="高校实验：两个实验室不能直连，同学拿板子跑一趟",
        run_id="sim-lab-01",
        duration_s=600,
        range_m=120.0,
        islands=[
            {"id": "L1", "name": "302 实验室", "x": 350.0, "y": 400.0, "radius": 130.0},
            {"id": "L2", "name": "307 实验室", "x": 850.0, "y": 400.0, "radius": 130.0},
        ],
        fixed=[
            (1, "L1", 320.0, 370.0, "台式节点"),
            (2, "L1", 385.0, 425.0, "串口节点"),
            (3, "L2", 880.0, 370.0, "台式节点"),
            (4, "L2", 815.0, 425.0, "串口节点"),
        ],
        carriers=[
            {"id": 5, "name": "同学-甲", "speed": 1.6,
             "route": [(350.0, 400.0, 20), (850.0, 400.0, 20)]},
        ],
        plan=[
            (30, 1, 3, 1, 900, KIND_POS, "302 实验台坐标"),
            (120, 3, 1, 1, 900, KIND_TXT, "207 号测试通过，收到请回"),
            (240, 2, 4, 0, 900, KIND_MARK, "楼道拐角信号最好"),
            (360, 1, 4, 1, 900, KIND_TXT, "把板子放在 307 靠窗位置"),
        ],
    ),
}


# ---------------- 移动模型 ----------------

@dataclass
class Carrier:
    node_id: int
    name: str
    speed: float
    route: list[tuple[float, float, float]]
    x: float = 0.0
    y: float = 0.0
    _leg: int = 0
    _phase: str = "dwell"
    _timer: float = 0.0
    _forward: bool = True

    def __post_init__(self) -> None:
        self.x, self.y = self.route[0][0], self.route[0][1]
        self._timer = self.route[0][2]

    def step(self, dt: float) -> None:
        if self._phase == "dwell":
            self._timer -= dt
            if self._timer <= 0:
                self._phase = "move"
                self._timer = 0.0
            return
        target_index = self._leg + (1 if self._forward else -1)
        if target_index < 0 or target_index >= len(self.route):
            self._forward = not self._forward
            target_index = self._leg + (1 if self._forward else -1)
        tx, ty, _dwell = self.route[target_index]
        dx, dy = tx - self.x, ty - self.y
        distance = math.hypot(dx, dy)
        travel = self.speed * dt
        if distance <= travel or distance == 0:
            self.x, self.y = tx, ty
            self._leg = target_index
            self._phase = "dwell"
            self._timer = self.route[target_index][2]
            if self._leg in (0, len(self.route) - 1):
                self._forward = self._leg == 0
        else:
            self.x += dx / distance * travel
            self.y += dy / distance * travel


# ---------------- V1 日志写出 ----------------

class LogWriter:
    def __init__(self, path: str, scenario: Scenario) -> None:
        self.handle = open(path, "w", encoding="utf-8", newline="\n")
        self.seq: dict[int, int] = {}
        self.scenario = scenario

    def close(self) -> None:
        self.handle.close()

    def event(
        self,
        node_id: int,
        t_s: float,
        event: str,
        result: str,
        *,
        message_id: dict | None = None,
        reason: str | None = None,
        details: dict | None = None,
        position: tuple[float, float] | None = None,
    ) -> None:
        self.seq[node_id] = self.seq.get(node_id, 0) + 1
        payload = dict(details or {})
        if position is not None:
            lat, lon = to_latlon(*position)
            payload["position"] = {"latitude_deg": lat, "longitude_deg": lon, "accuracy_m": 15}
        record = {
            "format_version": 1,
            "run_id": self.scenario.run_id,
            "source_kind": "SIM",
            "code_version": None,
            "config_version": f"{self.scenario.key}-config-v1",
            "strategy_version": "epidemic-store-carry-forward-v1",
            "node_id": node_id,
            "session_id": f"sim-node-{node_id}-boot-1",
            "event_seq": self.seq[node_id],
            "monotonic_ms": int(t_s * 1000),
            "clock_basis": "simulation_run",
            "message_id": message_id,
            "event": event,
            "result": result,
            "reason": reason,
            "details": payload,
        }
        self.handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


@dataclass
class Message:
    sequence: int
    source_id: int
    destination_id: int
    priority: int
    created_at: float
    lifetime_s: float
    kind: str
    text: str
    delivered: bool = False
    delivered_at: float | None = None
    expired: bool = False
    hops: list[tuple[int, int, float]] = field(default_factory=list)


def payload_bytes(kind: str, text: str) -> int:
    """按业务类型估载荷长度（用来算 frame_bytes）。"""
    if kind == KIND_TXT:
        return min(120, len(text.encode("utf-8")))
    if kind == KIND_MARK:
        return 24 + min(40, len(text.encode("utf-8")))
    return 16   # POS：两个 4 字节定点数 + 精度 + 时间戳


def simulate(out_dir: str, scenario: Scenario) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    trace_path = os.path.join(out_dir, "trace.jsonl")
    log_path = os.path.join(out_dir, "log.jsonl")
    log = LogWriter(log_path, scenario)

    carriers = [Carrier(node_id=spec["id"], name=spec["name"], speed=spec["speed"],
                        route=list(spec["route"])) for spec in scenario.carriers]
    fixed_pos = {node_id: (x, y) for node_id, _island, x, y, _name in scenario.fixed}

    def position_of(node_id: int) -> tuple[float, float] | None:
        if node_id in fixed_pos:
            return fixed_pos[node_id]
        for carrier in carriers:
            if carrier.node_id == node_id:
                return (carrier.x, carrier.y)
        return None

    plan = [
        Message(sequence=index + 1, source_id=src, destination_id=dst, priority=priority,
                created_at=t0, lifetime_s=lifetime, kind=kind, text=text)
        for index, (t0, src, dst, priority, lifetime, kind, text) in enumerate(scenario.plan)
    ]
    buffers: dict[int, dict[int, Message]] = {}
    pending = list(plan)
    node_ids = [node_id for node_id, *_ in scenario.fixed] + [c.node_id for c in carriers]

    deliveries: list[dict] = []
    transfers = 0

    with open(trace_path, "w", encoding="utf-8", newline="\n") as trace:
        trace.write(json.dumps({
            "type": "meta", "run_id": scenario.run_id, "title": scenario.title,
            "scenario": scenario.key, "interval_s": DT_S, "range_m": scenario.range_m,
            "duration_s": scenario.duration_s, "islands": scenario.islands,
            "fixed": [{"node_id": n, "island": i, "x": x, "y": y, "name": name}
                      for n, i, x, y, name in scenario.fixed],
            "carriers": [{"node_id": c["id"], "name": c["name"]} for c in scenario.carriers],
        }, ensure_ascii=False) + "\n")

        t = 0.0
        while t <= scenario.duration_s + 1e-9:
            for message in [m for m in pending if m.created_at <= t + 1e-9]:
                pending.remove(message)
                buffers.setdefault(message.source_id, {})[message.sequence] = message
                log.event(
                    message.source_id, t, "MESSAGE_CREATED", "OK",
                    message_id={"source_id": message.source_id, "boot_counter": BOOT_COUNTER,
                                "sequence": message.sequence},
                    details={"destination_id": message.destination_id,
                             "payload_kind": message.kind,
                             "payload_len": payload_bytes(message.kind, message.text)},
                    position=position_of(message.source_id),
                )

            positions = {node_id: position_of(node_id) for node_id in node_ids}
            links: list[list[int]] = []
            for i, a in enumerate(node_ids):
                for b in node_ids[i + 1:]:
                    pa, pb = positions.get(a), positions.get(b)
                    if pa and pb and math.dist(pa, pb) <= scenario.range_m:
                        links.append([a, b])

            for a, b in links:
                for sender, receiver in ((a, b), (b, a)):
                    sender_buf = buffers.setdefault(sender, {})
                    receiver_buf = buffers.setdefault(receiver, {})
                    for sequence, message in list(sender_buf.items()):
                        if message.delivered or message.expired or sequence in receiver_buf:
                            continue
                        length = payload_bytes(message.kind, message.text)
                        frame_bytes = min(168, 20 + length)
                        message_id = {"source_id": message.source_id,
                                      "boot_counter": BOOT_COUNTER, "sequence": message.sequence}
                        log.event(sender, t, "DATA_TX", "OK", message_id=message_id,
                                  details={"peer_id": receiver, "attempt": 1,
                                           "frame_bytes": frame_bytes,
                                           "tx_scope": "local_uart_queued"},
                                  position=position_of(sender))
                        log.event(receiver, t, "DATA_RX", "OK", message_id=message_id,
                                  details={"peer_id": sender, "frame_bytes": frame_bytes},
                                  position=position_of(receiver))
                        receiver_buf[sequence] = message
                        log.event(receiver, t, "MESSAGE_CACHED", "OK", message_id=message_id,
                                  details={"storage": "FLASH"},
                                  position=position_of(receiver))
                        log.event(receiver, t, "ACK_TX", "OK", message_id=message_id,
                                  details={"peer_id": sender, "ack_status": "ACCEPTED",
                                           "frame_bytes": 23, "tx_scope": "local_uart_queued"},
                                  position=position_of(receiver))
                        log.event(sender, t, "ACK_RX", "OK", message_id=message_id,
                                  details={"peer_id": receiver, "ack_status": "ACCEPTED",
                                           "frame_bytes": 23}, position=position_of(sender))
                        log.event(sender, t, "HOP_CONFIRMED", "OK", message_id=message_id,
                                  details={"peer_id": receiver, "ack_status": "ACCEPTED"},
                                  position=position_of(sender))
                        transfers += 1
                        message.hops.append((sender, receiver, t))
                        if receiver == message.destination_id and not message.delivered:
                            message.delivered = True
                            message.delivered_at = t
                            log.event(receiver, t, "APP_DELIVERED", "OK", message_id=message_id,
                                      details={"destination_id": message.destination_id},
                                      position=position_of(receiver))
                            deliveries.append({
                                "sequence": message.sequence, "kind": message.kind,
                                "text": message.text,
                                "source_id": message.source_id,
                                "destination_id": message.destination_id,
                                "created_at": message.created_at, "delivered_at": t,
                                "carried_by": [hop[0] for hop in message.hops],
                            })

            for message in plan:
                if message.delivered or message.expired:
                    continue
                if t - message.created_at >= message.lifetime_s:
                    message.expired = True
                    log.event(message.source_id, t, "MESSAGE_EXPIRED", "REJECTED",
                              message_id={"source_id": message.source_id,
                                          "boot_counter": BOOT_COUNTER,
                                          "sequence": message.sequence},
                              reason="EXPIRED", details={},
                              position=position_of(message.source_id))

            trace.write(json.dumps({
                "type": "tick", "t": round(t, 1),
                "nodes": [[node_id, round(positions[node_id][0], 1), round(positions[node_id][1], 1)]
                          for node_id in node_ids if positions.get(node_id)],
                "links": links,
            }, ensure_ascii=False) + "\n")

            for carrier in carriers:
                carrier.step(DT_S)
            t = round(t + DT_S, 3)

    log.close()

    return {
        "scenario": scenario.key,
        "title": scenario.title,
        "trace": trace_path,
        "log": log_path,
        "messages": len(plan),
        "delivered": sum(1 for message in plan if message.delivered),
        "expired": sum(1 for message in plan if message.expired),
        "transfers": transfers,
        "deliveries": deliveries,
        "duration_s": scenario.duration_s,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="MobiWeave 场景仿真（共享位置 / 短文字 / 离线标注）")
    parser.add_argument("--scenario", default="hiking", choices=sorted(SCENARIOS))
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    scenario = SCENARIOS[args.scenario]
    base = os.path.dirname(os.path.abspath(__file__))
    out = args.out or os.path.join(base, "..", "sim" if args.scenario == "hiking" else "sim-" + args.scenario)
    summary = simulate(os.path.abspath(out), scenario)
    print(json.dumps({k: v for k, v in summary.items() if k != "deliveries"},
                     ensure_ascii=False, indent=2))
    print("\n交付明细：")
    carrier_ids = [c["id"] for c in scenario.carriers]
    for item in summary["deliveries"]:
        carriers = sorted({node for node in item["carried_by"] if node in carrier_ids})
        text = item["text"]
        if len(text) > 14:
            text = text[:14] + "…"
        print(f"  [{KIND_TEXT[item['kind']]}] 消息#{item['sequence']} {item['source_id']}→"
              f"{item['destination_id']}  {item['delivered_at']:5.0f}s 送达"
              f"（{text}；经移动节点 {carriers or '无'}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
