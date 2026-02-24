# PR Draft: Feature Issue #20 - MinIO 上传基础设施（前置）

## 关联 Issue

- refs #20

## Why

后续每个实验都要求“完成后上传 MinIO 并清理本地结果”，但当前环境没有 `mc/aws`。本 PR 提供仓库内可复用上传脚本，统一上传协议。

## 变更内容

1. 新增 `scripts_flow/minio_uploader.py`
   - 从 `config/minio.txt` 读取 `access/secret/endpoint`
   - 支持 bucket 自动创建
   - 支持上传文件/目录（递归）
   - 上传后 `stat_object` 校验
   - 自动上传 `metadata.json`（包含 issue、分支、commit、命令、时间等）
   - `--cleanup` 成功后清理本地结果
   - `--dry-run` 预演模式
2. 新增 issue 文档：
   - `issues/0034-minio-upload-bootstrap.md`

## 验证命令（已执行）

```bash
python3 -m py_compile scripts_flow/minio_uploader.py
mkdir -p run_dir/issue20_smoke && echo 'hello-minio' > run_dir/issue20_smoke/result.txt
python3 scripts_flow/minio_uploader.py --issue-id 20 --run-tag issue20_smoke_20260224 --paths run_dir/issue20_smoke --config config/minio.txt --bucket snn-sra-exp --command "smoke-test" --dry-run
python3 scripts_flow/minio_uploader.py --issue-id 20 --run-tag issue20_smoke_20260224 --paths run_dir/issue20_smoke --config config/minio.txt --bucket snn-sra-exp --command "smoke-test" --cleanup
```

## 验证结果

- 成功上传：
  - `s3://snn-sra-exp/issue-20/issue20_smoke_20260224/issue20_smoke/result.txt`
  - `s3://snn-sra-exp/issue-20/issue20_smoke_20260224/metadata.json`
- 本地目录 `run_dir/issue20_smoke` 已删除（cleanup 生效）

## 备注

- 后续实验 issue 将统一调用本脚本执行上传与清理。
