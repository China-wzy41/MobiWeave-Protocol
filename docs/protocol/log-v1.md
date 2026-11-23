# MobiWeave 日志 V1

状态：**结构已冻结（2026-11-23）**。第 2 节的必填字段与类型、第 3 节的事件名与语义视为稳定，可据此开发；第 3 节的**事件按里程碑逐步实现**，新增事件与新增可选字段不升版本。
当前实现进度：板端已输出 `BOOT`、`DATA_TX`、`DATA_RX`、`FRAME_REJECTED` 四个事件，其余事件待协议实现跟上。
本规范不改变无线 DATA/ACK 字段。旧草图的人类可读输出不属本格式，抓包时按非 JSON 行跳过。

## 1. 编码与边界

采用 UTF-8 JSON Lines：每行一个完整 JSON 对象，以 LF 结束；读取端也接受 CRLF。字符串中的换行由 JSON 转义，禁止直接拆成多行。无 BOM、无 NaN/Infinity、无重复键。数值使用十进制，不写 0x 前缀。

每行上限暂定 4096 字节（不含行尾），是日志接口限制，不是无线包限制。超限行拒绝并记录导入错误；不能截断后当成有效 JSON。读取端需处理半行、连续多行和行尾前断连，未完成行不输出业务事件。

日志走 USB 调试通道或电脑文件，默认不发往 LoRa。若共享同一串口，纯文本调试行不属于 V1 日志，应单独保存或标注为非结构化行，禁止补造事件。未知版本保留原文并报告 unsupported_log_version；未知附加字段忽略，未知事件只展示原文，不参与指标计算。

## 2. 每行必有的字段

| 字段 | JSON 类型 | 含义与约束 |
|---|---|---|
| format_version | integer | 固定 1 |
| run_id | string | 1～64 个 ASCII 字符，限字母数字及 . _ -；同一次实验统一 |
| source_kind | string | REAL / SIM / ESTIMATED；说明记录来源 |
| code_version | string 或 null | 代码提交号或构建版本；未知为 null |
| config_version | string 或 null | 配置版本或配置内容哈希，实验记录需能查到配置 |
| strategy_version | string 或 null | 调度/转发策略版本；未知为 null |
| node_id | integer | 产生日志的节点，1～65534 |
| session_id | string | 本节点本次启动的日志会话，1～64 个 ASCII 字符；同一 run_id、来源、节点内不得重复 |
| event_seq | integer | 本会话从 1 递增，范围 1～4294967295；耗尽前开启新会话 |
| monotonic_ms | integer | 本会话起点以来的单调毫秒，0～9007199254740991；同会话不递减 |
| clock_basis | string | node_session / simulation_run；REAL 用前者，SIM 用后者 |
| message_id | object 或 null | 可可信关联时为 source_id、boot_counter、sequence；不能可信解析时为 null |
| event | string | 下表固定事件名 |
| result | string | OK / REJECTED / RETRY / FAILED / INFO |
| reason | string 或 null | result=OK 时必须为 null；REJECTED / RETRY / FAILED 必须使用原因码；INFO 为 null |
| details | object | 事件参数；无附加信息用 {} |
| channel | string | 事件所属物理通道：`uart0` 为 USB 调试口，`uart1` 为 LoRa 串口，其他通道另行约定。对 DATA_TX、ACK_TX、MESSAGE_FORWARDED、DATA_RX、ACK_RX、FRAME_REJECTED、STREAM_TIMEOUT、LINK_UP、LINK_DOWN 必填；其余事件可省略 |

channel 用于把事件归属到某一对节点/某一条串口。多串口上位机必须据此区分，不能只按 COM 口顺序猜。channel 不是 node_id，也不是模块地址。

message_id 中 source_id 为 1～65534，boot_counter、sequence 为 1～4294967295。日志编号本身不代替持久化消息编号方案。

session_id 可采用主机分配的唯一会话标记，或已可靠递增的节点启动计数；未实现可靠启动计数时不得声称它已经持久化。日志唯一键为 (run_id, source_kind, node_id, session_id, event_seq)。上位机据此去除日志重复；不得只按 message_id 去重，因为一条消息具有多个事件。

同节点允许同毫秒多个事件，用 event_seq 排序。重启必须换 session_id。板端若使用 32 位 millis()，应扩展回绕或在回绕前切新日志会话，不能将回绕后的值直接记为单调时间。

event_seq 在**同一个 session_id 内**唯一并从 1 递增；不同 run 或不同会话之间可以重复。session_id 本身在 (run_id, source_kind, node_id) 内唯一，因此同一 session_id 不得跨 run 复用，但同一节点在不同 run 里出现同名会话本身不构成错误。

## 3. 事件与语义

