# 网关板端

A 负责板端收发与串口输出，B 统一消息和日志，D 在 [Host](../../Host/README.md) 接入电脑端。这里尚无已验证固件。

板型、引脚、烧录和串口参数先用 [硬件清单](../hardware/inventory.md)、[接线](../hardware/wiring.md)、[开发环境](../hardware/dev-environment.md)，记录用 [Tests/serial-log.md](../../Tests/serial-log.md)。可烧录程序和样例日志仍待补。交付时再把当时的依赖版本和实测日志写回这里。按[统一协议](../../docs/protocol/README.md)处理半帧、错误长度和重连。网关日志采集不能暗中替代断链实验中的无线业务传输。

任务：[#2](https://github.com/China-wzy41/MobiWeave-Protocol/issues/2)、[#21](https://github.com/China-wzy41/MobiWeave-Protocol/issues/21)。
