# PR Draft: Feature Issue #7 - 公式改进 V2 与 A/B 对照开关

## 关联 Issue

- refs #7

## Why

当前公式存在硬截断与硬最小值决策，可能造成应力饱和和路径抖动。该 PR 引入可选的 V2 公式，并保留 V1 默认兼容。

## 变更内容

1. `scripts_flow/snn_node.py`
   - 新增 `stress_mode` 机制：
     - `v1`：原有 `kappa=min(1, raw)`
     - `v2_sigmoid`：`kappa=sigmoid(gain*(raw-center))`
2. `scripts_flow/snn_router.py`
   - 新增评分归一化选项 `score_norm_mode=bounded`
   - 新增 softmin 温度采样选路（`softmin_temperature>0`）
   - 默认保持原先 hard-min 行为
3. `scripts_flow/main_snn.py`
   - 新增环境变量：
     - `SNN_FORMULA_MODE` (`v1`/`v2`)
     - `SNN_STEPS`
     - `SNN_FAIL_STEP`
   - 将 `formula_mode` 写入可视化元数据
4. 新增 issue/PR 文档
   - `issues/0024-formula-v2-and-ab-comparison.md`
   - `prs/0023-feature-formula-v2-and-ab-comparison.md`

## 验证命令

```bash
python3 -m py_compile scripts_flow/snn_node.py scripts_flow/snn_router.py scripts_flow/main_snn.py
EXPERIMENT_RUN_DIR=run_dir/issue7_v1 SNN_NUM_NODES=25 SNN_TOPOLOGY=ba SNN_BA_M=2 SNN_ROUTING_MODE=snn_event_dv SNN_FORMULA_MODE=v1 SNN_STEPS=80 SNN_FAIL_STEP=40 python3 scripts_flow/main_snn.py
EXPERIMENT_RUN_DIR=run_dir/issue7_v2 SNN_NUM_NODES=25 SNN_TOPOLOGY=ba SNN_BA_M=2 SNN_ROUTING_MODE=snn_event_dv SNN_FORMULA_MODE=v2 SNN_STEPS=80 SNN_FAIL_STEP=40 python3 scripts_flow/main_snn.py
```

## 备注

- 本 PR 重点是“可切换公式框架”与最小 A/B 可运行性，不宣称已是最优参数。
