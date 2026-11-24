# 硬件与固件

近期节点不带屏幕。坐标由手机经低功耗蓝牙（BLE）交给节点。整条手机坐标 → BLE → 节点 → LoRa → 队友节点 → 队友手机显示作为整体还没有实现，也没有整段验证。ESP 与 LoRa 的实验台通信，以及两节点无线通信，在已有记录的条件内已经做过。BLE、队友手机显示和整段集成还没做。独立 GNSS 不列入近期预算；已到货模块和预留接口见硬件清单，不新购。

尚无已核验的整条徒步链路固件。2026-11-17 保留了 ESP↔LoRa 的接线与串口 bring-up。2026-11-18 的短文字和 4 帧 DATA/CRC 见[团队日志](../docs/ProjectLog/TeamLog/2026-11-18-双节点LoRa互传与DATA-CRC验证.md)，没有 ACK，不是整条徒步链路。

- [硬件清单与接线](hardware/硬件清单与接线.md)
- [2026-11-17 工程日志](../docs/ProjectLog/A_wzy/2026-11-17-电脑-ESP32-S3-LoRa串口联调.md)
- [板1、板2](hardware/2026-11-17-ESP32-LoRa成功板记录.md)
- [开发环境与烧录](hardware/开发环境与烧录.md)
- [初次连接测试](初次连接测试/README.md)：2026-11-17 用过的 AT 程序。这份 AT 记录是串口，不是两节点无线记录。
- [LoRa USB 桥](LoRaUsbBridge/README.md)：两块板共用的 USB 与 LoRa 字节转发。编译通过不等于已经烧录或无线通过。
- [芯路城 ESP32-S3 资料](hardware/vendor/xinlu-esp32s3/README.md)：普通 N16R8 图纸。新买的两块到货未确认，不是板1、板2。
- [固定节点](<nodes/fixed nodes/README.md>)：目录还没有可运行的徒步节点程序。
- 串口记录、已有无线记录与待补验收步骤在 [Tests](../Tests/README.md)。

方向见 [长期计划](../docs/planning/长期计划.md)。
