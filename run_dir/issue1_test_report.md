# 增强版仿真测试报告（Issue #1）

## 1. 测试目标

- 仅覆盖增强版仿真链路（`scripts_flow/`）
- 验证核心入口、对比基线、统计评估、消融、开销、鲁棒性脚本可运行
- 形成可复现的中文测试证据

## 2. 测试环境

- 仓库：`unicorners-compin/snn-sra`
- 分支：`feature/issue-0021-enhanced-simulation-full-test`
- Python：系统 `python3`
- GitHub Issue：`#1`

## 3. 执行项与结果

### 3.1 语法与导入检查

- 命令：`python3 -m py_compile scripts_flow/*.py`
- 结果：通过

### 3.2 核心主入口（SNN A/B）

- 命令：
  `EXPERIMENT_RUN_DIR=run_dir/issue1_main SNN_NUM_NODES=36 SNN_TOPOLOGY=ba SNN_TOPO_SEED=17 SNN_BA_M=2 SNN_ROUTING_MODE=snn_event_dv python3 scripts_flow/main_snn.py`
- 结果：通过
- 输出文件：
  - `run_dir/issue1_main/snn_metrics.csv`
  - `run_dir/issue1_main/snn_ablation_summary.csv`
  - `run_dir/issue1_main/snn_route_viz.json`
- 关键摘要（终值）：
  - `baseline_beta0`: `final_pdr=0.607935`, `final_loss=4114`
  - `snn_beta8`: `final_pdr=0.621099`, `final_loss=3995`

### 3.3 基线对比脚本

- 命令：
  `python3 scripts_flow/compare_snn_vs_ospf.py --algos ospf,ospf_sync,ecmp,backpressure,ppo,snn --topos ba --seeds 11 --steps 80 --fail-step 45 --ba-m 2 --snn-mode snn_spike_native --out run_dir/issue1/compare_runs.csv --out-agg run_dir/issue1/compare_agg.csv`
- 结果：通过
- 输出文件：
  - `run_dir/issue1/compare_runs.csv`
  - `run_dir/issue1/compare_agg.csv`

### 3.4 统计评估脚本（串行/并行）

- 命令：
  - `paper_stat_eval.py`（小矩阵）
  - `paper_stat_eval_parallel.py`（workers=2）
- 结果：通过
- 输出文件：
  - `run_dir/issue1/paper_stat_runs.csv`
  - `run_dir/issue1/paper_stat_summary.csv`
  - `run_dir/issue1/paper_stat_significance.csv`
  - `run_dir/issue1/paper_stat_parallel_runs.csv`
  - `run_dir/issue1/paper_stat_parallel_summary.csv`
  - `run_dir/issue1/paper_stat_parallel_significance.csv`

### 3.5 尖峰因果分析

- 命令：
  `python3 scripts_flow/analyze_spike_causality.py --topos ba --seeds 11 --steps 80 --fail-step 45 --ba-m 2 --out run_dir/issue1/spike_causality.csv --out-agg run_dir/issue1/spike_causality_agg.csv`
- 结果：通过
- 输出文件：
  - `run_dir/issue1/spike_causality.csv`
  - `run_dir/issue1/spike_causality_agg.csv`

### 3.6 时延分解/开销/消融

- 命令：
  - `paper_delay_eval_parallel.py`（workers=2）
  - `overhead_eval.py`（workers=2）
  - `paper_ablation_eval.py`（workers=2）
- 结果：通过
- 输出文件：
  - `run_dir/issue1/paper_delay_runs.csv`
  - `run_dir/issue1/paper_delay_summary.csv`
  - `run_dir/issue1/paper_delay_significance.csv`
  - `run_dir/issue1/overhead_runs.csv`
  - `run_dir/issue1/overhead_summary.csv`
  - `run_dir/issue1/overhead_significance.csv`
  - `run_dir/issue1/overhead_benefit_cost.csv`
  - `run_dir/issue1/ablation_runs.csv`
  - `run_dir/issue1/ablation_summary.csv`
  - `run_dir/issue1/ablation_significance.csv`
  - `run_dir/issue1/ablation_contrib.csv`

### 3.7 旧增强版入口与鲁棒性网格

- 命令：
  - `EXPERIMENT_RUN_DIR=run_dir/issue1_flow_main python3 scripts_flow/main.py`
  - `python3 scripts_flow/main_decentralized.py`
  - `python3 scripts_flow/robustness_grid_eval.py --algos ospf,ecmp,snn --topos ba --sizes 30 --seeds 1-2 --steps 60 --fail-step 35 --failure-profiles single --background-scales 1.0 --ba-ms 2 --workers 2 --out-prefix run_dir/issue1/robustness`
- 结果：通过
- 输出文件：
  - `run_dir/issue1_flow_main/flow_metrics.csv`
  - `run_dir/global_metrics.csv`
  - `run_dir/issue1/robustness_runs.csv`
  - `run_dir/issue1/robustness_summary.csv`
  - `run_dir/issue1/robustness_significance.csv`
  - `run_dir/issue1/robustness_boundary.csv`

## 4. 结论

- 本次增强版仿真全链路 smoke 测试通过，无运行时崩溃。
- 统计类脚本在小规模参数下均可产出完整 `runs/summary/significance` 结果。
- 测试结果已可作为后续 issue 的回归基线。

## 5. 风险与后续建议

- 当前为 smoke 规模（小 seeds/小规模/短步长），不代表论文主结论稳定性。
- 建议下一 issue 增加“回归测试参数集”与“固定随机种子矩阵”，并自动化保存日志与摘要表。
