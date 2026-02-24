# Issue #17 - V2 参数敏感性与稳定区间实验（执行记录）

关联 Issue： https://github.com/unicorners-compin/snn-sra/issues/17

## 目标

1. 验证参数配置在合理扰动范围下的敏感性与稳定性，给出参数级稳健性结论。
2. 覆盖参数：`stress_smooth_gain`、`stress_smooth_center`、`softmin_temperature`、`switch_hysteresis`、`route_ttl` 的单因素和关键二元组交叉。
3. 生成完整的四类 CSV：`*_sensitivity_runs.csv`、`*_sensitivity_summary.csv`、`*_sensitivity_significance.csv`、`*_stable_region.csv`。

## 本次执行

```bash
python3 scripts_flow/parameter_sensitivity_eval.py \
  --topos ba \
  --sizes 30 \
  --seeds 1 \
  --steps 60 \
  --fail-step 30 \
  --failure-profiles single \
  --pairwise stress_smooth_gain,stress_smooth_center,softmin_temperature \
  --base-mult 0.2 \
  --out-prefix run_dir/issue17_smoke \
  --issue-id 17
```

### 运行结果

- 总 case 数：`23`
- 运行路径：
  - `run_dir/issue17_smoke_sensitivity_runs.csv`
  - `run_dir/issue17_smoke_sensitivity_summary.csv`
  - `run_dir/issue17_smoke_sensitivity_significance.csv`
  - `run_dir/issue17_smoke_stable_region.csv`

### MinIO 上报

- bucket：`snn-sra-exp`
- prefix：`issue-17/issue17_smoke_20260224/`
- 命令：

```bash
python3 scripts_flow/minio_uploader.py \
  --issue-id 17 \
  --run-tag issue17_smoke_20260224 \
  --paths run_dir/issue17_smoke_sensitivity_runs.csv,run_dir/issue17_smoke_sensitivity_summary.csv,run_dir/issue17_smoke_sensitivity_significance.csv,run_dir/issue17_smoke_stable_region.csv \
  --bucket snn-sra-exp \
  --config config/minio.txt \
  --command "python3 scripts_flow/parameter_sensitivity_eval.py --topos ba --sizes 30 --seeds 1 --steps 60 --fail-step 30 --failure-profiles single --out-prefix run_dir/issue17_smoke --issue-id 17" \
  --cleanup
```

### 归档结果

- 上传成功 5 个对象（含 metadata.json）
- 本地文件已清理删除

## 验证结论（Smoke）

1. 脚本可正常运行，参数计划生成功能正常。
2. 输出 4 类文件格式完整，关键字段（`pdr_final`、`loss_final`、`delay_final`、`route_changes_final`、`table_updates_final`）均可计算。
3. 稳健性判定表已生成，支持后续扩展至完整矩阵实验。

