# 一年路线｜方案 B

更新：2026-10-31。计划周期：2026-10-30 至 2027-10-29，日期均按北京时间。由五人团队执行；这些是项目日期，不是正式赛程。

## 一年后交什么

先做两节点通信，再做三节点断链携带，最终形成四个固定节点加一个移动节点的系统：节点能独立缓存和转发，上位机能接入、保存和展示，实验工具能回放和校准，固定规则与预测策略有可信的实测对比。

调度首先回答“短暂相遇时发哪些消息、发多少、何时停止或回退”。路线先人工预设。机器人自主导航、多移动节点路径优化、复杂学习模型与云平台留作拓展，不占当前主线。

## 八个阶段

|阶段|计划截止|要看到的成果|任务|
|---|---|---|---|
|[M0 首轮准备](https://github.com/China-wzy41/MobiWeave-Protocol/milestone/1)|2026-11-30|五个方向完成首轮交付，做一次软件演示|[#1](https://github.com/China-wzy41/MobiWeave-Protocol/issues/1)、[#2](https://github.com/China-wzy41/MobiWeave-Protocol/issues/2)、[#5](https://github.com/China-wzy41/MobiWeave-Protocol/issues/5)、[#6](https://github.com/China-wzy41/MobiWeave-Protocol/issues/6)、[#7](https://github.com/China-wzy41/MobiWeave-Protocol/issues/7)、[#8](https://github.com/China-wzy41/MobiWeave-Protocol/issues/8)、[#9](https://github.com/China-wzy41/MobiWeave-Protocol/issues/9)、[#20](https://github.com/China-wzy41/MobiWeave-Protocol/issues/20)|
|[M1 通信与断链转发](https://github.com/China-wzy41/MobiWeave-Protocol/milestone/2)|2026-12-31|两节点无线通信；三节点保存、携带、转发消息|[#3](https://github.com/China-wzy41/MobiWeave-Protocol/issues/3)、[#10](https://github.com/China-wzy41/MobiWeave-Protocol/issues/10)、[#11](https://github.com/China-wzy41/MobiWeave-Protocol/issues/11)、[#12](https://github.com/China-wzy41/MobiWeave-Protocol/issues/12)、[#13](https://github.com/China-wzy41/MobiWeave-Protocol/issues/13)、[#21](https://github.com/China-wzy41/MobiWeave-Protocol/issues/21)|
|[M2 短时间接触传输](https://github.com/China-wzy41/MobiWeave-Protocol/milestone/3)|2027-01-31|分片、断点续传；普通顺序与优先级传输对比|[#14](https://github.com/China-wzy41/MobiWeave-Protocol/issues/14)|
|[M3 网络数字孪生](https://github.com/China-wzy41/MobiWeave-Protocol/milestone/4)|2027-03-15|实测校准、实验回放、拓扑与消息路径展示|[#15](https://github.com/China-wzy41/MobiWeave-Protocol/issues/15)、[#22](https://github.com/China-wzy41/MobiWeave-Protocol/issues/22)|
|[M4 预测与调度](https://github.com/China-wzy41/MobiWeave-Protocol/milestone/5)|2027-04-30|比较固定规则和轻量预测，验证实际收益|[#16](https://github.com/China-wzy41/MobiWeave-Protocol/issues/16)|
|[M5 完整系统与实验](https://github.com/China-wzy41/MobiWeave-Protocol/milestone/6)|2027-06-30|五节点系统、重复实验、对照结果与技术报告|[#17](https://github.com/China-wzy41/MobiWeave-Protocol/issues/17)|
|[M6 场景试用](https://github.com/China-wzy41/MobiWeave-Protocol/milestone/7)|2027-08-31|一个受控场景试用，获得反馈并改进|[#18](https://github.com/China-wzy41/MobiWeave-Protocol/issues/18)|
|[M7 年度成果](https://github.com/China-wzy41/MobiWeave-Protocol/milestone/8)|2027-10-29|稳定版本、复现资料、演示视频与答辩材料|[#19](https://github.com/China-wzy41/MobiWeave-Protocol/issues/19)|

每阶段开始前两周，再把阶段任务细化为 1–2 周可验收的小任务。后期指标是待验证目标，不是成果承诺。

## 依赖与到货调整

M0 软件准备 → M1 实物断链转发 → M2 分片与固定基线 → M3 校准和回放 → M4 预测验证 → M5 完整实验 → M6 受控试用 → M7 冻结成果。

LoRa 暂按未到货，型号和数量待 A 核对。用 T 表示两套可用节点就绪日，T3 表示第三套就绪日。内部安排参考：T+3 首次收发、T+7 无线基线、T+10 可靠传输、max(T+14,T3+7) 首次三节点携带、max(T+21,T3+14) 完整实物验收。以上是就绪后的工作节奏，不改变上表日期而不留记录。

若预计赶不上里程碑，由 E 与主责在 issue 中记录原因、新日期和后续影响，再更新 milestone。软件任务继续；不能用模拟结果关闭实物验收，也不靠削减实验重复次数维持日期。

M1 未通过先修通信；M3 误差大先修校准；M4 无收益就保留负结果和更简单的规则。优先缩减拓展功能。正式赛事通知一旦明确，E 另行倒排提交与材料冻结时间，不沿用历史大纲中的推定赛期。

## 作品厚度怎样落实

“科学问题深度 × 系统完整度 × 实验可信度 × 应用价值 × 展示效果”用于检查短板，不编造乘积分数。

|维度|必须留下什么|任务|
|---|---|---|
|科学问题|原始资料对照、可被否定的假设、强基线、消融与失败边界|[#7](https://github.com/China-wzy41/MobiWeave-Protocol/issues/7)、[#14](https://github.com/China-wzy41/MobiWeave-Protocol/issues/14)、[#16](https://github.com/China-wzy41/MobiWeave-Protocol/issues/16)|
|完整系统|节点—协议—缓存—上位机—实验回放—策略—实测反馈|[#2](https://github.com/China-wzy41/MobiWeave-Protocol/issues/2)、[#10](https://github.com/China-wzy41/MobiWeave-Protocol/issues/10)–[#12](https://github.com/China-wzy41/MobiWeave-Protocol/issues/12)、[#15](https://github.com/China-wzy41/MobiWeave-Protocol/issues/15)、[#20](https://github.com/China-wzy41/MobiWeave-Protocol/issues/20)–[#22](https://github.com/China-wzy41/MobiWeave-Protocol/issues/22)|
|可信实验|版本、配置、原始数据、独立重复、置信区间、复现过程|[#3](https://github.com/China-wzy41/MobiWeave-Protocol/issues/3)、[#8](https://github.com/China-wzy41/MobiWeave-Protocol/issues/8)、[#13](https://github.com/China-wzy41/MobiWeave-Protocol/issues/13)、[#17](https://github.com/China-wzy41/MobiWeave-Protocol/issues/17)|
|应用价值|一个可达场景、访谈、真实成本、受控试用与改进|[#5](https://github.com/China-wzy41/MobiWeave-Protocol/issues/5)、[#9](https://github.com/China-wzy41/MobiWeave-Protocol/issues/9)、[#18](https://github.com/China-wzy41/MobiWeave-Protocol/issues/18)|
|展示效果|可追溯消息路径、现场闭环、策略对比、视频和备用回放|[#20](https://github.com/China-wzy41/MobiWeave-Protocol/issues/20)–[#22](https://github.com/China-wzy41/MobiWeave-Protocol/issues/22)、[#19](https://github.com/China-wzy41/MobiWeave-Protocol/issues/19)|

系统做成、实验可信、证明预测有效是三个不同结论。论文、专利和奖项均不作为保证。

## 协作节奏

每周 20–30 分钟核对证据和阻塞；每两周演示一次；每月给老师一页结论与待决问题。每人同时推进不超过两项主任务。卡住超过 48 小时，在 issue 写“原因、下一步、需要谁提供什么”。

关闭任务前补上文件/PR、运行记录、验收人和日期，由另一成员复核。原始数据不覆盖，修改实验口径须记录日期与原因。完整方法见[实验说明](../experiments/README.md)，本月安排见[首轮计划](first-month.md)。
