"""灾害场景地图：回放 sim\\trace.jsonl（位置）+ sim\\log.jsonl（消息）。

为什么先做电脑端而不是手机端：
* 手机方案要么写原生 App（Android/Flutter，装工具链、签名、装包），
  要么用 Web Bluetooth（只支持 Android Chrome，iOS 直接不可用），
  两者都会把工期拖进「和画地图无关的事情」；
* 电脑端今天就能跑起来，而且**数据通路和将来手机端完全一样**——
  都是「读同一份 JSONL」。将来换手机只换前端，解析层一行不改。

界面（Tkinter Canvas，无第三方依赖、完全离线）：
    左：示意图（孤岛、固定节点、移动节点轨迹、活跃链路、消息流向）
    右：时间、活跃链路数、已交付进度、最近事件
    下：播放/暂停、速度、时间轴

跑：
    python -m visual.mapview
    python -m visual.mapview --trace sim\\trace.jsonl --log sim\\log.jsonl --t 300
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import filedialog, ttk

BG = "#0b1220"
PANEL = "#111b2e"
GRID = "#16233a"
ISLAND = "#0f3b34"
ISLAND_EDGE = "#1f7a68"
FIXED = "#e8f4ff"
CARRIER = "#ffb347"
LINK = "#3fd0c9"
DELIVER = "#ffd166"
TEXT = "#dbe7ff"
MUTED = "#7f93b3"
WARN = "#ff6b6b"

ROLE_FIXED = "fixed"
ROLE_CARRIER = "carrier"


@dataclass
class World:
    islands: list[dict]
    fixed: list[dict]
    carriers: list[dict]
    range_m: float
    interval_s: float
    duration_s: float
    ticks: list[dict] = field(default_factory=list)

    width_m: float = 1200.0
    height_m: float = 800.0
    title: str = ""
    scenario: str = ""


@dataclass
class MessageTrack:
    sequence: int
    source_id: int
    destination_id: int
    created_at: float
    delivered_at: float | None = None
    kind: str = ""


def load_world(trace_path: str) -> World:
    islands: list[dict] = []
    fixed: list[dict] = []
    carriers: list[dict] = []
    meta: dict = {}
    ticks: list[dict] = []
    with open(trace_path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if obj.get("type") == "meta":
                meta = obj
                islands = obj.get("islands", [])
                fixed = obj.get("fixed", [])
                carriers = obj.get("carriers", [])
            elif obj.get("type") == "tick":
                ticks.append(obj)
    xs = [node[1] for tick in ticks for node in tick["nodes"]]
    ys = [node[2] for tick in ticks for node in tick["nodes"]]
    world = World(
        islands=islands, fixed=fixed, carriers=carriers,
        range_m=float(meta.get("range_m", 160)), interval_s=float(meta.get("interval_s", 5)),
        duration_s=float(meta.get("duration_s", ticks[-1]["t"] if ticks else 0)),
        ticks=ticks,
    )
    world.title = str(meta.get("title", ""))
    world.scenario = str(meta.get("scenario", ""))
    if xs and ys:
        world.width_m = max(1200.0, max(xs) + 120)
        world.height_m = max(800.0, max(ys) + 120)
    return world


def load_messages(log_path: str) -> dict[int, MessageTrack]:
    """只取消息生命周期用得到的事件，其余交给 logview 的解析器（此处刻意保持轻量）。"""
    tracks: dict[int, MessageTrack] = {}
    if not os.path.exists(log_path):
        return tracks
    with open(log_path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            mid = obj.get("message_id") or {}
            sequence = mid.get("sequence")
            if not isinstance(sequence, int):
                continue
            event = obj.get("event")
            t_ms = obj.get("monotonic_ms", 0) / 1000.0
            if event == "MESSAGE_CREATED":
                details = obj.get("details") or {}
                tracks.setdefault(sequence, MessageTrack(
                    sequence=sequence, source_id=obj.get("node_id", 0),
                    destination_id=details.get("destination_id", 0),
                    created_at=t_ms, kind=str(details.get("payload_kind", "")),
                ))
            elif event == "APP_DELIVERED":
                track = tracks.get(sequence)
                if track is None:
                    track = MessageTrack(sequence=sequence, source_id=mid.get("source_id", 0),
                                         destination_id=obj.get("node_id", 0), created_at=t_ms)
                    tracks[sequence] = track
                if track.delivered_at is None:
                    track.delivered_at = t_ms
    return tracks


class MapView(tk.Tk):
    def __init__(self, trace_path: str, log_path: str, start_t: float = 0.0) -> None:
        super().__init__()
        self.title("MobiWeave 场景回放 — 共享位置 / 短文字 / 离线标注")
        self.geometry("1280x760")
        self.configure(bg=BG)
        self.trace_path = trace_path
        self.log_path = log_path
        self.world = load_world(trace_path)
        self.messages = load_messages(log_path)
        self.index = 0
        self.playing = False
        self.speed = 4.0
        self._toast: list[tuple[float, str]] = []

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TButton", background="#16233a", foreground=TEXT, borderwidth=1)
        style.map("TButton", background=[("active", "#22335a")])
        style.configure("TCombobox", fieldbackground="#16233a", background="#16233a", foreground=TEXT)
        style.configure("Horizontal.TScale", background=BG, troughcolor="#16233a")
        self._build_ui()
        self._seek_time(start_t)
        self._render()

    # ---------- UI ----------
    def _build_ui(self) -> None:
        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="both", expand=True, padx=10, pady=(10, 4))

        self.canvas = tk.Canvas(outer, bg=BG, highlightthickness=0, width=900, height=600)
        self.canvas.pack(side="left", fill="both", expand=True)

        side = tk.Frame(outer, bg=PANEL, width=360)
        side.pack(side="right", fill="y", padx=(10, 0))
        side.pack_propagate(False)

        tk.Label(side, text=self.world.title or "场景回放", bg=PANEL, fg="#8fe3d2", anchor="w",
                 justify="left", wraplength=330,
                 font=("Microsoft YaHei UI", 10, "bold")).pack(fill="x", padx=14, pady=(12, 2))
        tk.Label(side, text="⚠ 模拟数据：轨迹与消息由 simulate.py 生成，非真实链路",
                 bg=PANEL, fg=WARN, anchor="w", justify="left", wraplength=330,
                 font=("Microsoft YaHei UI", 8)).pack(fill="x", padx=14, pady=(0, 10))
        tk.Label(side, text="运行状态", bg=PANEL, fg=TEXT, anchor="w",
                 font=("Microsoft YaHei UI", 11, "bold")).pack(fill="x", padx=14, pady=(14, 6))
        self.lbl_time = tk.Label(side, text="", bg=PANEL, fg=TEXT, anchor="w",
                                 font=("Consolas", 12))
        self.lbl_time.pack(fill="x", padx=14)
        self.lbl_stat = tk.Label(side, text="", bg=PANEL, fg=MUTED, anchor="w", justify="left",
                                 font=("Microsoft YaHei UI", 9))
        self.lbl_stat.pack(fill="x", padx=14, pady=(2, 10))

        legend = tk.Frame(side, bg=PANEL)
        legend.pack(fill="x", padx=14, pady=(0, 10))
        for color, text in ((LINK, "青绿虚线 = 可达链路"),
                            (CARRIER, "橙点 = 移动节点"),
                            (FIXED, "白方块 = 固定节点"),
                            (DELIVER, "金色圈 = 消息送达时刻")):
            row = tk.Frame(legend, bg=PANEL)
            row.pack(fill="x", pady=1)
            box = tk.Label(row, text="■", bg=PANEL, fg=color, font=("Microsoft YaHei UI", 9))
            box.pack(side="left")
            tk.Label(row, text=text, bg=PANEL, fg=MUTED, anchor="w",
                     font=("Microsoft YaHei UI", 8)).pack(side="left", padx=(4, 0))
        tk.Label(side, text="最近事件", bg=PANEL, fg=TEXT, anchor="w",
                 font=("Microsoft YaHei UI", 10, "bold")).pack(fill="x", padx=14, pady=(6, 4))
        self.txt_events = tk.Text(side, bg="#0d1728", fg=TEXT, relief="flat", height=14,
                                  font=("Consolas", 9), wrap="none", insertbackground=TEXT)
        self.txt_events.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        self.txt_events.configure(state="disabled")



        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=10, pady=(0, 10))

        self.btn_play = ttk.Button(bar, text="▶ 播放", width=10, command=self.toggle_play)
        self.btn_play.pack(side="left")
        ttk.Button(bar, text="重置", width=6, command=lambda: self._seek_time(0)).pack(side="left", padx=(6, 10))

        self.btn_speed = ttk.Button(bar, text="速度 4x", width=9, command=self._cycle_speed)
        self.btn_speed.pack(side="left", padx=(14, 12))

        self.scale = ttk.Scale(bar, from_=0, to=max(1.0, self.world.duration_s),
                               command=self._on_scale)
        self.scale.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ttk.Button(bar, text="打开日志…", command=self._open).pack(side="right")

    # ---------- 交互 ----------
    SPEEDS = (1.0, 2.0, 4.0, 10.0, 30.0)

    def _cycle_speed(self) -> None:
        index = self.SPEEDS.index(self.speed) if self.speed in self.SPEEDS else 2
        self.speed = self.SPEEDS[(index + 1) % len(self.SPEEDS)]
        self.btn_speed.configure(text=f"速度 {self.speed:g}x")

    def _on_scale(self, value) -> None:
        self._seek_time(float(value))
        self._render()

    def toggle_play(self) -> None:
        self.playing = not self.playing
        self.btn_play.configure(text="⏸ 暂停" if self.playing else "▶ 播放")
        if self.playing:
            self._tick()

    def _open(self) -> None:
        path = filedialog.askopenfilename(title="选择 trace.jsonl",
                                          filetypes=[("JSONL", "*.jsonl"), ("所有文件", "*.*")])
        if not path:
            return
        self.trace_path = path
        self.log_path = os.path.join(os.path.dirname(path), "log.jsonl")
        self.world = load_world(path)
        self.messages = load_messages(self.log_path)
        self.scale.configure(to=max(1.0, self.world.duration_s))
        self._seek_time(0)
        self._render()

    def _tick(self) -> None:
        if not self.playing:
            return
        if self.index >= len(self.world.ticks) - 1:
            self.playing = False
            self.btn_play.configure(text="▶ 播放")
            return
        self.index += 1
        self.scale.set(self.world.ticks[self.index]["t"])
        self._render()
        self.after(120, self._tick)

    def _seek_time(self, t: float) -> None:
        ticks = self.world.ticks
        if not ticks:
            return
        best = 0
        for index, tick in enumerate(ticks):
            if tick["t"] <= t + 1e-6:
                best = index
            else:
                break
        self.index = best

    # ---------- 绘制 ----------
    def _project(self, x: float, y: float) -> tuple[float, float]:
        width = self.canvas.winfo_width() or 900
        height = self.canvas.winfo_height() or 600
        margin = 40
        scale = min((width - margin * 2) / self.world.width_m,
                    (height - margin * 2) / self.world.height_m)
        return (margin + x * scale, height - margin - y * scale)

    def _render(self) -> None:
        if not self.world.ticks:
            self.canvas.delete("all")
            self.canvas.create_text(450, 300, text="没有 trace 数据", fill=WARN)
            return
        tick = self.world.ticks[self.index]
        now = tick["t"]
        self.canvas.delete("all")
        self._draw_background()

        positions = {node[0]: (node[1], node[2]) for node in tick["nodes"]}
        roles = {node[0]: (ROLE_CARRIER if node[0] in {c["node_id"] for c in self.world.carriers}
                           else ROLE_FIXED) for node in tick["nodes"]}
        names = {entry["node_id"]: entry.get("name", f"节点{entry['node_id']}") for entry in self.world.fixed}
        for entry in self.world.carriers:
            names[entry["node_id"]] = entry["name"]

        # 活跃链路
        for a, b in tick["links"]:
            pa, pb = self._project(*positions[a]), self._project(*positions[b])
            self.canvas.create_line(*pa, *pb, fill=LINK, width=1, dash=(4, 6))

        # 移动节点走过的轨迹（到当前时刻）
        for carrier in self.world.carriers:
            node_id = carrier["node_id"]
            trail = [(snap["t"], dict((n[0], (n[1], n[2])) for n in snap["nodes"]).get(node_id))
                     for snap in self.world.ticks[: self.index + 1]]
            points = [point for _t, point in trail if point]
            if len(points) > 1:
                flat = []
                for point in points[-260:]:
                    flat.extend(self._project(*point))
                self.canvas.create_line(*flat, fill="#5b4a2a", width=2, smooth=True)

        # 交付动画：消息从源到目的的方向线
        for message in self.messages.values():
            if message.delivered_at is None:
                continue
            if now < message.created_at:
                continue
            span = max(1.0, message.delivered_at - message.created_at)
            progress = min(1.0, (now - message.created_at) / span)
            start = positions.get(message.source_id)
            end = positions.get(message.destination_id)
            if not start or not end or angle_is_zero(start, end):
                continue
            px, py = self._project(*start)
            qx, qy = self._project(*end)
            x = px + (qx - px) * progress
            y = py + (qy - py) * progress
            if progress >= 1.0:
                age = now - message.delivered_at
                if age <= 25.0:
                    grow = 9 + age * 0.35
                    self.canvas.create_oval(x - grow, y - grow, x + grow, y + grow,
                                            outline=DELIVER, width=1)
                    self.canvas.create_text(x, y - 26, text=f"#{message.sequence} 送达",
                                            fill=DELIVER, font=("Microsoft YaHei UI", 8))
            else:
                self.canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill=DELIVER, outline="")
                self.canvas.create_line(px, py, x, y, fill="#6b5a2a", dash=(2, 6))

        # 节点
        for node_id, (x, y) in positions.items():
            px, py = self._project(x, y)
            if roles[node_id] == ROLE_CARRIER:
                self.canvas.create_oval(px - 7, py - 7, px + 7, py + 7, fill=CARRIER, outline="")
                self.canvas.create_text(px, py - 14, text=names.get(node_id, str(node_id)),
                                        fill=CARRIER, font=("Microsoft YaHei UI", 9))
            else:
                self.canvas.create_rectangle(px - 5, py - 5, px + 5, py + 5, fill=FIXED, outline="")
                offset = 15
                self.canvas.create_text(px, py + offset, text=names.get(node_id, str(node_id)),
                                        fill=MUTED, font=("Microsoft YaHei UI", 8))

        self._draw_hud(now, tick)
        self._draw_events(now)

    def _draw_background(self) -> None:
        width = self.canvas.winfo_width() or 900
        height = self.canvas.winfo_height() or 600
        for gx in range(0, 7):
            x = 40 + gx * (width - 80) / 6
            self.canvas.create_line(x, 40, x, height - 40, fill=GRID)
        for gy in range(0, 5):
            y = 40 + gy * (height - 80) / 4
            self.canvas.create_line(40, y, width - 40, y, fill=GRID)

        # 孤岛之间的地形阻隔（示意：断崖/河谷），说明为什么直连不上
        for gx_m in (400.0, 800.0):
            left = self._project(gx_m - 22, 0)[0]
            right = self._project(gx_m + 22, 0)[0]
            self.canvas.create_rectangle(left, 30, right, height - 30, fill="#1a1620", outline="")
            self.canvas.create_text((left + right) / 2, 18, text="地形阻隔", fill="#b98cff",
                                    font=("Microsoft YaHei UI", 8))

        for island in self.world.islands:
            cx, cy = self._project(island["x"], island["y"])
            width_px = self.canvas.winfo_width() or 900
            scale = min((width_px - 80) / self.world.width_m,
                        ((self.canvas.winfo_height() or 600) - 80) / self.world.height_m)
            radius = island["radius"] * scale
            self.canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius,
                                    fill=ISLAND, outline=ISLAND_EDGE, width=2)
            self.canvas.create_text(cx, cy - radius - 14, text=f"孤岛 {island['id']} · {island['name']}",
                                    fill="#8fe3d2", font=("Microsoft YaHei UI", 9, "bold"))

    def _draw_hud(self, now: float, tick: dict) -> None:
        total = len(self.messages)
        delivered = sum(1 for m in self.messages.values()
                        if m.delivered_at is not None and m.delivered_at <= now + 1e-6)
        pending = sum(1 for m in self.messages.values()
                      if m.created_at <= now and (m.delivered_at is None or m.delivered_at > now))
        self.lbl_time.configure(text=f"T = {now:6.0f} s")
        self.lbl_stat.configure(text=(
            f"活跃链路：{len(tick['links'])} 条（半径 {self.world.range_m:.0f} m）\n"
            f"已交付：{delivered} / {total}   在途：{pending}\n"
            f"移动节点：{len(self.world.carriers)} 个   固定节点：{len(self.world.fixed)} 个"
        ))

    def _draw_events(self, now: float) -> None:
        lines = []
        recent = [m for m in self.messages.values() if m.created_at <= now]
        recent.sort(key=lambda m: m.created_at, reverse=True)
        for message in recent[:8]:
            if message.delivered_at is not None and message.delivered_at <= now:
                lines.append(f"{message.delivered_at:6.0f}s  [{message.kind or '--'}] "
                             f"#{message.sequence} {message.source_id}→{message.destination_id} 已送达")
            else:
                lines.append(f"{message.created_at:6.0f}s  [{message.kind or '--'}] "
                             f"#{message.sequence} {message.source_id}→{message.destination_id} 在途…")
        self.txt_events.configure(state="normal")
        self.txt_events.delete("1.0", "end")
        self.txt_events.insert("1.0", "\n".join(lines) if lines else "（还没有消息）")
        self.txt_events.configure(state="disabled")


def angle_is_zero(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return math.dist(a, b) < 1e-6


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MobiWeave 灾害场景地图回放")
    base = os.path.dirname(os.path.abspath(__file__))
    parser.add_argument("--trace", default=os.path.join(base, "..", "sim", "trace.jsonl"))
    parser.add_argument("--log", default=os.path.join(base, "..", "sim", "log.jsonl"))
    parser.add_argument("--dir", default=None, help="sim 数据目录（含 trace.jsonl / log.jsonl）")
    parser.add_argument("--t", type=float, default=0.0, help="从第几秒开始")
    args = parser.parse_args(argv)

    if args.dir:
        args.trace = os.path.join(args.dir, "trace.jsonl")
        args.log = os.path.join(args.dir, "log.jsonl")
    trace_path = os.path.abspath(args.trace)
    if not os.path.exists(trace_path):
        print(f"找不到 {trace_path}\n先跑：python visual\\simulate.py --out sim", file=sys.stderr)
        return 1
    app = MapView(trace_path, os.path.abspath(args.log), start_t=args.t)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
