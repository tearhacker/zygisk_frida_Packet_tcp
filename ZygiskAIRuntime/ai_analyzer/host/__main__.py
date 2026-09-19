# -*- coding: utf-8 -*-
"""MCP Server 启动入口。

用法
----
    # 用 Mock 后端跑通全链路（无真机、无 NDK）
    python -m ai_analyzer.host --mock

    # 连真机 Runtime（需先 adb forward 或设备侧 UDS）
    python -m ai_analyzer.host --endpoint tcp:127.0.0.1:60500

    # 只做装配自检并打印可见工具，不启动服务
    python -m ai_analyzer.host --mock --check

    # 【推荐对接方式】常驻 HTTP 服务 —— 客户端只填 URL，不必 spawn 进程
    python -m ai_analyzer.host --mock --transport sse --port 60501
    #   启动后会打印可直接复制的客户端配置，形如：
    #   {"type": "sse", "url": "http://127.0.0.1:60501/sse"}
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from ..mock import MockRuntimeServer
from ..protocol.constants import DEFAULT_TCP_ENDPOINT
from .server import build_from_endpoint, describe

# HTTP 传输的默认监听参数。
#
# 端口刻意取 60501：60500 已裁定给「设备侧 Runtime IPC」。
# 这俩不是一回事 —— 60500 是 PC↔手机 的 IPC，60501 是 MCP 客户端↔本服务 的 HTTP。
# 错开一位只为不混淆，改之前先想清楚动的是哪一层。
DEFAULT_HTTP_HOST = "127.0.0.1"
DEFAULT_HTTP_PORT = 60501
SSE_PATH = "/sse"
STREAMABLE_HTTP_PATH = "/mcp"

# 客户端 mcp.json 里 `type` 字段的取值（各客户端写法略有差异，这里取主流写法）
CLIENT_TYPE_BY_TRANSPORT = {"sse": "sse", "streamable-http": "http"}


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m ai_analyzer.host", description="AI Analyzer MCP Server")
    p.add_argument(
        "--endpoint",
        default=None,
        help=f"IPC 端点。unix:/path 或 tcp:host:port（默认 {DEFAULT_TCP_ENDPOINT}）",
    )
    p.add_argument("--mock", action="store_true", help="同时启动 Mock Runtime 后端")
    p.add_argument(
        "--mount",
        default="",
        help="逗号分隔的 Expert 组，例如 'Memory+,Packet+,Job'；留空表示不挂载",
    )
    p.add_argument("--check", action="store_true", help="只做装配自检并打印工具清单")
    p.add_argument("--transport", default="stdio", choices=["stdio", "sse", "streamable-http"])
    p.add_argument(
        "--host",
        default=DEFAULT_HTTP_HOST,
        help=f"HTTP 传输监听地址（默认 {DEFAULT_HTTP_HOST}）",
    )
    p.add_argument(
        "--port",
        type=int,
        default=DEFAULT_HTTP_PORT,
        help=f"HTTP 传输监听端口（默认 {DEFAULT_HTTP_PORT}）",
    )
    p.add_argument(
        "--path",
        default=None,
        help=f"HTTP 路径覆盖（sse 默认 {SSE_PATH}，streamable-http 默认 {STREAMABLE_HTTP_PATH}）",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    mock_server: MockRuntimeServer | None = None
    endpoint = args.endpoint

    if args.mock:
        if endpoint is None:
            # 端口 0 让系统分配，避免占用冲突
            endpoint = "tcp:127.0.0.1:0"
        mock_server = MockRuntimeServer(endpoint).start()
        endpoint = mock_server.endpoint
        print(f"[mock] Runtime 后端已启动：{endpoint}", file=sys.stderr)

    if endpoint is None:
        endpoint = DEFAULT_TCP_ENDPOINT

    mounted = tuple(g.strip() for g in args.mount.split(",") if g.strip())

    try:
        bridge, server, sm, registered = build_from_endpoint(
            endpoint, mounted_groups=mounted
        )
    except Exception as exc:  # noqa: BLE001
        print(f"装配失败：{exc}", file=sys.stderr)
        if mock_server is not None:
            mock_server.stop()
        return 2

    summary = describe(server, sm)
    snapshot = bridge.snapshot()
    report = {
        "endpoint": endpoint,
        "registered_total": len(registered),
        "registered": registered,
        "session": snapshot["session"],
        "capabilities": snapshot["capabilities"],
        **summary,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2), file=sys.stderr)

    if args.check:
        tools = asyncio.run(server.list_tools())
        print(
            json.dumps(
                {
                    "tools_list_count": len(tools),
                    "tools_list_names": [t.name for t in tools],
                    "names_match_registered": [t.name for t in tools] == registered,
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        bridge.close()
        if mock_server is not None:
            mock_server.stop()
        return 0

    def _shutdown() -> None:
        bridge.close()
        if mock_server is not None:
            mock_server.stop()

    if args.transport == "stdio":
        try:
            server.run(transport="stdio")
        finally:
            _shutdown()
        return 0

    # sse / streamable-http：起常驻 HTTP 服务，客户端只填 URL 即可接入。
    http_kwargs: dict[str, Any] = {"host": args.host, "port": args.port}
    if args.transport == "sse":
        path = args.path or SSE_PATH
        http_kwargs["sse_path"] = path
    else:
        path = args.path or STREAMABLE_HTTP_PATH
        http_kwargs["streamable_http_path"] = path

    url = f"http://{args.host}:{args.port}{path}"
    client_type = CLIENT_TYPE_BY_TRANSPORT[args.transport]
    print(f"[mcp] {args.transport} 监听中：{url}", file=sys.stderr)
    print(f'[mcp] 客户端配置：{{"type": "{client_type}", "url": "{url}"}}', file=sys.stderr)

    try:
        server.run(transport=args.transport, **http_kwargs)  # type: ignore[arg-type]
    finally:
        _shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
