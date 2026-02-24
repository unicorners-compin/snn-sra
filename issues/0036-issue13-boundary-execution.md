# Issue #13 - 定向攻击与 k-failure 抗毁边界实验执行记录

GitHub Issue: https://github.com/unicorners-compin/snn-sra/issues/13

## 目标

完成 `random_edge / target_edge / target_node` 三类攻击与 `k` 递增边界评估，输出 `runs/summary/significance/boundary`。

## 执行命令

```bash
python3 scripts_flow/resilience_boundary_eval.py \
  --algos v1,v2,ospf_sync,ecmp,ppo \
  --topos ba,er \
  --sizes 50,100 \
  --seeds 1-10 \
  --attack-modes random_edge,target_edge,target_node \
  --k-values 1-4 \
  --steps 160 \
  --fail-step 80 \
  --snn-mode snn_event_dv \
  --out-prefix run_dir/issue13_boundary_20260224
```

## MinIO 归档

- issue-id: `13`
- run-tag: `issue13_boundary_20260224`
- 上传后执行清理（`--cleanup`）

## 本次执行（Phase 1，2026-02-24）

为控制单次执行时长，先完成 seeds `1-5` 的 phase1 全覆盖：

```bash
python3 scripts_flow/resilience_boundary_eval.py \
  --algos v1,v2,ospf_sync,ecmp,ppo \
  --topos ba,er \
  --sizes 50,100 \
  --seeds 1-5 \
  --attack-modes random_edge,target_edge,target_node \
  --k-values 1-4 \
  --steps 160 \
  --fail-step 80 \
  --snn-mode snn_event_dv \
  --workers 20 \
  --out-prefix run_dir/issue13_boundary_phase1_20260224
```

输出：

- `run_dir/issue13_boundary_phase1_20260224_runs.csv`
- `run_dir/issue13_boundary_phase1_20260224_summary.csv`
- `run_dir/issue13_boundary_phase1_20260224_significance.csv`
- `run_dir/issue13_boundary_phase1_20260224_boundary.csv`

### MinIO（已归档）

- `s3://snn-sra-exp/issue-13/issue13_boundary_phase1_20260224/`
- 已上传对象：4个结果文件 + `metadata.json`

### 本地清理（已完成）

- 上述 4 个结果文件已在上传校验后删除
