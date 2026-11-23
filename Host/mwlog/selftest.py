"""自检：不用打开界面，也能证明解析器和聚合逻辑是对的。

跑法：`python -m mwlog.selftest`（在 Host/ 目录下），或者直接 `python mwlog/selftest.py`。
每一条都是断言，任何一条不成立就以非零码退出。
"""

from __future__ import annotations

import os
import sys
import tempfile

if __package__ in (None, ""):  # 允许 python mwlog/selftest.py 直接跑
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from mwlog.records import load_file  # type: ignore
    from mwlog.state import (  # type: ignore
        STATUS_DOWN_CONFIRMED, STATUS_DOWN_INFERRED, STATUS_OK, STATUS_UNKNOWN, build)
else:
    from .records import load_file
    from .state import (STATUS_DOWN_CONFIRMED, STATUS_DOWN_INFERRED, STATUS_OK,
                        STATUS_UNKNOWN, build)

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(os.path.dirname(HERE), "samples")

PASSED: list = []
FAILED: list = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(name)
        print(f"  PASS  {name}")
    else:
        FAILED.append(f"{name} {detail}".strip())
        print(f"  FAIL  {name}  {detail}")


def _write_temp(text: str) -> str:
    handle = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False,
                                         encoding="utf-8", newline="\n")
    handle.write(text)
    handle.close()
    return handle.name


GOOD = ('{{"format_version":1,"run_id":"t1","source_kind":"SIM","code_version":null,'
        '"config_version":null,"strategy_version":null,"node_id":1,"session_id":"s1",'
        '"event_seq":{seq},"monotonic_ms":{ms},"clock_basis":"simulation_run",'
        '"message_id":{mid},"event":"{event}","result":"{result}","reason":{reason},'
        '"details":{details},"channel":"uart1"}}')

MID = '{"source_id":1,"boot_counter":1,"sequence":1}'


