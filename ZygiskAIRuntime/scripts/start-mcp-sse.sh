#!/usr/bin/env bash
# 启动 MCP Server（SSE 常驻模式）。
#
# SSE 模式下**服务端必须先跑起来**，客户端才连得上：
# 没起服务就在客户端点连接，会报
#   SSE error: TypeError: fetch failed: connect ECONNREFUSED 127.0.0.1:60501
# 这不是配置写错，是 60501 上没人监听。
#
# 用法（Git Bash / WSL）：
#   bash scripts/start-mcp-sse.sh            # Mock 后端，无需真机
#   bash scripts/start-mcp-sse.sh --device   # 连真机（先 adb forward tcp:60500 tcp:60500）
#
# 可用环境变量覆盖：
#   ZAI_PYTHON  指定 Python（默认本机装了 mcp SDK 的 venv）
#   ZAI_PORT    监听端口（默认 60501）
#
# 客户端配置（服务起来后填这个即可）：
#   { "mcpServers": { "zy_packet_tearhacker": { "type": "sse",
#                     "url": "http://127.0.0.1:60501/sse" } } }

set -euo pipefail
cd "$(dirname "$0")/.."

PY="${ZAI_PYTHON:-C:/Users/52334/.workbuddy-ai/binaries/python/envs/default/Scripts/python.exe}"
PORT="${ZAI_PORT:-60501}"

if [[ "${1:-}" == "--device" ]]; then
  set -- --endpoint tcp:127.0.0.1:60500
else
  set -- --mock
fi

echo "[start-mcp-sse] python: $PY"
echo "[start-mcp-sse] 端口:   $PORT"
echo "[start-mcp-sse] 参数:   $*"
exec "$PY" -m ai_analyzer.host "$@" --transport sse --port "$PORT"
