# Issue #4: Destination Beacon Spikes for Native SNN Routing

## Type

Feature + Focused Experiment

## Background

`snn_spike_native` 已有 burst 平面与 temporal-STDP，但在 ER 拓扑仍显著落后 OSPF。当前主要问题是脉冲信号缺少“目的地语义”，导致扩散虽活跃，但对选路引导不够精确。

## Single Idea (Only One)

引入 **destination beacon spikes**：

- 每个目的地节点持续注入目的地标记脉冲（beacon）
- 脉冲在拓扑中按时间衰减扩散
- 转发时优先选择对目标 `dst` beacon 强度更高的邻居

本轮只验证这一个想法，不混入其他新机制。

## Scope

- In scope:
  - 在 `snn_spike_native` 中增加 `dst_beacon` 状态与更新
  - 转发评分接入 `dst_beacon`（目的地导向）
  - 针对 ER 做小规模种子对照
- Out of scope:
  - 新学习规则
  - 新损失函数
  - 多目标联合优化

## Acceptance Criteria

1. 新增机制可通过参数开关启用/关闭。
2. 在 ER（seeds=11/17/23）上，相比“未启用 beacon 的 native 模式”：
   - `PDR` 提升且 `Loss` 下降（优先目标），
   - `Delay` 可小幅上升（作为容量与稳定性的代价）。
3. 保持 BA 的容量优势不退化（`PDR` 不下降超过 2% 绝对值）。

## Validation Plan

```bash
python3 scripts_flow/compare_snn_vs_ospf.py --topos er --seeds 11,17,23 --snn-mode snn_spike_native
python3 scripts_flow/compare_snn_vs_ospf.py --topos ba --seeds 11,17,23 --snn-mode snn_spike_native
```

## Risks

- beacon 过强会引发路径过度汇聚
- beacon 过弱则无法提供有效目标导向

## Current Findings

- ER（vs OSPF, seeds=11/17/23, snn_spike_native）：
  - `PDR` +0.0292，`Loss` -1041.0
  - `Delay` +1.50（符合“以轻微时延换容量/稳定性”预期）
- BA（vs OSPF, seeds=11/17/23, snn_spike_native）：
  - `PDR` +0.1534，`Loss` -3773.3
  - `Delay` +0.41（小幅增加）

## Rollback

- 通过参数关闭 `destination beacon`，回退到当前 native 基线
