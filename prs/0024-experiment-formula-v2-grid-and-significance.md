# PR Draft: Experiment Issue #9 - V2 参数扫描与显著性验证

## 关联 Issue

- refs #9

## Why

Issue #7 已证明 V2 公式可运行，但缺少多种子统计证据。本 PR 增加 v2-v1 配对评估流程，输出论文可用的统计与显著性文件。

## 变更内容

1. 新增 `scripts_flow/formula_v2_eval.py`
   - 对同一组 `topo/size/seed/failure_profile` 同时运行 `formula_mode=v1` 与 `v2`
   - 输出：
     - `*_runs.csv`
     - `*_summary.csv`
     - `*_significance.csv`（v2-v1 差值 + CI + sign-flip p-value）
2. 新增 issue 与 PR 文档：
   - `issues/0025-formula-v2-grid-and-significance.md`
   - `prs/0024-experiment-formula-v2-grid-and-significance.md`

## 验证命令

```bash
python3 -m py_compile scripts_flow/formula_v2_eval.py scripts_flow/main_snn.py scripts_flow/snn_node.py scripts_flow/snn_router.py
python3 scripts_flow/formula_v2_eval.py --topos ba --sizes 25 --seeds 1-2 --steps 80 --fail-step 40 --failure-profiles single --snn-mode snn_event_dv --out-prefix run_dir/issue9_formula_v2_smoke
```

## 备注

- 当前 PR 的目标是建立统计流程，不对“V2 全面优于 V1”做先验结论，最终结论以全矩阵统计为准。
