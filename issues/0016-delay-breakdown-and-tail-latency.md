# Issue #16: 时延分解与尾时延（P95/P99）评估补充

## 类型

Experiment + Measurement

## 背景

当前论文结论已明确“以时延换容量/稳定性”，但缺少时延结构化证据：

- 时延由哪些部分构成（排队、绕路、重路由）
- 尾时延是否可控（P95/P99）

## 单一目标（Only One）

只补充测量与统计，不改路由策略。

## 范围

- In scope:
  - 增加端到端时延分解指标
  - 输出 P50/P95/P99 及其置信区间
  - 对比 OSPF/ECMP/PPO/SNN 在故障+重背景流下的尾时延
- Out of scope:
  - 算法参数调优
  - 新控制机制

## 验收标准

1. 输出可直接用于论文图表的尾时延统计表。
2. 给出“时延代价来源”定量解释。
3. 与现有 PDR/Loss 结论形成闭环叙事。

## 验证命令（预期）

```bash
python3 scripts_flow/paper_stat_eval_parallel.py --algos ospf,ecmp,ppo,snn --topos ba,er --sizes 50,100 --seeds 1-20 --steps 240 --fail-step 150 --failure-profiles single,frequent --background-scale 2.0 --workers 20 --out-prefix run_dir/issue16_delay
```

## 当前进展（2026-02-23）

已完成实现与全量评估（仅新增测量层，不改路由策略）：

- 新增 `scripts_flow/paper_delay_eval_parallel.py`
  - 输出 `P50/P95/P99`（final/post）
  - 输出时延分解：`queue_delay_mean` 与 `extra_hop_mean`（final/post）
  - 保留原有 `PDR/Loss/avg_delay` 指标并给出配对显著性
- 在模拟器增加逐包统计记录：
  - `scripts_flow/snn_simulator.py`
  - `scripts_flow/compare_snn_vs_ospf.py`

完整矩阵命令：

```bash
python3 scripts_flow/paper_delay_eval_parallel.py --algos ospf,ecmp,ppo,snn --topos ba,er --sizes 50,100 --seeds 1-20 --steps 240 --fail-step 150 --failure-profiles single,frequent --background-scale 2.0 --workers 20 --out-prefix run_dir/issue16_delay
```

结果文件：

- `run_dir/issue16_delay_runs.csv`
- `run_dir/issue16_delay_summary.csv`
- `run_dir/issue16_delay_significance.csv`

核心结论（SNN vs 基线，8 个分组平均）：

1. 尾时延上升是客观存在的：
   - `delay_p99_post`：对 OSPF `+18.05`，对 ECMP `+16.54`，对 PPO `+18.79`
2. 时延代价来源以“绕路项”为主，其次是排队项：
   - `extra_hop_mean_post`：对 OSPF/ECMP 约 `+0.77`（8/8 分组显著）
   - `queue_delay_mean_post`：对 OSPF `+1.11`，对 ECMP `+0.66`，对 PPO `+1.95`
3. 与容量稳定性收益形成闭环：
   - `pdr_post` 仍显著高于 OSPF/ECMP（均值 +10.75% / +6.57%）
   - `loss_final` 显著低于 OSPF/ECMP（均值 -4943.94 / -3033.57）
