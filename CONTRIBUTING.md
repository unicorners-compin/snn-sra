# Contributing Guide (Git Flow + Research Traceability)

本仓库从现在开始严格采用 Git Flow，并用 `Issue -> Branch -> Commit -> PR` 记录技术演进。

## 1. Branch Model

- `main`: 仅存放可发布/可复现实验版本。
- `develop`: 日常集成分支（所有 feature 先合入此分支）。
- `feature/*`: 新功能/实验实现分支。
- `hotfix/*`: 线上修复，基于 `main` 拉出，完成后回合并到 `main` 与 `develop`。
- `release/*`: 发布准备（可选，版本冻结时使用）。

命名规范：

- `feature/issue-<id>-<slug>`
- `hotfix/issue-<id>-<slug>`
- `release/v<major>.<minor>.<patch>`

## 2. Issue First

任何技术变更先建 Issue，再写代码。Issue 最少包含：

- 背景与目标
- 范围（In/Out）
- 验收标准（可量化）
- 风险与回滚方案

请使用 `.github/ISSUE_TEMPLATE/` 下模板。

## 3. Commit Convention

提交信息采用 Conventional Commits，并强制引用 Issue：

- `feat(scope): ... (refs #<id>)`
- `fix(scope): ... (refs #<id>)`
- `docs(scope): ... (refs #<id>)`
- `refactor(scope): ... (refs #<id>)`
- `test(scope): ... (refs #<id>)`
- `chore(scope): ... (refs #<id>)`

建议单次提交保持单一意图，可回滚、可审阅。

## 4. Pull Request Rules

PR 必须关联一个 Issue，且满足：

- 描述变更动机与方案
- 列出验证步骤和结果
- 明确风险与兼容性影响
- 附关键指标对比（如 PDR/Delay/Loss）

请使用 `.github/pull_request_template.md` 模板。

## 5. Merge Policy

- `feature/*` -> `develop`：通过 PR 合并，不直接 push 到 `develop`。
- `develop` -> `main`：仅在里程碑发布时，通过 `release/*` 或受控 PR。
- `hotfix/*`：合并到 `main` 后，必须回合并到 `develop`。

## 6. Research Traceability

每个 PR 需保证可复现实验：

- 固定随机种子
- 记录拓扑参数（BA/ER/Grid）
- 保存输出文件路径（如 `run_dir/*.csv`）
- 记录关键命令与环境变量

## 7. Quick Start

```bash
# 1) 同步主线
git checkout main
git pull

# 2) 创建或同步 develop（首次需要）
git checkout -b develop || git checkout develop
git pull || true

# 3) 从 issue 创建 feature 分支
bash scripts/gitflow/start_issue.sh 12 snn-route-stability
```
