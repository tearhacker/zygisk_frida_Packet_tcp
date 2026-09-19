# -*- coding: utf-8 -*-
"""九种协议消息的构造与校验。

依据：总基线 §7.1 统一事件格式 · §10.2~10.6 连接流程 / 消息三态。

九种消息：HELLO · HELLO_ACK · READY · REQUEST · RESPONSE · EVENT · PING · PONG · ERROR

⚠️ 已登记的口径不一致（实现按文档原样，不改文档）
------------------------------------------------
总基线里 HELLO / HELLO_ACK 用字段 `protocol`，
而 REQUEST / RESPONSE / EVENT 用字段 `version`，两者语义相同。
本模块按文档原样实现，并提供 `protocol_version_of()` 做归一化读取。
是否统一字段名属协议变更，需先改文档与黄金样例（工程纪律 §19.6），
已记入待裁决项。
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from . import commands
from .constants import (
    CAPABILITY_KEYS_NETWORK,
    CAPABILITY_KEYS_RUNTIME,
    CLIENT_NAME,
    CLIENT_VERSION,
    EVENT_TYPES,
    PROTOCOL_VERSION,
    SERVER_NAME,
    SERVER_VERSION,
    MessageType,
    SessionState,
)
from .errors import ErrorCode, ProtocolError, protocol_version_mismatch

# ---------------------------------------------------------------------------
# ID 生成
# ---------------------------------------------------------------------------


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def new_session_id() -> str:
    return _new_id("sess")


def new_request_id() -> str:
    return _new_id("req")


def new_event_id() -> str:
    return _new_id("evt")


def new_job_id() -> str:
    return _new_id("job")


def now_ms() -> int:
    """毫秒时间戳。协议内所有 timestamp 统一毫秒整数。"""
    return int(time.time() * 1000)


# ---------------------------------------------------------------------------
# 构造器
# ---------------------------------------------------------------------------


def make_hello(
    *,
    client: str = CLIENT_NAME,
    client_version: str = CLIENT_VERSION,
    capabilities: list[str] | None = None,
    protocol: str = PROTOCOL_VERSION,
) -> dict[str, Any]:
    """客户端首帧。"""
    return {
        "type": MessageType.HELLO.value,
        "protocol": protocol,
        "client": client,
        "client_version": client_version,
        "capabilities": list(capabilities)
        if capabilities is not None
        else ["runtime", "memory", "network", "packet"],
    }


def make_hello_ack(
    *,
    session_id: str,
    server: str = SERVER_NAME,
    server_version: str = SERVER_VERSION,
    capabilities: list[str] | None = None,
    protocol: str = PROTOCOL_VERSION,
) -> dict[str, Any]:
    """服务端应答，携带新建的 session_id。"""
    return {
        "type": MessageType.HELLO_ACK.value,
        "protocol": protocol,
        "server": server,
        "server_version": server_version,
        "session_id": session_id,
        "capabilities": list(capabilities) if capabilities is not None else [],
    }


def make_ready(
    *,
    session_id: str,
    state: SessionState = SessionState.RUNNING,
    capabilities: dict[str, dict[str, bool]] | None = None,
) -> dict[str, Any]:
    """握手完成、可以收命令。

    capabilities 必须如实反映后端真实能力——不可用时上报 false，
    由 Tool Surface Manager 摘除对应工具，而不是等 AI 调了才报错。
    """
    if capabilities is None:
        capabilities = {
            "runtime": {k: False for k in CAPABILITY_KEYS_RUNTIME},
            "network": {k: False for k in CAPABILITY_KEYS_NETWORK},
        }
    return {
        "version": PROTOCOL_VERSION,
        "type": MessageType.READY.value,
        "session_id": session_id,
        "timestamp": now_ms(),
        "state": state.value,
        "capabilities": capabilities,
    }


def make_request(
    *,
    command: str,
    payload: dict[str, Any] | None = None,
    session_id: str,
    request_id: str | None = None,
) -> dict[str, Any]:
    """一条命令请求。"""
    if not commands.is_known(command):
        raise ProtocolError(
            ErrorCode.E_UNKNOWN_CMD,
            f"未知命令：{command}",
            {"command": command},
            next_step="改用 commands.ALL_COMMANDS 中的命令",
        )
    return {
        "version": PROTOCOL_VERSION,
        "type": MessageType.REQUEST.value,
        "request_id": request_id or new_request_id(),
        "session_id": session_id,
        "timestamp": now_ms(),
        "command": command,
        "payload": dict(payload or {}),
    }


def make_response(
    *,
    request_id: str,
    session_id: str,
    status: str = "ok",
    code: str = "OK",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """命令应答。

    ⚠️ status="ok" 只代表**调用成功**，不代表业务已验证生效。
    执行型命令必须额外返回 accepted / executed / verified 三态
    （总基线 §12.5 禁止 Fake Success）。
    """
    return {
        "version": PROTOCOL_VERSION,
        "type": MessageType.RESPONSE.value,
        "request_id": request_id,
        "session_id": session_id,
        "timestamp": now_ms(),
        "status": status,
        "code": code,
        "payload": dict(payload or {}),
    }


def make_event(
    *,
    event_type: str,
    session_id: str,
    source: str,
    payload: dict[str, Any] | None = None,
    pid: int | None = None,
    tid: int | None = None,
    event_id: str | None = None,
    timestamp: int | None = None,
) -> dict[str, Any]:
    """事件。所有 Runtime / Network 事件统一走这个格式。"""
    if event_type not in EVENT_TYPES:
        raise ProtocolError(
            ErrorCode.E_BAD_ARGS,
            f"未知事件类型：{event_type}",
            {"event_type": event_type, "known_count": len(EVENT_TYPES)},
        )
    if source not in ("runtime", "network", "session", "system"):
        raise ProtocolError(
            ErrorCode.E_BAD_ARGS,
            f"未知事件来源：{source}",
            {"source": source},
        )
    return {
        "version": PROTOCOL_VERSION,
        "type": MessageType.EVENT.value,
        "event_id": event_id or new_event_id(),
        "session_id": session_id,
        "timestamp": timestamp if timestamp is not None else now_ms(),
        "pid": pid,
        "tid": tid,
        "event_type": event_type,
        "source": source,
        "payload": dict(payload or {}),
    }


def make_ping(*, seq: int = 0) -> dict[str, Any]:
    return {
        "version": PROTOCOL_VERSION,
        "type": MessageType.PING.value,
        "timestamp": now_ms(),
        "seq": seq,
    }


def make_pong(*, seq: int = 0) -> dict[str, Any]:
    return {
        "version": PROTOCOL_VERSION,
        "type": MessageType.PONG.value,
        "timestamp": now_ms(),
        "seq": seq,
    }


def make_error(
    *,
    error: ProtocolError,
    request_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """把 ProtocolError 包装成线上 ERROR 消息。"""
    return {
        "version": PROTOCOL_VERSION,
        "type": MessageType.ERROR.value,
        "request_id": request_id,
        "session_id": session_id,
        "timestamp": now_ms(),
        "error": error.to_dict(),
    }


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------

#: 每种消息的必填字段。
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    MessageType.HELLO.value: ("type", "protocol", "client", "client_version", "capabilities"),
    MessageType.HELLO_ACK.value: (
        "type",
        "protocol",
        "server",
        "server_version",
        "session_id",
        "capabilities",
    ),
    MessageType.READY.value: (
        "version",
        "type",
        "session_id",
        "timestamp",
        "state",
        "capabilities",
    ),
    MessageType.REQUEST.value: (
        "version",
        "type",
        "request_id",
        "session_id",
        "timestamp",
        "command",
        "payload",
    ),
    MessageType.RESPONSE.value: (
        "version",
        "type",
        "request_id",
        "session_id",
        "timestamp",
        "status",
        "code",
        "payload",
    ),
    MessageType.EVENT.value: (
        "version",
        "type",
        "event_id",
        "session_id",
        "timestamp",
        "pid",
        "tid",
        "event_type",
        "source",
        "payload",
    ),
    MessageType.PING.value: ("version", "type", "timestamp", "seq"),
    MessageType.PONG.value: ("version", "type", "timestamp", "seq"),
    MessageType.ERROR.value: (
        "version",
        "type",
        "request_id",
        "session_id",
        "timestamp",
        "error",
    ),
}


def message_type_of(message: dict[str, Any]) -> str:
    t = message.get("type")
    if not isinstance(t, str):
        raise ProtocolError(
            ErrorCode.E_MALFORMED_FRAME,
            "消息缺少 type 字段",
            {"keys": sorted(message.keys())},
        )
    return t


def protocol_version_of(message: dict[str, Any]) -> str | None:
    """归一化读取协议版本（HELLO 用 protocol，其余用 version）。"""
    return message.get("protocol") or message.get("version")


def validate(message: dict[str, Any], *, strict: bool = True) -> str:
    """校验消息结构。返回消息类型。

    strict=True 时拒绝未知字段，防止两端字段名悄悄漂移。
    """
    t = message_type_of(message)

    if t not in REQUIRED_FIELDS:
        raise ProtocolError(
            ErrorCode.E_MALFORMED_FRAME,
            f"未知消息类型：{t}",
            {"type": t, "known": [m.value for m in MessageType]},
        )

    required = REQUIRED_FIELDS[t]
    missing = [f for f in required if f not in message]
    if missing:
        raise ProtocolError(
            ErrorCode.E_BAD_ARGS,
            f"{t} 缺少必填字段：{', '.join(missing)}",
            {"type": t, "missing": missing, "required": list(required)},
        )

    if strict:
        unknown = sorted(set(message) - set(required))
        if unknown:
            raise ProtocolError(
                ErrorCode.E_BAD_ARGS,
                f"{t} 含未知字段：{', '.join(unknown)}",
                {"type": t, "unknown": unknown},
            )

    # --- 类型相关校验 ---
    if t == MessageType.REQUEST.value:
        cmd = message["command"]
        if not commands.is_known(cmd):
            raise ProtocolError(
                ErrorCode.E_UNKNOWN_CMD,
                f"未知命令：{cmd}",
                {"command": cmd},
                next_step="改用 commands.ALL_COMMANDS 中的命令",
            )
    elif t == MessageType.EVENT.value:
        if message["event_type"] not in EVENT_TYPES:
            raise ProtocolError(
                ErrorCode.E_BAD_ARGS,
                f"未知事件类型：{message['event_type']}",
                {"event_type": message["event_type"]},
            )
    elif t == MessageType.READY.value:
        if message["state"] not in {s.value for s in SessionState}:
            raise ProtocolError(
                ErrorCode.E_BAD_ARGS,
                f"未知 Session 状态：{message['state']}",
                {"state": message["state"]},
            )
    elif t == MessageType.ERROR.value:
        err = message["error"]
        if not isinstance(err, dict) or "code" not in err:
            raise ProtocolError(
                ErrorCode.E_BAD_ARGS,
                "ERROR 消息的 error 字段必须是含 code 的对象",
                {"error_type": type(err).__name__},
            )

    return t


def check_protocol_version(
    message: dict[str, Any], *, expected: str = PROTOCOL_VERSION
) -> None:
    """校验协议版本。不匹配抛 ERROR_PROTOCOL_VERSION。

    总基线 §10.3：版本不兼容必须**禁止进入 READY**，
    避免后续每条命令静默失败。
    """
    got = protocol_version_of(message)
    if got != expected:
        raise protocol_version_mismatch(expected, got)


def assert_ready_for_command(
    message: dict[str, Any],
    *,
    link_ready: bool,
    current_session_id: str | None,
) -> None:
    """命令前置条件检查：必须先 READY，且 session 必须有效。

    session_id 不匹配即 E_SESSION_STALE——这是重连后旧 Session
    被强制失效（总基线 §9.4）在协议层的落点。
    """
    if not link_ready:
        raise ProtocolError(
            ErrorCode.E_NOT_READY,
            "链路尚未 READY，禁止下发命令",
            {},
            next_step="先完成 HELLO → HELLO_ACK → READY 握手",
        )
    sid = message.get("session_id")
    if current_session_id is not None and sid != current_session_id:
        raise ProtocolError(
            ErrorCode.E_SESSION_STALE,
            "session_id 已失效（重连后旧 Session 不恢复）",
            {"got": sid, "current": current_session_id},
            next_step="重新 session.list 获取新 Session",
        )
