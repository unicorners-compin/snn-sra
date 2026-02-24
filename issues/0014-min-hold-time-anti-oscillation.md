# Issue #14: 最小稳定保持时延（Minimum Hold Time）抑制路由震荡

## 类型

Feature + Focused Experiment

## 背景

SNN 路由在动态场景下可能出现下一跳频繁切换，导致额外时延与抖动。当前已有 `switch_hysteresis` 与 `native_min_switch_interval`，但缺少“稳定保持时延”作为显式机制目标和系统评估。

## 单一目标（Only One）

在不改 SNN 核心机制（LIF/beacon/STDP）的前提下，仅加强“最小保持时延”策略，抑制不必要切换。

## 范围

- In scope:
  - 增强 `(node,dst)` 级的最小保持时延逻辑
  - 增加故障例外条件（不可达/连续恶化可提前切换）
  - 输出震荡指标（route change rate）与性能指标（PDR/Delay/Loss）
- Out of scope:
  - BC 输入替换
  - 新学习规则
  - 新拓扑类型

## 验收标准

1. 震荡指标显著下降（相对当前主线）。
2. `PDR/Loss` 不显著退化。
3. 结果写入 issue 与 PR 草案。

## 验证命令（预期）

```bash
python3 scripts_flow/compare_snn_vs_ospf.py --algos snn --topos ba,er --seeds 11,17,23 --steps 240 --fail-step 150 --snn-mode snn_spike_native --out run_dir/issue14_runs.csv --out-agg run_dir/issue14_agg.csv
```

## 当前结果（快速对照，seeds=11/17/23）

对照方式：仅比较 `hold_off` 与 `hold_on`（其余机制不变，`snn_spike_native`）。

- BA（hold_on - hold_off，均值）：
  - `route_changes_final: -4.00`
  - `delay_final: -0.110`
  - `pdr_final: -0.00649`
  - `loss_final: +111.0`
- ER（hold_on - hold_off，均值）：
  - `route_changes_final: -2.67`
  - `delay_final: -0.180`
  - `pdr_final: +0.00078`
  - `loss_final: -41.67`

## 初步结论

1. 最小保持时延确实降低了路由震荡（route changes 下降）。
2. ER 上收益更稳（PDR 微升、Loss 微降、Delay 降低）。
3. BA 上出现轻微容量代价（PDR/Loss 小幅变差），后续需在 issue #15 做自适应 hold 与紧急切换权衡。
