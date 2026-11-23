# 硬件与固件

近期节点不带屏幕。坐标由手机经低功耗蓝牙（BLE）交给节点。手机取得坐标、BLE、节点、LoRa 和队友手机显示都还没有实现，也还没有验证。独立 GNSS 不列入近期预算；已到货模块和预留接口见硬件清单，不新购。

尚无已核验、可构建的徒步链路固件。2026-11-17 只验证了串口 AT，不是这条链路。

- [硬件清单与接线](hardware/硬件清单与接线.md)
- [2026-11-17 工程日志](../docs/ProjectLog/A_wzy/2026-11-17-电脑-ESP32-S3-LoRa串口联调.md)
- [板1、板2](hardware/2026-11-17-ESP32-LoRa成功板记录.md)
- [开发环境与烧录](hardware/开发环境与烧录.md)
- [初次连接测试](初次连接测试/README.md)：当天用过的 AT 程序。串口通过不是无线通过。
- [芯路城 ESP32-S3 资料](hardware/vendor/xinlu-esp32s3/README.md)：普通 N16R8 图纸。新买的两块到货未确认，不是板1、板2。
- [固定节点](<nodes/fixed nodes/README.md>)：目录还没有可运行程序。
- 串口记录和尚未执行的无线步骤在 [Tests](../Tests/README.md)。

方向见 [长期计划](../docs/planning/长期计划.md)。
