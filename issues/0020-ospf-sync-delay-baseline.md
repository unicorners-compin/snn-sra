# Issue #20: OSPF 同步周期与收敛时延建模（公平基线）

## 类型

Feature + Experiment

## 背景

当前 OSPF 基线是理想化最短路转发（每步近似全局即时最短路），缺少协议控制面同步与收敛时延。审稿人可能质疑该对比口径不完整。

## 单一目标（Only One）

仅补充 OSPF 控制面时延建模，不改 SNN/PPO 机制：

- 增加 `ospf_sync` 基线
- 建模 LSA/同步周期与 SPF 重计算时延
- 在四基线主表中加入 `ospf_sync` 对照

## 范围

- In scope:
  - 新增 `OSPFSyncSimulator`
  - 参数：`sync_period`, `spf_delay`
  - 接入统计脚本（paper_stat/delay/overhead/robustness）
- Out of scope:
  - 真实协议栈级字节精算
  - 链路恢复完整状态机

## 验收标准

1. `ospf_sync` 可在现有评估脚本中与 `ospf/ecmp/ppo/snn` 并行运行。
2. 输出 `SNN vs ospf_sync` 的差值与显著性。
3. 文档说明“理想 ospf 与同步时延 ospf_sync”的差异口径。

## 验证命令（示例）

```bash
python3 scripts_flow/paper_stat_eval_parallel.py --algos ospf,ospf_sync,ecmp,ppo,snn --topos ba,er --sizes 50,100 --seeds 1-20 --steps 240 --fail-step 150 --failure-profiles single,frequent --background-scale 2.0 --workers 20 --out-prefix run_dir/issue20_sync
```

## 当前进展（2026-02-23）

已完成实现与全量评估：

- 在 `scripts_flow/compare_snn_vs_ospf.py` 新增 `OSPFSyncSimulator`
  - 建模参数：`sync_period=12`, `spf_delay=4`
  - 维护 `effective_graph` 与延迟生效拓扑变更
  - 周期性重计算路由表（模拟 SPF 周期）
- 已接入脚本：
  - `scripts_flow/paper_stat_eval.py`
  - `scripts_flow/paper_stat_eval_parallel.py`
  - `scripts_flow/paper_delay_eval_parallel.py`
  - `scripts_flow/overhead_eval.py`
  - `scripts_flow/robustness_grid_eval.py`

全量执行命令：

```bash
python3 scripts_flow/paper_stat_eval_parallel.py --algos ospf,ospf_sync,ecmp,ppo,snn --topos ba,er --sizes 50,100 --seeds 1-20 --steps 240 --fail-step 150 --failure-profiles single,frequent --background-scale 2.0 --workers 20 --out-prefix run_dir/issue20_sync
```

结果文件：

- `run_dir/issue20_sync_runs.csv`
- `run_dir/issue20_sync_summary.csv`
- `run_dir/issue20_sync_significance.csv`

核心结论（8分组平均）：

1. `SNN vs ospf_sync` 仍显著优势：
   - `pdr_final +0.1253`（8/8 显著）
   - `pdr_post +0.1176`（8/8 显著）
   - `loss_final -5355.94`（8/8 显著）
2. 对比原理想 OSPF，`ospf_sync` 让 OSPF 更弱一些（符合预期），但不改变主结论方向：
   - `SNN` 对 OSPF 类基线的优势不是由“不公平即时 OSPF”造成。
3. 时延代价依旧存在：
   - `delay_final` 约 `+0.7767`（显著性 2/8），与“以时延换容量稳定性”的主叙事一致。
