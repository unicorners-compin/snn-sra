# Issue #12: 论文主版本全量统计评估（含 PPO）

## 类型

Experiment + Statistical Validation

## 背景

Issue #10 完成了统计流程与首轮样本（seeds=1-8），Issue #11 新增了学习型基线 PPO。

为形成论文主结果，需要运行全量矩阵并产出可直接引用的统计结论：

- 算法：`ospf,ecmp,backpressure,ppo,snn`
- 拓扑：`ba,er`
- 规模：`50,100`
- 故障模式：`single,frequent`
- 种子：`1-20`

## 单一目标（Only One）

只完成全量统计运行与结论汇总，不改任何算法实现。

## 验收标准

1. 成功生成全量 `runs/summary/significance` 三个 CSV。
2. 给出 `SNN vs OSPF/ECMP/PPO` 的主指标显著性结论（PDR/Delay/Loss）。
3. 结果记录到 issue 与 PR 草案。

## 计划命令

```bash
python3 scripts_flow/paper_stat_eval.py --algos ospf,ecmp,backpressure,ppo,snn --topos ba,er --sizes 50,100 --seeds 1-20 --steps 240 --fail-step 150 --failure-profiles single,frequent --snn-mode snn_spike_native --out-prefix run_dir/issue12_full
```

## 实际执行说明

为降低总耗时，本轮采用 8 个分片并行运行（按 `topo x size x failure_profile` 切分），再统一合并：

- `run_dir/issue12_shard_*_runs.csv`
- 合并后：
  - `run_dir/issue12_full_runs.csv`（800 条，完整矩阵）
  - `run_dir/issue12_full_summary.csv`
  - `run_dir/issue12_full_significance.csv`

## 全量主结论（seeds=1-20，160 对配对样本）

### SNN vs OSPF（总体配对差值）

- `pdr_final`: `+0.11624`，95%CI `[+0.09841, +0.13461]`，`p=5e-05`
- `loss_final`: `-2434.50`，95%CI `[-2812.84, -2065.17]`，`p=5e-05`
- `delay_final`: `+0.52216`，95%CI `[+0.10195, +0.92086]`，`p=0.0144`

### SNN vs ECMP（总体配对差值）

- `pdr_final`: `+0.06225`，95%CI `[+0.05289, +0.07193]`，`p=5e-05`
- `loss_final`: `-1383.73`，95%CI `[-1569.93, -1208.04]`，`p=5e-05`
- `delay_final`: `+0.69100`，95%CI `[+0.35850, +1.03030]`，`p=2.5e-04`

### SNN vs PPO（总体配对差值）

- `pdr_final`: `+0.01295`，95%CI `[+0.00757, +0.01843]`，`p=5e-05`
- `loss_final`: `-434.67`，95%CI `[-528.55, -348.05]`，`p=5e-05`
- `delay_final`: `+0.96512`，95%CI `[+0.67237, +1.27978]`，`p=5e-05`

## 结论

1. 在论文主评估矩阵上，SNN 相比 OSPF/ECMP/PPO 均呈现统计显著的 `PDR` 提升与 `Loss` 下降。
2. 代价是统计显著的 `Delay` 增长（与“以时延换容量/稳定性”的研究目标一致）。
3. PPO 已构成强学习型基线，但全量统计下 SNN 仍保持稳定优势（尤其在 loss 指标）。
