# Issue #11: 新增 PPO-Lite 学习型路由基线（替代老式 Q-learning）

## 类型

Feature + Focused Experiment

## 背景

为回应“学习型基线要更新”的要求，本项目不采用传统 Q-learning，改用 PPO 思路的离散动作学习基线。

当前环境未引入 `torch/sb3`，为保证可复现与快速迭代，本轮先实现纯 `numpy` 的 PPO-Lite：

- 动作：下一跳邻居选择（带可行动作掩码）
- 策略：线性 logits + softmax
- 更新：clipped surrogate（PPO 核心）+ entropy 正则

## 单一目标（Only One）

仅新增并接入 PPO-Lite 学习基线，不改 SNN 机制。

## 范围

- In scope:
  - 新增 PPO-Lite 策略模块
  - 在对比脚本接入 `ppo` 算法入口
  - 输出 `SNN vs PPO` 对比结果
- Out of scope:
  - 引入 torch/sb3
  - 多智能体复杂训练框架
  - SNN 算法改动

## 验收标准

1. `compare` 脚本支持 `--algos ... ,ppo,...`。
2. PPO-Lite 在 ER/BA（seeds=11,17,23）稳定可运行。
3. 输出并记录 `SNN vs PPO` 的主指标差值（PDR/Delay/Loss）。

## 验证命令

```bash
python3 scripts_flow/compare_snn_vs_ospf.py --algos ospf,ecmp,ppo,snn --topos ba,er --seeds 11,17,23 --steps 240 --fail-step 150 --snn-mode snn_spike_native --out run_dir/issue11_compare_runs.csv --out-agg run_dir/issue11_compare_agg.csv
```

## 当前结果（seeds=11,17,23）

### 均值结果

- BA:
  - OSPF: `pdr_final=0.6748`, `delay_final=11.3202`, `loss_final=7323`
  - ECMP: `pdr_final=0.7386`, `delay_final=10.2507`, `loss_final=5940`
  - PPO:  `pdr_final=0.7971`, `delay_final=9.8651`,  `loss_final=4573`
  - SNN:  `pdr_final=0.8314`, `delay_final=11.5148`, `loss_final=3758`
- ER:
  - OSPF: `pdr_final=0.8138`, `delay_final=9.8514`, `loss_final=4081.3`
  - ECMP: `pdr_final=0.8165`, `delay_final=10.5992`, `loss_final=4033.7`
  - PPO:  `pdr_final=0.8514`, `delay_final=10.3322`, `loss_final=3190.3`
  - SNN:  `pdr_final=0.8477`, `delay_final=11.2757`, `loss_final=3148.3`

### Delta（SNN - PPO）

- BA: `PDR +0.0343`, `Loss -815.0`, `Delay +1.650`
- ER: `PDR -0.0038`, `Loss -42.0`, `Delay +0.943`

## 结论

- PPO-Lite 基线已经是一个“更现代”的学习型对照，并且在当前实验里显著强于 OSPF/ECMP。
- 对 SNN 而言：
  - BA 上 SNN 仍有容量优势（PDR/Loss更优），但 delay 更高；
  - ER 上 PPO 与 SNN 非常接近，PPO 在 PDR 上略高、SNN 在 Loss 上略优，说明学习基线已成为强竞争对手。
