# PR Draft: Feature Issue #9 - Standardize Backpressure Baseline

## Linked Issue

- refs #9

## Why

Issue #8 的 backpressure 过于简化。为提高论文对比可信度，本次将其升级为更标准的 destination-aware 队列差分实现。

## What Changed

- `scripts_flow/compare_snn_vs_ospf.py`
  - 重写 `BackpressureSimulator`：
    - 按目的地统计队列长度 `Q_i^d`
    - 选路权重：`(Q_i^d - Q_j^d) + dist_bias * (d_i - d_j)`
    - 无正增益时执行 hold（重新入队），不立即丢包
  - 保持其余基线与 SNN 逻辑不变

## Validation

```bash
python3 -m py_compile scripts_flow/compare_snn_vs_ospf.py
python3 scripts_flow/compare_snn_vs_ospf.py --algos ospf,ecmp,backpressure,snn --topos ba,er --seeds 11,17,23 --steps 240 --fail-step 150 --snn-mode snn_spike_native --out run_dir/issue9_compare_runs.csv --out-agg run_dir/issue9_compare_agg.csv
```

## Results

- Backpressure(v9) mean:
  - BA: `pdr_final=0.5061`, `delay_final=24.6549`, `loss_final=8027.7`
  - ER: `pdr_final=0.4619`, `delay_final=29.6916`, `loss_final=4660`
- vs Backpressure(v8):
  - BA: `pdr_final +0.1142`, `delay_final +4.972`, `loss_final +1921.0`
  - ER: `pdr_final +0.0851`, `delay_final +5.113`, `loss_final -1196.7`

## Interpretation

- 基线强度较 issue #8 明显提升（PDR上升）。
- 代价是时延上升，在 BA 上 loss 也变差。
- 在当前仿真抽象下，`SNN` 依然显著优于该 backpressure 基线。
