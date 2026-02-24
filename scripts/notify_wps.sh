#!/usr/bin/env bash
set -euo pipefail

CONF_PATH="${NOTIFY_CONF:-config/notify.local.json}"
if [[ $# -lt 1 ]]; then
  echo "用法: $0 <消息文本>"
  exit 1
fi

if [[ ! -f "$CONF_PATH" ]]; then
  echo "配置文件不存在: $CONF_PATH"
  echo "请复制 config/notify.example.json 到 $CONF_PATH 并填写 wps_webhook"
  exit 1
fi

WEBHOOK=$(python3 - <<'PY' "$CONF_PATH"
import json,sys
p=sys.argv[1]
with open(p,'r',encoding='utf-8') as f:
    cfg=json.load(f)
print(cfg.get('wps_webhook','').strip())
PY
)

if [[ -z "$WEBHOOK" ]]; then
  echo "wps_webhook 为空: $CONF_PATH"
  exit 1
fi

MSG="$1"
RESP=$(curl -sS -X POST "$WEBHOOK" \
  -H 'Content-Type: application/json' \
  -d "{\"msgtype\":\"text\",\"text\":{\"content\":\"${MSG//\"/\\\"}\"}}")

echo "$RESP"
