"""对接验收用的自检：拿一份日志，逐条核对「显示得对不对」。

跑法：
    python -m mwlog.acceptance samples\\log-v1-sim.jsonl
    python -m mwlog.acceptance new-from-A.jsonl --verbose

它只做两件事：
1. 打印每条消息的关键事实（几号、状态、DATA_TX 几次、attempt 列表、有没有 ACK、有没有最终交付）；
2. 按下面 4 条规则判 PASS / FAIL，并给出"人话解释"。

规则（来自任务 #20 与组员口头约定）：
    R1 正常单跳收发：有 DATA_TX + 本跳 ACK，没有最终交付 → 必须显示「本跳已确认」
    R2 重发场景：同一个 message_id 的多次发送必须归在同一条消息下，attempt 从 1 连续递增，
       且最终状态是「本跳已确认」或「已送达」
    R3 只有出现 APP_DELIVERED 才允许显示「已送达」
    R4 没有任何确认证据的消息不能显示成「正常/已送达」，只能是「已发出，等确认」或更早的状态

任何一条不成立就返回 1，方便直接接进脚本或 CI。
"""

from __future__ import annotations

import os
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from mwlog.records import load_file  # type: ignore
    from mwlog.state import build  # type: ignore
else:
    from .records import load_file
    from .state import build


def _attempts_of(msg) -> list:
    seen = []
    for row in msg.timeline:
        if row.event == "DATA_TX":
            detail = row.detail_text
            for part in detail.split(","):
                part = part.strip()
                if part.startswith("attempt="):
                    try:
                        seen.append(int(part.split("=", 1)[1]))
                    except ValueError:
                        pass
    return seen


def main(argv: list) -> int:
    if len(argv) < 2:
        print("用法: python -m mwlog.acceptance <日志.jsonl> [--verbose]")
        return 2
    path = argv[1]
    verbose = "--verbose" in argv

    loaded = load_file(path)
    state = build(loaded)

    print("=" * 78)
    print(f"文件: {path}")
    print(f"行数 {state.total_lines}｜有效记录 {len(state.records)}｜坏行 {state.bad_lines}"
          f"｜错误 {state.error_count}｜提示 {state.hint_count}｜来源 {'/'.join(state.sources) or '无'}")
    if state.banner:
        print(f"横幅: {state.banner[:60]}…")

    print("=" * 78)
    header = f"{'消息编号':<12}{'状态':<14}{'DATA_TX':<8}{'attempt':<12}{'ACK':<14}{'最终交付':<8}"
    print(header)
    print("-" * 78)
    for msg in state.messages:
        attempts = _attempts_of(msg)
        ack = msg.last_ack or "-"
        delivered = "是" if msg.delivered else "否"
        print(f"{msg.mid:<12}{msg.state:<14}{msg.tx_count:<8}"
              f"{(','.join(str(a) for a in attempts) or '-'):<12}{ack:<14}{delivered:<8}")
        if verbose:
            for row in msg.timeline:
                print(f"    {row.ms:>7} ms  {row.event:<18}{row.result:<10}{row.detail_text[:70]}")

    print("=" * 78)
    passed, failed = [], []

    def check(name: str, ok: bool, detail: str) -> None:
        (passed if ok else failed).append(name)
        print(f"  {'PASS' if ok else 'FAIL'}  {name}  —— {detail}")

    OK_ACK_STATUS = {"ACCEPTED", "ALREADY_HAVE"}

    for msg in state.messages:
        attempts = _attempts_of(msg)
        # 只有 ACCEPTED / ALREADY_HAVE 这种"对方收下了"的 ACK 才算成功；
        # ACK 里带 EXPIRED / REJECTED / DUPLICATE 仍然是失败，不能当成确认。
        ack_statuses = [row.detail_text for row in msg.timeline
                        if row.event in ("HOP_CONFIRMED", "ACK_RX")]
        has_ack = bool(msg.hop_confirmed) or any(
            status in text for text in ack_statuses for status in OK_ACK_STATUS)
        terminal = msg.expired or msg.dropped
        tag = f"[{msg.mid} run={msg.run_id}]"

        # R1 正常单跳：有发送、有本跳 ACK、没有最终交付 → 本跳已确认
        if msg.tx_count and has_ack and not msg.delivered and not terminal:
            check(f"R1 {tag} 正常单跳显示本跳已确认", msg.state == "本跳已确认",
                  f"实际显示「{msg.state}」，DATA_TX {msg.tx_count} 次，ACK={msg.last_ack}")
        # R2 重发：多次发送 + attempts 连续 + 最终确认为止
        if len(attempts) >= 2:
            contiguous = attempts == list(range(1, len(attempts) + 1))
            check(f"R2 {tag} 重发归在同一条消息下（attempt 连续）", contiguous,
                  f"attempt 列表 {attempts}")
            check(f"R2 {tag} 重发后状态是确认类", msg.state in ("本跳已确认", "已送达"),
                  f"实际显示「{msg.state}」")
        # R3 已送达只能由 APP_DELIVERED 触发
        if msg.state == "已送达":
            check(f"R3 {tag} 已送达必须有最终交付事件", msg.delivered,
                  "有 APP_DELIVERED，对应得上" if msg.delivered
                  else "状态是已送达但没看到 APP_DELIVERED")
        # R4 无证据不能显示成正常/送达
        if msg.tx_count and not has_ack and not msg.delivered and not terminal:
            allowed = ("已发出，等确认", "存在被拒帧", "已创建", "本轮失败")
            check(f"R4 {tag} 没有成功的 ACK 时不得显示成确认", msg.state in allowed,
                  f"实际显示「{msg.state}」（ACK 状态 {msg.last_ack}）")

    if not failed:
        print("-" * 78)
        print(f"总结论: PASS — {len(passed)} 项检查全部通过")
        return 0
    print("-" * 78)
    print(f"总结论: FAIL — {len(failed)} 项不通过")
    for name in failed:
        print("   - " + name)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
