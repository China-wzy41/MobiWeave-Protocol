# 串口记录模板

更新：2026-11-12。A 负责板型、环境、烧录和板端串口；D 负责电脑端工具和界面。本文件只覆盖 A 的部分。电脑端程序、字段类型和字节序以 [#6](https://github.com/China-wzy41/MobiWeave-Protocol/issues/6) 为准，未冻结前不要另起一套同名不同义的字段。

对应 [#2](https://github.com/China-wzy41/MobiWeave-Protocol/issues/2)。协议分组见 [docs/protocol/README.md](../docs/protocol/README.md)。环境步骤见 [Firmware/hardware/dev-environment.md](../Firmware/hardware/dev-environment.md)。

**板端测试程序待实现。** 下面没有实测行。LoRa 未到货不挡住这次串口；没有无线测量时 RSSI/SNR 写 `unknown`。

## 怎样记一次

一次运行一个 `run_id`，目录：

```text
Tests/raw/<run_id>/
  env.md          # 抄下面的表头
  pc.log          # 电脑发出的原文
  board.log       # 板端发出的原文
  notes.md        # 断开、半帧、对不上的地方
```

不要覆盖已有 `run_id`。失败也留着。来源标记用 `REAL`。没有板时不要制造一份看起来像通过的日志；[#2](https://github.com/China-wzy41/MobiWeave-Protocol/issues/2) 允许先用文件回放，那种运行标记 `SIM`，并写「模拟通过、板端待验」。

电脑只保存和显示。不要把这块板的业务内容从 USB 再写进另一块板。

## 表头（env.md）

```text
run_id:
source: REAL
date:
operator:
role: A
board: ESP32-S3 N16R8 或 N8R8
board_marking:          # 屏蔽罩丝印，没看到就写待确认
usb_socket:             # 用的哪个口，芯片是片内 USB 还是 CH340/CP210x，待确认就照写
com_port:
ide_version:
esp32_core_version:
flash_size:
flash_mode:
psram:
partition:
usb_cdc_on_boot:
upload_speed:
boot_button_needed:     # 是 / 否 / 待确认
firmware: 待实现
firmware_version:
pc_serial: 115200 8N1
lora_serial:            # 未接模块写 未接。接了则写实际值，出厂为 9600 8N1
clock:                  # 写明时间来自电脑还是板端单调计时，不要混用后相减
start_condition:
end_condition:
expected:               # 本次希望看到的现象
actual:                 # 实际现象。没有运行就写 未测
rssi: unknown
snr: unknown
```

## 事件行

板端程序尚未规定打印格式。在 [#6](https://github.com/China-wzy41/MobiWeave-Protocol/issues/6) 给出字段之前，原始日志用一行一个事件，逗号分隔，第一行是列名：

```text
time_ms,node_id,msg_id,event,result,rssi,snr,raw
```

|列|填写|
|---|---|
|time_ms|表头里那个时钟的读数。单位毫秒。没有同步就不要用两台设备的时间戳相减|
|node_id|板上的编号。表头写清这个编号贴在哪块板|
|msg_id|对方约定的消息编号。半帧、还没解析出来时留空，原文放在 raw|
|event|`pc_tx`、`board_rx`、`board_tx`、`pc_rx`、`disconnect`、`reconnect`、`half_frame`、`bad_length`、`duplicate` 之一。含义只表示观察到的动作，不表示最终交付|
|result|`ok` 或简短原因。解析失败不要改成 ok|
|rssi|这次没有无线测量，写 `unknown`。不要写 0|
|snr|同上，写 `unknown`|
|raw|该行对应的原始字节或文本，半帧也原样留下|

列名和 [协议说明](../docs/protocol/README.md) 里的「哪次实验、哪个节点、哪条消息、发生了什么、何时、结果」对齐。类型、单位、字节序、CRC 等 [#6](https://github.com/China-wzy41/MobiWeave-Protocol/issues/6) 冻结后再改列，并在 `notes.md` 写版本。

## 有板之后要做的事

程序仍待实现。做的时候按这个顺序，做完把证据路径填进 `notes.md`：

1. 按开发环境文档烧录。空草图只证明端口可用，不计入下面几步。
2. 电脑按约定帧发送一条合法消息。板端解析后回传。电脑把两侧原文存进上面的两个日志。
3. 再各做一次半帧、过长、重复编号、拔插 USB。这些行都保留。半帧不能丢弃后再统计。
4. 另一名成员按 `env.md` 重做一次，在 `notes.md` 签验收人和日期。签之前这些格子留空。

未接 LoRa 时第 2 步的 RSSI/SNR 维持 `unknown`。无线数字只出现在 [两节点测试](lora-two-node.md) 的 `REAL` 记录里。

## 关闭 [#2](https://github.com/China-wzy41/MobiWeave-Protocol/issues/2) 时 A 要交的证据

- 本文件表头的一次真实 `env.md`
- `Tests/raw/<run_id>/` 里的原始日志
- 开发环境版本和烧录时是否按过 BOOT
- 验收人、日期

只有空草图、或只有 D 的文件回放时，issue 里「ESP32 可用时完成电脑发送、板端解析回传」这一项保持未勾。勾选不在本文件里做。
