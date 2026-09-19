# -*- coding: utf-8 -*-
"""MCP Server 命令行入口 —— **唯一**的参数定义处。

`python -m ai_analyzer.host` 与顶层 `mcp_server.py` 都走这里，
保证两种启动方式的参数、默认值、行为完全一致（常量/参数单一源）。

两种客户端对接形态
------------------
1) stdio（推荐，也是默认）—— 客户端 spawn 进程，用 stdin/stdout 说 JSON-RPC：:

       {"mcpServers": {"zy_packet_tearhacker": {
           "command": "C:/Users/.../python.exe",
           "args": ["D:/.../ZygiskAIRuntime/mcp_server.py",
                    "--port", "27184",
                    "--adb", "C:/Program Files/platform-tools/adb.exe"]}}}

   端口、adb 都可以不写：不写就用默认值。

2) sse —— 常驻 HTTP，客户端只填 url：:

       python mcp_server.py --transport sse --port 60501
       {"mcpServers": {"zy_packet_tearhacker": {"type": "sse",
                       "url": "http://127.0.0.1:60501/sse"}}}

端口分两层，别混
----------------
    --port         MCP 客户端 ↔ 本服务（HTTP 传输才用得上，默认 60501）
    --device-port  PC ↔ 手机 Runtime IPC（默认 60500，adb forward 用的就是它）

IPC 失败不阻断启动：adb 不在 / 设备 offline / Runtime 没起来，
服务照常启动、照常响应，工具返回 E_NOT_READY。禁止把失败伪装成成功。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from ..mock import MockRuntimeServer
from ..protocol.constants import DEFAULT_TCP_PORT
from .adb import DEFAULT_ADB_TIMEOUT, default_adb_path, ensure_forward, resolve_adb
from .runtime_bridge import RuntimeBridge
from .server import build_server, describe
from .surfaces import SurfaceManager

# HTTP 传输的默认监听参数。
#
# 端口刻意取 60501：60500 已裁定给「设备侧 Runtime IPC」。
# 这俩不是一回事 —— 60500 是 PC↔手机 的 IPC，60501 是 MCP 客户端↔本服务 的 HTTP。
# 错开一位只为不混淆，改之前先想清楚动的是哪一层。
DEFAULT_HTTP_HOST = "127.0.0.1"
DEFAULT_HTTP_PORT = 60501
SSE_PATH = "/sse"
STREAMABLE_HTTP_PATH = "/mcp"
DEFAULT_SERVER_NAME = "ai-analyzer-mcp"

# 客户端 mcp.json 里 `type` 字段的取值（各客户端写法略有差异，这里取主流写法）
CLIENT_TYPE_BY_TRANSPORT = {"sse": "sse", "streamable-http": "http"}

# 顶层单文件入口（供客户端 command+args 拉起）：ZygiskAIRuntime/mcp_server.py
ENTRY_SCRIPT = Path(__file__).resolve().parents[2] / "mcp_server.py"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="mcp_server.py",
        description="Zygisk AI Runtime —— MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    p.add_argument("--adb", default=None, help=f"adb 可执行文件路径（默认 {default_adb_path()}）")
    p.add_argument(
        "--device-port",
        type=int,
        default=DEFAULT_TCP_PORT,
        help=f"设备侧 Runtime IPC 端口，adb forward 两端都用它（默认 {DEFAULT_TCP_PORT}）",
    )
    p.add_argument(
        "--no-forward",
        action="store_true",
        help="不自动建 adb forward（你自己保证 60500 已通时才用）",
    )
    p.add_argument("--serial", default=None, help="设备序列号（多台设备时指定）")
    p.add_argument(
        "--adb-timeout",
        type=float,
        default=DEFAULT_ADB_TIMEOUT,
        help=f"单次 adb 调用超时秒数（默认 {DEFAULT_ADB_TIMEOUT}）",
    )

    p.add_argument(
        "--endpoint",
        default=None,
        help=f"直接指定 IPC 端点（unix:/path 或 tcp:host:port）；给了它就不走 adb forward",
    )
    p.add_argument("--mock", action="store_true", help="用 Mock Runtime 后端（不需要真机）")
    p.add_argument(
        "--mount",
        default="",
        help="逗号分隔的 Expert 组，例如 'Memory+,Packet+,Job'；留空表示不挂载",
    )
    p.add_argument("--check", action="store_true", help="只做装配自检并打印工具清单，不启动服务")
    p.add_argument(
        "--print-config",
        action="store_true",
        help="只打印可直接粘贴的客户端 mcp.json 片段，然后退出",
    )

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
        help=f"HTTP 传输监听端口，仅 sse/streamable-http 生效（默认 {DEFAULT_HTTP_PORT}）",
    )
    p.add_argument(
        "--path",
        default=None,
        help=f"HTTP 路径覆盖（sse 默认 {SSE_PATH}，streamable-http 默认 {STREAMABLE_HTTP_PATH}）",
    )
    p.add_argument("--server-name", default=DEFAULT_SERVER_NAME, help="MCP Server 名称")
    return p.parse_args(argv)


def _client_args(args: argparse.Namespace) -> list[str]:
    """把当前参数翻译回命令行（只带非默认项，配置尽量短）。"""
    out: list[str] = []
    if args.server_name != DEFAULT_SERVER_NAME:
        out += ["--server-name", args.server_name]
    if args.mock:
        out.append("--mock")
    if args.mount:
        out += ["--mount", args.mount]
    if args.adb and args.adb != default_adb_path():
        out += ["--adb", args.adb]
    if args.device_port != DEFAULT_TCP_PORT:
        out += ["--device-port", str(args.device_port)]
    if args.serial:
        out += ["--serial", args.serial]
    if args.no_forward:
        out.append("--no-forward")
    if args.endpoint:
        out += ["--endpoint", args.endpoint]
    if args.transport != "stdio":
        out += ["--transport", args.transport, "--host", args.host, "--port", str(args.port)]
    if args.path:
        out += ["--path", args.path]
    return out


def client_config(args: argparse.Namespace, *, python: str | None = None) -> dict[str, Any]:
    """生成可直接粘贴进客户端的 mcp.json 片段。"""
    name = args.server_name
    if args.transport == "stdio":
        entry = str(ENTRY_SCRIPT).replace("\\", "/")
        return {
            "mcpServers": {
                name: {
                    "command": python or sys.executable.replace("\\", "/"),
                    "args": [entry, *_client_args(args)],
                }
            }
        }

    path = args.path or (SSE_PATH if args.transport == "sse" else STREAMABLE_HTTP_PATH)
    url = f"http://{args.host}:{args.port}{path}"
    return {
        "mcpServers": {
            name: {
                "type": CLIENT_TYPE_BY_TRANSPORT[args.transport],
                "url": url,
            }
        }
    }


def _prepare_forward(args: argparse.Namespace) -> tuple[str | None, dict[str, Any] | None]:
    """按需建立 adb forward。

    返回 (endpoint_or_None, forward_报告或None)。
    失败不抛异常 —— 服务照常起，连不上由工具层如实报 E_NOT_READY。
    """
    adb_path = args.adb or default_adb_path()
    resolved, why = resolve_adb(adb_path)
    print(f"[adb] {why}", file=sys.stderr)

    if resolved is None:
        return None, {"ok": False, "detail": why}

    result = ensure_forward(
        resolved,
        args.device_port,
        args.device_port,
        serial=args.serial,
        timeout=args.adb_timeout,
    )
    report = result.as_dict()
    if result.verified:
        print(f"[adb] forward 已就绪：tcp:{args.device_port} -> 设备 tcp:{args.device_port}", file=sys.stderr)
    else:
        print(
            f"[adb] ⚠ forward 未生效：{result.detail}\n"
            f"[adb]   设备侧要先 adb forward tcp:{args.device_port} tcp:{args.device_port}，"
            f"否则 Runtime 工具会返回 E_NOT_READY",
            file=sys.stderr,
        )
    return f"tcp:127.0.0.1:{args.device_port}", report


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if args.print_config:
        # 这条走 stdout：它就是给用户复制的，且打印完立刻退出，不会污染 stdio 通道。
        print(json.dumps(client_config(args), ensure_ascii=False, indent=2))
        return 0

    mock_server: MockRuntimeServer | None = None
    endpoint = args.endpoint
    forward_report: dict[str, Any] | None = None

    if args.mock:
        if endpoint is None:
            # 端口 0 让系统分配，避免占用冲突
            endpoint = "tcp:127.0.0.1:0"
        mock_server = MockRuntimeServer(endpoint).start()
        endpoint = mock_server.endpoint
        print(f"[mock] Runtime 后端已启动：{endpoint}", file=sys.stderr)
    elif endpoint is None and not args.no_forward:
        endpoint, forward_report = _prepare_forward(args)

    if endpoint is None:
        endpoint = f"tcp:127.0.0.1:{args.device_port}"

    if args.transport == "stdio" and args.port != DEFAULT_HTTP_PORT:
        print(
            f"[warn] stdio 传输不监听端口，--port {args.port} 不生效；"
            f"要改设备侧端口请用 --device-port",
            file=sys.stderr,
        )

    mounted = tuple(g.strip() for g in args.mount.split(",") if g.strip())

    # 🔴 连不上 Runtime 时**不许让服务起不来**。
    #
    # stdio 模式下客户端是 spawn 本进程的：进程一退出，用户在客户端里
    # 只能看到一个"连接失败"，而工具层精心准备的 E_NOT_READY
    # （带链路状态、endpoint、下一步该查什么）全都没机会呈现 ——
    # 排障信息在最需要它的地方被吞掉了。
    #
    # 所以：照常注册工具、照常起服务，让调用方拿到结构化的 E_NOT_READY。
    bridge = RuntimeBridge(endpoint, auto_reconnect=True)
    link_error: str | None = None
    try:
        bridge.connect()
    except Exception as exc:  # noqa: BLE001
        link_error = str(exc)
        print(f"[ipc] ⚠ Runtime 未就绪：{link_error}", file=sys.stderr)
        print(
            f"[ipc]   端点 {endpoint}。adb forward 建好 ≠ Runtime 起来了：\n"
            f"[ipc]   模块没刷 / 目标 App 没重启 / 设备没 root 都会是这个结果",
            file=sys.stderr,
        )

    try:
        sm = SurfaceManager(mounted_groups=mounted)
        # 未连上时 capabilities 必须传 None（= 不过滤）：
        # 若按"当前能力"过滤，能力全空会把工具整批摘掉，
        # 客户端一个工具都看不到 —— 那比"看得见但调用报 E_NOT_READY"更难排查。
        caps = None if link_error else bridge.capabilities()
        server, sm, registered = build_server(
            bridge, surfaces=sm, capabilities=caps, name=args.server_name
        )
    except Exception as exc:  # noqa: BLE001
        print(f"装配失败：{exc}", file=sys.stderr)
        bridge.close()
        if mock_server is not None:
            mock_server.stop()
        return 2

    summary = describe(server, sm)
    snapshot = bridge.snapshot()
    report: dict[str, Any] = {
        "endpoint": endpoint,
        "transport": args.transport,
        "link_error": link_error,
        "registered_total": len(registered),
        "registered": registered,
        "session": snapshot["session"],
        "capabilities": snapshot["capabilities"],
        **summary,
    }
    if forward_report is not None:
        report["adb_forward"] = forward_report
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