除 BOOT、FRAME_REJECTED、STREAM_TIMEOUT、LINK_UP、LINK_DOWN 外，下列事件要求 message_id 非 null。链路事件不对应具体消息，只带 peer_id。

| event | result | details 必填内容 | 何时记录 |
|---|---|---|---|
| BOOT | INFO | 无 | 启动日志会话，message_id=null |
| MESSAGE_CREATED | OK | destination_id | 新建消息 |
| DATA_TX | OK | peer_id、attempt、frame_bytes、tx_scope | 整帧已交给底层发送接口；tx_scope 固定 local_uart_queued，不代表无线完成或送达 |
| DATA_RX | OK | peer_id、frame_bytes | 完整帧及业务检查通过；尚不等于缓存成功 |
| MESSAGE_CACHED | OK | storage | 实际缓存完成，storage=RAM 或 FLASH；FLASH 必须确有持久化验证 |
| ACK_TX | OK | peer_id、ack_status、frame_bytes、tx_scope | ACK 已交给底层；tx_scope 同上 |
| ACK_RX | OK | peer_id、ack_status、frame_bytes | 有效 ACK 被解析，但尚不等于与等待消息匹配 |
| HOP_CONFIRMED | OK | peer_id、ack_status | 与等待消息及邻居匹配，状态为 ACCEPTED/ALREADY_HAVE，结束本跳重试 |
| RETRY_SCHEDULED | RETRY | peer_id、attempt | 安排下一次尝试；attempt 是即将执行的尝试编号 |
| MESSAGE_FORWARDED | OK | peer_id、attempt、frame_bytes、tx_scope | 中继已将转发帧交给底层，不等于下游确认 |
| APP_DELIVERED | OK | destination_id | 最终目的节点的应用实际接受该消息，首次交付 |
| MESSAGE_EXPIRED | REJECTED | age_ms、lifetime_ms | 本地判定有效期已到；两个字段用于事后复核判据是否成立 |
| MESSAGE_DROPPED | REJECTED | 无 | 按明确规则删除/拒绝消息 |
| TRANSFER_FAILED | FAILED | peer_id、attempt | 本轮有限尝试终止，不自动等于永久丢失 |
| FRAME_REJECTED | REJECTED | frame_type | 坏帧或业务无效；无法信任消息身份时 message_id=null |
| STREAM_TIMEOUT | REJECTED | pending_bytes | 字节流候选超时；message_id=null。半帧可能不含完整帧头，禁止推断 peer_id |
| LINK_UP | OK | peer_id、basis | 本跳链路由 DOWN 或 UNKNOWN 转为可用，仅在状态跳变时记录一次 |
| LINK_DOWN | FAILED | peer_id、basis、consecutive_failures | 本跳链路由可用转为不可用，仅在状态跳变时记录一次 |

LINK_UP 的 basis 取 `ack_ok` 或 `data_rx`；LINK_DOWN 的 basis 取 `ack_timeout` 或 `no_rx_timeout`。consecutive_failures 表示判定前连续失败次数，从 1 开始。

链路事件是**本跳推断，不是物理层观测**。节点只能从「有 ACK/收到帧」推断链路可用，从「连续超时」推断链路中断；LoRa 透传模块不提供链路层状态回报。界面因此必须区分「观测到的断开」与「推断的断开」：前者来自显式失败事件，后者来自超时窗口。禁止把推断值回写成 REAL 观测。

peer_id、destination_id 为 1～65534；attempt 从 1 开始，首次发送为 1，重试为 2、3……。DATA frame_bytes 为 36～168，ACK 为 23。pending_bytes 为非负整数。frame_type 为 DATA / ACK / UNKNOWN。

ack_status 使用 ACCEPTED / ALREADY_HAVE / BUSY / EXPIRED，与无线状态 0/1/2/3 对应；未知无线状态通过 FRAME_REJECTED + UNKNOWN_ACK_STATUS 记录，不能标记成功。收到 BUSY/EXPIRED 可以有 ACK_RX，但不能有 HOP_CONFIRMED。

建议原因码：BAD_MAGIC、BAD_LENGTH、BAD_CRC、UNSUPPORTED_VERSION、UNSUPPORTED_TYPE、INVALID_ADDRESS、INVALID_MESSAGE_ID、INVALID_PRIORITY、INVALID_PAYLOAD_TYPE、INVALID_UTF8、HOP_LIMIT、ACK_TIMEOUT、ACK_MISMATCH、UNKNOWN_ACK_STATUS、BUFFER_FULL、EXPIRED、DUPLICATE、ID_CONFLICT、RETRY_LIMIT、STREAM_IDLE_TIMEOUT、IO_ERROR。新增原因码需记录兼容变更；读取端可展示未知码，但不自行解释为成功。

DUPLICATE 表示禁止重复业务交付，不自动代表已删除已有副本。ALREADY_HAVE 仅在仍持有消息或交付记录时使用。普通 ACK、日志去重与最终应用去重是三件不同的事。

