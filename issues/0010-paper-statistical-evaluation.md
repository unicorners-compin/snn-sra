# Issue #10: 论文统计版实验评估（多种子/多规模/多故障）

## 类型

Feature + Experiment

## 背景

目前已有 OSPF/ECMP/Backpressure/SNN 对比结果，但要达到论文发表强度，还需要更完整统计证据：

- 更多随机种子（20+）
- 多节点规模（如 50/100/200）
- 多故障模式（单次故障/高频故障）
- 置信区间与显著性检验

## 单一目标（Only One）

仅新增“统计评估流程与脚本”，不改任何路由算法。

## 范围

- In scope:
  - 新增统计评估脚本，批量运行四算法（ospf/ecmp/backpressure/snn）
  - 输出 run-level 结果、分组汇总、显著性结果
  - 输出论文可用的摘要表
- Out of scope:
  - SNN 算法改动
  - 新拓扑类型
  - 新前端功能

## 验收标准

1. 可通过单命令完成批量评估并输出 csv。
2. 汇总包含均值、标准差、95%置信区间。
3. 给出 SNN 对各基线的显著性结果（至少 p-value + 差值CI）。

## 计划命令

```bash
python3 scripts_flow/paper_stat_eval.py --algos ospf,ecmp,backpressure,snn --topos ba,er --sizes 50,100 --seeds 1-20 --steps 240 --fail-step 150 --failure-profiles single,frequent --snn-mode snn_spike_native --out-prefix run_dir/issue10
```

## 当前进展（首轮样本）

已完成首轮统计样本运行（`seeds=1-8`）：

```bash
python3 scripts_flow/paper_stat_eval.py --algos ospf,ecmp,backpressure,snn --topos ba,er --sizes 50,100 --seeds 1-8 --steps 240 --fail-step 150 --failure-profiles single,frequent --snn-mode snn_spike_native --out-prefix run_dir/issue10_pilot
```

输出文件：

- `run_dir/issue10_pilot_runs.csv`
- `run_dir/issue10_pilot_summary.csv`
- `run_dir/issue10_pilot_significance.csv`

## 首轮关键结论（seeds=1-8）

1. SNN 相对 OSPF：
   - 在全部 8 个场景（2拓扑 x 2规模 x 2故障）中，`PDR` 全部提升、`Loss` 全部下降。
   - `Loss` 改善在 6/8 场景达到统计显著（双侧随机符号检验，`p<0.05`）。
2. SNN 相对 ECMP：
   - 同样在 8/8 场景中 `PDR` 提升、`Loss` 下降。
   - `Loss` 改善在 8/8 场景显著；`PDR` 改善在 4/8 场景显著（主要集中在 `size=100`）。
3. Delay trade-off 依然存在：
   - 相对 OSPF/ECMP，SNN 在 ER-50 等场景有显著时延上升；
   - 在 ER-100 场景，SNN 与 ECMP 的时延差不显著（接近持平）。

## 代表性数值（均值）

- BA-100-single：`SNN vs ECMP`
  - `PDR: 0.8621 vs 0.7236`（+0.1385, p=0.0117）
  - `Loss: 3012 vs 6244`（-3232, p=0.0117）
  - `Delay: 10.22 vs 9.96`（+0.25, 不显著）
- ER-100-frequent：`SNN vs ECMP`
  - `PDR: 0.8613 vs 0.8199`（+0.0414, p=0.0195）
  - `Loss: 2964 vs 4005`（-1041, p=0.0117）
  - `Delay: 9.52 vs 9.54`（-0.018, 不显著）

## 下一步

- 按原计划将 seeds 扩展到 `1-20`，得到论文主结果版本。
