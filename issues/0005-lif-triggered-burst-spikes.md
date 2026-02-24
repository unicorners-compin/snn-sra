# Issue #5: LIF-Triggered Burst Spikes (No Manual Frequency Compression)

## Type

Feature + Focused Experiment

## Background

当前 `snn_spike_native` 的 burst 平面仍含手工阈值/比例参数（`burst_low/high_threshold`, `burst_scale`），这不符合我们要验证的 SNN 核心机制。

## Single Idea (Only One)

将 burst 广播触发改为 **LIF 事件触发**：

- 节点广播仅在其 LIF 神经元跨阈值放电时触发（`last_spike == 1`）
- 放电后复位由节点 LIF 模型本身完成（已存在）
- 不再由手工阈值和比例规则决定广播频率

## Scope

- In scope:
  - `SNNSimulator._update_burst_plane` 改为读取节点 spike 事件
  - 保持其余机制不变（destination beacon, STDP, 路由评分逻辑）
- Out of scope:
  - 新增神经元模型
  - 多参数联合调优

## Acceptance Criteria

1. burst 广播频率由节点 spike 事件自然决定。
2. ER/BA 对比中，`PDR` 与 `Loss` 不显著劣化（相对 issue #4 基线）。
3. delay 允许小幅波动。

## Validation Plan

```bash
python3 scripts_flow/compare_snn_vs_ospf.py --topos er --seeds 11,17,23 --steps 240 --fail-step 150 --snn-mode snn_spike_native --out run_dir/issue5_er_compare.csv --out-agg run_dir/issue5_er_compare_agg.csv
python3 scripts_flow/compare_snn_vs_ospf.py --topos ba --seeds 11,17,23 --steps 240 --fail-step 150 --snn-mode snn_spike_native --out run_dir/issue5_ba_compare.csv --out-agg run_dir/issue5_ba_compare_agg.csv
```

## Current Findings

- vs OSPF（issue #5 版本，seeds=11/17/23）：
  - ER: `pdr_final +0.0339`, `loss_final -933.0`, `delay_final +1.424`
  - BA: `pdr_final +0.1566`, `loss_final -3565.0`, `delay_final +0.195`
- vs issue #4 基线（仅替换为 LIF 触发 burst）：
  - ER: `pdr_final +0.0047`, `delay_final -0.076`, `loss_final +108.0`
  - BA: `pdr_final +0.0032`, `delay_final -0.215`, `loss_final +208.3`

结论：广播频率由 LIF 事件自然产生后，核心容量优势保持，且时延略有改善；Loss 在 issue #4 基线之上有小幅回升，但整体仍显著优于 OSPF。
