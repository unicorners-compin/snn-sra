# PR Draft: Experiment Issue #16 - 时延分解与尾时延（P95/P99）

## 关联 Issue

- refs #16

## Why

补齐论文中“以时延换容量/稳定性”的结构化证据：

1. 尾时延（P95/P99）是否可量化；
2. 时延代价来自排队还是绕路；
3. 与既有 PDR/Loss 优势形成闭环。

## 变更内容

- 更新 `scripts_flow/snn_simulator.py`
  - 增加逐包交付采样记录（delay/hops/shortest-hop/extra-hop/queue-delay/step）
- 更新 `scripts_flow/compare_snn_vs_ospf.py`
  - 为 OSPF/ECMP/Backpressure/PPO 同步增加逐包交付采样记录
- 新增 `scripts_flow/paper_delay_eval_parallel.py`
  - 20核并行评估 OSPF/ECMP/PPO/SNN
  - 输出 `P50/P95/P99`（final/post）
  - 输出 `queue_delay_mean` 与 `extra_hop_mean`（final/post）
  - 输出与 SNN 配对差值、CI、sign-flip 显著性

## 验证命令

```bash
python3 -m py_compile scripts_flow/compare_snn_vs_ospf.py scripts_flow/snn_simulator.py scripts_flow/paper_delay_eval_parallel.py
python3 scripts_flow/paper_delay_eval_parallel.py --algos ospf,ecmp,ppo,snn --topos ba,er --sizes 50,100 --seeds 1-20 --steps 240 --fail-step 150 --failure-profiles single,frequent --background-scale 2.0 --workers 20 --out-prefix run_dir/issue16_delay
```

## 结果摘要

输出文件：

- `run_dir/issue16_delay_runs.csv`
- `run_dir/issue16_delay_summary.csv`
- `run_dir/issue16_delay_significance.csv`

关键结果（8 个分组平均）：

1. 尾时延提升（SNN - baseline）：
   - `delay_p99_post` vs OSPF: `+18.05`
   - `delay_p99_post` vs ECMP: `+16.54`
   - `delay_p99_post` vs PPO: `+18.79`
2. 时延代价来源：
   - `extra_hop_mean_post` vs OSPF/ECMP: 约 `+0.77`（8/8 分组显著）
   - `queue_delay_mean_post` vs OSPF: `+1.11`，vs ECMP: `+0.66`
3. 与容量/稳定性收益闭环：
   - `pdr_post` vs OSPF: `+0.1075`，vs ECMP: `+0.0657`
   - `loss_final` vs OSPF: `-4943.94`，vs ECMP: `-3033.57`

## 论文叙事建议

- SNN 的时延代价主要来自“路径绕行 + 控制稳定性换取拥塞回避”；
- 该代价在故障与重背景流下换来了更高 PDR 与更低 Loss，符合“容量/稳定性优先”的设计目标。
