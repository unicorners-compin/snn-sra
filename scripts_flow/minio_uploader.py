import argparse
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from minio import Minio
from minio.error import S3Error


def read_minio_config(path: Path):
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if len(lines) < 3:
        raise ValueError(f"Invalid minio config file: {path}")
    access_key, secret_key, endpoint = lines[0], lines[1], lines[2]
    parsed = urlparse(endpoint)
    if parsed.scheme:
        secure = parsed.scheme == "https"
        host = parsed.netloc
    else:
        secure = False
        host = endpoint
    if not host:
        raise ValueError(f"Invalid endpoint in {path}: {endpoint}")
    return access_key, secret_key, host, secure


def collect_files(paths):
    files = []
    for p in paths:
        src = Path(p).resolve()
        if not src.exists():
            raise FileNotFoundError(f"Path not found: {src}")
        if src.is_file():
            files.append((src, src.name))
        else:
            for f in sorted(src.rglob("*")):
                if f.is_file():
                    rel = f.relative_to(src).as_posix()
                    files.append((f, f"{src.name}/{rel}"))
    return files


def git_value(args):
    try:
        out = subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL).strip()
        return out
    except Exception:
        return "unknown"


def upload_all(client, bucket, prefix, files):
    uploaded = []
    for src, rel in files:
        obj = f"{prefix}{rel}"
        client.fput_object(bucket, obj, str(src))
        client.stat_object(bucket, obj)
        uploaded.append(obj)
        print(f"[UPLOADED] {src} -> s3://{bucket}/{obj}")
    return uploaded


def cleanup_paths(paths):
    removed = []
    for p in paths:
        path = Path(p).resolve()
        if not path.exists():
            continue
        if path.is_file():
            path.unlink()
            removed.append(str(path))
        else:
            shutil.rmtree(path)
            removed.append(str(path))
    return removed


def main():
    parser = argparse.ArgumentParser(description="Upload experiment results to MinIO with issue metadata.")
    parser.add_argument("--issue-id", required=True, help="GitHub issue id, e.g. 20")
    parser.add_argument("--run-tag", required=True, help="Run tag, e.g. issue20_bootstrap_20260224")
    parser.add_argument("--paths", required=True, help="Comma-separated files/dirs to upload")
    parser.add_argument("--bucket", default="snn-sra-exp")
    parser.add_argument("--config", default="config/minio.txt")
    parser.add_argument("--command", default="", help="Experiment command string for metadata")
    parser.add_argument("--cleanup", action="store_true", help="Delete local paths after successful upload")
    parser.add_argument("--dry-run", action="store_true", help="Show operations without upload")
    args = parser.parse_args()

    cfg_path = Path(args.config).resolve()
    access_key, secret_key, host, secure = read_minio_config(cfg_path)
    paths = [x.strip() for x in args.paths.split(",") if x.strip()]
    files = collect_files(paths)
    if not files:
        raise ValueError("No files to upload.")

    prefix = f"issue-{args.issue_id}/{args.run_tag}/"
    now = datetime.now(timezone.utc).isoformat()
    metadata = {
        "issue_id": str(args.issue_id),
        "run_tag": args.run_tag,
        "bucket": args.bucket,
        "prefix": prefix,
        "paths": [str(Path(p).resolve()) for p in paths],
        "file_count": len(files),
        "git_branch": git_value(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
        "git_commit": git_value(["git", "rev-parse", "HEAD"]),
        "host": socket.gethostname(),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "timestamp_utc": now,
        "command": args.command,
    }

    if args.dry_run:
        print(json.dumps(metadata, indent=2, ensure_ascii=False))
        for _, rel in files:
            print(f"[DRY] s3://{args.bucket}/{prefix}{rel}")
        return

    client = Minio(host, access_key=access_key, secret_key=secret_key, secure=secure)
    try:
        if not client.bucket_exists(args.bucket):
            client.make_bucket(args.bucket)
            print(f"[BUCKET] created {args.bucket}")
    except S3Error as e:
        raise RuntimeError(f"MinIO bucket check/create failed: {e}") from e

    uploaded = upload_all(client, args.bucket, prefix, files)

    metadata_file = Path("/tmp") / f"{args.run_tag}_metadata.json"
    metadata_file.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    meta_obj = f"{prefix}metadata.json"
    client.fput_object(args.bucket, meta_obj, str(metadata_file))
    client.stat_object(args.bucket, meta_obj)
    uploaded.append(meta_obj)
    print(f"[UPLOADED] metadata -> s3://{args.bucket}/{meta_obj}")

    if args.cleanup:
        removed = cleanup_paths(paths)
        for item in removed:
            print(f"[CLEANED] {item}")

    print(f"[DONE] uploaded_objects={len(uploaded)} bucket={args.bucket} prefix={prefix}")


if __name__ == "__main__":
    main()
