# PR Draft: Experiment Issue #12 - V2 全矩阵统计主实验（v2 vs v1）

## 关联 Issue

- refs #12

## Why

按路线图执行 V2 主实验，在完整矩阵下验证 `v2` 相对 `v1` 的统计收益，并严格执行 MinIO 归档与本地清理。

## 本 PR 包含

1. `issues/0035-issue12-v2-full-matrix-execution.md`
   - 记录完整执行命令、结果摘要、MinIO 路径、清理状态
2. 前置能力（若主干尚未合入）：
   - `scripts_flow/formula_v2_eval.py`
   - `scripts_flow/minio_uploader.py`
   - 相关公式 V2 开关实现（`snn_node/snn_router/main_snn`）

## 实验命令（已执行）

```bash
python3 scripts_flow/formula_v2_eval.py \
  --topos ba,er \
  --sizes 50,100 \
  --seeds 1-20 \
  --steps 240 \
  --fail-step 150 \
  --failure-profiles single,frequent \
  --snn-mode snn_event_dv \
  --out-prefix run_dir/issue12_formula_v2_full_20260224
```

## 归档与清理（已执行）

```bash
python3 scripts_flow/minio_uploader.py \
  --issue-id 12 \
  --run-tag issue12_formula_v2_full_20260224 \
  --paths run_dir/issue12_formula_v2_full_20260224_runs.csv,run_dir/issue12_formula_v2_full_20260224_summary.csv,run_dir/issue12_formula_v2_full_20260224_significance.csv \
  --config config/minio.txt \
  --bucket snn-sra-exp \
  --cleanup
```

- MinIO: `s3://snn-sra-exp/issue-12/issue12_formula_v2_full_20260224/`
- 本地结果 CSV 已删除（上传校验后清理）

## 结论摘要

- BA 拓扑：`v2` 在 PDR/Loss 上显著优于 `v1`，且在 BA-100 上时延也显著改善。
- ER 拓扑：`v2` 改善幅度较弱，部分指标仅呈趋势不显著，后续需在 issue #13~#17 中继续定位边界与参数稳定区。
