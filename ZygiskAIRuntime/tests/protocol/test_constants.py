# -*- coding: utf-8 -*-
"""常量一致性测试。

这是 M0 契约的**核心断言**：Python 侧 `constants.py` 与 Android 侧
`native/include/ipc/protocol_constants.h` 必须逐项一致。

不依赖 NDK —— 直接解析头文件文本比对。任何一侧改了值而另一侧没跟，
测试立刻失败。这正是「同一个 JSON → 同样解析 → 同样字段」的前提。
"""

from __future__ import annotations

import re

import pytest

from ai_analyzer.protocol import commands
from ai_analyzer.protocol import constants as C
from ai_analyzer.protocol.constants import (
    CommandClass,
    ExecutionState,
    HttpsCapability,
    LinkState,
    MessageType,
    SessionState,
)
from ai_analyzer.protocol.errors import ErrorCode, ErrorLayer

# ---------------------------------------------------------------------------
# 头文件解析
# ---------------------------------------------------------------------------

_DEFINE_RE = re.compile(r"^\s*#define\s+(ZAI_[A-Z0-9_]+)\s+(.+?)\s*$", re.MULTILINE)
_ENUM_RE = re.compile(r"enum\s+class\s+(\w+)\s*:\s*int\s*\{([^}]*)\}", re.DOTALL)
_ENUM_ITEM_RE = re.compile(r"(\w+)\s*=\s*(-?\d+)")
_INT_EXPR_RE = re.compile(r"^[0-9+\-*/(). ]+$")


def parse_defines(text: str) -> dict[str, object]:
    """解析 #define，把值还原成 str / int / tuple[int, ...]。"""
    out: dict[str, object] = {}
    for name, raw in _DEFINE_RE.findall(text):
        raw = raw.strip()
        if raw.startswith('"') and raw.endswith('"'):
            out[name] = raw[1:-1]
        elif raw.startswith("{") and raw.endswith("}"):
            out[name] = tuple(int(x) for x in re.findall(r"-?\d+", raw))
        elif _INT_EXPR_RE.match(raw):
            # 只允许数字与四则运算，杜绝任意代码执行
            out[name] = int(eval(raw, {"__builtins__": {}}, {}))  # noqa: S307
        else:
            out[name] = raw
    return out


def parse_enums(text: str) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for cls, body in _ENUM_RE.findall(text):
        out[cls] = {m: int(v) for m, v in _ENUM_ITEM_RE.findall(body)}
    return out


