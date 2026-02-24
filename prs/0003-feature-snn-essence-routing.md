# PR Draft: Feature Issue #3 - SNN Essence Routing

## Linked Issue

- refs #3

## Why

将现有 `snn_event_dv` 从“事件触发 DV”进一步演进为更接近 SNN 原生机制的路由：

- burst 脉冲广播
- temporal-STDP
- 无路由表的脉冲解码转发

## What Changed

- `snn_spike_native` 路由模式（`SNNSimulator`）
- burst 广播平面与邻居脉冲视图
- temporal-STDP 链路可塑性（按脉冲时序）
- 基准脚本支持 `--snn-mode`

## Validation

```bash
SNN_TOPOLOGY=ba SNN_ROUTING_MODE=snn_spike_native python3 scripts_flow/main_snn.py
SNN_TOPOLOGY=er SNN_ROUTING_MODE=snn_spike_native python3 scripts_flow/main_snn.py
python3 scripts_flow/compare_snn_vs_ospf.py --topos ba,er --seeds 11,17,23 --snn-mode snn_spike_native
```

## Current Findings

- BA：SNN 相比 OSPF 在 PDR/Loss 上有优势，时延接近。
- ER：SNN 仍落后 OSPF（PDR/Delay/Loss 均不占优）。
- ER 定向稳定化尝试（更强滞回、更低 burst）在 seeds=11/17/23 上未见改观，已记录为负结果。

## Risks

- ER 稀疏随机图上的路由振荡
- burst 编码阈值在不同拓扑下的泛化性不足

## Next Iteration

- Topology-aware 参数自适应（ER/BA 不同广播与滞回策略）
- 目的地导向脉冲编码（降低无效扩散）
- 恢复时间与控制开销联合优化
