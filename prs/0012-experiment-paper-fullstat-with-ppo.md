# PR Draft: Experiment Issue #12 - 论文主版本全量统计（含 PPO）

## 关联 Issue

- refs #12

## Why

将首轮样本（issue #10）升级为论文主版本的全量统计结论，并纳入学习型强基线 PPO（issue #11）。

## 做了什么

- 运行全量矩阵：
  - 算法：`ospf,ecmp,backpressure,ppo,snn`
  - 拓扑：`ba,er`
  - 规模：`50,100`
  - 故障：`single,frequent`
  - 种子：`1-20`
- 采用分片并行执行后统一合并，得到：
  - `run_dir/issue12_full_runs.csv`（800 runs）
  - `run_dir/issue12_full_summary.csv`
  - `run_dir/issue12_full_significance.csv`

## 主结果（160 对配对样本）

- SNN vs OSPF：
  - `pdr_final +0.11624`，`p=5e-05`
  - `loss_final -2434.50`，`p=5e-05`
  - `delay_final +0.52216`，`p=0.0144`
- SNN vs ECMP：
  - `pdr_final +0.06225`，`p=5e-05`
  - `loss_final -1383.73`，`p=5e-05`
  - `delay_final +0.69100`，`p=2.5e-04`
- SNN vs PPO：
  - `pdr_final +0.01295`，`p=5e-05`
  - `loss_final -434.67`，`p=5e-05`
  - `delay_final +0.96512`，`p=5e-05`

## 解释

- 在论文主矩阵下，SNN 对 OSPF/ECMP/PPO 都实现了统计显著的容量与稳定性优势（PDR↑、Loss↓）。
- 代价是时延增加，符合项目既定 trade-off 叙事。
