# Issue #5 - README 数学化重写（增强版 SNN-SRA 仿真思路）

GitHub Issue: https://github.com/unicorners-compin/snn-sra/issues/5

## 背景

当前仓库根目录 `README.md` 缺失有效内容，不利于后续论文讨论与工程协作。项目核心机制（SNN 状态更新、链路打分、事件驱动控制面、指标定义）需要统一为可审阅的数学表达。

## 目标

重写根目录 `README.md`，用数学公式系统描述增强版 `scripts_flow/` 的仿真逻辑，覆盖：

1. 节点动力学（LIF/应力更新）
2. 链路代价与路由评分
3. 事件驱动控制面更新规则
4. 数据面转发流程
5. 全局评估指标定义

## 验收标准

- `README.md` 包含完整数学公式与变量定义；
- 与当前代码实现保持一致，不夸大未实现机制；
- 文档可直接支撑“公式来源与改进”讨论。

## 输出物

- `README.md`
- `prs/0022-docs-readme-math-formulation.md`
