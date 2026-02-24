# Issue #9: Standardize Backpressure Baseline (Per-Destination Queue Differential)

## Type

Feature + Focused Experiment

## Background

Issue #8 中的 backpressure 为简化近似，容易被质疑“基线过弱”。需要提升为更标准的 destination-aware MaxWeight 形式。

## Single Idea (Only One)

只升级 backpressure 基线实现，不改 SNN：

- 使用按目的地的队列差分权重 `Q_i^d - Q_j^d`
- 引入轻量最短路偏置（仅用于打破歧义与减小环路）
- 当无正增益下一跳时允许 hold（不立即丢包）

## Scope

- In scope:
  - 重写 `BackpressureSimulator` 的选路与无路可走处理
  - 在现有对比脚本中复现实验
- Out of scope:
  - 修改 SNN 机制
  - 新拓扑/新指标体系

## Acceptance Criteria

1. backpressure 基线在 ER/BA 上可稳定运行。
2. 与 issue #8 相比，backpressure 的 `PDR` 提升且 `Delay` 下降（至少其一明显改善）。
3. 结果记录进 issue 文档并给出结论。

## Validation Plan

```bash
python3 scripts_flow/compare_snn_vs_ospf.py --algos ospf,ecmp,backpressure,snn --topos ba,er --seeds 11,17,23 --steps 240 --fail-step 150 --snn-mode snn_spike_native --out run_dir/issue9_compare_runs.csv --out-agg run_dir/issue9_compare_agg.csv
```

## Current Findings

### Mean Results (seeds=11,17,23)

- BA:
  - Backpressure(v9): `pdr_final=0.5061`, `delay_final=24.6549`, `loss_final=8027.7`
  - OSPF: `pdr_final=0.6748`, `delay_final=11.3202`, `loss_final=7323`
  - ECMP: `pdr_final=0.7386`, `delay_final=10.2507`, `loss_final=5940`
  - SNN: `pdr_final=0.8314`, `delay_final=11.5148`, `loss_final=3758`
- ER:
  - Backpressure(v9): `pdr_final=0.4619`, `delay_final=29.6916`, `loss_final=4660`
  - OSPF: `pdr_final=0.8138`, `delay_final=9.8514`, `loss_final=4081.3`
  - ECMP: `pdr_final=0.8165`, `delay_final=10.5992`, `loss_final=4033.7`
  - SNN: `pdr_final=0.8477`, `delay_final=11.2757`, `loss_final=3148.3`

### Improvement vs Issue #8 Backpressure

- BA:
  - `pdr_final +0.1142`, `pdr_post +0.0681`
  - `delay_final +4.972`, `delay_post +2.747`
  - `loss_final +1921.0`
- ER:
  - `pdr_final +0.0851`, `pdr_post +0.0498`
  - `delay_final +5.113`, `delay_post +2.209`
  - `loss_final -1196.7`

## Conclusion

- 更标准的“按目的地队列差分 + hold”实现后，backpressure 的吞吐相关指标（PDR）明显提升。
- 但在当前队列抽象下，时延显著升高，且 BA 上总丢包未改善。
- 该基线已较 issue #8 更接近标准 MaxWeight，但在本仿真模型里仍不是最强对手，`SNN` 依旧保持明显优势。
