# 硬件与固件

A 主责，B 配合协议，D 配合电脑串口。没有已核验可构建的固件。

2026-11-12 起，型号和数量以 [硬件清单](hardware/inventory.md) 为准：ESP32-S3 N16R8 两块、N8R8 两块，DX-LR22-433T22D 四块，定位模块四颗。开发板品牌和部分辅料仍是待确认。LoRa 暂按未到货。清单、接线和环境说明都还没有在板上核过，不代表已经连通。

- [硬件清单](hardware/inventory.md)：型号、数量、资料链接、到货。
- [接线](hardware/wiring.md)：ESP32-S3 与 DX-LR22，供电、天线、定位模块备忘。
- [开发环境](hardware/dev-environment.md)：Windows、Arduino IDE、烧录和两套串口速率。
- [串口记录模板](../Tests/serial-log.md)、[两节点到货测试](../Tests/lora-two-node.md)。
- [gateway](gateway/README.md)：网关板端，电脑端放 Host。
- [固定节点](nodes/fixed%20nodes/README.md)：节点收发、缓存与转发。
- 移动节点按同一协议配置，后续确有代码时再补目录，不提前堆占位文件。

11 月先核对硬件、有板做串口、准备无线测试步骤；无线实物验收在到货后进行。任务 [#2](https://github.com/China-wzy41/MobiWeave-Protocol/issues/2)、[#3](https://github.com/China-wzy41/MobiWeave-Protocol/issues/3)、[#11](https://github.com/China-wzy41/MobiWeave-Protocol/issues/11)。标准见[协议](../docs/protocol/README.md)和[实验方法](../docs/experiments/README.md)，记录放 [Tests](../Tests/README.md)。
