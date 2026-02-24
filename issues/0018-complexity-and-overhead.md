# Issue #18: 复杂度与开销评估（控制开销/计算开销）

## 类型

Experiment + Measurement

## 背景

目前论文结果强调性能优势，但缺少“代价端”证据：控制消息开销、路由计算开销、可扩展性。

## 单一目标（Only One）

只补充开销测量，不改路由策略：

- 控制广播次数/每步消息量
- 每步决策计算时间（wall-clock）
- 节点规模扩展（50/100/200）下的增长趋势

## 验收标准

1. 输出开销统计表与趋势图数据。
2. 给出 SNN 与 OSPF/ECMP/PPO 的开销对比。
3. 与性能收益（PDR/Loss）形成收益-代价分析。

## 计划命令（示例）

```bash
python3 scripts_flow/overhead_eval.py --algos ospf,ecmp,ppo,snn --topos ba,er --sizes 50,100,200 --seeds 1-20 --workers 20 --out-prefix run_dir/issue18_overhead
```

## 当前进展（2026-02-23）

已完成实现与全量评估（只补测量，不改路由策略）：

- 新增 `scripts_flow/overhead_eval.py`
  - 每步 wall-clock：`wall_ms_mean/p95/p99`
  - 控制面消息：`ctrl_msgs_mean/p95/p99`（由 `broadcasts/table_updates` 增量构成）
  - 输出收益-代价分析：`issue18_overhead_benefit_cost.csv`

完整矩阵命令：

```bash
python3 scripts_flow/overhead_eval.py --algos ospf,ecmp,ppo,snn --topos ba,er --sizes 50,100,200 --seeds 1-20 --failure-profiles single,frequent --workers 20 --out-prefix run_dir/issue18_overhead
```

结果文件：

- `run_dir/issue18_overhead_runs.csv`
- `run_dir/issue18_overhead_summary.csv`
- `run_dir/issue18_overhead_significance.csv`
- `run_dir/issue18_overhead_benefit_cost.csv`

核心结论（global，SNN 相对基线）：

1. 开销增量（计算 + 控制）：
   - 相对 OSPF：`delta_wall_ms_mean +108.97`，`delta_ctrl_msgs_mean +0.625`
   - 相对 ECMP：`delta_wall_ms_mean +109.31`，`delta_ctrl_msgs_mean +0.625`
   - 相对 PPO：`delta_wall_ms_mean +70.88`，`delta_ctrl_msgs_mean +0.625`
2. 对应收益（性能侧）：
   - 相对 OSPF：`delta_pdr_mean +0.1263`，`delta_loss_mean -5756.75`
   - 相对 ECMP：`delta_pdr_mean +0.0734`，`delta_loss_mean -3315.77`
   - 相对 PPO：`delta_pdr_mean +0.0169`，`delta_loss_mean -982.23`
3. 收益-代价比（global）：
   - 对 OSPF：`pdr_gain_per_ms_overhead 0.002246`，`loss_reduction_per_ctrl_msg 9477.59`
   - 对 ECMP：`0.001351`，`5319.66`
   - 对 PPO：`0.001318`，`1481.71`

说明：

- 本仿真框架中 OSPF/ECMP/PPO 未显式建模控制广播，因此其 `ctrl_msgs_*` 接近 0；该项主要反映 SNN 控制面事件开销。
