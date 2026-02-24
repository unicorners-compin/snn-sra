# Issue #8: Add Backpressure Baseline for SNN Routing Comparison

## Type

Feature + Focused Experiment

## Background

已有 `OSPF/ECMP/SNN` 对比，为进一步提升论文说服力，需要加入经典吞吐导向基线 `Backpressure (MaxWeight)`。

## Single Idea (Only One)

仅新增 `Backpressure` 基线，不修改 SNN 机制：

- 在同一队列模型下实现 destination-aware 的 MaxWeight 选路
- 与 `OSPF/ECMP/SNN` 在同配置下对比

## Scope

- In scope:
  - 在对比脚本中新增 `BackpressureSimulator`
  - 输出 `ospf/ecmp/backpressure/snn` 四算法结果
- Out of scope:
  - 新拓扑类型
  - 新指标体系
  - SNN算法改动

## Acceptance Criteria

1. 对比脚本支持输出 `backpressure` 结果。
2. 在 ER/BA（seeds=11,17,23）可稳定复现四算法表格。
3. 结果写入 issue 文档并给出初步结论。

## Validation Plan

```bash
python3 scripts_flow/compare_snn_vs_ospf.py --algos ospf,ecmp,backpressure,snn --topos ba,er --seeds 11,17,23 --steps 240 --fail-step 150 --snn-mode snn_spike_native --out run_dir/issue8_compare_runs.csv --out-agg run_dir/issue8_compare_agg.csv
```

## Current Findings

### Mean Results (seeds=11,17,23)

- BA:
  - OSPF: `pdr_final=0.6748`, `delay_final=11.3202`, `loss_final=7323`
  - ECMP: `pdr_final=0.7386`, `delay_final=10.2507`, `loss_final=5940`
  - Backpressure: `pdr_final=0.3919`, `delay_final=19.6829`, `loss_final=6106.7`
  - SNN: `pdr_final=0.8314`, `delay_final=11.5148`, `loss_final=3758`
- ER:
  - OSPF: `pdr_final=0.8138`, `delay_final=9.8514`, `loss_final=4081.3`
  - ECMP: `pdr_final=0.8165`, `delay_final=10.5992`, `loss_final=4033.7`
  - Backpressure: `pdr_final=0.3768`, `delay_final=24.5782`, `loss_final=5856.7`
  - SNN: `pdr_final=0.8477`, `delay_final=11.2757`, `loss_final=3148.3`

### Delta (SNN - Backpressure)

- BA: `PDR +0.4395`, `Loss -2348.7`, `Delay -8.168`
- ER: `PDR +0.4709`, `Loss -2708.3`, `Delay -13.302`

## Conclusion

- 本轮加入的是“destination-aware queue-differential”包级 backpressure 近似基线。
- 在当前队列转发模型下，该近似基线明显弱于 `OSPF/ECMP/SNN`。
- `SNN` 相对其在 `PDR/Loss/Delay` 三项都更优。
