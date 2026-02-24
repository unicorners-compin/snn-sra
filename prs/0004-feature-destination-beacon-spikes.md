# PR Draft: Feature Issue #4 - Destination Beacon Spikes

## Linked Issue

- refs #4

## Why

`snn_spike_native` 在 ER 图上缺少目的地语义，容易出现“有压力感知但缺少目标牵引”的转发。  
本迭代只做一个想法：加入 destination beacon，让目的地信息以脉冲形式扩散并参与选路。

## What Changed

- `SNNSimulator` 新增 destination beacon 平面（可开关）：
  - beacon 状态与衰减传播
  - destination 节点持续注入 beacon
- native 转发评分改为使用“邻居相对当前节点的 beacon 增量”：
  - 只奖励更接近目的地的邻居
  - 采用局部分数尺度归一化，避免 beacon 量纲过弱
- 修复对比脚本参数透传：
  - `compare_snn_vs_ospf.py` 现在会把 `--snn-mode` 正确传给 SNN 分支

## Validation

```bash
python3 scripts_flow/compare_snn_vs_ospf.py --topos er --seeds 11,17,23 --steps 240 --fail-step 150 --snn-mode snn_spike_native --out run_dir/issue4_er_compare.csv --out-agg run_dir/issue4_er_compare_agg.csv
python3 scripts_flow/compare_snn_vs_ospf.py --topos ba --seeds 11,17,23 --steps 240 --fail-step 150 --snn-mode snn_spike_native --out run_dir/issue4_ba_compare.csv --out-agg run_dir/issue4_ba_compare_agg.csv
```

## Results (mean, SNN - OSPF)

- ER:
  - `pdr_final`: `+0.0292`
  - `loss_final`: `-1041.0`
  - `delay_final`: `+1.50`
- BA:
  - `pdr_final`: `+0.1534`
  - `loss_final`: `-3773.3`
  - `delay_final`: `+0.41`

## Interpretation

结果符合当前研究目标：以可接受的小幅 delay 增量，换取更高容量（PDR）和更低丢包（Loss），并改善故障后稳定性（`pdr_post` 提升）。

## Risks

- beacon 权重过大时，可能在局部形成路径汇聚
- ER 拓扑在部分 seed 上仍可能出现时延放大
