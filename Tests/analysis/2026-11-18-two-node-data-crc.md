# 2026-11-18 两节点 DATA/CRC 核算

数字来自[原始 zip](../raw/2026-11-18-two-node-data-crc/README.md)里的 `.bin`。CRC 按草案单独重算：CRC-16/CCITT-FALSE，多项式 `0x1021`，初值 `0xFFFF`，不反转、不异或终值，范围是 version 到 body 末字节，结果按小端存放。events 只用来对照文字，不作为字节来源。当天日志在[团队日志](../../docs/ProjectLog/TeamLog/2026-11-18-双节点LoRa互传与DATA-CRC验证.md)。

入库文件与附件字节一致：

- `node1-original.zip`，1816 字节，SHA256 `1d26071905b80095ce9d36404970fd46267a7ca887dfc00279424ed6880e2f19`
- `node2-original.zip`，1876 字节，SHA256 `7dddecfad0399c1cb5587113aeb93c6d24bba278198c7d76d733155be97244a1`

## 字节对照

- `node1-tx.bin` 与 `node2-rx.bin` 都是 126 字节，逐字节相同。SHA256 `c42c0ba60c91462df1e99e4d773c51647825468e4dafbd7a5bc2bf0854d5b463`。
- `node2-tx.bin` 与 `node1-rx.bin` 都是 41 字节，逐字节相同。SHA256 `cc0d54349b32428ea3ed7f12ba1e1ae06324f905bdbcb235e780410cf7754124`。
- 两个 `.bin` 都从偏移 0 切出完整帧，没有前缀、帧间噪声或半帧残留。
- node1 的 3 段 read 拼起来等于它的 `rx.bin`（11+21+9）。node2 的 9 段 read 拼起来等于它的 `rx.bin`（11+21+9、19+19+5、3+29+10）。一次 read 不是一帧。

各帧都是 magic `A5 5A`、version 1、DATA、`boot_counter` 1、priority 0、age 0、lifetime 60000、hop 1/1、UTF-8。没有 ACK 帧。

## 四帧

| 方向 | seq | 文本 | 总长 | 帧内 CRC | 重算 CRC | 结果 |
|---|---|---|---|---|---|---|
| node1 → node2 | 1 | hello | 41 | `0x4DD5` | `0x4DD5` | 通过 |
| node2 → node1 | 1 | kskbl | 41 | `0x337B` | `0x337B` | 通过 |
| node1 → node2 | 2 | BAD-CRC | 43 | `0xE860` | `0xE89F` | 不符，node2 记录拒收 |
| node1 → node2 | 3 | 111666 | 42 | `0x7F58` | `0x7F58` | 通过，紧接在坏帧之后 |

地址都是直达：hello 与后两帧是 sender/src=1、receiver/dest=2；kskbl 是 sender/src=2、receiver/dest=1。`0xE89F` 与 `0xE860` 相差低 8 位翻转（异或 `0x00FF`）。node2 的拒收行没有写下 seq，判定同时依据重算 CRC 和紧随该 43 字节的拒收记录。

两台电脑时戳对不上。例如 hello 在 node2 的接收时间早于 node1 的发送时间。不能用这些时间算单程延迟，日志里也没有 SNR。

这 4 帧不能外推成丢包率、距离或无线可靠性。没有 ACK、重传、去重的记录。

## 当天配置和复现

每个节点：ESP32-S3、LoRa、PJ15。PJ15 只给 LoRa 供电，ESP 用自己的 USB，共地。LoRa TXD → GPIO18，RXD → GPIO17，模块侧 9600 8N1，电脑侧 115200。两端退出 AT，透明传输。读回是 MODE0、LEVEL3、SLEEP2、CH01、10 dBm。冒烟工具不发 AT。

软件版本：`4e9a3b22598ca1f1aff54193911e4ca8e28e697b`。固件目录 [LoRaUsbBridge](../../Firmware/LoRaUsbBridge/)，两端同一份。该树在 esp32 核心 3.3.13 下四种 USB 配置编译通过；编译通过不等于本次重新烧录证明。原来的 AT 菜单没有改。电脑工具是 [v1_data_smoke](../../Host/v1_data_smoke/)。

软件测试在 `Host/v1_data_smoke` 执行：

`python3 -m unittest discover -s tests -t .`

19 项通过，不打开串口。

实物步骤：关掉串口监视器后再连接；两台电脑分别选节点 1 和节点 2；各发一条短消息；再发一条坏 CRC，然后发一条正常帧。依赖若在官方 PyPI 上遇到 TLS 中断，可改用清华 HTTPS 镜像，不要关闭证书校验。21:22 已停止继续插拔和加测。
