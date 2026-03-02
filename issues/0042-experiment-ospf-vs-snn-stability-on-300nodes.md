# [Experiment] 300节点卫空海场景下 OSPF vs SNN-SRA 稳定性对比

## Hypothesis

在高动态拓扑下，SNN-SRA 在“控制面稳定性”指标（路由切换频率、恢复尾延迟、控制更新开销）上优于 OSPF 同步重算基线。

## Baseline

- OSPF Sync Baseline（含 sync_period / spf_delay 参数）
- 可选：ECMP / backpressure 基线

## Variables

- Topology:
  - 300节点时变卫空海拓扑
- Traffic pattern:
  - 持续均匀流 + 突发流叠加
- Failure pattern:
  - 链路瞬断、节点短时失效、混合扰动
- Model params:
  - SNN 参数主配置 + 小范围灵敏度扫描

## Metrics

- PDR / Avg Delay / Packet Loss / Avg Hop
- P95 / P99 delay
- Route-change rate
- Broadcast / table-update count (控制开销)
- Recovery T50 / T90 / AUC

## Success Criteria

1. 至少 10 个随机种子下完成统计比较（均值+方差+显著性检验）。
2. 输出科研可引用图表：稳定性-负载曲线、恢复动力学曲线。
3. 给出“何种条件下 SNN-SRA 优于 OSPF”的边界说明。

## Repro Command

```bash
# placeholder: to be filled after dataset + adapter ready
python scripts_flow/compare_snn_vs_ospf.py --nodes 300 --topo-kind dynamic --seeds 10
```
