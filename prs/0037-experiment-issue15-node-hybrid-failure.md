# PR Draft: Issue #15 - 节点失效与混合失效（节点+链路）抗毁实验

## 关联 Issue

- refs #15

## 变更摘要

1. 新增 `scripts_flow/node_hybrid_failure_eval.py`。
2. 覆盖节点/混合失效场景的抗毁仿真评估，统一输出 4 个结果文件。
3. 兼容算法集合：`v1`、`v2`、`ospf_sync`、`ecmp`、`ppo`（本次 smoke 中使用 `v1,v2,ospf_sync`）。

## 核心实现点

1. 故障事件建模
2. 支持 `random` 与 `targeted` 节点失效。
3. 支持 `hybrid_alternating`、`hybrid_simultaneous`、`hybrid_flap`。
4. 混合场景在每次构造时按 `rng` 选取随机/定向节点模式。
5. 指标计算覆盖基线 PDR、峰值掉线率、`t50`、`t90`、`auc_recovery`。
6. 输出 run / summary / significance 三层文件，含均值、标准差、95% CI 与配对显著性检验。
7. 复用现有仿真器与拓扑/流量接口，兼容主实验框架。

## 验证

```bash
python3 scripts_flow/node_hybrid_failure_eval.py \
  --algos v1,v2,ospf_sync \
  --topos ba \
  --sizes 30 \
  --seeds 1 \
  --steps 80 \
  --fail-step 40 \
  --failure-profiles single \
  --node-k-values 1 \
  --hybrid-k-values 1 \
  --out-prefix run_dir/issue15/node15_smoke_20260224
```

输出：
- `run_dir/issue15/node15_smoke_20260224_node_failure_runs.csv`
- `run_dir/issue15/node15_smoke_20260224_hybrid_failure_runs.csv`
- `run_dir/issue15/node15_smoke_20260224_summary.csv`
- `run_dir/issue15/node15_smoke_20260224_significance.csv`

## 关联文档

1. `issues/0037-issue15-execution.md`
