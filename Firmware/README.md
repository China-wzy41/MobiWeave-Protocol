# 硬件与固件

A 主责，B 配合协议，D 配合电脑串口。尚无已核验可构建的固件。

先交付硬件型号/数量清单、官方资料来源、供电与接线说明、开发环境、构建/烧录步骤和串口记录。引脚以实际模块为准，未知项填待确认。ESP32-S3 与北斗模块已到货，丝印仍待确认。天线、去耦电容和 GNSS 底板是否支持 5 V 仍待确认，以硬件清单为准。

2026-11-12 的清单把 LoRa 按未到货写。2026-11-17 的当天日志记为：模块已用于串口联调，两块 ESP 的 UART/AT 已通，无线互传仍未做。见 [工程日志](../docs/ProjectLog/A_wzy/2026-11-17-电脑-ESP32-S3-LoRa串口联调.md) 和 [板1、板2](hardware/2026-11-17-ESP32-LoRa成功板记录.md)。

- [硬件清单与接线](hardware/硬件清单与接线.md)：ESP32-S3、DX-LR22-433T22D、ATGM336H-6N-74 的资料核对、接线和空口时间。11 月 12 日的核对稿不是当时的实测结果；11 月 17 日的串口结果见下面两份记录。
- [2026-11-17 工程日志](../docs/ProjectLog/A_wzy/2026-11-17-电脑-ESP32-S3-LoRa串口联调.md)：当天成果和注意事项。
- [板1、板2](hardware/2026-11-17-ESP32-LoRa成功板记录.md)：按成功时间编号。COM 号不是永久身份。
- [开发环境与烧录](hardware/开发环境与烧录.md)：Windows 与 Arduino IDE 的板级选项、烧录和串口监视。第三套循环复位没有在这里写成已修复。
- [初次连接测试](初次连接测试/README.md)：2026-11-17 板1、板2 串口 AT 用过的程序，从 `LoRa_AT_Test_v2.ino` 原样保存。UART 通过不是无线通过。
- [芯路城 ESP32-S3 资料](hardware/vendor/xinlu-esp32s3/README.md)：2026-11-18 保存的普通 N16R8 开发板原理图和引脚图。新买的两块到货未确认，不是板1、板2。
- [gateway](gateway/README.md)：网关板端，电脑端放 Host。
- [固定节点](nodes/fixed%20nodes/README.md)：节点收发、缓存与转发。
- 串口记录和到货后的两节点步骤在 [Tests](../Tests/README.md)。
- 移动节点按同一协议配置，后续确有代码时再补目录，不提前堆占位文件。

11 月先核对硬件、有板做串口、准备无线测试步骤；无线实物验收在到货后进行。任务 [#2](https://github.com/China-wzy41/MobiWeave-Protocol/issues/2)、[#3](https://github.com/China-wzy41/MobiWeave-Protocol/issues/3)、[#11](https://github.com/China-wzy41/MobiWeave-Protocol/issues/11)。标准见[协议](../docs/protocol/README.md)和[实验方法](../docs/method/README.md)，记录放 [Tests](../Tests/README.md)。
