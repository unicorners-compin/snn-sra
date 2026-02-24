# PR Draft: Feature Issue #7 - Add ECMP Baseline

## Linked Issue

- refs #7

## Why

为增强论文对比说服力，新增常见工程基线 `ECMP`（Equal-Cost Multi-Path），与 `OSPF`、`SNN` 在同一队列模型下统一评估。

## What Changed

- `scripts_flow/compare_snn_vs_ospf.py`
  - 新增 `ECMPSimulator`
  - 新增参数 `--algos`（默认 `ospf,ecmp,snn`）
  - 输出新增 `delta snn-ecmp`
  - 保持 `snn_mode` 透传

## Validation

```bash
python3 -m py_compile scripts_flow/compare_snn_vs_ospf.py
python3 scripts_flow/compare_snn_vs_ospf.py --topos ba,er --seeds 11,17,23 --steps 240 --fail-step 150 --snn-mode snn_spike_native --out run_dir/issue7_compare_runs.csv --out-agg run_dir/issue7_compare_agg.csv
```

## Results (mean)

- BA:
  - OSPF: `pdr_final=0.6748`, `delay_final=11.3202`, `loss_final=7323`
  - ECMP: `pdr_final=0.7386`, `delay_final=10.2507`, `loss_final=5940`
  - SNN:  `pdr_final=0.8314`, `delay_final=11.5148`, `loss_final=3758`
- ER:
  - OSPF: `pdr_final=0.8138`, `delay_final=9.8514`, `loss_final=4081.3`
  - ECMP: `pdr_final=0.8165`, `delay_final=10.5992`, `loss_final=4033.7`
  - SNN:  `pdr_final=0.8477`, `delay_final=11.2757`, `loss_final=3148.3`

## Interpretation

- `ECMP` 相比 `OSPF` 是更强基线。
- `SNN` 在容量/稳定性上仍领先两者（更高 PDR、更低 Loss），但时延更高。
