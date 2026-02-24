# PR Draft: Test Issue #1 - 增强版仿真全量测试与归档

## 关联 Issue

- refs #1

## Why

建立增强版仿真（`scripts_flow/`）的可复现测试基线，为后续按 Git Flow 逐 issue 开发提供回归依据。

## 本 PR 做了什么

1. 新增并完善 Issue 文档：
   - `issues/0021-enhanced-simulation-full-test.md`
   - 已关联 GitHub Issue #1
2. 执行增强版全链路 smoke 测试：
   - 语法编译检查
   - 核心主入口 `main_snn.py`
   - 基线对比 `compare_snn_vs_ospf.py`
   - 统计/并行/时延分解/开销/消融/鲁棒性/因果分析脚本
   - 旧增强版入口 `main.py`, `main_decentralized.py`
3. 新增完整中文测试报告：
   - `run_dir/issue1_test_report.md`

## 验证命令（本次已执行）

```bash
python3 -m py_compile scripts_flow/*.py
EXPERIMENT_RUN_DIR=run_dir/issue1_main SNN_NUM_NODES=36 SNN_TOPOLOGY=ba SNN_TOPO_SEED=17 SNN_BA_M=2 SNN_ROUTING_MODE=snn_event_dv python3 scripts_flow/main_snn.py
python3 scripts_flow/compare_snn_vs_ospf.py --algos ospf,ospf_sync,ecmp,backpressure,ppo,snn --topos ba --seeds 11 --steps 80 --fail-step 45 --ba-m 2 --snn-mode snn_spike_native --out run_dir/issue1/compare_runs.csv --out-agg run_dir/issue1/compare_agg.csv
python3 scripts_flow/paper_stat_eval.py --algos ospf,ecmp,ppo,snn --topos ba --sizes 30 --seeds 1-2 --steps 60 --fail-step 35 --failure-profiles single --background-scale 1.3 --snn-mode snn_spike_native --out-prefix run_dir/issue1/paper_stat
python3 scripts_flow/paper_stat_eval_parallel.py --algos ospf,ecmp,snn --topos ba --sizes 30 --seeds 1-2 --steps 60 --fail-step 35 --failure-profiles single --workers 2 --snn-mode snn_spike_native --out-prefix run_dir/issue1/paper_stat_parallel
python3 scripts_flow/analyze_spike_causality.py --topos ba --seeds 11 --steps 80 --fail-step 45 --ba-m 2 --out run_dir/issue1/spike_causality.csv --out-agg run_dir/issue1/spike_causality_agg.csv
python3 scripts_flow/paper_delay_eval_parallel.py --algos ospf,ecmp,snn --topos ba --sizes 30 --seeds 1-2 --steps 60 --fail-step 35 --failure-profiles single --background-scale 1.5 --workers 2 --out-prefix run_dir/issue1/paper_delay
python3 scripts_flow/overhead_eval.py --algos ospf,ecmp,snn --topos ba --sizes 30 --seeds 1-2 --steps 60 --fail-step 35 --failure-profiles single --background-scale 1.5 --workers 2 --out-prefix run_dir/issue1/overhead
python3 scripts_flow/paper_ablation_eval.py --variants full,no_dst_beacon,no_lif_burst,no_stdp,no_min_hold --topos ba --sizes 30 --seeds 1-2 --steps 60 --fail-step 35 --failure-profiles single --background-scale 1.5 --workers 2 --out-prefix run_dir/issue1/ablation
EXPERIMENT_RUN_DIR=run_dir/issue1_flow_main python3 scripts_flow/main.py
python3 scripts_flow/main_decentralized.py
python3 scripts_flow/robustness_grid_eval.py --algos ospf,ecmp,snn --topos ba --sizes 30 --seeds 1-2 --steps 60 --fail-step 35 --failure-profiles single --background-scales 1.0 --ba-ms 2 --workers 2 --out-prefix run_dir/issue1/robustness
```

## 结果摘要

- 全部目标脚本在 smoke 参数下通过。
- 主入口 `main_snn.py` 成功生成 `snn_metrics.csv / snn_ablation_summary.csv / snn_route_viz.json`。
- 统计脚本均生成 `runs/summary/significance` 三类结果文件。
- 详细结果见：`run_dir/issue1_test_report.md`。

## 备注

- 本 PR 不改动算法逻辑，仅完成测试与文档归档。
