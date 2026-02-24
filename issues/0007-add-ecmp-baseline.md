# Issue #7: Add ECMP Baseline for SNN Routing Comparison

## Type

Feature + Focused Experiment

## Background

当前论文基础对比主要是 `SNN vs OSPF`。为了增强结论可信度，需要加入工程上常见的多路径基线 `ECMP`（Equal-Cost Multi-Path）。

## Single Idea (Only One)

仅新增 `ECMP` 基线，不修改 SNN 机制：

- 在同一队列模型下实现 hop-count `ECMP`
- 与 `OSPF`、`SNN` 在同配置下对比

## Scope

- In scope:
  - 在对比脚本中新增 `ECMPSimulator`
  - 输出 `ospf/ecmp/snn` 三算法结果
- Out of scope:
  - 新拓扑类型
  - 新指标体系
  - 新路由机制

## Acceptance Criteria

1. 对比脚本支持输出 `ecmp` 结果。
2. 在 ER/BA（seeds=11,17,23）可稳定复现三算法表格。
3. 结果写入 issue 文档并给出初步结论。

## Validation Plan

```bash
python3 scripts_flow/compare_snn_vs_ospf.py --topos ba,er --seeds 11,17,23 --steps 240 --fail-step 150 --snn-mode snn_spike_native --out run_dir/issue7_compare_runs.csv --out-agg run_dir/issue7_compare_agg.csv
```

## Current Findings

### Mean Results (seeds=11,17,23)

- BA:
  - OSPF: `pdr_final=0.6748`, `delay_final=11.3202`, `loss_final=7323`
  - ECMP: `pdr_final=0.7386`, `delay_final=10.2507`, `loss_final=5940`
  - SNN:  `pdr_final=0.8314`, `delay_final=11.5148`, `loss_final=3758`
- ER:
  - OSPF: `pdr_final=0.8138`, `delay_final=9.8514`, `loss_final=4081.3`
  - ECMP: `pdr_final=0.8165`, `delay_final=10.5992`, `loss_final=4033.7`
  - SNN:  `pdr_final=0.8477`, `delay_final=11.2757`, `loss_final=3148.3`

### Delta (SNN - Baseline)

- vs OSPF:
  - BA: `PDR +0.1566`, `Loss -3565.0`, `Delay +0.195`
  - ER: `PDR +0.0339`, `Loss -933.0`, `Delay +1.424`
- vs ECMP:
  - BA: `PDR +0.0928`, `Loss -2182.0`, `Delay +1.264`
  - ER: `PDR +0.0312`, `Loss -885.3`, `Delay +0.676`

## Conclusion

- `ECMP` 是比 `OSPF` 更强的工程基线（尤其 BA 上延迟更优、PDR更高）。
- `SNN` 依然在容量和稳定性指标（PDR/Loss）上优于 `OSPF` 与 `ECMP`。
- trade-off 清晰：`SNN` 的代价是更高时延，这与“以小幅时延换容量/稳定性”的研究目标一致。
