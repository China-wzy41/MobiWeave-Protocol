# 研究问题与资料整理

主责 C，B 配合；首轮任务 [#7](https://github.com/China-wzy41/MobiWeave-Protocol/issues/7)，2026-11-30 交付相关工作矩阵和一页假设。这里是研究方向，不是创新已经成立的声明。

**主问题：**接触短暂且难预测、缓存和空口资源有限时，轻量预测能否比固定优先级提高重要完整消息的按时交付率，同时控制开销和普通消息饥饿？

|假设|要比较什么|可能不成立的情况|
|---|---|---|
|H1 预测质量|历史可获信息与常数/EWMA基线|接触随机、数据少、历史失效|
|H2 端到端收益|同一DTN底座上的固定规则与预测调度|预测提升不足以抵消控制成本|
|H3 孪生可信度|留出实测中的指标误差和策略排序|环境变化、状态陈旧、竞争模型不准|

至少阅读 8 项原始资料，覆盖 DTN/BPv7、实际模块官方手册、LoRa Mesh/DTN、接触预测与调度、孪生校准验证。每项记录：来源、问题、假设、硬件/数据、基线、指标、已解决内容、本项目差异。成果放本目录 related-work.md；不要只列标题或二手摘要。

沿用原计划的阅读起点，仍需成员逐项阅读核对：

- [RFC 4838](https://www.rfc-editor.org/rfc/rfc4838.html)：DTN 架构。
- [RFC 9171](https://www.rfc-editor.org/rfc/rfc9171.html)：BPv7；本项目不据此自称完整兼容。
- [Semtech LoRa Calculator](https://www.semtech.com/design-support/lora-calculator)：参数与空口时长核算起点，须对照实际模块。
- [NIST 数字孪生可信度方法](https://www.nist.gov/publications/credibility-consideration-digital-twins-manufacturing)：作为方法参考，不是本系统有效的证据。

评价口径、强基线和消融见[实验方法](../experiments/README.md)。组合现有技术本身不证明原创；保留正结果、负结果与适用边界。
