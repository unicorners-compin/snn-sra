# PR Draft: Feature Issue #11 - 新增 PPO-Lite 学习型路由基线

## 关联 Issue

- refs #11

## Why

为避免学习基线过旧（Q-learning），新增更现代的 PPO 思路基线，并在同一仿真框架下和 `OSPF/ECMP/SNN` 公平对比。

## 变更内容

- 新增 `scripts_flow/ppo_lite.py`
  - 纯 `numpy` 的 PPO-Lite 策略
  - 离散动作（下一跳）+ 动作掩码
  - clipped surrogate 更新（PPO 核心）
- 更新 `scripts_flow/compare_snn_vs_ospf.py`
  - 新增 `PPOSimulator`
  - `--algos` 增加 `ppo`
  - 新增 `delta snn-ppo` 输出
- 更新 `scripts_flow/paper_stat_eval.py`
  - 支持 `ppo` 算法入口（便于后续论文统计）

## 验证命令

```bash
python3 -m py_compile scripts_flow/ppo_lite.py scripts_flow/compare_snn_vs_ospf.py scripts_flow/paper_stat_eval.py
python3 scripts_flow/compare_snn_vs_ospf.py --algos ospf,ecmp,ppo,snn --topos ba,er --seeds 11,17,23 --steps 240 --fail-step 150 --snn-mode snn_spike_native --out run_dir/issue11_compare_runs.csv --out-agg run_dir/issue11_compare_agg.csv
```

## 结果摘要（均值）

- BA:
  - PPO: `pdr_final=0.7971`, `delay_final=9.8651`, `loss_final=4573`
  - SNN: `pdr_final=0.8314`, `delay_final=11.5148`, `loss_final=3758`
- ER:
  - PPO: `pdr_final=0.8514`, `delay_final=10.3322`, `loss_final=3190.3`
  - SNN: `pdr_final=0.8477`, `delay_final=11.2757`, `loss_final=3148.3`

## 解释

- PPO-Lite 已成为强学习型基线：
  - 相比 OSPF/ECMP 表现更强；
  - 与 SNN 在 ER 上非常接近，部分指标出现互有胜负。
- 这能显著提升论文说服力，也意味着后续 SNN 需要在 ER 场景进一步强化优势或明确 trade-off 叙事。
