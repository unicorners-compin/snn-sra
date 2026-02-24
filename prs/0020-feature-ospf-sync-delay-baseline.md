# PR Draft: Feature Issue #20 - OSPF 同步周期与收敛时延基线

## 关联 Issue

- refs #20

## Why

回答审稿质疑：当前 OSPF 是否过于理想化（即时全局最短路），从而影响 SNN 对比结论的公平性。

## 变更内容

- 在 `scripts_flow/compare_snn_vs_ospf.py` 新增 `OSPFSyncSimulator`
  - `sync_period` 周期同步
  - `spf_delay` 拓扑变化延迟生效
  - 周期性重计算路由表
- 将 `ospf_sync` 接入以下脚本：
  - `scripts_flow/paper_stat_eval.py`
  - `scripts_flow/paper_stat_eval_parallel.py`
  - `scripts_flow/paper_delay_eval_parallel.py`
  - `scripts_flow/overhead_eval.py`
  - `scripts_flow/robustness_grid_eval.py`

## 验证命令

```bash
python3 -m py_compile scripts_flow/compare_snn_vs_ospf.py scripts_flow/paper_stat_eval.py scripts_flow/paper_stat_eval_parallel.py scripts_flow/paper_delay_eval_parallel.py scripts_flow/overhead_eval.py scripts_flow/robustness_grid_eval.py
python3 scripts_flow/paper_stat_eval_parallel.py --algos ospf,ospf_sync,ecmp,ppo,snn --topos ba,er --sizes 50,100 --seeds 1-20 --steps 240 --fail-step 150 --failure-profiles single,frequent --background-scale 2.0 --workers 20 --out-prefix run_dir/issue20_sync
```

## 结果摘要

- 文件：
  - `run_dir/issue20_sync_runs.csv`
  - `run_dir/issue20_sync_summary.csv`
  - `run_dir/issue20_sync_significance.csv`
- `SNN vs ospf_sync`（8分组平均）：
  - `pdr_final +0.1253`（8/8 显著）
  - `pdr_post +0.1176`（8/8 显著）
  - `loss_final -5355.94`（8/8 显著）

## 结论

- OSPF 加入同步周期与收敛时延后，SNN 对 OSPF 类基线的优势依然显著。
- 因此“ SNN 优势来自不公平 OSPF 建模 ”这一质疑不成立。
