"""MobiWeave 上位机（M0）：导入日志 V1 → 看节点和消息 → 点开一条消息看事件 → 保存并重新打开。

界面只做三件事：把 `mwlog` 算出来的东西摆出来、让人能点、让人能存。
所有"这条消息到底算送达没有"的判断都在 `mwlog/state.py` 里，界面不复述一遍规则。

启动：双击 `start_host.bat`，或者在本目录执行
    python app.py
    python app.py samples/log-v1-sim.jsonl
"""

from __future__ import annotations

import os
import shutil
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from mwlog import DEFAULT_T_DOWN_MS, build, load_file
from mwlog.records import LoadResult
from mwlog.state import (STATUS_DOWN_CONFIRMED, STATUS_DOWN_INFERRED, STATUS_OK,
                         STATUS_UNKNOWN, MessageView, ViewState)

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(HERE, "samples")

BG = "#f7f8fa"
PANEL = "#ffffff"
INK = "#1f2430"
MUTED = "#6b7280"
LINE = "#d8dce3"
WARN_BG = "#fff4d6"
WARN_INK = "#7a4b00"

# 状态 → 背景色。绿=有观测证据、黄=推断、灰=没证据、红=确认断开。
STATUS_STYLE = {
    "正常": ("#e7f6ec", "#1c7c3c"),
    STATUS_OK: ("#e7f6ec", "#1c7c3c"),
    "断开（推断）": ("#fff6dc", "#8a5a00"),
    STATUS_DOWN_INFERRED: ("#fff6dc", "#8a5a00"),
    "断开（已确认）": ("#fdeaea", "#a12a2a"),
    STATUS_DOWN_CONFIRMED: ("#fdeaea", "#a12a2a"),
    "未知": ("#eef0f4", "#4b5563"),
    STATUS_UNKNOWN: ("#eef0f4", "#4b5563"),
}

MSG_STYLE = {
    "已送达": ("#e7f6ec", "#1c7c3c"),
    "本跳已确认": ("#e8f1ff", "#1f4fa5"),
    "已发出，等确认": ("#fff6dc", "#8a5a00"),
    "本轮失败": ("#fdeaea", "#a12a2a"),
    "已过期": ("#eef0f4", "#4b5563"),
    "已丢弃": ("#fdeaea", "#a12a2a"),
    "存在被拒帧": ("#fdeaea", "#a12a2a"),
    "已创建": ("#eef0f4", "#4b5563"),
    "未知": ("#eef0f4", "#4b5563"),
}


