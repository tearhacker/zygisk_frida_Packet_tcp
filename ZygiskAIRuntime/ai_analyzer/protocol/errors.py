# -*- coding: utf-8 -*-
"""错误体系。

依据：总基线 §10.8 错误分层 · §21 变更边界（错误码表发布后只增不改义）。

核心纪律
--------
1. **两层必须分开**：协议层错误是「AI 调错了」，执行层失败是「调用合法但后端失败」。
   混为一谈 = AI 无法自我纠错（该改参数时它去重试，该换策略时它改参数）。
2. **错误消息必须可行动**：含 code / message / context / retryable / next_step。
   只说"操作失败"会让 AI 陷入无限重试。
3. **错误码表是稳定契约**：发布后只增不改义。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ErrorLayer(str, Enum):
    """错误分层。决定错误以什么形式返回给客户端。"""

    PROTOCOL = "protocol"
    """协议层：未知命令 / 参数校验失败 / 版本不匹配 / JSON 解析失败。
    返回方式：JSON-RPC error。"""

    EXECUTION = "execution"
    """执行层：读内存失败 / 权限被拒 / 进程已退出 / 扫描无结果。
    返回方式：isError=true 的 tool result。"""


class ErrorCode(str, Enum):
    """错误码表。稳定契约，发布后只增不改义。"""

    # --- 协议层 ---
    ERROR_PROTOCOL_VERSION = "ERROR_PROTOCOL_VERSION"
    E_BAD_ARGS = "E_BAD_ARGS"
    E_UNKNOWN_CMD = "E_UNKNOWN_CMD"
    E_MALFORMED_FRAME = "E_MALFORMED_FRAME"

    # --- 执行层 ---
    E_NOT_READY = "E_NOT_READY"
    E_SESSION_STALE = "E_SESSION_STALE"
    E_READ_FAILED = "E_READ_FAILED"
    E_WRITE_FAILED = "E_WRITE_FAILED"
    E_MAP_STALE = "E_MAP_STALE"
    E_TIMEOUT = "E_TIMEOUT"
    E_CANCELLED = "E_CANCELLED"
    E_NOT_FOUND = "E_NOT_FOUND"
    E_PERMISSION_DENIED = "E_PERMISSION_DENIED"
    E_INTERNAL = "E_INTERNAL"


@dataclass(frozen=True)
class ErrorMeta:
    """错误的静态元信息：属于哪一层、是否可重试、AI 应该做什么。"""

    layer: ErrorLayer
    retryable: bool
    ai_action: str


ERROR_META: dict[ErrorCode, ErrorMeta] = {
    # --- 协议层 ---
    ErrorCode.ERROR_PROTOCOL_VERSION: ErrorMeta(
        ErrorLayer.PROTOCOL, False, "停止，报告需升级；不可重试"
    ),
    ErrorCode.E_BAD_ARGS: ErrorMeta(ErrorLayer.PROTOCOL, False, "改参数"),
    ErrorCode.E_UNKNOWN_CMD: ErrorMeta(ErrorLayer.PROTOCOL, False, "改工具名 / 改命令"),
    ErrorCode.E_MALFORMED_FRAME: ErrorMeta(
        ErrorLayer.PROTOCOL, False, "检查帧格式与长度前缀"
    ),
    # --- 执行层 ---
    ErrorCode.E_NOT_READY: ErrorMeta(
        ErrorLayer.EXECUTION, True, "先完成前置步骤（等待 RUNTIME_READY）"
    ),
    ErrorCode.E_SESSION_STALE: ErrorMeta(
        ErrorLayer.EXECUTION, False, "Session 已失效，重建 Session"
    ),
    ErrorCode.E_READ_FAILED: ErrorMeta(
        ErrorLayer.EXECUTION, False, "查地址 / 换候选 / 查映射可读性"
    ),
    ErrorCode.E_WRITE_FAILED: ErrorMeta(
        ErrorLayer.EXECUTION, False, "查地址 / 查映射可写性；已尝试回滚"
    ),
    ErrorCode.E_MAP_STALE: ErrorMeta(
        ErrorLayer.EXECUTION, True, "模块映射已变，重新 process.modules"
    ),
    ErrorCode.E_TIMEOUT: ErrorMeta(
        ErrorLayer.EXECUTION, True, "当作后端可能异常，先探活"
    ),
    ErrorCode.E_CANCELLED: ErrorMeta(ErrorLayer.EXECUTION, True, "重新发起"),
    ErrorCode.E_NOT_FOUND: ErrorMeta(
        ErrorLayer.EXECUTION, True, "换搜索方式（放宽条件 / 改特征码）"
    ),
    ErrorCode.E_PERMISSION_DENIED: ErrorMeta(
        ErrorLayer.EXECUTION, False, "报告权限不足，降级"
    ),
    ErrorCode.E_INTERNAL: ErrorMeta(ErrorLayer.EXECUTION, False, "查日志"),
}


@dataclass
class ProtocolError(Exception):
    """协议层 / 执行层错误的统一载体。

    同时承担两个角色：
      - 作为 Python 异常在内部抛出
      - 作为线上错误对象序列化（to_dict）
    """

    code: ErrorCode
    message: str
    context: dict[str, Any] = field(default_factory=dict)
    next_step: str | None = None

    def __post_init__(self) -> None:
        Exception.__init__(self, f"{self.code.value}: {self.message}")

    # -- 派生属性 ---------------------------------------------------------

    @property
    def meta(self) -> ErrorMeta:
        return ERROR_META[self.code]

    @property
    def layer(self) -> ErrorLayer:
        return self.meta.layer

    @property
    def retryable(self) -> bool:
        return self.meta.retryable

    # -- 序列化 -----------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """线上错误对象。字段固定，AI 依赖它自我纠错。"""
        return {
            "code": self.code.value,
            "layer": self.layer.value,
            "message": self.message,
            "context": dict(self.context),
            "retryable": self.retryable,
            "next_step": self.next_step or self.meta.ai_action,
        }

    def to_error_message(self, request_id: str | None = None, session_id: str | None = None):
        """包装成协议 ERROR 消息。"""
        from . import messages

        return messages.make_error(
            error=self, request_id=request_id, session_id=session_id
        )


# --- 便捷构造器 -------------------------------------------------------------


def protocol_version_mismatch(
    expected: str, got: str | None
) -> ProtocolError:
    """版本不匹配。必须禁止进入 READY。"""
    return ProtocolError(
        code=ErrorCode.ERROR_PROTOCOL_VERSION,
        message=f"协议版本不匹配：服务端 {expected}，客户端 {got!r}",
        context={"expected": expected, "got": got},
        next_step="升级客户端到协议版本 " + expected,
    )


def bad_args(message: str, **context: Any) -> ProtocolError:
    return ProtocolError(ErrorCode.E_BAD_ARGS, message, context)


def unknown_command(command: str, known: tuple[str, ...] = ()) -> ProtocolError:
    return ProtocolError(
        ErrorCode.E_UNKNOWN_CMD,
        f"未知命令：{command}",
        {"command": command, "known_sample": list(known[:10])},
        next_step="改用已知命令；可用 session.capabilities 查询当前能力",
    )


def not_ready(what: str, **context: Any) -> ProtocolError:
    return ProtocolError(
        ErrorCode.E_NOT_READY, f"前置条件未满足：{what}", context
    )


def session_stale(session_id: str | None) -> ProtocolError:
    """Session 已失效。

    典型触发：重连之后旧 Session 被强制失效（总基线 §9.4）。
    """
    return ProtocolError(
        ErrorCode.E_SESSION_STALE,
        "Session 已失效（重连后旧 Session 不恢复，必须重建）",
        {"session_id": session_id},
        next_step="重新 session.list 获取新 Session",
    )


def timeout(command: str, seconds: float) -> ProtocolError:
    return ProtocolError(
        ErrorCode.E_TIMEOUT,
        f"命令 {command} 超时（{seconds}s）",
        {"command": command, "timeout_s": seconds},
    )


def internal(message: str, **context: Any) -> ProtocolError:
    return ProtocolError(ErrorCode.E_INTERNAL, message, context)
