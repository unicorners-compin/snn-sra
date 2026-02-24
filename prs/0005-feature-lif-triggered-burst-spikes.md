# PR Draft: Feature Issue #5 - LIF-Triggered Burst Spikes

## Linked Issue

- refs #5

## Why

为保证仿真机制贴近 SNN 本体，广播频率不应由手工阈值压缩决定，而应来自神经元泄露积分-跨阈值放电-复位这一事件过程。

## What Changed

- `scripts_flow/snn_simulator.py`
  - `SNNSimulator._update_burst_plane` 改为仅在 `node.last_spike == 1` 时发射 1 个 burst pulse
  - 移除了原先基于 `burst_low/high_threshold` 与 `burst_scale` 的手工脉冲触发逻辑
  - 保留 burst 衰减与邻居接收视图，不改动 destination beacon/STDP/转发评分

## Validation

```bash
python3 -m py_compile scripts_flow/snn_simulator.py
python3 scripts_flow/compare_snn_vs_ospf.py --topos er --seeds 11,17,23 --steps 240 --fail-step 150 --snn-mode snn_spike_native --out run_dir/issue5_er_compare.csv --out-agg run_dir/issue5_er_compare_agg.csv
python3 scripts_flow/compare_snn_vs_ospf.py --topos ba --seeds 11,17,23 --steps 240 --fail-step 150 --snn-mode snn_spike_native --out run_dir/issue5_ba_compare.csv --out-agg run_dir/issue5_ba_compare_agg.csv
```

## Results

- vs OSPF（mean, SNN - OSPF）
  - ER: `pdr_final +0.0339`, `loss_final -933.0`, `delay_final +1.424`
  - BA: `pdr_final +0.1566`, `loss_final -3565.0`, `delay_final +0.195`
- vs Issue #4 baseline（mean, issue5 - issue4, SNN only）
  - ER: `pdr_final +0.0047`, `delay_final -0.076`, `loss_final +108.0`
  - BA: `pdr_final +0.0032`, `delay_final -0.215`, `loss_final +208.3`

## Interpretation

该改动实现了“频率由 LIF 放电自然产生”的机制一致性目标。容量优势保持且 delay 略降；loss 相比 issue #4 有小幅回升，但整体仍明显优于 OSPF。