def _elide(text: str, limit: int) -> str:
    text = "" if text is None else str(text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


class App:
    def __init__(self, root: tk.Tk, initial: str | None = None) -> None:
        self.root = root
        self.state: ViewState | None = None
        self.loaded: LoadResult | None = None
        self.current_path: str | None = None
        self.selected_message: MessageView | None = None
        self._search_hits: list = []
        self._search_index = -1

        root.title("MobiWeave 上位机 · 日志 V1 查看器（M0）")
        root.geometry("1360x820")
        root.minsize(1020, 660)
        root.configure(bg=BG)

        self._init_style()
        self._build_toolbar()
        self._build_banner()
        self._build_body()
        self._build_statusbar()

        if initial:
            self.open_path(initial)

    # ------------------------------------------------------------ 样式

    def _init_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", background=BG, foreground=INK)
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL, relief="flat")
        style.configure("TLabel", background=BG, foreground=INK)
        style.configure("Title.TLabel", background=BG, foreground=INK,
                        font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("Muted.TLabel", background=BG, foreground=MUTED)
        style.configure("Panel.TLabel", background=PANEL, foreground=INK)
        style.configure("TButton", padding=(10, 4))
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL,
                        foreground=INK, rowheight=23, borderwidth=0)
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 9, "bold"),
                        background="#eef1f6", foreground=INK, relief="flat")
        style.map("Treeview", background=[("selected", "#d3e3fd")],
                  foreground=[("selected", "#10233f")])
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(14, 5))

    # ------------------------------------------------------------ 结构

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self.root, padding=(10, 8, 10, 4))
        bar.pack(fill="x")

        ttk.Label(bar, text="MobiWeave 上位机", style="Title.TLabel").pack(side="left")
        ttk.Label(bar, text="  日志 V1 · M0", style="Muted.TLabel").pack(side="left")

        right = ttk.Frame(bar)
        right.pack(side="right")

        ttk.Button(right, text="打开日志…", command=self.ask_open).pack(side="left", padx=(0, 6))
        ttk.Button(right, text="打开示例…", command=self.ask_sample).pack(side="left", padx=(0, 6))
        ttk.Button(right, text="保存原始记录…", command=self.save_raw).pack(side="left", padx=(0, 6))
        ttk.Button(right, text="退出", command=self.root.destroy).pack(side="left")

        # 查找单独一行，免得挤掉标题或被窗口边缘裁掉
        bar2 = ttk.Frame(self.root, padding=(10, 0, 10, 2))
        bar2.pack(fill="x")
        ttk.Label(bar2, text="按消息编号查找：").pack(side="left")
        self.search_var = tk.StringVar()
        entry = ttk.Entry(bar2, textvariable=self.search_var, width=18)
        entry.pack(side="left")
        entry.bind("<Return>", lambda _e: self.do_search())
        ttk.Button(bar2, text="查找", command=self.do_search).pack(side="left", padx=4)
        ttk.Button(bar2, text="下一个", command=self.next_hit).pack(side="left")
        ttk.Label(bar2, text="（可只输一部分，比如 7-12）", style="Muted.TLabel").pack(side="left", padx=8)

    def _build_banner(self) -> None:
        self.banner = tk.Label(self.root, text="", anchor="w", justify="left",
                               bg=WARN_BG, fg=WARN_INK, padx=12, pady=7, wraplength=1300,
                               font=("Microsoft YaHei UI", 9))
        self.root.bind("<Configure>", self._on_resize)
        # 一开始没有数据，不占位
        self._banner_shown = False

    def _on_resize(self, event) -> None:
        if event.widget is self.root:
            self.banner.configure(wraplength=max(600, event.width - 60))

    def _set_banner(self, text: str) -> None:
        if text:
            self.banner.configure(text="⚠  " + text)
            if not self._banner_shown:
                self.banner.pack(fill="x", padx=10, pady=(0, 4), after=self.root.winfo_children()[0])
                self._banner_shown = True
        else:
            if self._banner_shown:
                self.banner.pack_forget()
                self._banner_shown = False

    def _build_body(self) -> None:
        outer = ttk.Frame(self.root, padding=(10, 4, 10, 4))
        outer.pack(fill="both", expand=True)

        split = ttk.Panedwindow(outer, orient="horizontal")
        split.pack(fill="both", expand=True)

        # -------- 左：节点 + 链路
        left = ttk.Frame(split, style="Panel.TFrame")
        split.add(left, weight=2)

        ttk.Label(left, text="节点", style="Panel.TLabel",
                  font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w", padx=10, pady=(8, 2))
        node_box = ttk.Frame(left, style="Panel.TFrame")
        node_box.pack(fill="both", expand=True, padx=8)
        cols = ("node", "status", "records", "last")
        self.node_tree = ttk.Treeview(node_box, columns=cols, show="headings", height=7)
        for key, title, width in (("node", "节点编号", 70), ("status", "连接状态", 120),
                                  ("records", "记录数", 58), ("last", "最近事件", 200)):
            self.node_tree.heading(key, text=title)
            self.node_tree.column(key, width=width, anchor="w" if key == "last" else "center")
        node_sb = ttk.Scrollbar(node_box, orient="vertical", command=self.node_tree.yview)
        self.node_tree.configure(yscrollcommand=node_sb.set)
        self.node_tree.pack(side="left", fill="both", expand=True)
        node_sb.pack(side="right", fill="y")
        self.node_tree.tag_configure("ok", background="#e7f6ec")
        self.node_tree.tag_configure("down", background="#fdeaea")
        self.node_tree.tag_configure("inferred", background="#fff6dc")
        self.node_tree.tag_configure("unknown", background="#eef0f4")

        ttk.Label(left, text="链路（本跳推断，不是全路径）", style="Panel.TLabel",
                  font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w", padx=10, pady=(10, 2))
        link_box = ttk.Frame(left, style="Panel.TFrame")
        link_box.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        lcols = ("pair", "channel", "status", "evidence")
        self.link_tree = ttk.Treeview(link_box, columns=lcols, show="headings", height=6)
        for key, title, width in (("pair", "链路", 104), ("channel", "通道", 56),
                                  ("status", "状态", 96), ("evidence", "判据", 210)):
            self.link_tree.heading(key, text=title)
            self.link_tree.column(key, width=width, anchor="w")
        link_sb = ttk.Scrollbar(link_box, orient="vertical", command=self.link_tree.yview)
        self.link_tree.configure(yscrollcommand=link_sb.set)
        self.link_tree.pack(side="left", fill="both", expand=True)
        link_sb.pack(side="right", fill="y")

        # -------- 右：消息
        right = ttk.Frame(split, style="Panel.TFrame")
        split.add(right, weight=5)

        head = ttk.Frame(right, style="Panel.TFrame")
        head.pack(fill="x", padx=10, pady=(8, 2))
        ttk.Label(head, text="消息", style="Panel.TLabel",
                  font=("Microsoft YaHei UI", 10, "bold")).pack(side="left")
        self.msg_hint = ttk.Label(head, text="", style="Panel.TLabel", foreground=MUTED)
        self.msg_hint.pack(side="left", padx=10)

        msg_box = ttk.Frame(right, style="Panel.TFrame")
        msg_box.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        mcols = ("mid", "state", "run", "src", "dst", "attempts", "ack", "created")
        self.msg_tree = ttk.Treeview(msg_box, columns=mcols, show="headings", height=14)
        for key, title, width, anchor in (
                ("mid", "消息编号", 96, "center"),
                ("state", "状态", 104, "w"),
                ("run", "run_id", 104, "w"),
                ("src", "来源", 58, "center"),
                ("dst", "目标", 42, "center"),
                ("attempts", "尝试", 42, "center"),
                ("ack", "最后 ACK", 84, "center"),
                ("created", "创建时刻", 76, "center")):
            self.msg_tree.heading(key, text=title)
            self.msg_tree.column(key, width=width, anchor=anchor)
        msg_sb = ttk.Scrollbar(msg_box, orient="vertical", command=self.msg_tree.yview)
        self.msg_tree.configure(yscrollcommand=msg_sb.set)
        self.msg_tree.pack(side="left", fill="both", expand=True)
        msg_sb.pack(side="right", fill="y")
        self.msg_tree.bind("<<TreeviewSelect>>", self.on_message_select)

        # -------- 底：详情
        self.detail_nb = ttk.Notebook(self.root)
        self.detail_nb.pack(fill="both", expand=False, padx=10, pady=(0, 6))

        ev_frame = ttk.Frame(self.detail_nb, style="Panel.TFrame")
        self.detail_nb.add(ev_frame, text="选中消息的事件")
        ecols = ("ms", "event", "result", "reason", "channel", "node", "source", "details")
        self.event_tree = ttk.Treeview(ev_frame, columns=ecols, show="headings", height=8)
        for key, title, width, anchor in (
                ("ms", "时刻 ms", 82, "center"),
                ("event", "事件", 156, "w"),
                ("result", "result", 76, "center"),
                ("reason", "reason", 112, "center"),
                ("channel", "通道", 66, "center"),
                ("node", "节点", 56, "center"),
                ("source", "数据来源", 82, "center"),
                ("details", "details", 520, "w")):
            self.event_tree.heading(key, text=title)
            self.event_tree.column(key, width=width, anchor=anchor)
        ev_sb = ttk.Scrollbar(ev_frame, orient="vertical", command=self.event_tree.yview)
        self.event_tree.configure(yscrollcommand=ev_sb.set)
        self.event_tree.pack(side="left", fill="both", expand=True)
        ev_sb.pack(side="right", fill="y")

        issue_frame = ttk.Frame(self.detail_nb, style="Panel.TFrame")
        self.detail_nb.add(issue_frame, text="问题行 (0)")
        icols = ("line", "level", "code", "message", "raw")
        self.issue_tree = ttk.Treeview(issue_frame, columns=icols, show="headings", height=8)
        for key, title, width in (("line", "行号", 60), ("level", "级别", 56),
                                  ("code", "代码", 130), ("message", "说明", 320),
                                  ("raw", "原始行", 620)):
            self.issue_tree.heading(key, text=title)
            self.issue_tree.column(key, width=width, anchor="w")
        is_sb = ttk.Scrollbar(issue_frame, orient="vertical", command=self.issue_tree.yview)
        self.issue_tree.configure(yscrollcommand=is_sb.set)
        self.issue_tree.pack(side="left", fill="both", expand=True)
        is_sb.pack(side="right", fill="y")

    def _build_statusbar(self) -> None:
        bar = tk.Frame(self.root, bg="#e9edf3")
        bar.pack(fill="x", side="bottom")
        self.status = tk.Label(bar, text="还没有打开日志。点右上角「打开示例…」先看一份 SIM 样例。",
                               anchor="w", bg="#e9edf3", fg="#374151", padx=10, pady=5)
        self.status.pack(side="left")

    # ------------------------------------------------------------ 打开

    def ask_open(self) -> None:
        path = filedialog.askopenfilename(
            title="选择日志文件（JSONL）",
            filetypes=[("日志 JSONL", "*.jsonl"), ("所有文件", "*.*")],
            initialdir=SAMPLES if os.path.isdir(SAMPLES) else HERE)
        if path:
            self.open_path(path)

    def ask_sample(self) -> None:
        if not os.path.isdir(SAMPLES):
            messagebox.showwarning("没有样例目录", f"找不到样例目录：\n{SAMPLES}")
            return
        files = sorted(f for f in os.listdir(SAMPLES) if f.endswith(".jsonl"))
        if not files:
            messagebox.showwarning("没有样例文件", "samples/ 里没有 .jsonl 样例。")
            return
        pick = SampleDialog(self.root, files).result
        if pick:
            self.open_path(os.path.join(SAMPLES, pick))

    def open_path(self, path: str) -> None:
        try:
            loaded = load_file(path)
        except Exception as exc:  # 打不开也不能崩，给人看得懂的话
            messagebox.showerror("打不开这个文件", f"{path}\n\n{exc}")
            self.status.configure(text=f"打开失败：{path}（{exc}）")
            return
        state = build(loaded, t_down_ms=DEFAULT_T_DOWN_MS)
        self.loaded, self.state, self.current_path = loaded, state, path
        self.root.title(f"MobiWeave 上位机 · {os.path.basename(path)}")
        self._render()

    # ------------------------------------------------------------ 渲染

    def _render(self) -> None:
        assert self.state is not None and self.loaded is not None
        state = self.state

        self._set_banner(state.banner)

        # 节点
        self.node_tree.delete(*self.node_tree.get_children())
        link_status_by_node: dict = {}
        for link in state.links:
            link_status_by_node.setdefault(link.node_id, []).append(link.status)
        for node in state.nodes:
            statuses = link_status_by_node.get(node.node_id, [])
            if not statuses:
                status, tag = STATUS_UNKNOWN, "unknown"
            elif any(s == STATUS_DOWN_CONFIRMED for s in statuses):
                status, tag = STATUS_DOWN_CONFIRMED, "down"
            elif any(s == STATUS_DOWN_INFERRED for s in statuses):
                status, tag = STATUS_DOWN_INFERRED, "inferred"
            elif any(s == STATUS_OK for s in statuses):
                status, tag = STATUS_OK, "ok"
            else:
                status, tag = STATUS_UNKNOWN, "unknown"
            self.node_tree.insert("", "end", tags=(tag,), values=(
                node.node_id, status, node.records,
                _elide(f"{node.last_event}@{node.last_ms}", 15)))

        # 链路
        self.link_tree.delete(*self.link_tree.get_children())
        for link in state.links:
            self.link_tree.insert("", "end", values=(
                f"{link.node_id} ↔ {link.peer_id}", link.channel,
                link.status, _elide(link.evidence, 30)))

        # 消息
        self.msg_tree.delete(*self.msg_tree.get_children())
        for msg in state.messages:
            self.msg_tree.insert("", "end", iid=self._msg_iid(msg), values=(
                msg.mid, msg.state, msg.run_id,
                _short_source(msg.source_kind),
                "-" if msg.destination is None else msg.destination,
                msg.attempts or "-",
                _elide(msg.last_ack or "-", 9),
                "-" if msg.created_ms is None else msg.created_ms))
        self.msg_hint.configure(text=f"共 {len(state.messages)} 条消息")

        # 问题行
        self.issue_tree.delete(*self.issue_tree.get_children())
        for issue in state.issues:
            self.issue_tree.insert("", "end", values=(
                issue.line_no, issue.level, issue.code, issue.message,
                _elide(issue.raw, 160)))
        self.detail_nb.tab(1, text=f"问题行 ({len(state.issues)})")

        # 详情清空（换文件后不能残留上一条）
        self.event_tree.delete(*self.event_tree.get_children())
        self.selected_message = None

        self.status.configure(text=(
            f"{os.path.basename(self.current_path or '-')}：共 {state.total_lines} 行，"
            f"导入 {len(state.records)} 条记录，坏行 {state.bad_lines} 条，"
            f"错误 {state.error_count} 条，提示 {state.hint_count} 条；"
            f"数据来源 {('、'.join(state.sources) or '无')}"))

    def on_message_select(self, _event=None) -> None:
        sel = self.msg_tree.selection()
        if not sel or self.state is None:
            return
        target = sel[0]
        msg = next((m for m in self.state.messages if self._msg_iid(m) == target), None)
        if msg is None:
            return
        self.selected_message = msg
        self.event_tree.delete(*self.event_tree.get_children())
        for row in msg.timeline:
            self.event_tree.insert("", "end", values=(
                row.ms, row.event, row.result, row.reason or "-",
                row.channel or "-", row.node_id, _short_source(row.source_kind),
                _elide(row.detail_text, 160)))
        self.detail_nb.select(0)

    @staticmethod
    def _msg_iid(msg: MessageView) -> str:
        return f"{msg.run_id}|{msg.mid}"

    # ------------------------------------------------------------ 查找

    def do_search(self) -> None:
        if self.state is None:
            return
        needle = self.search_var.get().strip()
        if not needle:
            self.status.configure(text="先在右边输入要查的消息编号，再点「查找」。")
            return
        hits = [m for m in self.state.messages if m.mid == needle]
        if not hits:
            hits = [m for m in self.state.messages if needle in m.mid]
        self._search_hits = hits
        self._search_index = -1
        if not hits:
            self.status.configure(text=f"没有找到编号为「{needle}」的消息。")
            return
        self.next_hit()

    def next_hit(self) -> None:
        if not self._search_hits:
            return
        self._search_index = (self._search_index + 1) % len(self._search_hits)
        msg = self._search_hits[self._search_index]
        iid = self._msg_iid(msg)
        self.msg_tree.selection_set(iid)
        self.msg_tree.focus(iid)
        self.msg_tree.see(iid)
        self.on_message_select()
        self.status.configure(text=(
            f"找到 {len(self._search_hits)} 条编号为 {msg.mid} 的记录"
            f"（第 {self._search_index + 1} 条，run_id={msg.run_id}，状态：{msg.state}）；"
            f"按回车或「下一个」继续"))

    # ------------------------------------------------------------ 保存

    def save_raw(self) -> None:
        if not self.current_path:
            messagebox.showinfo("还没有打开日志", "先打开一份日志，再保存。")
            return
        base = os.path.basename(self.current_path)
        path = filedialog.asksaveasfilename(
            title="保存原始记录（逐行原样复制，坏行也保留）",
            defaultextension=".jsonl", initialfile=f"saved-{base}",
            filetypes=[("日志 JSONL", "*.jsonl"), ("所有文件", "*.*")],
            initialdir=HERE)
        if not path:
            return
        try:
            shutil.copyfile(self.current_path, path)
        except OSError as exc:
            messagebox.showerror("保存失败", str(exc))
            return
        self.status.configure(text=f"已保存 {os.path.getsize(path)} 字节到 {path}（原样复制，可直接重新打开）")
        if messagebox.askyesno("保存完成", f"已保存到：\n{path}\n\n现在重新打开这份文件核对一遍吗？"):
            self.open_path(path)


def _short_source(kind: str) -> str:
    # 表格里只放缩写，完整含义写在状态栏和图例里
    return {"SIM": "SIM", "REAL": "REAL", "ESTIMATED": "EST"}.get(kind, kind)


class SampleDialog(tk.Toplevel):
    """挑样例的小窗（只用标准库，不引第三方）。"""

    def __init__(self, master: tk.Tk, files: list) -> None:
        super().__init__(master)
        self.title("选择示例日志")
        self.result: str | None = None
        self.configure(bg=BG)
        self.transient(master)
        self.grab_set()
        tk.Label(self, text="仓库里带的样例（SIM = 模拟数据，不是真实链路）",
                 bg=BG, fg=INK, padx=12, pady=8).pack(anchor="w")
        box = tk.Listbox(self, height=min(8, max(3, len(files))), width=52,
                         activestyle="none", bg=PANEL, fg=INK,
                         highlightthickness=1, highlightbackground=LINE)
        for name in files:
            box.insert("end", name)
        box.selection_set(0)
        box.pack(padx=12, pady=(0, 10))
        box.bind("<Double-Button-1>", lambda _e: self._ok(box))

        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(row, text="取消", command=self.destroy).pack(side="right")
        ttk.Button(row, text="打开", command=lambda: self._ok(box)).pack(side="right", padx=6)

        self.update_idletasks()
        x = master.winfo_rootx() + 120
        y = master.winfo_rooty() + 90
        self.geometry(f"+{x}+{y}")
        self.wait_window(self)

    def _ok(self, box: tk.Listbox) -> None:
        sel = box.curselection()
        if sel:
            self.result = box.get(sel[0])
        self.destroy()


def main(argv: list) -> int:
    initial = argv[1] if len(argv) > 1 else None
    root = tk.Tk()
    App(root, initial)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
