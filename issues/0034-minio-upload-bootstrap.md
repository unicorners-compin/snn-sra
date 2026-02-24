# Issue #20 - MinIO 上传基础设施（前置）

GitHub Issue: https://github.com/unicorners-compin/snn-sra/issues/20

## 依赖

- 依赖：实验总路线图与 MinIO 协议 issue

## 背景

当前环境缺少 `mc/aws` 客户端，无法稳定执行“每次实验完成即上传 MinIO 并清理本地”的流程。

## 目标

实现一个仓库内可复用的上传工具，后续实验统一调用。

## 任务

1. 新增上传脚本（`scripts_flow/minio_uploader.py`）
2. 支持从 `config/minio.txt` 读取 endpoint/access/secret
3. 自动创建 bucket（若不存在）
4. 上传目录与 `metadata.json`
5. 校验对象存在后执行本地清理
6. 输出上传清单与删除清单日志

## 验收标准

- 可对给定 `out_prefix` 完成上传+校验+删除
- 上传路径包含 issue 信息：`issue-<id>/<run_tag>/`
- 失败时不删除本地结果
