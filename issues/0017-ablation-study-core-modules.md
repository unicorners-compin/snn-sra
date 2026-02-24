# Issue #17: 核心机制消融实验（Ablation Study）

## 类型

Experiment + Statistical Validation

## 背景

论文主结果已显示 SNN 整体优于 OSPF/ECMP/PPO，但尚缺“各机制贡献度”证据，审稿人通常会要求完整消融。

## 单一目标（Only One）

仅做消融，不改算法新机制：

- 去掉 destination beacon
- 去掉 LIF 触发广播（退回弱事件触发）
- 去掉 STDP 可塑性
- 去掉最小保持时延（与 issue #14 结果联动）

## 验收标准

1. 每个消融版本在同一评估矩阵下可复现。
2. 输出与 full-SNN 的配对差值与显著性。
3. 给出“哪一部分贡献最大”的量化结论。

## 计划命令（示例）

```bash
python3 scripts_flow/paper_ablation_eval.py --topos ba,er --sizes 50,100 --seeds 1-20 --failure-profiles single,frequent --background-scale 2.0 --workers 20 --out-prefix run_dir/issue17_ablation
```

## 当前进展（2026-02-23）

- 已新增 `scripts_flow/paper_ablation_eval.py`，支持以下消融版本并行评估：
  - `full`
  - `no_dst_beacon`
  - `no_lif_burst`
  - `no_stdp`
  - `no_min_hold`
- 已输出四类结果文件：
  - `*_runs.csv`
  - `*_summary.csv`
  - `*_significance.csv`（与 full 做配对显著性）
  - `*_contrib.csv`（贡献度排序）
- 已通过小规模 smoke：

```bash
python3 scripts_flow/paper_ablation_eval.py --topos ba --sizes 30 --seeds 1-2 --steps 80 --fail-step 45 --failure-profiles single --workers 4 --background-scale 1.5 --out-prefix run_dir/issue17_smoke
```

- 下一步执行完整矩阵（20 核并行）并写入 issue 结论。

## 完整矩阵结果（2026-02-23）

执行命令：

```bash
python3 scripts_flow/paper_ablation_eval.py --topos ba,er --sizes 50,100 --seeds 1-20 --failure-profiles single,frequent --background-scale 2.0 --workers 20 --out-prefix run_dir/issue17_ablation
```

结果文件：

- `run_dir/issue17_ablation_runs.csv`
- `run_dir/issue17_ablation_summary.csv`
- `run_dir/issue17_ablation_significance.csv`
- `run_dir/issue17_ablation_contrib.csv`

核心结论（与 full-SNN 配对比较）：

1. `no_dst_beacon` 退化最明显，是当前贡献最大的核心模块：
   - 全局 `pdr_post` 平均差值（variant-full）约 `-0.0333`
   - `route_changes_final` 平均增加约 `+327`
   - 在 8 个分组中，`pdr_post` 有 6/8 显著（`p<0.05`），`delay_post` 有 7/8 显著
2. `no_lif_burst` 与 `no_stdp` 的主效应较小：
   - 全局均值接近 0，显著性通过率低（多数分组不显著）
3. `no_min_hold` 在本批负载下对容量指标无负面，且部分分组 loss 更低：
   - 说明最小保持时延主要是“抗抖动保护项”，并非容量提升主因

贡献度排序（`issue17_ablation_contrib.csv` 的 global 行）：

1. `no_dst_beacon`（最高）
2. `no_stdp`
3. `no_lif_burst`
4. `no_min_hold`
