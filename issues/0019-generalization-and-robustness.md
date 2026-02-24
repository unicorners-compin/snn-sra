# Issue #19: 泛化与稳健性复现（跨参数/跨负载）

## 类型

Experiment + Robustness

## 背景

审稿人常问：方法是否只在当前参数有效，还是对负载、故障频率、拓扑参数扰动具有稳健性。

## 单一目标（Only One）

仅做泛化/稳健性复现：

- 背景流倍率：1.0 / 1.5 / 2.0 / 2.5
- 故障频率：single / frequent / very_frequent
- 拓扑参数扰动：ER-p、BA-m 小范围扫描

## 验收标准

1. 输出每个扰动条件下 SNN 相对基线的差值与显著性。
2. 标注失效边界（何时优势缩小或消失）。
3. 形成论文中的“鲁棒性讨论”章节数据。

## 计划命令（示例）

```bash
python3 scripts_flow/robustness_grid_eval.py --algos ospf,ecmp,ppo,snn --topos ba,er --sizes 50,100 --seeds 1-20 --workers 20 --out-prefix run_dir/issue19_robustness
```

## 当前进展（2026-02-23）

已完成实现与 phase1 大矩阵（`seeds=1-10`）：

- 新增 `scripts_flow/robustness_grid_eval.py`
  - 扫描维度：
    - 背景流倍率：`1.0/1.5/2.0/2.5`
    - 故障频率：`single/frequent/very_frequent`
    - 拓扑扰动：`ER-p=0.05/0.06/0.07`、`BA-m=2/3/4`
  - 输出：
    - `runs/summary/significance/boundary`
  - 支持“优势状态”标注：`robust/weakened/failed`

phase1 执行命令：

```bash
python3 scripts_flow/robustness_grid_eval.py --algos ospf,ecmp,ppo,snn --topos ba,er --sizes 50,100 --seeds 1-10 --steps 240 --fail-step 150 --failure-profiles single,frequent,very_frequent --background-scales 1.0,1.5,2.0,2.5 --er-ps 0.05,0.06,0.07 --ba-ms 2,3,4 --workers 20 --out-prefix run_dir/issue19_robustness_phase1
```

结果文件：

- `run_dir/issue19_robustness_phase1_runs.csv`
- `run_dir/issue19_robustness_phase1_summary.csv`
- `run_dir/issue19_robustness_phase1_significance.csv`
- `run_dir/issue19_robustness_phase1_boundary.csv`

核心结论（phase1）：

1. 对 OSPF：SNN 鲁棒优势最稳定
   - `robust` 占比约 `76.39%`
   - `failed` 未出现（0%）
2. 对 ECMP：总体仍稳健，但存在边缘弱化
   - `robust` 占比约 `56.25%`
   - `failed` 约 `0.69%`（极少）
3. 对 PPO：优势最容易缩小
   - `robust` 约 `17.36%`
   - `weakened/failed` 合计约 `82.64%`

失效边界（phase1 观察）：

- 主要出现在 `PPO` 对比下，且集中于高压组合（`very_frequent + background_scale=2.5`）；
- 对 `OSPF/ECMP`，SNN 优势在本矩阵下仍以 `robust/weakened` 为主，几乎无 `failed`。

下一步：

- 可扩展到 `seeds=1-20` 作为最终版鲁棒性统计，提升置信度并用于论文终稿。
