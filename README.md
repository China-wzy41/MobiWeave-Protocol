# MobiWeave Protocol｜织网计划

户外徒步时，手机取得坐标，经低功耗蓝牙（BLE）交给无屏的 ESP32 + LoRa 节点，再发给队友的节点，由队友的手机显示位置、短文字和离线地图上的集合点。

整条链路作为整体还没有实现，也没有整段验证：手机取得坐标 → BLE → 本机无屏节点 → LoRa → 队友节点 → 队友手机显示。ESP 与 LoRa 的实验台通信，以及两节点无线通信，在已有记录的条件内已经做过。BLE、队友手机显示，以及把各段接成整段，还没做。没有蜂窝网络时手机仍可能定位，但权限、冷启动和天空遮挡还没测。确认、重试、去重、转发和多跳没有验收。

方向于 2026-11-23 更新。当前计划见 [长期计划](docs/planning/长期计划.md)。

## 已经有的记录

- 2026-11-17 保留了板1、板2 的 ESP↔LoRa 接线与串口 bring-up。[工程日志](docs/ProjectLog/A_wzy/2026-11-17-电脑-ESP32-S3-LoRa串口联调.md)、[板1、板2](Firmware/hardware/2026-11-17-ESP32-LoRa成功板记录.md)。实验台两节点无线通信另有记录，范围以那些记录为准。
- 2026-11-18 的[团队日志](docs/ProjectLog/TeamLog/2026-11-18-双节点LoRa互传与DATA-CRC验证.md)是短文字和 4 帧 DATA/CRC。[原始包](Tests/raw/2026-11-18-two-node-data-crc/README.md)、[核算](Tests/analysis/2026-11-18-two-node-data-crc.md)。那天没有 ACK，不是可靠性验收，也不是整条手机链路。
- v1 日志格式已冻结，工作基线在分支 `Yanis0118-patch-1`（`ca128e3`），不在 `main`。格式冻结、送进 main 的拉取请求、合入 main，以及确认、重试、去重、转发、多跳，各自单独记账。

## 从这里进入

- [长期计划](docs/planning/长期计划.md)
- [硬件与固件](Firmware/README.md)
- [协议说明](docs/protocol/README.md)
- [怎么验证](docs/method/README.md)
- [测试记录](Tests/README.md)
- [工程日志](docs/ProjectLog/README.md)

队友手机上的显示和仿真目录里还没有可运行程序。实验台电脑侧的 DATA/CRC 工具在 [Host/v1_data_smoke](Host/v1_data_smoke/README.md)，不是手机界面。
