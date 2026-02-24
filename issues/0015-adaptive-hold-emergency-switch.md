# Issue #15: 自适应保持时延 + 紧急切换门控

## 类型

Feature + Focused Experiment

## 背景

固定保持时延可降震荡，但可能牺牲故障恢复速度。需要在“稳态抗抖动”和“故障快速恢复”之间引入自适应门控。

## 单一目标（Only One）

仅实现并验证：

- 稳态时增大 hold time
- 高压力/链路失效时降低 hold time 或触发紧急切换

## 范围

- In scope:
  - 自适应 hold 调度（基于局部压力/丢包信号）
  - 紧急切换触发条件
  - 恢复速度与震荡强度联合评估
- Out of scope:
  - 新基线算法
  - 新奖励函数

## 验收标准

1. 相比 issue #14，故障后恢复速度提升或不下降。
2. 相比无 hold 基线，震荡仍显著降低。
3. 结果记录并与 issue #14 对比。

## 验证命令（预期）

```bash
python3 scripts_flow/paper_stat_eval_parallel.py --algos ospf,ecmp,ppo,snn --topos ba,er --sizes 50,100 --seeds 1-20 --steps 240 --fail-step 150 --failure-profiles single,frequent --background-scale 2.0 --workers 20 --out-prefix run_dir/issue15_adaptive
```
