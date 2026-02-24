# PR Draft: Experiment Issue #17 - 核心机制消融实验（Ablation）

## 关联 Issue

- refs #17

## Why

补齐论文关键缺口：量化 SNN 各核心模块（destination beacon、LIF 触发广播、STDP、最小保持时延）的贡献度，并给出与 full-SNN 的配对显著性证据。

## 变更内容

- 更新 `scripts_flow/snn_simulator.py`
  - 新增参数 `enable_lif_burst`（默认开启）
  - 在 burst 平面更新逻辑中支持关闭 LIF 触发广播，保证可做单因素消融
- 新增 `scripts_flow/paper_ablation_eval.py`
  - 支持 5 个版本并行运行：`full/no_dst_beacon/no_lif_burst/no_stdp/no_min_hold`
  - 输出 `runs/summary/significance/contrib` 四类 CSV
  - 对每个消融版本与 full-SNN 进行配对差值 + 置信区间 + 符号翻转检验
  - 输出贡献度评分（按 `pdr_post` 降幅与 `loss_final` 升幅的相对退化组合）

## 验证命令

```bash
python3 -m py_compile scripts_flow/snn_simulator.py scripts_flow/paper_ablation_eval.py
python3 scripts_flow/paper_ablation_eval.py --topos ba --sizes 30 --seeds 1-2 --steps 80 --fail-step 45 --failure-profiles single --workers 4 --background-scale 1.5 --out-prefix run_dir/issue17_smoke
```

## 结果（完整矩阵）

- 已执行 issue #17 完整矩阵：

```bash
python3 scripts_flow/paper_ablation_eval.py --topos ba,er --sizes 50,100 --seeds 1-20 --failure-profiles single,frequent --background-scale 2.0 --workers 20 --out-prefix run_dir/issue17_ablation
```

- 生成文件：
  - `run_dir/issue17_ablation_runs.csv`
  - `run_dir/issue17_ablation_summary.csv`
  - `run_dir/issue17_ablation_significance.csv`
  - `run_dir/issue17_ablation_contrib.csv`

关键发现：

1. `no_dst_beacon` 退化最明显（主要贡献模块）：
   - 全局 `pdr_post` 差值均值约 `-0.0333`（variant-full）
   - 全局 `route_changes_final` 均值增加约 `+327`
   - `pdr_post` 在 8 个分组中 6 个显著，`delay_post` 在 8 个分组中 7 个显著
2. `no_lif_burst`、`no_stdp` 总体影响较小，多数分组不显著。
3. `no_min_hold` 未显示容量退化主效应，符合其“抗抖动门控”定位。

论文可用结论：

- Full-SNN 的主要收益来自 destination beacon 提供的目的地梯度信号；
- LIF burst 与 STDP 在当前配置下更多是二阶优化项；
- min-hold 主要负责稳定性而非吞吐提升。
