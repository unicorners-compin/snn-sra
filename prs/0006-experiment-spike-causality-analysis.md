# PR Draft: Experiment Issue #6 - Spike Causality Analysis

## Linked Issue

- refs #6

## Why

为验证 SNN 机制链条是否成立，需要回答三个问题：

1) 高压 spike 是否触发邻居绕行；
2) 事件节点流量是否下降；
3) 故障后 PDR 是否更快恢复。

## What Changed

- `scripts_flow/snn_simulator.py`
  - 新增每步观测字段（不改路由策略）：
    - `last_step_edge_forward_counts`
    - `last_step_route_change_increase`
- `scripts_flow/analyze_spike_causality.py`（新增）
  - 识别高压 spike 事件（`last_spike==1` + 压力高分位）
  - 计算事件后 `5-20` step 的：
    - 路径变化率
    - 事件节点入流量下降率
  - 计算故障后 PDR 恢复速度（每步 PDR 口径）

## Validation

```bash
python3 -m py_compile scripts_flow/snn_simulator.py scripts_flow/analyze_spike_causality.py
python3 scripts_flow/analyze_spike_causality.py --topos er,ba --seeds 11,17,23 --steps 240 --fail-step 150 --out run_dir/issue6_spike_causality.csv --out-agg run_dir/issue6_spike_causality_agg.csv
```

## Results (mean over seeds 11/17/23)

- ER:
  - `events_valid`: 95.0
  - `events_flow_valid`: 33.33
  - `route_change_rate_delta`: `+0.054`
  - `through_node_drop_rate`: `0.379`
  - `pdr_recovery_slope`: `-0.000725`
- BA:
  - `events_valid`: 100.0
  - `events_flow_valid`: 37.67
  - `route_change_rate_delta`: `+0.012`
  - `through_node_drop_rate`: `0.458`
  - `pdr_recovery_slope`: `+0.001797`

## Interpretation

- 机制因果链在局部层面成立：高压 spike 后事件节点流量下降，且出现额外改路活动。
- BA 的恢复趋势更稳定；ER 在恢复速度上呈 mixed，说明随机图下仍有 seed 敏感性。
