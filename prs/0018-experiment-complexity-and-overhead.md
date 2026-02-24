# PR Draft: Experiment Issue #18 - 复杂度与开销评估

## 关联 Issue

- refs #18

## Why

补齐论文“代价端”证据：

1. 计算开销（每步 wall-clock）
2. 控制开销（控制消息量）
3. 与性能收益（PDR/Loss）形成收益-代价分析

## 变更内容

- 新增 `scripts_flow/overhead_eval.py`
  - 并行评估 OSPF/ECMP/PPO/SNN（20核）
  - 输出 `wall_ms_mean/p95/p99`
  - 输出 `ctrl_msgs_mean/p95/p99`（由 `broadcasts/table_updates` 增量得到）
  - 输出 `benefit_cost` 表（PDR/Loss 收益与开销增量配对）

## 验证命令

```bash
python3 -m py_compile scripts_flow/overhead_eval.py
python3 scripts_flow/overhead_eval.py --algos ospf,ecmp,ppo,snn --topos ba,er --sizes 50,100,200 --seeds 1-20 --failure-profiles single,frequent --workers 20 --out-prefix run_dir/issue18_overhead
```

## 结果文件

- `run_dir/issue18_overhead_runs.csv`
- `run_dir/issue18_overhead_summary.csv`
- `run_dir/issue18_overhead_significance.csv`
- `run_dir/issue18_overhead_benefit_cost.csv`

## 关键结果（global）

- SNN vs OSPF：
  - `delta_wall_ms_mean +108.97`
  - `delta_ctrl_msgs_mean +0.625`
  - `delta_pdr_mean +0.1263`
  - `delta_loss_mean -5756.75`
- SNN vs ECMP：
  - `delta_wall_ms_mean +109.31`
  - `delta_ctrl_msgs_mean +0.625`
  - `delta_pdr_mean +0.0734`
  - `delta_loss_mean -3315.77`
- SNN vs PPO：
  - `delta_wall_ms_mean +70.88`
  - `delta_ctrl_msgs_mean +0.625`
  - `delta_pdr_mean +0.0169`
  - `delta_loss_mean -982.23`

收益-代价比（global）：

- 对 OSPF：
  - `pdr_gain_per_ms_overhead 0.002246`
  - `loss_reduction_per_ctrl_msg 9477.59`
- 对 ECMP：
  - `0.001351`
  - `5319.66`
- 对 PPO：
  - `0.001318`
  - `1481.71`

## 解释

- SNN 引入可观计算/控制开销，但在故障+重背景流下换来稳定的 PDR/Loss 收益。
- 该结果与 issue #16（时延代价）共同支持“以可控代价换容量与稳定性”的论文叙事。

## 模型边界

- 现有仿真中 OSPF/ECMP/PPO 未显式实现控制广播过程，其 `ctrl_msgs` 近似 0；
- 因此控制开销结论主要解释 SNN 控制面事件量级，而非协议栈级报文字节精算。
