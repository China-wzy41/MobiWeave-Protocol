# 测试记录

C 负责实验口径和统计，各方向保存自己的原始证据；目前尚无已核验测试结果。

实际产生数据时使用以下结构，无需先堆空目录：

```text
Tests/
  configs/             # 可复用配置
  raw/<run_id>/        # 单次运行的原始日志与环境记录
  analysis/<run_id>/   # 分析输出、图表及脚本版本说明
```

每次运行记录：REAL/SIM/ESTIMATED 来源、日期、人员、版本、硬件/环境、配置、随机种子、开始结束条件、预期和实际结果。失败也保留；原始文件不覆盖。大文件可放受控存储，记录固定版本、校验值和访问方式。

执行步骤和指标见[实验方法](../docs/experiments/README.md)。日志格式由 [B 统一](../docs/protocol/README.md)，模拟工具放 [Simulation](../Simulation/README.md)，显示和保存工具放 [Host](../Host/README.md)。

关闭任务前附复现步骤、证据路径、验收人和日期。不要把一次演示当成全部实验通过。
