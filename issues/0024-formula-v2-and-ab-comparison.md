# Issue #7 - SNN-SRA 公式改进 V2 与 A/B 对照验证

GitHub Issue: https://github.com/unicorners-compin/snn-sra/issues/7

## 背景

当前增强版 SNN-SRA 公式包含较强工程经验项（线性加权、硬截断、硬最小值选路），在高压场景下可能出现饱和与抖动，限制性能上限。

## 目标

实现一版可运行的公式 V2，并保留 V1 兼容开关，完成最小 A/B 对照。

## 方案范围

1. 节点应力更新 V2
   - 将 `kappa` 从硬截断改为平滑函数（sigmoid）
2. 邻居评分 V2
   - 对各项评分做归一化，减少量纲失衡
3. 选路策略 V2
   - 增加 softmin 温度采样选路（可关闭）
4. 配置层
   - 在 `main_snn.py` 增加 V2 运行模式入口（环境变量）
5. 文档
   - 新增 issue 与 PR 中文说明，记录公式变化与测试结论

## 验收标准

- 默认行为不变（V1 路径可用）
- V2 可通过开关启用并成功运行
- 主脚本 smoke 测试通过并产生结果文件
- 代码含必要注释与文档，便于论文讨论

## 输出物

- `scripts_flow/snn_node.py`（V2 stress 选项）
- `scripts_flow/snn_router.py`（归一化评分 + softmin 选项）
- `scripts_flow/main_snn.py`（V2 模式入口）
- `prs/0023-feature-formula-v2-and-ab-comparison.md`
