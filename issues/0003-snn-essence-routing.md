# Issue #3: SNN Essence Routing (Event Bursts + Temporal STDP + Spike-Decoding Forwarding)

## Type

Feature + Experiment

## Background

当前 `snn_event_dv` 已是事件驱动控制面，但本质仍偏向“事件触发 DV”，尚未体现 SNN 路由精髓：

- 脉冲广播的动态范围不足（高压节点广播频率提升不明显）
- STDP 仍是简化项（缺少 pre/post 时间差学习窗）
- 转发仍依赖路由表，不是脉冲解码决策

## Goal

实现“更接近 SNN 原生”的路由机制，并验证在至少一个拓扑上优于现有 `snn_event_dv`。

## Scope

- In scope:
  - Event burst 编码：压力/丢包触发多脉冲广播，而非仅周期阈值触发
  - Temporal STDP：基于 pre/post 脉冲到达时间差更新链路可塑性
  - Spike-decoding forwarding：基于邻居脉冲轨迹/电位解码选择下一跳
  - 与 `snn_event_dv`、`OSPF` 对照评估
- Out of scope:
  - Q-learning/value-based 路由
  - 分布式部署与系统级优化

## Acceptance Criteria

1. 新增路由模式（例如 `snn_spike_native`）可运行并在前端可视化。
2. `run_dir/` 输出包含新增模式对照结果。
3. 至少在一个拓扑（BA/ER）达到以下之一：
   - `PDR` 高于 `snn_event_dv` 且 `Delay` 不显著恶化（<= +5%）
   - `Loss` 低于 `snn_event_dv` 且 `PDR` 不下降

## Validation Plan

```bash
SNN_TOPOLOGY=ba SNN_ROUTING_MODE=snn_spike_native python3 scripts_flow/main_snn.py
SNN_TOPOLOGY=er SNN_ROUTING_MODE=snn_spike_native python3 scripts_flow/main_snn.py
python3 scripts_flow/compare_snn_vs_ospf.py --topos ba,er --seeds 11,17,23
```

## Risks

- 脉冲事件过多导致控制面风暴
- STDP 参数敏感导致不稳定振荡
- 本地解码策略在稀疏拓扑上陷入局部最优

## Experiment Log

- Attempt A (ER stabilization with stronger hysteresis + longer switch interval + lower burst aggressiveness):
  - Result: ER 指标未改善，`PDR` 仍显著落后 OSPF，`Delay` 更高。
  - Action: 保留该配置框架用于后续拓扑自适应，但不作为最终默认参数结论。

## Rollback

- 保留 `snn_event_dv` 作为默认稳定模式
- 新模式通过 `SNN_ROUTING_MODE` 参数开关启停
