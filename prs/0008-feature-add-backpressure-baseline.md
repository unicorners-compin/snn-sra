# PR Draft: Feature Issue #8 - Add Backpressure Baseline

## Linked Issue

- refs #8

## Why

在 `OSPF/ECMP/SNN` 之外补充吞吐导向基线，增强论文对比覆盖面。

## What Changed

- `scripts_flow/compare_snn_vs_ospf.py`
  - 新增 `BackpressureSimulator`
  - `--algos` 默认扩展为 `ospf,ecmp,backpressure,snn`
  - 新增 `delta snn-backpressure` 输出

## Baseline Definition

- 本实现是 **destination-aware queue-differential** 的包级近似基线：
  - 下一跳权重：`(q_curr - q_neigh) + dist_bias * (d_curr - d_neigh)`
  - 在权重最优邻居中随机选路
- 备注：不是完整的“按 commodity 队列 + 链路调度”的理论 throughput-optimal Backpressure。

## Validation

```bash
python3 -m py_compile scripts_flow/compare_snn_vs_ospf.py
python3 scripts_flow/compare_snn_vs_ospf.py --algos ospf,ecmp,backpressure,snn --topos ba,er --seeds 11,17,23 --steps 240 --fail-step 150 --snn-mode snn_spike_native --out run_dir/issue8_compare_runs.csv --out-agg run_dir/issue8_compare_agg.csv
```

## Results (mean)

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

## Interpretation

- 在当前实验抽象下，近似 backpressure 基线显著弱于 `OSPF/ECMP/SNN`。
- `SNN` 继续保持容量/稳定性优势。