### 3.1 链路三态与界面判据

上位机显示「正常 / 断开 / 未知」时必须按下表判定，不得各自另算一套：

| 显示 | 判据 | 证据性质 |
|---|---|---|
| 未知 | 该 (peer_id, channel) 从未出现任何事件 | 无数据 |
| 正常 | 窗口内出现 HOP_CONFIRMED、LINK_UP，或该 peer 的 DATA_RX / ACK_RX | 观测 |
| 断开（已确认） | 出现 LINK_DOWN 或 TRANSFER_FAILED，且此后没有成功事件 | 观测 |
| 断开（推断） | 距最近成功事件超过 T_down 秒且期间无 LINK_UP | 推断 |

T_down 由上位机配置并写入实验记录，协议不规定默认值。确认态与推断态在界面上必须可区分。

STREAM_TIMEOUT 不作为链路判据：它只说明某个 channel 上的字节流断了，不能证明对端消失。因此 STREAM_TIMEOUT 不带 peer_id，也不会产生 LINK_DOWN。

## 4. 时间与测量

不同节点的 monotonic_ms 不可直接相减计算端到端时延。当前未规定跨节点同步；需要时由实验记录补充同步方法与误差。上位机可以增加 host_received_at（RFC3339 UTC 字符串），但它是主机收到日志的时间，不是节点事件发生时间。

source_kind=REAL 只用于真实设备观测；本地构造的串口日志样例和虚拟收发链不得标为无线实测。SIM 为仿真，ESTIMATED 为估计。模拟时间自测也不证明真实无线超时参数合理。

details 可选接收观测 rssi_dbm、snr_db；电量 battery_mv；队列 queue_messages、queue_bytes；位置 position。无测量时省略或使用 null，不能用 0 代替未知。单位依次为 dBm、dB、mV、条、字节。position 若提供，应是 {latitude_deg, longitude_deg, accuracy_m}，未知子项为 null；位置数据只在确有需求和实际来源时输出。

details 可增加 radio_config 对象，记录实际频段、信道、速率等级和串口波特率；默认参数不得冒充读取值。REAL 记录若混入估计观测，必须另附 measurement_source 对象按字段标记 ESTIMATED，不能静默混用。

## 5. 样例与验收

[examples/log-v1-sim.jsonl](examples/log-v1-sim.jsonl) 是手工构造的 SIM 接口样例，覆盖正常三段转发、ACK 超时重试、坏帧与半帧超时三类场景。

[examples/log-v1-extra.jsonl](examples/log-v1-extra.jsonl) 补齐其余事件：BOOT、MESSAGE_EXPIRED、MESSAGE_DROPPED、TRANSFER_FAILED，以及 BUSY/EXPIRED 的 ACK、FLASH 缓存、LINK_UP/LINK_DOWN 和一条 ESTIMATED 记录。

两份样例都不是实测数据。字段是否符合本规范由 `tools/mwlog_check.py` 校验，不靠肉眼。

验收要求：A 板端、C 仿真、D 上位机分别读取同一组样例，确认字段一致；上位机区分本跳确认和最终应用交付，不能将 DATA_TX/ACK_RX 自动显示为最终送达。原始日志完整保留，统计输出需注明来源和配置。

当前没有要求将所有事件一次实现。尚未实现的功能不得为了补全界面而产生 REAL 成功日志。

## 6. 版本与迁移

目前为 V1 候选，需 A/B/C/D 评审后记录冻结日期及提交号。旧草图人类可读输出保持为旧格式，不自动视为 V1。增加可选字段可保持版本 1；修改必填字段、类型、单位、事件含义或删除字段必须升版本并提供迁移说明。

## 7. 修订记录

2026-11-22（未冻结状态下的扩展，版本号仍为 1）：

- 新增 `LINK_UP`、`LINK_DOWN` 事件与「正常 / 断开 / 未知」三态判据，解决上位机无法表达链路断开的问题。
- 新增必填字段 `channel`，用于把事件归属到具体串口与链路；`STREAM_TIMEOUT` 因此可定位，但仍不推断 `peer_id`。
- `MESSAGE_EXPIRED` 的 details 补 `age_ms`、`lifetime_ms`，使过期判据可事后复核。
- 明确 `result=OK` 时 `reason` 必须为 null；此前「通常为 null」无法用于校验。
- 明确 `event_seq` 在同一 `session_id` 内唯一，跨会话可重复。
- 新增 `examples/log-v1-extra.jsonl` 覆盖缺失事件，新增 `tools/mwlog_check.py` 做机器校验。

以上改动尚未被任何已实现代码使用，因此不构成破坏性变更；一旦板端开始输出，后续修改必须按第 6 节升版本。
