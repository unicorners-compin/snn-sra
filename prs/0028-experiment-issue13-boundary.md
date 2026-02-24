# PR Draft: Experiment Issue #13 - 定向攻击与 k-failure 抗毁边界

## 关联 Issue

- refs #13

## Why

补齐“抗毁性”核心证据：在随机故障、链路定向攻击、节点定向攻击下，比较 v2 与基线并给出边界判定。

## 变更内容

1. 新增 `scripts_flow/resilience_boundary_eval.py`
  - 支持攻击模式：`random_edge,target_edge,target_node`
  - 支持 `k` 递增扫描
  - 支持并行执行（`--workers`）
  - 对比：`v2` vs `v1/ospf_sync/ecmp/ppo`
  - 输出：`runs/summary/significance/boundary`
2. 新增执行记录：
   - `issues/0036-issue13-boundary-execution.md`

## 归档与清理

- 使用 `scripts_flow/minio_uploader.py` 上传到：
  - `s3://snn-sra-exp/issue-13/issue13_boundary_phase1_20260224/`
- 上传校验后清理本地结果文件

## 本次执行范围

- Phase 1（seeds=1-5）已完成并归档
- seeds=6-10 将在后续补跑并合并到同 issue 讨论
