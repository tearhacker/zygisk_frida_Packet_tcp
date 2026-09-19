# -*- coding: utf-8 -*-
"""MCP Server 门面层（L6）。

职责：装配 FastMCP/MCPServer 实例并注册工具。**不写业务逻辑**。

架构位置
--------
    AI → Tool Surface Manager → MCP Server → RuntimeBridge → Bridge → IPC → Runtime

AI 不允许直接碰 Frida / Gum / LSPlant / ADB / mitmproxy（总基线 §14.1）。
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from ..protocol.constants import PROTOCOL_VERSION
from ..tools.handlers import ToolHandlers
from .registry import bind_tools, verify_three_point_registration
from .runtime_bridge import RuntimeBridge
from .surfaces import SurfaceManager

SERVER_INSTRUCTIONS = """\
Android AI Dynamic Analysis Platform —— 运行时动态分析控制面。

工作纪律（必须遵守）：
1. 动手前先调 session.capabilities 确认可用能力。能力为 false 的工具已被摘除，不要试。
2. 探活用 runtime.status。任何超时之后先探活，不要盲目重试。
3. 执行型工具禁止把 accepted 当 verified。看 execution.verified 与 events_observed。
4. HTTPS 五级状态逐级如实上报：captured / decoded / decrypted / interceptable / modifiable。
   抓到 ≠ 解密，解密 ≠ 能改。禁止跨级推断。
5. 写操作（memory.write / packet.modify）必须显式传 confirm=true 才执行。
6. 大对象（PCAP / dump / trace）只回 metadata + sha256，需要内容走 Artifact 通道。
7. 重连后 session_id 一定变化，旧 id 已失效，不要复用。
8. 零命中不等于不存在。返回里带候选与搜索范围，据此换策略而不是下结论。
"""


def build_server(
    bridge: RuntimeBridge,
    *,
    surfaces: SurfaceManager | None = None,
    capabilities: dict[str, dict[str, bool]] | None = None,
    name: str = "ai-analyzer-mcp",
    version: str = PROTOCOL_VERSION,
    instructions: str = SERVER_INSTRUCTIONS,
    strict_registration: bool = True,
) -> tuple[MCPServer, SurfaceManager, list[str]]:
    """装配 MCP Server。

    返回 (server, surfaces, registered_tool_names)。

    capabilities 决定哪些工具被注册：
      - None  → 注册全部（含全部 Expert 组），用于静态契约检查
      - 传入  → 按能力过滤，不可用的工具**不注册**
    """
    sm = surfaces or SurfaceManager()
    sm.assert_budget()

    if strict_registration:
        problems = verify_three_point_registration(sm)
        if problems:
            raise RuntimeError("注册三件套不一致：\n  " + "\n  ".join(problems))

    handlers = ToolHandlers(bridge)
    server = MCPServer(name=name, version=version, instructions=instructions)

    registered = bind_tools(server, handlers, sm, capabilities=capabilities)
    return server, sm, registered


def build_from_endpoint(
    endpoint: str,
    *,
    auto_reconnect: bool = True,
    mounted_groups: tuple[str, ...] = (),
    name: str = "ai-analyzer-mcp",
    connect: bool = True,
) -> tuple[RuntimeBridge, MCPServer, SurfaceManager, list[str]]:
    """一步到位：连上 Runtime 并装配好 Server。"""
    bridge = RuntimeBridge(endpoint, auto_reconnect=auto_reconnect)
    if connect:
        bridge.connect()

    sm = SurfaceManager(mounted_groups=mounted_groups)
    caps = bridge.capabilities() if connect else None
    server, sm, registered = build_server(bridge, surfaces=sm, capabilities=caps)
    return bridge, server, sm, registered


def describe(server: MCPServer, sm: SurfaceManager) -> dict[str, Any]:
    """装配结果摘要，用于验收输出。"""
    return {
        "surface": sm.report().to_dict(),
        "budget": sm.budget_report(),
        "expert_groups_available": list(sm.all_groups),
        "expert_groups_mounted": list(sm.mounted_groups),
    }
