# 硬件与固件

A 主责，B 配合协议，D 配合电脑串口。目前只有目录说明，没有已核验可构建的固件。

先交付硬件型号/数量清单、官方资料来源、供电与接线说明、开发环境、构建/烧录步骤和串口记录。引脚以实际模块为准，未知项填待确认。ESP32 与 LoRa 已购买，LoRa 暂按未到货，其他硬件未购买；不假定数量和型号。

- [gateway](gateway/README.md)：网关板端，电脑端放 Host。
- [固定节点](nodes/fixed%20nodes/README.md)：节点收发、缓存与转发。
- 移动节点按同一协议配置，后续确有代码时再补目录，不提前堆占位文件。

11 月先核对硬件、有板做串口、准备无线测试步骤；无线实物验收在到货后进行。任务 [#2](https://github.com/China-wzy41/MobiWeave-Protocol/issues/2)、[#3](https://github.com/China-wzy41/MobiWeave-Protocol/issues/3)、[#11](https://github.com/China-wzy41/MobiWeave-Protocol/issues/11)。标准见[协议](../docs/protocol/README.md)和[实验方法](../docs/experiments/README.md)，记录放 [Tests](../Tests/README.md)。
