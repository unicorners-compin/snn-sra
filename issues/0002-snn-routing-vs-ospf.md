# Issue #2: SNN Routing vs OSPF Performance Gap Closure

## Type

Experiment + Feature

## Background

当前纯 SNN 本地路由在 BA/ER 拓扑下与 OSPF 对比时，`PDR`、`Delay`、`Loss` 均落后。理论上 SNN 应该通过高压力节点的高频脉冲更快传播高代价，从而实现绕拥塞与绕故障。

## Goal

在相同拓扑、相同流量、相同故障条件下，让 SNN 至少在一个核心指标上达到或优于 OSPF，并形成可复现实验报告。

## Scope

- In scope:
  - 引入脉冲触发的 cost 广播机制（事件驱动控制面）
  - 去除 ER/BA 上不合理的曼哈顿启发
  - 增加切换滞回与防环策略，降低路由抖动
  - 完成 BA/ER 多种子对照实验
- Out of scope:
  - Q-learning 或 value-based 路由
  - 大规模并行/分布式工程化部署

## Acceptance Criteria

1. 在 `BA` 或 `ER` 任一拓扑上，相比 OSPF 满足以下之一：
   - `PDR` 不低于 OSPF 且 `avg_delay` 更低；或
   - `PDR` 明显更高（>= +3% 绝对值）
2. 对照实验至少 5 个随机种子，结果输出到 `run_dir/`。
3. 前端可视化可展示故障前后路径变化与恢复过程。

## Validation Plan

```bash
SNN_TOPOLOGY=ba python3 scripts_flow/main_snn.py
SNN_TOPOLOGY=er python3 scripts_flow/main_snn.py
python3 -m http.server 8010
```

## Risks

- 路由滞回过强导致收敛变慢
- 广播频率过高导致控制开销反噬吞吐
- 流量场景偏置导致结论不稳健

## Rollback

- 保留 `routing_mode=snn_local` 作为基线模式
- 所有新机制通过参数开关控制，可快速退回旧路径
