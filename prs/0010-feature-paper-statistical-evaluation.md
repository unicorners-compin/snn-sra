# PR Draft: Feature Issue #10 - 论文统计版评估流程

## 关联 Issue

- refs #10

## Why

将现有“点状对比结果”升级为论文可用的统计证据：多种子、多规模、多故障模式、置信区间与显著性检验。

## 变更内容

- 新增 `scripts_flow/paper_stat_eval.py`
  - 支持算法矩阵：`ospf,ecmp,backpressure,snn`
  - 支持规模矩阵：`--sizes`（如 `50,100`）
  - 支持故障模式：`single,frequent`
  - 支持 seed 范围写法：`1-20`
  - 输出：
    - run-level：`*_runs.csv`
    - 分组统计：`*_summary.csv`（mean/std/95%CI）
    - 显著性：`*_significance.csv`（SNN-基线差值CI + p-value）

## 验证命令

```bash
python3 -m py_compile scripts_flow/paper_stat_eval.py
python3 scripts_flow/paper_stat_eval.py --algos ospf,ecmp,backpressure,snn --topos ba,er --sizes 50,100 --seeds 1-8 --steps 240 --fail-step 150 --failure-profiles single,frequent --snn-mode snn_spike_native --out-prefix run_dir/issue10_pilot
```

## 首轮结果（seeds=1-8）

- SNN vs OSPF：8/8 场景 `PDR` 提升、`Loss` 下降；`Loss` 在 6/8 场景显著。
- SNN vs ECMP：8/8 场景 `PDR` 提升、`Loss` 下降；`Loss` 在 8/8 场景显著，`PDR` 在 4/8 场景显著（主要为 size=100）。
- 时延方面仍体现 trade-off：部分场景升高，但 ER-100 相对 ECMP 接近持平。

## 备注

- 本 PR 提供统计流程与首轮样本结果；论文主结果建议继续跑 `seeds=1-20` 全量矩阵。
