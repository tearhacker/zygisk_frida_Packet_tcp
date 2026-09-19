# -*- coding: utf-8 -*-
"""MCP Server 启动入口。

用法
----
    # 用 Mock 后端跑通全链路（无真机、无 NDK）
    python -m ai_analyzer.host --mock

    # 连真机 Runtime（需先 adb forward 或设备侧 UDS）
    python -m ai_analyzer.host --endpoint tcp:127.0.0.1:27901

    # 只做装配自检并打印可见工具，不启动 stdio 服务
    python -m ai_analyzer.host --mock --check
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from ..mock import MockRuntimeServer
from ..protocol.constants import DEFAULT_TCP_ENDPOINT
from .server import build_from_endpoint, describe


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

    try:
        server.run(transport=args.transport)  # type: ignore[arg-type]
    finally:
        bridge.close()
        if mock_server is not None:
            mock_server.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
