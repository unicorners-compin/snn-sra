# PR Draft: Feature Issue #14 - 最小保持时延抑制路由震荡

## 关联 Issue

- refs #14

## Why

SNN 在动态场景下存在下一跳抖动风险，需要在不改核心机制（LIF/beacon/STDP）的前提下，通过最小保持时延降低无效切换。

## 变更内容

- `scripts_flow/snn_simulator.py`
  - 新增参数：
    - `native_min_hold_steps`
    - `native_emergency_improvement`
  - 在 native 选路切换逻辑中加入：
    - 持有期内默认保持旧下一跳
    - 仅当改进幅度超过紧急阈值才允许提前切换
- `scripts_flow/main_snn.py`
  - 补充默认与 ER 参数配置：
    - BA 默认 hold=6
    - ER 默认 hold=8（并提高 emergency 阈值）

## 快速验证（seeds=11/17/23）

- BA（hold_on - hold_off）：
  - `route_changes_final -4.00`
  - `delay_final -0.110`
  - `pdr_final -0.00649`
  - `loss_final +111.0`
- ER（hold_on - hold_off）：
  - `route_changes_final -2.67`
  - `delay_final -0.180`
  - `pdr_final +0.00078`
  - `loss_final -41.67`

## 解释

- 震荡抑制目标达成：两类拓扑 route changes 均下降。
- ER 上总体收益更稳；BA 上出现轻微容量代价，下一步在 issue #15 用自适应 hold 继续优化稳态/恢复速度权衡。
