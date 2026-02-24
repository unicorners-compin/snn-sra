# PR Draft: Issue #17 - V2 参数敏感性与稳定区间实验

## 关联 Issue

- refs #17

## 变更摘要

1. 新增 `scripts_flow/parameter_sensitivity_eval.py`，用于 V2 参数敏感性与稳定区间评估。
2. 实现参数计划构建：支持基线、五个参数单因素扰动（±20%）、三组关键参数二元交叉。
3. 统一导出：
   - `run_prefix_sensitivity_runs.csv`
   - `run_prefix_sensitivity_summary.csv`
   - `run_prefix_sensitivity_significance.csv`
   - `run_prefix_stable_region.csv`
4. 支持与现有结果上传流程兼容（带 `issue-id` 与 MinIO metadata）。

## 关键实现点

1. 故障注入：
   - 支持 `single` 与 `frequent`（脚本内部支持，当前 Smoke 使用 `single`）。
   - 多事件时按介数中心性选择高风险边。
2. 指标集合：
   - `pdr_final` / `loss_final` / `delay_final` / `hop_final`
   - `pdr_post` / `delay_post`
   - `route_changes_final` / `table_updates_final`
3. 统计：
   - 每组输出均值、标准差、95% Bootstrap CI。
   - 与基线配对显著性检验（sign-flip bootstrap）。
   - 稳定区间按主指标阈值分类为 `robust / weakened / failed`。
4. 可复现实验元数据：
   - 所有关键参数以列方式落盘，便于与主实验矩阵对齐。

## 验证（Smoke）

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

### 结果文件

- `run_dir/issue17_smoke_sensitivity_runs.csv`
- `run_dir/issue17_smoke_sensitivity_summary.csv`
- `run_dir/issue17_smoke_sensitivity_significance.csv`
- `run_dir/issue17_smoke_stable_region.csv`

## MinIO 上传记录

- 目标：`snn-sra-exp`
- Prefix：`issue-17/issue17_smoke_20260224/`
- 执行上传命令并清理本地文件（见对应执行文档）

## 关联文档

1. `issues/0039-issue17-sensitivity-execution.md`

