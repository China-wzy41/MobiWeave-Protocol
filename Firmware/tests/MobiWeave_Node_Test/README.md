# MobiWeave M1 联调：ACK / 重传 / 去重

在 [Link_Test](../MobiWeave_Link_Test/README.md) 验证过"帧能收发"的基础上，加上协议真正缺的那一层：**确认、重传、去重**。

> 本目录只用 g++ 做过语法检查；主机端逻辑测试（`test_mw_protocol.cpp`）编译通过但**未在实机运行**，本机策略禁止执行编译产物。首次上板请从下面「第一轮」开始。

## 文件

| 文件 | 作用 |
|---|---|
| `mw_protocol.h` / `.cpp` | 协议核心：组帧、CRC、流式分帧、ACK、重传状态机、去重缓存。**不依赖 Arduino**，可在电脑上单测 |
| `MobiWeave_Node_Test.ino` | 板端程序：两块板同一份，只改 `MW_ROLE` |
| `test_mw_protocol.cpp` | 主机端测试（28 项），`g++ test_mw_protocol.cpp mw_protocol.cpp -o t && ./t` |
| `model_check.py` | 同一套状态机的 Python 模型，`python model_check.py`（本机可跑，已 28/28 通过） |

`mw_protocol.cpp` 与 `model_check.py` 是两份互相校对的实现：改协议逻辑时两边都要改，否则模型失去意义。

## 烧录

两块板同一份代码：

```cpp
#define MW_ROLE   0        // A 板：发送端，node_id = 1
```

```cpp
#define MW_ROLE   1        // B 板：接收端，node_id = 2
```

其余与 Link_Test 相同：`LORA_BAUD 9600`、`USB CDC On Boot = Disabled`、引脚 17/18。

## 命令

| 键 | 作用 |
|---|---|
| `1` | 手动发一条消息 |
| `2` | 每 3 秒自动发一条，再按停止 |
| `0` | 停止发送 |
| `r` | 打印统计 |
| `v` | 开关人类可读行（关掉只剩 JSONL） |
| `RUN <id>` | 设置实验编号并开新日志会话 |

## 第一轮：正常确认

1. 两块板都烧好，接线（17↔18 交叉 + GND）
2. B 板先不动，A 板按 `1`

**A 侧预期**：
```
QUEUED seq=101
TX  seq=101 attempt=1 len=39
ACK seq=101 status=ACCEPTED
HOP_CONFIRMED 本跳完成
```

**B 侧预期**：
```
RX seq=101 -> ACCEPTED
```

A 侧出现 `HOP_CONFIRMED`，说明**一条消息在本跳被确认**——这是 M1 的第一个硬指标。

## 第二轮：重传

只开 A（B 断电或拔掉模块天线）：

- A 侧应看到 `attempt=1/2/3` 三次 `TX`，间隔约 1 秒
- 然后 `TRANSFER_FAILED 重试用尽`

再给 B 上电、A 重发同一条（需要 B 保留缓存）：B 会回 `ALREADY_HAVE`，A 直接 `HOP_CONFIRMED`，B 侧 `RX ... -> ALREADY_HAVE` 且缓存计数不涨。

## 第三轮：去重

B 板按 `r` 看 `cache=` 和 `dup=`：

- 同一 `sequence` 重发 3 次 → `cache` 只 +1，`dup` +2
- 这是"重复消息不得重复交付"的直接证据

## 第四轮：缓存满

B 连收 9 条不同消息（A 按 `2` 自动发，seq 递增）：

- 前 8 条 → `ACCEPTED`
- 第 9 条 → `BUSY`，A 侧进入 `DEFERRED`，延后重试

## 已知限制

- **没有转发**：B 不会把消息转给第三方，三节点要等下一版
- **boot_counter 固定为 7**：重启编号不重复还没实现（需要持久化）
- **age_ms 恒为 0**：有效期累计没实现，只能验"过期拒收"的判定分支
- **一次只有一条在途**：没有队列，消息会排队等前一条结束
- **无半帧空闲超时**：半帧会一直挂在解析器里（日志表现为 `pending` 不归零）

## 日志

沿用 [日志 V1](../../../docs/protocol/log-v1.md)。本版新增事件：`MESSAGE_CREATED`、`ACK_TX`、`ACK_RX`、`HOP_CONFIRMED`、`RETRY_SCHEDULED`、`MESSAGE_CACHED`、`TRANSFER_FAILED`。

抓包后校验：

```powershell
python tools/mwlog_check.py --strict capture.txt
```
