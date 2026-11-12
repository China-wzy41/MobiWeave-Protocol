# 两节点无线测试步骤

更新：2026-11-12。主责 A，数据由 C 复核。这是到货以后的步骤和空表，**不是已经做完的基线**。LoRa 暂按未到货。到货日期填在 [硬件清单](../Firmware/hardware/inventory.md)。

对应 [#3](https://github.com/China-wzy41/MobiWeave-Protocol/issues/3)。口径以 [实验方法](../docs/experiments/README.md) 的「M1：双节点无线基线」为准。接线以 [wiring.md](../Firmware/hardware/wiring.md) 为准。固件不在本文里，板端发包程序待实现。

近距工程目标是每轮 PDR ≥ 95%。这是目标，不是结果。它不代表户外覆盖。最远距离测试后置。

## 开始之前

1. 两套节点：每套一块 ESP32-S3（记下 N16R8 或 N8R8）和一块 DX-LR22-433T22D。第三套留给以后的 [#11](https://github.com/China-wzy41/MobiWeave-Protocol/issues/11)，这次不用。
2. 天线已拧到 SMA 上。没有天线就不给模块发任何会进入发射的数据，查询类 AT 是否触发射频，手册未写，同样先接天线。
3. 按接线表接好，VCC 用 5 V，共地，RX/TX 交叉，AUX 到 GPIO4。M0、M1 保持不接。
4. 两节点之间没有连接 TX/RX 的杜邦线。电脑 USB 只供电和采日志，不把发送端的载荷写进接收端。
5. 实验地点的发射约束仍待确认。确认前只用默认信道 00（433.15 MHz），不把信道改到手册表里更高的频点。
6. 发包程序待实现。没有程序时不要手写一份「已通过」的数字。

## 参数记录

每一轮、每一端各存一份。查询命令来自串口应用指导，字母大写，行尾 CR+LF。进入 AT：发送 `+++`，期望看到 `Entry AT`。手册没写 `+++` 前面的等待时间；没有 `Entry AT` 就停，记在 notes 里。

先读，再改。把模块返回的原文存盘，不要只抄自己认为的设定。手册示例把参数直接接在命令后面，例如 `AT+MODE0`、`AT+POWE10`。打开 RSSI 就发 `AT+DRSSI1`。返回 `EEROR=105`（手册里的拼写）就停，对照串口指导，不要连发。

|项目|命令|本基线要求|出厂值（手册）|
|---|---|---|---|
|全部射频参数|`AT+HELP`|原文保存|—|
|传输模式|`AT+MODE`|两端都是 0，透明传输|0|
|速率等级|`AT+LEVEL`|两端相同。起点用 2|2。表：SF11，BW 500 kHz，CR 4/5，2148 bps|
|信道|`AT+CHANNEL`|两端都是 00|00 = 433.15 MHz|
|地址|`AT+MAC`|记下来。透明模式不靠地址过滤|ff,ff|
|密钥开关|`AT+OPENKEY`|两端一致|1，开启|
|密钥|不可查询|两端保持一致。不在仓库里扩散修改后的密钥|12345|
|发射功率|`AT+POWE`|记下 dBm。起点可用默认 22|22。命令拼写是 `POWE`|
|数据包 RSSI|`AT+DRSSI`|接收侧打开：`AT+DRSSI1`|0，关闭|
|硬件模式脚|`AT+SWITCH`|保持 0|0|
|工作模式|`AT+SLEEP`|保持 2，高时效|2|
|分包长度|`AT+PACKET`|记下。单次最长与此项一致，手册 FIFO 230 字节|3，即 230 字节|

改完发送 `AT+RESET`，再进 AT，再 `AT+HELP`，确认打出来的值就是记录里的值。退出 AT 用 `+++`，模块会复位。

`AT+HELP` 示例里的 LEVEL2 显示 2149 bps，速率表写 2148。保存原文。`Bandwidth:` 后面的数字是内部编号，kHz 以速率表为准。示例里 `CRC:0(false)`。命令一览没有单独的 CRC 开关，能不能打开待确认。本基线的完整性靠序号，不把模块 CRC 当成已经开启。

SNR：手册没有这条命令。接收日志的 snr 列写 `unsupported`，不要填 0，也不要写成芯片寄存器里「应该有」。`AT+ERSSI` 是当前信道噪声，不是每包 SNR；若查询了，把原文放进环境记录，列名不要叫 snr。

RSSI 字节只在 `AT+DRSSI` 打开时出现在模块交给 MCU 的数据末尾，不替代空中载荷。手册例子：载荷之后一字节 `0xAB`，强度 = −(0xFF − 0xAB) = −84 dBm。0xFF 在公式里是固定值。统计前把这一字节从载荷里拆走，原始字节和换算结果都保存。字节是 `0x00` 或 `0xFF` 时先只存原始值，不推进分布，手册没有说明这两个值是不是哨兵。

## 发送间隔

LoRa 半双工，同一时刻只让一个模块发射。手册要求不要在低空速下连续灌大量数据，否则堆积会丢，那种丢失不能算进无线 PDR。

间隔按空口时间留，不按电脑串口能发多快来定。

1. 用当轮真实载荷测 AUX。AUX 为高表示模块仍在发送、接收或切模式（技术手册 2.3.3）。用 GPIO4 量一包的高电平宽度，写入环境记录，来源标 `REAL`。没有示波器就用板端计时，程序待实现；量不到就不要开始那 1000 包。
2. 字符时间只作下限估算，来源标 `ESTIMATED`：载荷字节数 × 8 / 该等级的空中字符速率。LEVEL2 用手册表的 2148 bps。这不含前导码，不是空口时间。
3. 发送间隔取「AUX 高电平宽度的 2 倍」和「2 倍字符时间」里更大的那个。2 倍是操作约定，不是测出来的最佳值。
4. 本基线只发序号包，不发应用层 ACK。若某一轮确实发了 ACK，间隔还要盖住 ACK 的 AUX 高电平，并且在环境记录里写明，不和没有 ACK 的轮次放进同一个 PDR。
5. 例子（不是本项目的测量）：LEVEL2、16 字节载荷时，2 × 16 × 8 / 2148 ≈ 0.119 s。AUX 实测若更长，以实测为准。

载荷长度等 [#6](https://github.com/China-wzy41/MobiWeave-Protocol/issues/6) 的帧格式。格式没冻结之前，日志里至少要有单调序号，并记下完整字节数。不要在这里新造一种和协议冲突的二进制帧。

可选对照：用 [Semtech LoRa Calculator](https://www.semtech.com/design-support/lora-calculator) 和 `AT+HELP` 里的 SF、BW、CR 估算。前导码长度手册没写，计算器结果标 `ESTIMATED`，不能代替 AUX 测量。

## 三轮

每一轮是一次独立上电，一个新的 `run_id`。三轮就是三个目录。不要只把序号清零就叫新的一轮。

每一轮包含两个方向，每个方向至少 1000 个序号包：

1. 节点 A 发、节点 B 收，序号从 1 递增，至少到 1000。
2. 两边都停止发送。B 再等不少于 10 个发送间隔，用来收完已经在空中的包。10 是操作约定。
3. 交换方向，序号重新从 1 开始，再至少 1000 个。
4. 拔掉两块板的 USB，再上电，才开始下一轮。

发包过程中不改速率、信道、功率和间隔。近距布局固定：写下距离、天线高度、朝向、室内或室外、中间有没有障碍。距离数字到现场再填，本文不预填。

近距若接收异常，可以另开一轮把 `AT+POWE` 调低并写明。调过功率的轮次单独编号，不和 22 dBm 的轮次合成一个 PDR。手册还提到过近时邻信道也可能收到数据，所以两对节点不要叠在一起同时发射；这次只用一对。

## 每轮要算出的数

分母是发送端交出的不同序号个数。分子是接收端见到的不同序号个数。重复另计，不放进分子。缺号列出，不从文件里删掉。

```text
发送数 =
唯一接收数 =
缺号个数 =
重复个数 =
PDR = 唯一接收数 / 发送数
```

两个方向分开算。PDR 低于 95% 的轮次保留，先查天线是否拧紧、发射时 VCC、间隔是否短于 AUX、同频干扰和两端参数是否一致。查清之前不要用缩短的轮次替换它。队列溢出或发送端还没等 AUX 变低就发下一包，记成发送侧堆积，不记成无线丢包。

延迟：两块板没有共同时钟时，不把两个时间戳相减称作单向延迟。要测就用同一台电脑时钟测往返，并在 notes 里说明。这次基线可以写「未测」。

## 环境信息

放进 `Tests/raw/<run_id>/env.md`：

```text
run_id:
source: REAL
date:
operator:
place:                  # 室内/室外，大致地点。射频约束待确认则写上
distance_m:
antenna:                # 型号、增益、高度、朝向。没有就写待确认，不要空着发射
obstacles:
temperature:            # 没测写 未测
power_source:           # 例如笔记本 USB。发射时 VCC 电压：
vcc_tx_v:
node_a:                 # 板型 N16R8 或 N8R8，编号
node_b:
firmware_version:       # 没有程序就写 待实现，本轮不开始
level:
sf:
bw_khz:
cr:
power_dbm:
channel:
frequency_mhz:
payload_bytes:
interval_ms:
interval_basis:         # AUX 实测宽度、字符时间估算、取了哪一个
aux_high_us:
drssi: 1
snr_capability: unsupported
ack: 无
start_condition:
end_condition:
```

`AT+HELP` 原文：

```text
Tests/raw/<run_id>/node-a-at.txt
Tests/raw/<run_id>/node-b-at.txt
```

## 原始日志

```text
Tests/raw/<run_id>/tx-ab.log
Tests/raw/<run_id>/rx-ab.log
Tests/raw/<run_id>/tx-ba.log
Tests/raw/<run_id>/rx-ba.log
Tests/raw/<run_id>/notes.md
```

不要覆盖。分析以后放 `Tests/analysis/<run_id>/`，由 C 做，不改 raw。

发送端列名：

```text
time_ms,node_id,dir,seq,event,aux_high_us,note
```

`event` 用 `tx`。`dir` 用 `ab` 或 `ba`。

接收端列名：

```text
time_ms,node_id,dir,seq,event,rssi_raw,rssi_dbm,snr,note
```

`event` 用 `rx`。`snr` 写 `unsupported`。`rssi_raw` 是那个原始字节的十六进制，`rssi_dbm` 按上一节公式。模块没打开 DRSSI 时两列都写 `unknown`，并在 notes 说明这一轮不能做 RSSI 分布。

时间用接收端或发送端自己的单调计时，在 env 里说明。不要跨节点相减。

## 签收

另一名成员按同一 env 重做。重做用新的 `run_id`。

```text
复现人:
复现日期:
复现 run_id:
与原始轮次的差异:
```

签之前留空。模拟日志不能用来勾掉 [#3](https://github.com/China-wzy41/MobiWeave-Protocol/issues/3) 的实物项。

## 三节点

[#11](https://github.com/China-wzy41/MobiWeave-Protocol/issues/11) 不在这三轮里做。第三套就绪日 T3 仍待确认。以后的接触测试要另有 run_id，记录接触开始和结束，并保留连续录像。S 与 R 不能同时听到对方。那次测试的步骤以实验方法为准，不把两节点基线的 PDR 写成携带已经成功。
