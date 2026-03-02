# [Experiment] 300节点动态拓扑适配：dynamic-topo -> SNN-SRA 输入平面

## Hypothesis

将动态拓扑（时变邻接 + 链路属性）标准化接入 SNN-SRA 后，能够在统一数据源下公平比较 OSPF 与 SNN-SRA 稳定性，避免“拓扑源不一致”导致的结论偏差。

## Baseline

- Baseline A: OSPF 基线（现有仿真输出指标）
- Baseline B: 当前 SNN-SRA 抽象图（BA/ER/Grid）

## Variables

- Topology:
  - 输入A：静态 BA/ER 图
  - 输入B：dynamic-topo 导出的 300 节点时变邻接
- Traffic pattern:
  - 轻载/中载/突发三档
- Failure pattern:
  - 无故障 / 单链路故障 / 多链路扰动
- Model params:
  - SNN 应力与路由参数固定主配置，单变量扫描

## Metrics

- PDR
- Avg Delay
- Packet Loss
- Avg Hop
- Recovery time
- Route-change rate (per step)
- Control update count

## Success Criteria

1. 适配后实验可在相同输入上重复运行（固定 seed）。
2. 产生可比结果文件（CSV/JSON）并完整记录配置。
3. 明确指出抽象拓扑与真实动态拓扑下结论差异。

## Repro Command

```bash
# placeholder: to be filled after adapter implementation
python scripts_flow/main_snn.py --topo-kind dynamic --nodes 300 --seed 7
```
