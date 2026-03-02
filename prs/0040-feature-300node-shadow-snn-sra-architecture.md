## Linked Issue

- refs #28
- refs #29
- refs #30

## Why

为保证 300 节点卫空海实验在不影响现网的条件下推进，需要先建立统一的 shadow mode 研究架构，并明确 issue 分解与验收规范。

## What Changed

- 新增 Issue #40：300 节点 shadow mode 总体架构与边界定义。
- 新增 Issue #41：动态拓扑适配实验设计。
- 新增 Issue #42：OSPF vs SNN-SRA 稳定性统计对比实验设计。
- 补充本阶段 PR 草案，统一评审口径。

## Validation

### Commands

```bash
ls issues/0040-*.md issues/0041-*.md issues/0042-*.md prs/0040-*.md
```

### Results

- 新 issue 与 PR 草案文件完整存在。
- 每个 issue 具备背景/目标/变量/指标/成功标准/复现命令模板。

## Metrics Comparison (if applicable)

| Metric | Before | After | Delta |
| --- | ---: | ---: | ---: |
| Issue traceability | low | high | + |
| Experiment reproducibility spec | partial | structured | + |
| Non-interference boundary clarity | low | explicit | + |

## Risks

- Issue 编号与线上 GitHub issue 编号未自动对齐。

## Rollback

- 删除新增 issue/pr 草案文件，不影响代码主逻辑。
