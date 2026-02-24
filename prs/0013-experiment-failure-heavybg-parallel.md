# PR Draft: Experiment Issue #13 - 故障+重背景流统计评估（20核并行）

## 关联 Issue

- refs #13

## Why

补齐两个关键问题：

1. 在故障场景下是否仍保持优势；
2. 在重背景流负载下是否仍保持优势；

并提供标准化 20 核并行执行入口，缩短统计评估周期。

## 变更内容

- 更新 `scripts_flow/paper_stat_eval.py`
  - 增加 `--background-scale` 参数
  - 支持按倍率放大背景流（`base_rate/burst_rate`）
- 新增 `scripts_flow/paper_stat_eval_parallel.py`
  - `ProcessPoolExecutor` 并行执行 case
  - 支持 `--workers`（可设置为 20）
  - 输出与串行版本一致的 `runs/summary/significance`

## 验证命令

```bash
python3 -m py_compile scripts_flow/paper_stat_eval.py scripts_flow/paper_stat_eval_parallel.py
python3 scripts_flow/paper_stat_eval_parallel.py --algos ospf,ecmp,ppo,snn --topos ba,er --sizes 50,100 --seeds 1-20 --steps 240 --fail-step 150 --failure-profiles single,frequent --background-scale 2.0 --snn-mode snn_spike_native --workers 20 --out-prefix run_dir/issue13_heavybg
```

## 结果摘要（重背景流 2.0x）

- SNN vs OSPF（160 配对样本）：
  - `pdr_final +0.11515`，`loss_final -5023.30`，均显著
- SNN vs ECMP：
  - `pdr_final +0.07101`，`loss_final -3112.93`，均显著
- SNN vs PPO：
  - `pdr_final +0.01486`，`loss_final -941.39`，均显著

## 解释

- 在故障 + 重背景流下，SNN 的容量与稳定性优势依旧成立。
- 相对 PPO 的优势仍存在但更接近，说明学习型基线是更强挑战者。
