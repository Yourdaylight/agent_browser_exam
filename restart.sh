#!/bin/bash
# Agent Browser Exam 重启脚本
set -e

PORT=8080
DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="/tmp/agent-browser-exam.log"

echo ">>> 停止旧进程..."
lsof -ti :$PORT | xargs kill -9 2>/dev/null || true
sleep 1

echo ">>> 启动服务 (port=$PORT, reload=on)..."
cd "$DIR"
nohup uv run uvicorn server.main:app --host 0.0.0.0 --port $PORT --reload > "$LOG" 2>&1 &
sleep 2

if curl -s -o /dev/null -w "%{http_code}" http://localhost:$PORT/ | grep -q 200; then
    echo ">>> 服务启动成功 ✓  http://localhost:$PORT"
else
    echo ">>> 启动失败，查看日志: tail -f $LOG"
    exit 1
fi
