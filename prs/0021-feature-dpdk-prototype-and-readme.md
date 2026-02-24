# PR Draft: Feature Issue #3 - DPDK SNN-SRA 原型与文档

## 关联 Issue

- refs #3

## Why

为后续将增强版 SNN-SRA 从 Python 仿真迁移到高性能数据面，实现一个可演进的 DPDK C 原型，并建立清晰的映射说明文档。

## 变更内容

1. 新增 `dpdk/snn_sra_dpdk_prototype.c`
   - DPDK EAL 初始化、端口初始化、RX/TX 主循环
   - 端口级 `S/spike/loss/queue` 状态更新
   - 基于 SNN-SRA 评分的简化下一跳选择
   - 简化控制面周期重算（原型级）
2. 新增 `dpdk/README.md`
   - 描述 `scripts_flow` 增强版逻辑与 DPDK 原型的映射关系
   - 给出编译与运行示例
   - 给出工程化演进建议（LPM、多核 pipeline、控制面接口、指标导出）
3. 新增/更新 issue 文档
   - `issues/0022-dpdk-prototype-and-readme.md`

## 测试

本 PR 进行以下检查：

1. 文件结构检查：`dpdk/` 目录及目标文件存在
2. 构建依赖检查：`pkg-config --exists libdpdk`
3. 如环境具备 DPDK：执行编译命令

> 注：若 CI/本地缺少 DPDK 头文件与库，仅执行依赖检查并在结果中说明。

## 风险与边界

- 当前为“原型骨架”，不含完整 ARP/邻居发现、FIB、协议控制面。
- 路由控制逻辑为简化版，目标是验证映射路径而非直接生产可用。

## 后续计划

1. 使用 `rte_lpm`/`rte_fib` 替换当前简化路由表。
2. 引入多核流水线和无锁统计聚合。
3. 对齐 Python 实验指标导出（PDR/loss/delay/hop）与故障注入控制接口。
