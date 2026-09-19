# -*- coding: utf-8 -*-
"""错误映射层（L3 门禁层）。

依据：总基线 §10.8 错误分层。

    ┌──────────────────────────────────────────────────────────────┐
    │ 协议层错误（AI 调错了）                                        │
    │   未知命令 / 参数校验失败 / 版本不匹配 / JSON 解析失败           │
    │   → MCPError → JSON-RPC error                                │
    ├──────────────────────────────────────────────────────────────┤
    │ 执行层失败（调用合法但后端失败）                                │
    │   读内存失败 / 权限被拒 / 进程已退出 / 扫描无结果                │
    │   → ToolError → isError=true 的 tool result                   │
    └──────────────────────────────────────────────────────────────┘

**混为一谈 = AI 无法自我纠错**：该改参数时它去重试，该换策略时它改参数。

无论哪一层，`data` / 消息里都必须带 `code / layer / message / context /
retryable / next_step` 六项 —— 错误消息必须可行动，只说「操作失败」会让 AI
陷入无限重试。
"""

from __future__ import annotations

import functools
import json
from typing import Any, Awaitable, Callable

from mcp.server.mcpserver.exceptions import ToolError
from mcp.shared.exceptions import INVALID_REQUEST, MCPError

from ..protocol.errors import ErrorLayer, ProtocolError


def to_mcp_exception(exc: ProtocolError) -> Exception:
    """把 ProtocolError 映射成 MCP 侧的正确错误形态。"""
    payload = exc.to_dict()
    if exc.layer is ErrorLayer.PROTOCOL:
        # 协议层 → 顶层 JSON-RPC error
        return MCPError(INVALID_REQUEST, exc.message, payload)
    # 执行层 → isError=true 的 tool result
    return ToolError(json.dumps(payload, ensure_ascii=False))


def wrap_tool(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """给工具处理函数套上错误映射。

    用 `functools.wraps` 保留原始签名 —— MCP SDK 从签名派生 inputSchema，
    签名丢了工具就没参数了。
    """

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await fn(*args, **kwargs)
        except ProtocolError as exc:
            raise to_mcp_exception(exc) from exc

    return wrapper


def describe_error_contract() -> dict[str, Any]:
    """错误契约摘要，用于自检与文档回写。"""
    from ..protocol.errors import ERROR_META

    protocol_layer = sorted(
        c.value for c, m in ERROR_META.items() if m.layer is ErrorLayer.PROTOCOL
    )
    execution_layer = sorted(
        c.value for c, m in ERROR_META.items() if m.layer is ErrorLayer.EXECUTION
    )
    return {
        "protocol_layer_codes": protocol_layer,
        "protocol_layer_returns": "JSON-RPC error (MCPError)",
        "execution_layer_codes": execution_layer,
        "execution_layer_returns": "isError=true tool result (ToolError)",
        "error_fields": ["code", "layer", "message", "context", "retryable", "next_step"],
    }