def main() -> int:
    print("=" * 66)
    print("1) 仓库样例：两份都必须零错误导入")
    sim = load_file(os.path.join(SAMPLES, "log-v1-sim.jsonl"))
    extra = load_file(os.path.join(SAMPLES, "log-v1-extra.jsonl"))
    check("sim 样例 0 条导入错误", len(sim.errors) == 0, f"实际 {len(sim.errors)} 条：{[e.message for e in sim.errors[:2]]}")
    check("extra 样例 0 条导入错误", len(extra.errors) == 0, f"实际 {len(extra.errors)} 条：{[e.message for e in extra.errors[:2]]}")
    check("sim 读到 19 条记录", len(sim.records) == 19, f"实际 {len(sim.records)}")
    check("extra 读到 16 条记录", len(extra.records) == 16, f"实际 {len(extra.records)}")

    print("=" * 66)
    print("2) 聚合：节点 / 消息状态 / 链路四态")
    v = build(sim)
    check("识别出 3 个节点", len(v.nodes) == 3, f"实际 {[n.node_id for n in v.nodes]}")
    check("SIM 出现时必须标模拟数据", bool(v.banner) and "模拟" in v.banner)

    by_mid = {(m.run_id, m.mid): m for m in v.messages}
    normal = by_mid.get(("example-normal", "1-7-12"))
    check("example-normal 状态是「已送达」", normal is not None and normal.state == "已送达",
          f"实际 {normal.state if normal else '没找到'}")
    retry = by_mid.get(("example-retry", "1-7-12"))
    check("example-retry 状态是「本跳已确认」", retry is not None and retry.state == "本跳已确认",
          f"实际 {retry.state if retry else '没找到'}")
    check("重试样例记录了 2 次尝试", retry is not None and retry.attempts == 2,
          f"实际 {retry.attempts if retry else '-'}")
    check("同一编号跨 run 不合并", len({m.mid for m in v.messages}) < len(v.messages))

    ve = build(extra)
    link = next((l for l in ve.links if l.peer_id == 2 and l.node_id == 1), None)
    check("example-link 判为「断开（已确认）」", link is not None and link.status == STATUS_DOWN_CONFIRMED,
          f"实际 {link.status if link else '没找到'}")
    check("LINK_UP / LINK_DOWN 不再是未知事件",
          not any("UNKNOWN_EVENT" == i.code for i in ve.issues))

    print("=" * 66)
    print("3) 坏输入：每种都要变成问题行，且不崩")
    bad = _write_temp(
        "这不是 JSON，是串口调试文本\n"
        "\n"                                                                       # 空行
        + GOOD.format(seq=1, ms=0, mid=MID, event="MESSAGE_CREATED", result="OK",
                      reason="null", details='{"destination_id":2}') + "\n"
        + GOOD.format(seq=2, ms=10, mid=MID, event="DATA_TX", result="OK",
                      reason='"没理由但写了"', details='{"peer_id":2,"attempt":1,"frame_bytes":40,"tx_scope":"local_uart_queued"}') + "\n"
        + '{"format_version":1,"run_id":"t1"}\n'                                 # 缺字段
        + GOOD.format(seq=3, ms=20, mid="null", event="WEIRD_EVENT", result="OK",
                      reason="null", details='{}') + "\n"
        + GOOD.format(seq=4, ms=30, mid=MID, event="APP_DELIVERED", result="OK",
                      reason="null", details='{"destination_id":2}')            # 末行无换行
    )
    vb = load_file(bad)
    codes = {i.code for i in vb.issues}
    check("调试文本被识别为非 JSON", "NOT_JSON" in codes, f"实际 {sorted(codes)}")
    check("空行被拒绝", "EMPTY_LINE" in codes)
    check("缺字段被拒绝", "MISSING_FIELD" in codes)
    check("result=OK 带 reason 被拒绝", "REASON_ON_OK" in codes)
    check("未知事件只提示、不丢记录", "UNKNOWN_EVENT" in codes and any(r.event == "WEIRD_EVENT" for r in vb.records))
    check("坏行之后仍继续读", any(r.event == "APP_DELIVERED" for r in vb.records))
    check("问题行保留原始行", any("这不是 JSON" in i.raw for i in vb.issues))
    os.unlink(bad)

    print("=" * 66)
    print("4) 链路推断：超过 T_down 且没有新证据 → 「断开（推断）」")
    lines = [
        GOOD.format(seq=1, ms=0, mid=MID, event="HOP_CONFIRMED", result="OK",
                    reason="null", details='{"peer_id":2,"ack_status":"ACCEPTED"}'),
        GOOD.format(seq=2, ms=90000, mid=MID, event="DATA_TX", result="OK",
                    reason="null", details='{"peer_id":2,"attempt":1,"frame_bytes":40,"tx_scope":"local_uart_queued"}'),
    ]
    inf = _write_temp("\n".join(lines) + "\n")
    vi = build(load_file(inf), t_down_ms=30_000)
    lk = vi.links[0]
    check("判为「断开（推断）」", lk.status == STATUS_DOWN_INFERRED, f"实际 {lk.status}")
    check("推断态与确认态可区分", lk.status != STATUS_DOWN_CONFIRMED)
    vi2 = build(load_file(inf), t_down_ms=300_000)
    check("阈值放大后回到「正常」（说明 T_down 真的在起作用）", vi2.links[0].status == STATUS_OK,
          f"实际 {vi2.links[0].status}")
    os.unlink(inf)

    print("=" * 66)
    print("5) 去重：同一唯一键只保留第一条")
    dup_line = GOOD.format(seq=1, ms=0, mid=MID, event="MESSAGE_CREATED", result="OK",
                           reason="null", details='{"destination_id":2}')
    dup = _write_temp((dup_line + "\n") * 2)
    vd = load_file(dup)
    check("重复键只留 1 条记录", len(vd.records) == 1, f"实际 {len(vd.records)}")
    check("重复键给出提示", any(i.code == "DUPLICATE_KEY" for i in vd.issues))
    os.unlink(dup)

    print("=" * 66)
    print("6) 空链路：没有任何证据必须是「未知」，不能显示成正常")
    empty = _write_temp(GOOD.format(seq=1, ms=0, mid=MID, event="DATA_TX", result="OK",
                                    reason="null", details='{"peer_id":2,"attempt":1,"frame_bytes":40,"tx_scope":"local_uart_queued"}') + "\n")
    vu = build(load_file(empty))
    check("只有 DATA_TX 时链路是「未知」", vu.links[0].status == STATUS_UNKNOWN,
          f"实际 {vu.links[0].status}")
    os.unlink(empty)

    print("=" * 66)
    total = len(PASSED) + len(FAILED)
    if FAILED:
        print(f"总结论: FAIL — {len(FAILED)}/{total} 项未通过")
        for item in FAILED:
            print("   - " + item)
        return 1
    print(f"总结论: PASS — {len(PASSED)}/{total} 项全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
