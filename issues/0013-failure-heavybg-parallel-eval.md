# Issue #13: 故障场景 + 重背景流 场景统计评估（20核并行）

## 类型

Experiment + Infra

## 背景

Issue #12 已完成全量统计（含 single/frequent 故障），但尚未系统评估重背景流负载下的对比表现。

同时当前执行方式虽可分片并行，但未形成标准化 20 核并行入口。

## 单一目标（Only One）

仅扩展评估能力：

1. 支持背景流倍率（heavy background）
2. 支持多核心并行执行与自动合并

不改任何路由算法本体。

## 验收标准

1. 支持 `background_scale` 参数（例如 1.5 / 2.0）。
2. 支持 `workers` 参数并行运行（目标 20 核可用）。
3. 输出故障+重背景场景下 `SNN vs OSPF/ECMP/PPO` 的显著性结论。

## 计划命令（示例）

```bash
python3 scripts_flow/paper_stat_eval_parallel.py --algos ospf,ecmp,ppo,snn --topos ba,er --sizes 50,100 --seeds 1-20 --steps 240 --fail-step 150 --failure-profiles single,frequent --background-scale 2.0 --workers 20 --out-prefix run_dir/issue13_heavybg
```

## 实际执行结果

已按 20 核并行完成全量运行（`640` 组）：

- `run_dir/issue13_heavybg_runs.csv`
- `run_dir/issue13_heavybg_summary.csv`
- `run_dir/issue13_heavybg_significance.csv`

其中故障模式包含 `single` 与 `frequent`，背景流倍率为 `2.0x`。

## 关键结论（重背景流 + 故障）

### 聚合配对差值（160 对样本）

- SNN vs OSPF：
  - `pdr_final +0.11515`（95%CI `[+0.09866,+0.13256]`, `p=5e-05`）
  - `loss_final -5023.30`（95%CI `[-5816.91,-4286.11]`, `p=5e-05`）
  - `delay_final +0.40410`（95%CI `[-0.15662,+1.00201]`, `p=0.169`，不显著）
- SNN vs ECMP：
  - `pdr_final +0.07101`（95%CI `[+0.06066,+0.08153]`, `p=5e-05`）
  - `loss_final -3112.93`（95%CI `[-3556.88,-2693.37]`, `p=5e-05`）
  - `delay_final +0.61947`（95%CI `[+0.14474,+1.07556]`, `p=0.0109`）
- SNN vs PPO：
  - `pdr_final +0.01486`（95%CI `[+0.00969,+0.02042]`, `p=5e-05`）
  - `loss_final -941.39`（95%CI `[-1163.91,-723.22]`, `p=5e-05`）
  - `delay_final +1.17299`（95%CI `[+0.77448,+1.59290]`, `p=5e-05`）

### 场景级显著性计数（8 个场景）

- 对 OSPF：`PDR` 8/8 显著更好，`Loss` 8/8 显著更好。
- 对 ECMP：`PDR` 8/8 显著更好，`Loss` 8/8 显著更好。
- 对 PPO：`PDR` 6/8 更好（4/8 显著），`Loss` 8/8 更好（6/8 显著）。

## 结论

1. 在故障场景与重背景流条件下，SNN 的容量/稳定性优势（PDR↑、Loss↓）依然稳健。
2. 与 PPO 相比，SNN 仍保持统计显著优势，但优势幅度较对 OSPF/ECMP 更小，说明学习型基线竞争更强。
3. 延迟代价在重背景流下更明显，尤其对 PPO/ECMP 对比中需在论文中清晰阐述 trade-off。