@pytest.fixture(scope="module")
def defines(android_header) -> dict[str, object]:
    assert android_header.exists(), f"Android 侧常量头文件不存在：{android_header}"
    return parse_defines(android_header.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def enums(android_header) -> dict[str, dict[str, int]]:
    return parse_enums(android_header.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 标量常量
# ---------------------------------------------------------------------------

SCALAR_MAP: dict[str, tuple[str, type]] = {
    "ZAI_PROTOCOL_VERSION": ("PROTOCOL_VERSION", str),
    "ZAI_SERVER_NAME": ("SERVER_NAME", str),
    "ZAI_SERVER_VERSION": ("SERVER_VERSION", str),
    "ZAI_CLIENT_NAME": ("CLIENT_NAME", str),
    "ZAI_CLIENT_VERSION": ("CLIENT_VERSION", str),
    "ZAI_FRAME_HEADER_SIZE": ("FRAME_HEADER_SIZE", int),
    "ZAI_FRAME_MAX_PAYLOAD": ("FRAME_MAX_PAYLOAD", int),
    "ZAI_HEARTBEAT_INTERVAL": ("HEARTBEAT_INTERVAL", int),
    "ZAI_HEARTBEAT_TIMEOUT": ("HEARTBEAT_TIMEOUT", int),
    "ZAI_FAST_COMMAND_TIMEOUT": ("FAST_COMMAND_TIMEOUT", int),
    "ZAI_JOB_COMMAND_TIMEOUT": ("JOB_COMMAND_TIMEOUT", int),
    "ZAI_SESSION_IDLE_TIMEOUT": ("SESSION_IDLE_TIMEOUT", int),
    "ZAI_CONNECT_TIMEOUT": ("CONNECT_TIMEOUT", int),
    "ZAI_RECONNECT_BACKOFF_MAX": ("RECONNECT_BACKOFF_MAX", int),
    "ZAI_MAX_RESPONSE_TOKENS": ("MAX_RESPONSE_TOKENS", int),
    "ZAI_MAX_RESIDENT_TOOLS": ("MAX_RESIDENT_TOOLS", int),
    "ZAI_MAX_TOOLS_HARD_LIMIT": ("MAX_TOOLS_HARD_LIMIT", int),
    "ZAI_DEFAULT_SOCKET_PATH": ("DEFAULT_SOCKET_PATH", str),
}


@pytest.mark.parametrize("macro,py_name,kind", [(k, v[0], v[1]) for k, v in SCALAR_MAP.items()])
def test_scalar_constants_match(defines, macro, py_name, kind):
    assert macro in defines, f"Android 头文件缺少 {macro}"
    header_value = defines[macro]
    py_value = getattr(C, py_name)
    assert isinstance(py_value, kind), f"{py_name} 类型应为 {kind}"
    assert header_value == py_value, (
        f"{macro} 两侧不一致：头文件={header_value!r}，Python={py_value!r}"
    )


def test_reconnect_backoff_matches(defines):
    assert defines["ZAI_RECONNECT_BACKOFF"] == C.RECONNECT_BACKOFF
    assert C.RECONNECT_BACKOFF[-1] == C.RECONNECT_BACKOFF_MAX
    # 必须严格递增，否则指数退避没有意义
    assert list(C.RECONNECT_BACKOFF) == sorted(C.RECONNECT_BACKOFF)
    assert len(set(C.RECONNECT_BACKOFF)) == len(C.RECONNECT_BACKOFF)


@pytest.mark.parametrize(
    "macro,py_name",
    [
        ("ZAI_SESSION_ID_INVALIDATE_ON_RECONNECT", "SESSION_ID_INVALIDATE_ON_RECONNECT"),
        ("ZAI_WRITE_CONFIRM_DEFAULT", "WRITE_CONFIRM_DEFAULT"),
    ],
)
def test_bool_constants_match(defines, macro, py_name):
    py_value = getattr(C, py_name)
    assert int(py_value) == defines[macro], (
        f"{macro} 两侧不一致：头文件={defines[macro]}，Python={py_value}"
    )


# ---------------------------------------------------------------------------
# 线上字符串：消息类型 / Session 状态 / 错误码
# ---------------------------------------------------------------------------


def _wire_values(defines: dict, prefix: str) -> set[str]:
    return {v for k, v in defines.items() if k.startswith(prefix) and isinstance(v, str)}


def test_message_type_strings_match(defines):
    header = _wire_values(defines, "ZAI_MSG_")
    py = {m.value for m in MessageType}
    assert header == py, f"消息类型两侧不一致：仅头文件有 {header - py}，仅 Python 有 {py - header}"


def test_session_state_strings_match(defines):
    header = _wire_values(defines, "ZAI_SESSION_STATE_")
    py = {s.value for s in SessionState}
    assert header == py, f"Session 状态两侧不一致：{header ^ py}"


def test_error_code_strings_match(defines):
    header = _wire_values(defines, "ZAI_ERR_")
    py = {c.value for c in ErrorCode}
    assert header == py, f"错误码两侧不一致：{header ^ py}"


# ---------------------------------------------------------------------------
# 枚举成员名
# ---------------------------------------------------------------------------

ENUM_PAIRS = {
    "MessageType": MessageType,
    "CommandClass": CommandClass,
    "SessionState": SessionState,
    "LinkState": LinkState,
    "ExecutionState": ExecutionState,
    "HttpsCapability": HttpsCapability,
}


@pytest.mark.parametrize("cls_name", sorted(ENUM_PAIRS))
def test_enum_members_match(enums, cls_name):
    assert cls_name in enums, f"Android 头文件缺少 enum class {cls_name}"
    py_names = {m.name for m in ENUM_PAIRS[cls_name]}
    header_names = set(enums[cls_name])
    assert header_names == py_names, (
        f"{cls_name} 成员名不一致：仅头文件有 {header_names - py_names}，"
        f"仅 Python 有 {py_names - header_names}"
    )


def test_error_layer_is_two_valued():
    """错误分层必须严格二分：协议层 / 执行层。"""
    assert {layer.value for layer in ErrorLayer} == {"protocol", "execution"}


def test_every_error_code_has_meta():
    """错误码表与元信息表必须一一对应，否则 to_dict() 会 KeyError。"""
    from ai_analyzer.protocol.errors import ERROR_META

    assert set(ERROR_META) == set(ErrorCode)
    for code, meta in ERROR_META.items():
        assert meta.ai_action, f"{code} 缺少可行动的 ai_action"
        assert isinstance(meta.retryable, bool)


def test_error_layers_partitioned_as_documented():
    """总基线 §10.8 的分层归属不得改动。"""
    from ai_analyzer.protocol.errors import ERROR_META

    protocol_codes = {
        ErrorCode.ERROR_PROTOCOL_VERSION,
        ErrorCode.E_BAD_ARGS,
        ErrorCode.E_UNKNOWN_CMD,
        ErrorCode.E_MALFORMED_FRAME,
    }
    for code, meta in ERROR_META.items():
        expected = ErrorLayer.PROTOCOL if code in protocol_codes else ErrorLayer.EXECUTION
        assert meta.layer is expected, f"{code} 分层应为 {expected.value}"


# ---------------------------------------------------------------------------
# 命令表自检
# ---------------------------------------------------------------------------


def test_no_duplicate_commands():
    assert len(commands.ALL_COMMANDS) == len(set(commands.ALL_COMMANDS))


def test_command_naming_rule():
    """所有命令必须是 domain.action 的 snake_case。"""
    pattern = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
    bad = [c for c in commands.ALL_COMMANDS if not pattern.match(c)]
    assert not bad, f"违反 snake_case 命名规则：{bad}"


def test_fast_and_job_partition():
    assert set(commands.FAST_COMMANDS) | set(commands.JOB_COMMANDS) == set(
        commands.ALL_COMMANDS
    )
    assert not (set(commands.FAST_COMMANDS) & set(commands.JOB_COMMANDS))


def test_doc_specified_command_classes():
    """总基线 §10.7 明确列举的命令，分级不得改动。"""
    must_fast = [
        "process.list", "process.info", "runtime.status",
        "memory.read", "network.connections", "network.dns", "packet.get",
    ]
    must_job = [
        "memory.dump", "packet.export", "apk.decompile",
        "network.capture_start", "runtime.trace",
    ]
    for name in must_fast:
        assert commands.COMMANDS[name].cls is CommandClass.FAST, name
        assert commands.COMMANDS[name].spec_source, name
    for name in must_job:
        assert commands.COMMANDS[name].cls is CommandClass.JOB, name
        assert commands.COMMANDS[name].spec_source, name


def test_timeout_by_class():
    assert commands.COMMANDS["runtime.status"].timeout == C.FAST_COMMAND_TIMEOUT
    assert commands.COMMANDS["memory.dump"].timeout == C.JOB_COMMAND_TIMEOUT


def test_write_guard_coverage():
    """总基线 §12.1 列举的写命令必须在册，且只读命令不得误标。"""
    assert commands.WRITE_GUARDED_COMMANDS == {"memory.write", "packet.modify"}
    assert not commands.is_write_guarded("memory.read")
    assert not commands.is_write_guarded("runtime.status")
    # payload 带写意图标志时也要过闸门
    assert commands.is_write_guarded("runtime.hook", {"modify_return": True})
    assert commands.is_write_guarded("packet.get", {"write": True})
    assert not commands.is_write_guarded("runtime.hook", {"module": "libx.so"})
