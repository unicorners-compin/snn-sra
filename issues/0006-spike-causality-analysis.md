# Issue #6: Spike-Causality Analysis for SNN Routing

## Type

Experiment + Measurement

## Background

在 issue #5 中，burst 广播已改为 LIF 放电事件触发。我们需要验证“机制因果链”而非只看最终均值：

1. 高压节点 spike 触发后，邻居是否更快绕行；
2. 经过该节点的转发流量是否在短窗口内下降；
3. 全局 PDR 在故障后是否更快恢复。

## Single Idea (Only One)

不改算法，仅新增可复现实验分析：

- 识别高压 spike 事件（`last_spike==1` 且节点压力处于高分位）
- 统计事件后 `5-20` step 的绕行与流量变化
- 统计故障后 PDR 恢复速度

## Scope

- In scope:
  - 新增分析脚本，输出 ER/BA 的因果指标
  - 将结果回填 issue 与 PR 草案
- Out of scope:
  - 任何路由策略改动
  - 参数调优

## Metrics

1. 路径变化率（event-local）
   - 定义：事件后窗口内每步 route-change 增量相对事件前基线的变化量（delta）。
2. 经过该节点流量下降率（event-local）
   - 定义：事件节点入流量在 `t+5..t+20` 相对 `t-5..t-1` 的下降比例。
3. PDR 恢复速度（global）
   - 定义：故障后 `20` step 的每步 PDR 提升斜率（`(step_pdr[t+20]-step_pdr[t+1])/19`）。

## Acceptance Criteria

1. 分析脚本可在固定 seeds 下稳定复现结果。
2. 至少输出 ER/BA 的三项指标均值。
3. 结果记录到 issue 文档，且明确正负结论。

## Validation Plan

```bash
python3 scripts_flow/analyze_spike_causality.py --topos er,ba --seeds 11,17,23 --steps 240 --fail-step 150 --out run_dir/issue6_spike_causality.csv --out-agg run_dir/issue6_spike_causality_agg.csv
```

## Current Findings

### Aggregated (mean over seeds 11/17/23)

- ER:
  - `events_valid`: 95.0
  - `events_flow_valid`: 33.33
  - `route_change_rate_delta`: `+0.054`
  - `through_node_drop_rate`: `0.379`（在流量有效事件中，事件后 5-20 step 入流量平均下降约 37.9%）
  - `pdr_recovery_slope`: `-0.000725`（恢复速度在 ER 上呈 mixed）
- BA:
  - `events_valid`: 100.0
  - `events_flow_valid`: 37.67
  - `route_change_rate_delta`: `+0.012`
  - `through_node_drop_rate`: `0.458`（事件后入流量平均下降约 45.8%）
  - `pdr_recovery_slope`: `+0.001797`

### Interpretation

- 高压 spike 事件后，局部绕行现象成立：
  - 事件节点入流量在短窗口内显著下降（ER/BA 均为正下降率）。
  - 路径变化增量总体为正，说明事件后有额外改路活动。
- PDR 恢复速度：
  - BA 明确为正，恢复趋势清晰。
  - ER 为 mixed，seed 间差异较大（需要后续在 ER 上做更细分层分析）。

### Notes on Metric Robustness

- 对“流量下降率”加入了基线流量门限（`--min-base-flow 0.5`），避免低流量节点导致比率失真。
- `pdr_recovery_slope` 使用每步 PDR（由累计 delivered/generated 增量计算）而非累计 PDR，避免滞后效应。

## Extra Stress Test: Frequent Failures

### Setup

- 拓扑：ER/BA，seeds=`11,17,23`
- 运行步长：`260`
- 故障注入：`step=120,150,180,210` 连续移除 4 条高介数链路
- 对比：`SNN(snn_spike_native)` vs `OSPF`

### Results (mean, SNN - OSPF)

- ER:
  - `pdr_final`: `+0.0379`
  - `loss_final`: `-996.3`
  - `pdr_tail`（最后一次故障后窗口均值）: `+0.0376`
  - `delay_final`: `+1.658`
- BA:
  - `pdr_final`: `+0.1434`
  - `loss_final`: `-3540.3`
  - `pdr_tail`: `+0.1496`
  - `delay_final`: `+0.282`

### Conclusion for Frequent-Failure Networks

- 会自动绕路：是。高压 spike 触发后，局部流量与路径都出现可测重分配。
- 性能是否更好：在“容量与稳定性”指标上是更好（PDR 上升、Loss 下降）；代价是时延上升，且 ER 上升更明显。
