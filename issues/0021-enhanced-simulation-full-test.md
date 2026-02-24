# Issue #1 - 增强版仿真全量测试与结果归档

GitHub Issue: https://github.com/unicorners-compin/snn-sra/issues/1

## 背景

项目当前存在基础版（`scripts/`）与增强版（`scripts_flow/`）两套仿真链路。后续开发仅关注增强版，需要先完成一次系统化测试，建立可复现实验基线与测试证据。

## 目标

对增强版仿真代码进行完整测试，覆盖核心入口、对比基线、统计评估与鲁棒性脚本，形成统一中文测试文档，作为后续 issue 的回归基准。

## 范围

- 仅测试 `scripts_flow/` 相关代码与其依赖模块
- 不再关注 `scripts/` 基础版
- 产出测试日志与汇总文档到 `run_dir/`

## 任务清单

1. 语法与导入健康检查（`py_compile`）
2. 增强版核心主程序 smoke 测试（`main_snn.py`）
3. 对比基线程序 smoke 测试（`compare_snn_vs_ospf.py`）
4. 统计评估脚本 smoke 测试（`paper_*`, `overhead_eval.py`, `robustness_grid_eval.py`）
5. 汇总测试结果并生成中文报告

## 验收标准

- 所有目标脚本可成功编译
- 关键仿真入口可在小规模参数下跑通并生成结果文件
- 失败项（如有）具备明确错误定位与修复建议
- 测试过程与结论以中文完整记录

## 输出物

- `run_dir/issue21_test_report.md`
- `prs/0021-test-enhanced-simulation-full.md`

## 备注

- 本 issue 聚焦“测试与归档”，不涉及算法改动。
- 后续 commit / PR 统一使用 `refs #1` 关联。
