# Issue #15 - 节点失效与混合失效（节点+链路）抗毁实验（执行记录）

关联 Issue： https://github.com/unicorners-compin/snn-sra/issues/15

## 目标

1. 实现并验证节点失效与混合失效场景下的稳健性测试脚本。
2. 覆盖 `random` 与 `targeted` 两类节点失效。
3. 覆盖 `hybrid_alternating`、`hybrid_simultaneous` 与 `hybrid_flap` 三类混合失效场景。
4. 输出 `*_node_failure_runs.csv`、`*_hybrid_failure_runs.csv`、`*_summary.csv`、`*_significance.csv` 四类 CSV 文件。

## 关键实现文件

- `scripts_flow/node_hybrid_failure_eval.py`。

## 执行命令（Smoke）

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

## 输出结果（路径）

- `run_dir/issue15/node15_smoke_20260224_node_failure_runs.csv`
- `run_dir/issue15/node15_smoke_20260224_hybrid_failure_runs.csv`
- `run_dir/issue15/node15_smoke_20260224_summary.csv`
- `run_dir/issue15/node15_smoke_20260224_significance.csv`

## MinIO 上传结果

1. 存储路径：`snn-sra-exp/issue15/run_20260224_193041_smoke/`
2. 已上传对象为 `node15_smoke_20260224_node_failure_runs.csv`、`node15_smoke_20260224_hybrid_failure_runs.csv`、`node15_smoke_20260224_summary.csv`、`node15_smoke_20260224_significance.csv`。
3. 本地目录已清空并移动到 `/tmp/issue15_backup/issue15` 备份以便追溯。

## 验证结论

1. 脚本可正常运行，无运行时异常。
2. 四类 CSV 均成功落盘，字段包含抗毁指标（`max_drop_pct`、`t50_steps`、`t90_steps`、`auc_recovery`）与统计字段。
3. 混合场景下节点选择模式已按当前随机种子控制并与事件构造一致。

## 后续步骤

1. 进行 Issue 的完整矩阵运行，按 roadmap 计划扩展到 seed、规模与拓扑范围。
2. 按 minio 流程上传结果并清理本地中间文件。
