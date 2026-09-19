# -*- coding: utf-8 -*-
"""RuntimeBridge —— 能力层。

职责：持有 BridgeClient，向上提供**带能力门禁**的工具调用入口。

为什么要在这一层再做一次门禁
----------------------------
Surface Manager 已经把不可用的工具从可见集摘除了，但那是"不给 AI 看见"。
这一层是"即使被调用也不放行" —— 双保险。AI 不能绕过分面直接调底层命令
（总基线 §14.1：AI 不直接控制底层 Backend）。
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from ..bridge import BridgeClient
from ..protocol.constants import LinkState, SessionState
from ..protocol.errors import ErrorCode, ProtocolError
from ..tools.spec import ToolSpec
from ..tools.specs import SPECS_BY_NAME


class RuntimeBridge:
    """MCP 工具面到 Android Runtime 的唯一通道。"""

    def __init__(
        self,
        endpoint: str,
        *,
        auto_reconnect: bool = True,
        on_event: Callable[[dict[str, Any]], None] | None = None,
        on_link_change: Callable[[LinkState, str], None] | None = None,
    ) -> None:
        self.client = BridgeClient(
            endpoint,
            auto_reconnect=auto_reconnect,
            on_event=on_event,
            on_link_change=on_link_change,
        )
        self._link_log: list[tuple[str, str, float]] = []

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def connect(self):
        return self.client.connect()

    def close(self) -> None:
        self.client.close()

    @property
    def endpoint(self) -> str:
        return self.client.endpoint

    @property
    def connected(self) -> bool:
        return self.client.connected

    @property
    def link_state(self) -> LinkState:
        return self.client.link_state

    @property
    def link_reason(self) -> str:
        return self.client.link_reason

    @property
    def session(self):
        return self.client.session

    @property
    def rtt_ms(self) -> float | None:
        return self.client.rtt_ms

    # ------------------------------------------------------------------
    # 能力
    # ------------------------------------------------------------------

    def capabilities(self) -> dict[str, dict[str, bool]]:
        """当前会话能力。没有 Session 时一律返回全 false。"""
        sess = self.client.session
        if sess is None:
            return {"runtime": {}, "network": {}}
        return sess.capabilities

    def capability_summary(self) -> dict[str, Any]:
        caps = self.capabilities()
        flat: dict[str, bool] = {}
        for group, items in caps.items():
            for key, value in items.items():
                flat[f"{group}.{key}"] = bool(value)
        return {
            "available": [k for k, v in flat.items() if v],
            "unavailable": [k for k, v in flat.items() if not v],
        }

    # ------------------------------------------------------------------
    # 调用
    # ------------------------------------------------------------------

    async def call(
        self,
        tool_or_command: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """按工具名（或命令名）调用，带能力门禁。

        阻塞 I/O 经 `asyncio.to_thread` 隔离 —— 直接同步调用会卡死事件循环，
        导致 progress / cancel / 其他工具全部停摆（总基线 §19.3）。
        """
        spec = SPECS_BY_NAME.get(tool_or_command)
        command = spec.command if spec else tool_or_command

        if not self.connected:
            raise ProtocolError(
                ErrorCode.E_NOT_READY,
                f"链路不可用（{self.link_state.value}）：{self.link_reason}",
                {"link": self.link_state.value, "endpoint": self.endpoint},
                next_step="等待自动重连完成；仍失败则检查目标 App 是否在运行",
            )

        sess = self.client.sessions.require()

        if spec is not None:
            gaps = spec.capability_gaps(sess.capabilities)
            if gaps:
                raise ProtocolError(
                    ErrorCode.E_NOT_READY,
                    f"工具 {spec.name} 依赖的能力不可用：{', '.join(gaps)}",
                    {
                        "tool": spec.name,
                        "missing_capabilities": gaps,
                        "session_state": sess.state.value,
                    },
                    next_step="该工具已从可见集摘除；先 session.capabilities 确认可用能力",
                )

        resp = await self.client.acall(command, payload, timeout=timeout)
        body = resp.get("payload")
        return body if isinstance(body, dict) else {"value": body}

    # ------------------------------------------------------------------
    # 观测
    # ------------------------------------------------------------------

    def events(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        return self.client.events(limit=limit)

    def drain_events(self) -> list[dict[str, Any]]:
        return self.client.drain_events()

    def snapshot(self) -> dict[str, Any]:
        """MCP 侧健康快照。"""
        sess = self.client.session
        return {
            "endpoint": self.endpoint,
            "link_state": self.link_state.value,
            "link_reason": self.link_reason,
            "rtt_ms": self.rtt_ms,
            "session": sess.to_dict() if sess else None,
            "session_generation": self.client.sessions.generation,
            "invalidated_sessions": list(self.client.sessions.history),
            "event_buffer": len(self.client.events()),
            "capabilities": self.capability_summary(),
        }

    # ------------------------------------------------------------------
    # 测试辅助
    # ------------------------------------------------------------------

    async def awarmup(self, timeout: float = 5.0) -> dict[str, Any]:
        """等链路就绪。"""
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            if self.connected and self.client.session is not None:
                return self.snapshot()
            await asyncio.sleep(0.05)
        raise ProtocolError(
            ErrorCode.E_NOT_READY,
            f"链路在 {timeout}s 内未就绪",
            self.snapshot(),
        )


def session_state_of(bridge: RuntimeBridge) -> SessionState:
    sess = bridge.session
    return sess.state if sess else SessionState.CLOSED
