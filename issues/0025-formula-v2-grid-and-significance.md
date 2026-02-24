# Issue #9 - V2 公式参数扫描与显著性验证（v2 vs v1）

GitHub Issue: https://github.com/unicorners-compin/snn-sra/issues/9

## 背景

Issue #7 已完成 V2 公式开关与最小 A/B 跑通，但当前证据仅是单配置 smoke。为了支撑论文论证，需要系统化比较 `v2` 与 `v1` 在多种子/多拓扑下的统计差异。

## 目标

新增一套评估流程，输出：

1. run-level 明细（每个 seed、topo、size、mode）
2. 分组统计（mean/std/95% CI）
3. 配对显著性（v2-v1 差值、CI、sign-flip p-value）

## 范围

- 评估对象：SNN（`beta_s=8`）在 `formula_mode=v1` 与 `formula_mode=v2`
- 指标：`pdr_final`, `loss_final`, `delay_final`, `hop_final`, `pdr_post`, `delay_post`
- 脚本放在 `scripts_flow/`

## 验收标准

- 可通过 CLI 指定 seeds/topos/sizes/steps/fail-step
- 输出 `*_runs.csv`, `*_summary.csv`, `*_significance.csv`
- 在小规模 smoke 参数下可稳定运行

## 输出物

- `scripts_flow/formula_v2_eval.py`
- `prs/0024-experiment-formula-v2-grid-and-significance.md`
