# PR Draft: Experiment Issue #19 - 泛化与稳健性复现（跨参数/跨负载）

## 关联 Issue

- refs #19

## Why

补齐审稿高频问题：方法是否只在单一参数有效，还是在负载、故障频率与拓扑扰动下仍保持优势。

## 变更内容

- 新增 `scripts_flow/robustness_grid_eval.py`
  - 扫描维度：
    - `background_scale`: 1.0/1.5/2.0/2.5
    - `failure_profile`: single/frequent/very_frequent
    - `ER-p`: 0.05/0.06/0.07
    - `BA-m`: 2/3/4
  - 输出：
    - `*_runs.csv`
    - `*_summary.csv`
    - `*_significance.csv`
    - `*_boundary.csv`（robust/weakened/failed + worst-case 边界）

## 验证命令（phase1）

```bash
python3 -m py_compile scripts_flow/robustness_grid_eval.py
python3 scripts_flow/robustness_grid_eval.py --algos ospf,ecmp,ppo,snn --topos ba,er --sizes 50,100 --seeds 1-10 --steps 240 --fail-step 150 --failure-profiles single,frequent,very_frequent --background-scales 1.0,1.5,2.0,2.5 --er-ps 0.05,0.06,0.07 --ba-ms 2,3,4 --workers 20 --out-prefix run_dir/issue19_robustness_phase1
```

## 结果文件（phase1）

- `run_dir/issue19_robustness_phase1_runs.csv`
- `run_dir/issue19_robustness_phase1_summary.csv`
- `run_dir/issue19_robustness_phase1_significance.csv`
- `run_dir/issue19_robustness_phase1_boundary.csv`

## 关键结果（phase1）

按 `boundary` 统计（432 个条件-基线组合）：

- 对 OSPF：
  - `robust 76.39%`
  - `weakened 23.61%`
  - `failed 0%`
- 对 ECMP：
  - `robust 56.25%`
  - `weakened 43.06%`
  - `failed 0.69%`
- 对 PPO：
  - `robust 17.36%`
  - `weakened 50.69%`
  - `failed 31.94%`

失效边界特征：

- `failed` 主要集中在与 PPO 对比时，尤其在 `very_frequent + background_scale=2.5` 的高压组合。
- 对 OSPF/ECMP，SNN 在 phase1 中大多数条件下仍保持容量优势（robust 或 weakened）。

## 结论与边界

- SNN 的鲁棒性对传统基线（OSPF/ECMP）较强；
- 在强学习基线（PPO）下，优势随压力上升明显收缩，需在后续工作里强化高压稳定性策略；
- 该结果可直接用于论文“鲁棒性讨论/失效边界”章节。

## 下一步

- 扩展为 `seeds=1-20` 作为终稿统计版，提升置信区间稳定性。
