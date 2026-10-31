# 仿真与实验工具｜C 主责

目前只有目录说明，模拟器尚待实现。B 定义格式，C 生成与分析事件，D 使用样例做界面。

首轮 [#8](https://github.com/China-wzy41/MobiWeave-Protocol/issues/8)，2026-11-30：正常、丢包、重复、断链四类可重复案例，覆盖丢 ACK、延迟和重连；保存配置、固定种子、版本和原始日志；输出发送、唯一接收、缺号和重复统计。用小样例人工核对，提供 1000 包配置、发送间隔与结果导出。

后续 [#15](https://github.com/China-wzy41/MobiWeave-Protocol/issues/15) 做实测校准、回放、误差验证与策略比较；[#16](https://github.com/China-wzy41/MobiWeave-Protocol/issues/16) 做预测验证。D 的拓扑展示属于 Host，不代替模型可信度验证。

交付时补环境、依赖、运行命令、输入输出位置和预期结果。工具放本目录，运行证据放 [Tests](../Tests/README.md)。格式见[协议](../docs/protocol/README.md)，方法见[实验说明](../docs/experiments/README.md)。模拟不作为实物通过证据。
