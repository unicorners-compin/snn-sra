# PR Draft: Docs Issue #5 - README 数学化重写

## 关联 Issue

- refs #5

## Why

根目录 README 原为空，无法承载项目方法论。需要将增强版 `scripts_flow` 的仿真机制统一为数学表达，以支持论文讨论与后续公式改进。

## 变更内容

1. 重写 `README.md`
   - 系统对象与状态定义
   - 节点动力学（LIF + 应力更新）
   - 链路代价与 STDP/损失惩罚
   - 本地路由评分与 beacon 势场
   - 事件驱动控制面（snn_event_dv）
   - 转发流程与全局指标（PDR/Delay/Hop/Lyapunov）
2. 新增 issue 记录：
   - `issues/0023-readme-math-formulation.md`

## 检查

- 文档与当前代码保持一致（`scripts_flow/snn_node.py`, `snn_router.py`, `snn_simulator.py`）
- 数学符号与变量含义在 README 内完整定义

## 备注

- 本 PR 仅文档更新，不改动算法实现与实验结果。
