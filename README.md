# MobiWeave Protocol｜织网计划

研究在通信断续、节点移动时，如何用 ESP32 与 LoRa 保存、携带和转发重要消息，并通过实验判断预测调度是否比固定规则更有效。

## 当前阶段

**M0 首轮准备，统一截止 2026-11-30。** 先完成软件模拟和一次上位机演示。LoRa 暂按尚未到货安排，实物验收按可用节点就绪时间调整。

截至 2026-10-31，仓库仍处于准备阶段，尚无已核验可运行的完整系统；目录和任务建立不代表功能已完成。目前没有统一启动命令，后续各方向交付时补充运行说明。

## 五人分工

每人每周暂按 **8–10 小时**，其中约 **25% 留给学习和调试**。

|方向|11 月底交付|任务入口|
|---|---|---|
|A 硬件与集成|硬件清单、接线说明、串口记录、到货测试步骤|[#1](https://github.com/China-wzy41/MobiWeave-Protocol/issues/1)、[#2](https://github.com/China-wzy41/MobiWeave-Protocol/issues/2)、[#3](https://github.com/China-wzy41/MobiWeave-Protocol/issues/3)|
|B 通信协议|消息与日志字段、收发流程、正常与错误样例|[#6](https://github.com/China-wzy41/MobiWeave-Protocol/issues/6)|
|C 数据／孪生／实验|研究问题、可重复模拟、测试记录与结果表|[#7](https://github.com/China-wzy41/MobiWeave-Protocol/issues/7)、[#8](https://github.com/China-wzy41/MobiWeave-Protocol/issues/8)|
|D 上位机／可视化|节点列表、消息记录、连接状态、日志保存|[#2](https://github.com/China-wzy41/MobiWeave-Protocol/issues/2)、[#20](https://github.com/China-wzy41/MobiWeave-Protocol/issues/20)|
|E 项目／场景／市场|场景说明、赛事来源、资源表、访谈摘要|[#5](https://github.com/China-wzy41/MobiWeave-Protocol/issues/5)、[#9](https://github.com/China-wzy41/MobiWeave-Protocol/issues/9)|

B 统一格式；A 提供板端数据；C 模拟和统计；D 接入、显示和保存；E 汇总进度与需求。D 先用 C 的样例，硬件就绪后换成真实输入。

## 从这里开始

- [本月计划与交付方式](docs/planning/first-month.md) · [#1](https://github.com/China-wzy41/MobiWeave-Protocol/issues/1) 本月验收
- [一年路线](docs/planning/roadmap.md) · [#4](https://github.com/China-wzy41/MobiWeave-Protocol/issues/4) 年度总控 · [里程碑](https://github.com/China-wzy41/MobiWeave-Protocol/milestones)
- [协议与日志要求](docs/protocol/README.md) · [实验与验收方法](docs/experiments/README.md)
- [硬件与固件](Firmware/README.md) · [上位机](Host/README.md) · [仿真](Simulation/README.md) · [测试记录](Tests/README.md)

模拟、实测和估计值分别标注。地图、轨迹和热力图后置；没有位置或测量数据时不展示虚构覆盖。
