# 硬件与固件

A 主责，B 配合协议，D 配合电脑串口。已有板内自测草图及空口联调草图，正式节点固件仍未完成。

- [板内自测](tests/MobiWeave_Stream_Timeout_Test/MobiWeave_Stream_Timeout_Test.ino)：CRC、DATA 编解码、流式解析与模拟时间超时测试；负责人报告板端通过。
- [空口联调](tests/MobiWeave_Link_Test/README.md)：真实串口和无线链路准备程序；实测记录见 [2026-11-21 空口联调记录](../Tests/hardware-bringup-2026-11-21.md)。
- 两份草图各自独立打开，不应合并到同一个 Arduino 草图目录。

先交付硬件型号/数量清单、官方资料来源、供电与接线说明、开发环境、构建/烧录步骤和串口记录。引脚以实际模块为准，未知项填待确认。ESP32 与 LoRa 已购买，当前实际到货数量与其他硬件状态待负责人更新；不假定数量和型号。

- [gateway](gateway/README.md)：网关板端，电脑端放 Host。
- [固定节点](nodes/fixed%20nodes/README.md)：节点收发、缓存与转发。
- 移动节点按同一协议配置，后续确有代码时再补目录，不提前堆占位文件。

11 月先核对硬件、有板做串口、准备无线测试步骤；无线实物验收在到货后进行。任务 [#2](https://github.com/China-wzy41/MobiWeave-Protocol/issues/2)、[#3](https://github.com/China-wzy41/MobiWeave-Protocol/issues/3)、[#11](https://github.com/China-wzy41/MobiWeave-Protocol/issues/11)。标准见[协议](../docs/protocol/README.md)和[实验方法](../docs/experiments/README.md)，记录放 [Tests](../Tests/README.md)。
