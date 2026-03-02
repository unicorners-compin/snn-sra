# [Feature] 300节点卫空海 SNN-SRA 旁路灰度研究架构

## Background

当前环境中，300节点（卫星/飞机/船）运行拓扑仿真与路由机制评估，但现网主路径仍依赖 OSPF。为了进行科研验证并避免影响现网，需要构建“旁路影子（shadow mode）”研究架构：SNN-SRA 仅做并行推理、指标记录和离线/镜像评估，不写生产转发表。

## Goal

建立可复现实验框架，使 SNN-SRA 能在不干扰现网的前提下，与 OSPF 基线在相同动态拓扑和流量条件下进行稳定性对比。

## Scope

- In scope:
  - 定义 shadow mode 数据路径与控制边界（只读输入、只写研究键空间）。
  - 定义 300 节点命名映射（SAT-POLAR/SAT-INCL/AIR/SHIP）与实验对象。
  - 给出 issue 分解、分支策略、提交规范、PR 验收模板。
- Out of scope:
  - 生产转发切换到 SNN-SRA。
  - 修改现网 OSPF 参数/邻接关系。

## Acceptance Criteria

1. 形成明确的 shadow mode 架构文档，含输入/输出键、版本控制、回滚策略。
2. 至少拆分出 2 个可执行子 issue（数据适配 + 指标评估）。
3. 每个子 issue 有可量化验收条件和复现实验命令模板。
4. 不新增任何对生产键空间的写入。

## Validation Plan

- 文档审查：由团队确认边界条件与不干扰约束。
- 运行前检查：确认仅访问 `snn:*` 或专用研究命名空间。
- 代码审计：grep 写操作目标 key，不得覆盖现网 key。

## Risks / Rollback

- 风险：研究模块误写生产 Redis 键。
- 回滚：统一前缀开关，立即停用 shadow writer；删除 `snn:*` 键空间。
