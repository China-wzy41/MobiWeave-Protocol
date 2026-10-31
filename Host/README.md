# 上位机｜D 主责

目前是目录与交付约定，尚无可运行界面。

|阶段|交付|任务|
|---|---|---|
|M0，2026-11-30|读取 C 的样例日志，显示节点、消息与连接状态，保存记录；准备串口接口|[#20](https://github.com/China-wzy41/MobiWeave-Protocol/issues/20)、[#2](https://github.com/China-wzy41/MobiWeave-Protocol/issues/2)|
|M1，2026-12-31|接入真实网关，按消息编号跟踪收到、保存、转发与最终交付|[#21](https://github.com/China-wzy41/MobiWeave-Protocol/issues/21)|
|M3，2027-03-15|实验回放、逻辑拓扑和消息路径；未知、过期状态有提示|[#22](https://github.com/China-wzy41/MobiWeave-Protocol/issues/22)|

B 统一格式，C 提供模拟/统计结果，A 提供板端输入，D 负责接入、显示、保存与回放操作。先文件回放，再串口；输入适配与界面分开。技术栈在任务内记录选择依据，不在此假装已安装或已运行。

交付时补依赖版本、安装启动步骤、输入样例、预期界面、错误处理与已知限制；另一成员复现。原始日志保存到 Tests 对应 run_id。所有模拟值标明来源。

地图、轨迹和热力图后置。没有位置或测量数据时只画逻辑关系，不能制作看似真实的覆盖图。详见[协议](../docs/protocol/README.md)与[实验方法](../docs/experiments/README.md)。
