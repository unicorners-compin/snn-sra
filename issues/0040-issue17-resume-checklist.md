# Issue #17 续航说明（参数敏感性实验）

## 当前状态（截至 2026-02-24）

1. 已完成项
   - 分支：`feature/issue-0017-parameter-sensitivity`
   - 提交：`81be4d0`
   - 变更文件：
     - `scripts_flow/parameter_sensitivity_eval.py`
     - `issues/0039-issue17-sensitivity-execution.md`
     - `prs/0039-experiment-issue17-sensitivity.md`
   - PR 已创建：`#27`
     - 标题：`Feat: issue #17 parameter sensitivity and stability evaluation`
     - 关联 reviewer：`unicorners-compin`
   - Issue #17 已在 GitHub 上关闭（因为当前仅完成 smoke 与上传流程），且文档已记录。

2. 已通过的 smoke 验证
   - 命令：
     ```bash
     python3 scripts_flow/parameter_sensitivity_eval.py \
       --topos ba \
       --sizes 30 \
       --seeds 1 \
       --steps 60 \
       --fail-step 30 \
       --failure-profiles single \
       --pairwise stress_smooth_gain,stress_smooth_center,softmin_temperature \
       --base-mult 0.2 \
       --out-prefix run_dir/issue17_smoke \
       --issue-id 17
     ```
   - 结果文件已成功生成并上传：
     - `run_dir/issue17_smoke_sensitivity_runs.csv`
     - `run_dir/issue17_smoke_sensitivity_summary.csv`
     - `run_dir/issue17_smoke_sensitivity_significance.csv`
     - `run_dir/issue17_smoke_stable_region.csv`
   - MinIO 上传：
     - Bucket：`snn-sra-exp`
     - Prefix：`issue-17/issue17_smoke_20260224/`
     - `--cleanup` 后本地文件已清理

3. 当前工作区
   - `git status` 为 clean（无未提交改动）
   - PR 仍在 Open 状态（`#27`）

## 为什么要暂停（时间）

- 当前只完成了 smoke；全量矩阵规模如果按默认参数会很大，预计每次 1840 runs 左右，耗时明显长（通常十几分钟到接近 1 小时，视机器性能可更久）。
- 本次暂停点：**脚本没问题，尚未开始 full run 的完整矩阵分批执行**。

## 明天直接继续的最小步骤

1. 拉起本地分支并确认：
   ```bash
   git checkout feature/issue-0017-parameter-sensitivity
   git pull --ff-only
   ```

2. 先按轻负载分块跑（建议）：
   ```bash
   python3 scripts_flow/parameter_sensitivity_eval.py \
     --topos ba \
     --sizes 25 \
     --seeds 1-6 \
     --steps 160 \
     --fail-step 90 \
     --failure-profiles single \
     --pairwise stress_smooth_gain,stress_smooth_center,softmin_temperature \
     --base-mult 0.2 \
     --out-prefix run_dir/issue17/block1_ba25_seed1-6_single \
     --issue-id 17
   ```

3. 上传并清理（每个块完成后立即）：
   ```bash
   python3 scripts_flow/minio_uploader.py \
     --issue-id 17 \
     --run-tag issue17_block1_20260224 \
     --paths run_dir/issue17/block1_ba25_seed1-6_single_sensitivity_runs.csv,run_dir/issue17/block1_ba25_seed1-6_single_sensitivity_summary.csv,run_dir/issue17/block1_ba25_seed1-6_single_sensitivity_significance.csv,run_dir/issue17/block1_ba25_seed1-6_single_stable_region.csv \
     --bucket snn-sra-exp \
     --config config/minio.txt \
     --command "python3 scripts_flow/parameter_sensitivity_eval.py --topos ba --sizes 25 --seeds 1-6 --steps 160 --fail-step 90 --failure-profiles single --pairwise stress_smooth_gain,stress_smooth_center,softmin_temperature --base-mult 0.2 --out-prefix run_dir/issue17/block1_ba25_seed1-6_single --issue-id 17" \
     --cleanup
   ```

4. 分块建议清单（可按你机器承受能力调整）
   - `ba,25,seeds=1-6,single`
   - `ba,25,seeds=7-12,single`
   - `ba,25,seeds=13-20,single`
   - `ba,25,seeds=1-10,frequent`
   - `ba,25,seeds=11-20,frequent`
   - `ba,50`、`er,25`、`er,50` 继续同样按 chunks

## 注意事项（避免重跑和上传冲突）

- 每个块改用独立 `--out-prefix` 和唯一 `--run-tag`。
- 如果中途停机，保留 MinIO Prefix 命名策略，便于拼接汇总，不要覆盖现有文件。
- 如果要重启一个块，建议加 `--dry-run` 先确认路径和对象名。
- 若本地已清理，重新跑结果即可，不影响下一块汇总。

## 复现说明

- 代码依赖主分支中现有仿真器与指标字段，不需要额外安装。
- 运行前确保 `config/minio.txt` 可读、网络可连通（若离线可先只跑本地。

