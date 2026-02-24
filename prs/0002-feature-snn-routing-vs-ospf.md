# PR Draft: Feature Issue #2 - SNN Routing vs OSPF Gap Closure (Phase 1+2)

## Linked Issue

- refs #2

## Why

建立严格可追溯研发流程，并完成 SNN 路由前两阶段实现（含事件驱动控制面）与可视化基线，为后续“打赢 OSPF”优化提供可复现实验基础。

## What Changed

- 建立 Git Flow + Issue/PR 模板体系
- 新增纯 SNN 本地路由核心实现（节点、路由器、仿真器、主入口）
- 新增事件驱动控制面（高压力高频广播）+ 路由切换滞回 + 路由老化
- 拓扑扩展：支持 `BA/ER/grid`，默认 `BA`
- 新增前端页面展示路径演化、节点热力与故障事件
- 新增可复现评估脚本：`scripts_flow/compare_snn_vs_ospf.py`
- 修复 `scripts_flow/main.py` 的构造参数错误
- 忽略本地运行产物，避免污染 PR

## Validation

```bash
SNN_TOPOLOGY=ba python3 scripts_flow/main_snn.py
SNN_TOPOLOGY=er python3 scripts_flow/main_snn.py
python3 scripts_flow/compare_snn_vs_ospf.py --topos ba,er --seeds 11,17,23
python3 -m http.server 8010
```

输出文件：

- `run_dir/snn_metrics.csv`
- `run_dir/snn_ablation_summary.csv`
- `run_dir/snn_route_viz.json`
- `run_dir/ospf_compare_runs.csv`
- `run_dir/ospf_compare_agg.csv`

## Risks

- ER 拓扑上 SNN 仍落后 OSPF（时延/丢包）
- 广播参数在高随机拓扑上可能过激，导致路径振荡

## Next PR Scope

- 针对 ER 的参数自适应（广播周期与滞回强度）
- 恢复时间与控制开销联合优化
- 拓扑感知策略（避免单一参数跨拓扑退化）
