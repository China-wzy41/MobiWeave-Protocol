# 协议与日志

2026-11-23 起，协议和日志格式冻结为 v1。冻结的工作基线是 B（hsr）工作分支 `Yanis0118-patch-1` 尖端 `ca128e3d88589a5ef82af96bcf9f2ea97a2768ec` 上的现有日志，不在 `main`：

- `docs/protocol/log-v1.md`
- `docs/protocol/examples/log-v1-sim.jsonl`
- `docs/protocol/examples/log-v1-extra.jsonl`
- `tools/mwlog_check.py`

同一次提交里还有 `docs/protocol/protocol-v1.md` 和 `tools/mwframe.py`。这些文件正文仍写着候选、尚未冻结，那是决定之前的文字。本次不把该分支并进 `main`。

四件事分开：

1. 格式已经冻结，以上面的日志为工作基线。
2. 团队计划在 2026-11-23 晚间另行开启把 v1 送进 `main` 的拉取请求。本说明不把那个请求写成已经打开或已经合并。
3. 合入 `main` 还没有发生。
4. 确认、重试、去重、转发、多跳各自还要证据。样例日志不是无线实测。

[本目录的 protocol-v1.md](protocol-v1.md) 是 `main` 上更早的讨论稿，不是第二套格式。与分支不一致时，以分支上的 v1 日志为准。

不记录 SNR：DX-LR22 只有 RSSI（`AT+DRSSI1`）。没有测到的接收电平、电量和位置不要补造。方向见 [长期计划](../planning/长期计划.md)。
