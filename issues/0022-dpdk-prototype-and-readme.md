# Issue #3 - 基于 DPDK 的 SNN-SRA C 原型与文档落地

GitHub Issue: https://github.com/unicorners-compin/snn-sra/issues/3

## 背景

当前项目增强版实现位于 `scripts_flow/`，主要为 Python 仿真。为后续向高性能数据面迁移，需要先建立一个可演进的 DPDK C 代码原型，并提供配套说明文档。

## 目标

在 `dpdk/` 目录新增：

1. `snn_sra_dpdk_prototype.c`：SNN-SRA 逻辑的 DPDK 数据面原型；
2. `README.md`：说明当前 Python 逻辑到 DPDK 原型的映射、编译运行方式与后续演进路径。

## 范围

- 仅新增原型与文档，不替换现有 Python 仿真主流程；
- 不引入复杂控制面协议栈；
- 保持代码结构清晰，便于后续扩展。

## 验收标准

- `dpdk/` 目录存在原型 C 文件与 README；
- README 清楚描述 SNN 状态更新、路由评分、控制面周期更新的映射关系；
- 给出可执行的编译示例命令；
- 提供后续工程化建议（LPM、pipeline、多核、指标导出等）。

## 输出物

- `dpdk/snn_sra_dpdk_prototype.c`
- `dpdk/README.md`
- `prs/0021-feature-dpdk-prototype-and-readme.md`
