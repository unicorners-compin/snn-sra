# Issue #12 - V2 全矩阵统计主实验执行记录

GitHub Issue: https://github.com/unicorners-compin/snn-sra/issues/12

## 目标

执行 `v2 vs v1` 全矩阵对照，输出统计结论并完成 MinIO 归档与本地清理。

## 计划命令

```bash
python3 scripts_flow/formula_v2_eval.py \
  --topos ba,er \
  --sizes 50,100 \
  --seeds 1-20 \
  --steps 240 \
  --fail-step 150 \
  --failure-profiles single,frequent \
  --snn-mode snn_event_dv \
  --out-prefix run_dir/issue12_formula_v2_full
```

## 归档与清理

使用 `scripts_flow/minio_uploader.py`：

- issue-id: `12`
- run-tag: `issue12_formula_v2_full_<timestamp>`
- paths: `run_dir/issue12_formula_v2_full_*.csv`
- 上传成功后 `--cleanup`

## 本次执行结果（2026-02-24）

- 已完成全矩阵：`topos=ba,er` × `sizes=50,100` × `seeds=1-20` × `profiles=single,frequent` × `modes=v1,v2`（共 320 runs）
- 结果文件：
  - `run_dir/issue12_formula_v2_full_20260224_runs.csv`
  - `run_dir/issue12_formula_v2_full_20260224_summary.csv`
  - `run_dir/issue12_formula_v2_full_20260224_significance.csv`

### 主要结论（简要）

1. 在 BA 拓扑（50/100）下，`v2` 相比 `v1` 的 `pdr_final` 和 `pdr_post` 均为显著提升，`loss_final` 显著下降。
2. 在 BA-100 下，`v2` 对 `delay_final/post` 反而显著下降（改善了时延代价）。
3. 在 ER 拓扑下，`v2` 优势较弱，部分分组仅呈正向趋势但未全部显著，说明拓扑依赖性仍存在。

### MinIO 归档

- Bucket: `snn-sra-exp`
- Prefix: `issue-12/issue12_formula_v2_full_20260224/`
- 对象：
  - `issue12_formula_v2_full_20260224_runs.csv`
  - `issue12_formula_v2_full_20260224_summary.csv`
  - `issue12_formula_v2_full_20260224_significance.csv`
  - `metadata.json`

### 本地清理

- 上述 3 个结果 CSV 已在上传校验后删除（保留 MinIO 版本）。
