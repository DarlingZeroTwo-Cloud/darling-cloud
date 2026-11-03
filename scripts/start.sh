#!/usr/bin/env bash
# Darling Cloud 一条命令启动（Linux / Arch / macOS）
# 用法：./start.sh [端口]   （默认 8080）
set -e
cd "$(dirname "$0")"
PORT="${1:-8080}"
echo "[Darling Cloud] 正在启动（端口 ${PORT}）..."
if [ -x ./darling-cloud ]; then
  exec ./darling-cloud start --host 0.0.0.0 --port "$PORT" --data ./data
else
  # 源码运行（开发/未打包）：自动装依赖并启动
  cd server
  python3 -m pip install -r requirements.txt -i https://mirrors.huaweicloud.com/repository/pypi/simple -q 2>/dev/null || true
  exec python3 cli.py start --host 0.0.0.0 --port "$PORT" --data ../data
fi
