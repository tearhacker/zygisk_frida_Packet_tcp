# -*- coding: utf-8 -*-
"""Session 对象与 Session Manager。

依据：总基线 §9 Session（唯一数据边界）· §9.3 看门狗 · §9.4 重连规则。

三条冻结纪律
------------
1. **Session 是唯一状态边界**：Hook / Memory / Network / MCP 都不得自己造 Session。
2. **禁止无限持有 Session**：任何"打开→操作→关闭"三段式必须有 TTL，
   忘记关闭的代价是"自动过期"而不是"永久泄漏"。
3. **重连不恢复旧 Session**：断开即 INVALID，重连即新建，
   runtime / network / correlation 全部重来。

`generation` 是这套规则的执行机制：每次新建 Session 自增一次。
客户端持有的 (session_id, generation) 只要 generation 落后，就是幽灵 Session。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from ..protocol.constants import SESSION_IDLE_TIMEOUT, SessionState
from ..protocol.errors import ErrorCode, ProtocolError


@dataclass
class Session:
    """一次目标 App 分析的完整生命周期。"""

    session_id: str
    generation: int
    state: SessionState = SessionState.CREATED
    capabilities: dict[str, dict[str, bool]] = field(default_factory=dict)
    created_at: float = field(default_factory=time.monotonic)
    last_activity: float = field(default_factory=time.monotonic)
    package: str | None = None
    pid: int | None = None
    abi: str | None = None
    sdk: int | None = None

    def touch(self) -> None:
        """记录一次活动，用于空闲超时判定。"""
        self.last_activity = time.monotonic()

    @property
    def idle_seconds(self) -> float:
        return time.monotonic() - self.last_activity

    @property
    def age_seconds(self) -> float:
        return time.monotonic() - self.created_at

    @property
    def is_live(self) -> bool:
        return self.state not in (
            SessionState.CLOSED,
            SessionState.FAILED,
            SessionState.ERROR,
        )

    def capability(self, group: str, name: str) -> bool:
        """查询某项能力。未声明一律视为不可用 —— 不许凭空声称有能力。"""
        return bool(self.capabilities.get(group, {}).get(name, False))

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "generation": self.generation,
            "state": self.state.value,
            "package": self.package,
            "pid": self.pid,
            "abi": self.abi,
            "sdk": self.sdk,
            "age_seconds": round(self.age_seconds, 3),
            "idle_seconds": round(self.idle_seconds, 3),
            "capabilities": self.capabilities,
        }


class SessionManager:
    """当前 Session 的唯一持有者。"""

    def __init__(self, *, idle_timeout: float = SESSION_IDLE_TIMEOUT) -> None:
        self._current: Session | None = None
        self._generation = 0
        self._idle_timeout = idle_timeout
        self._history: list[str] = []

    # -- 读 ---------------------------------------------------------------

    @property
    def current(self) -> Session | None:
        return self._current

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def history(self) -> tuple[str, ...]:
        """已失效的 Session id 列表，用于诊断与 stale 判定。"""
        return tuple(self._history)

    def is_current(self, session_id: str | None) -> bool:
        return (
            self._current is not None
            and session_id is not None
            and session_id == self._current.session_id
        )

    def require(self) -> Session:
        """取当前 Session，没有就抛 E_NOT_READY。"""
        if self._current is None or not self._current.is_live:
            raise ProtocolError(
                ErrorCode.E_NOT_READY,
                "当前没有可用的 Session",
                {"generation": self._generation},
                next_step="等待 Runtime 建立 Session，或检查目标 App 是否已启动",
            )
        return self._current

    def require_matching(self, session_id: str | None) -> Session:
        """按 id 取 Session。不匹配即 E_SESSION_STALE。"""
        sess = self.require()
        if session_id != sess.session_id:
            raise ProtocolError(
                ErrorCode.E_SESSION_STALE,
                "session_id 已失效（重连后旧 Session 不恢复）",
                {"got": session_id, "current": sess.session_id},
                next_step="重新 session.list 获取新 Session",
            )
        return sess

    # -- 写 ---------------------------------------------------------------

    def open(
        self,
        session_id: str,
        *,
        state: SessionState = SessionState.RUNNING,
        capabilities: dict[str, dict[str, bool]] | None = None,
    ) -> Session:
        """新建 Session。

        若有旧 Session 存在，先强制失效 —— 这就是"重连不恢复旧 Session"的落点。
        """
        if self._current is not None:
            self._retire(self._current, SessionState.CLOSED)
        self._generation += 1
        self._current = Session(
            session_id=session_id,
            generation=self._generation,
            state=state,
            capabilities=capabilities or {},
        )
        return self._current

    def degrade(self, reason: str) -> Session | None:
        """把当前 Session 标记为 DEGRADED。"""
        if self._current is None:
            return None
        self._current.state = SessionState.DEGRADED
        return self._current

    def close(self, state: SessionState = SessionState.CLOSED) -> None:
        if self._current is not None:
            self._retire(self._current, state)
            self._current = None

    def _retire(self, sess: Session, state: SessionState) -> None:
        sess.state = state
        self._history.append(sess.session_id)

    # -- 看门狗 -----------------------------------------------------------

    def sweep(self) -> bool:
        """空闲超时清扫。返回是否发生了过期关闭。"""
        if self._current is None:
            return False
        if self._current.idle_seconds <= self._idle_timeout:
            return False
        self.close(SessionState.CLOSED)
        return True

    def touch(self) -> None:
        if self._current is not None:
            self._current.touch()
