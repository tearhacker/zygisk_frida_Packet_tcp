# -*- coding: utf-8 -*-
"""消息构造与校验测试。

覆盖：九种消息的构造/校验、严格模式、版本不匹配、READY 前置条件、Session 失效。
"""

from __future__ import annotations

import pytest

from ai_analyzer.protocol import commands, frame as F, messages as M
from ai_analyzer.protocol.constants import (
    PROTOCOL_VERSION,
    MessageType,
    SessionState,
)
from ai_analyzer.protocol.errors import ErrorCode, ErrorLayer, ProtocolError

SESS = "sess_0000000000a1"


# ---------------------------------------------------------------------------
# 构造 → 校验 全通过
# ---------------------------------------------------------------------------


def test_all_nine_message_types_construct_and_validate():
    built = [
        M.make_hello(),
        M.make_hello_ack(session_id=SESS),
        M.make_ready(session_id=SESS),
        M.make_request(command="runtime.status", session_id=SESS),
        M.make_response(request_id="req_0000000000b1", session_id=SESS),
        M.make_event(
            event_type="RUNTIME_READY", session_id=SESS, source="runtime", pid=1, tid=1
        ),
        M.make_ping(seq=1),
        M.make_pong(seq=1),
        M.make_error(
            error=ProtocolError(ErrorCode.E_NOT_READY, "未就绪"), request_id="req_x"
        ),
    ]
    assert len(built) == 9
    types = [M.validate(m) for m in built]
    assert types == [t.value for t in MessageType]


def test_all_message_types_roundtrip_through_frame():
    msgs = [
        M.make_hello(),
        M.make_hello_ack(session_id=SESS),
        M.make_ready(session_id=SESS),
        M.make_request(command="process.list", session_id=SESS),
        M.make_response(request_id="req_0000000000b1", session_id=SESS),
        M.make_event(
            event_type="HOOK_ENTER", session_id=SESS, source="runtime", pid=1, tid=1
        ),
        M.make_ping(seq=1),
        M.make_pong(seq=1),
        M.make_error(error=ProtocolError(ErrorCode.E_TIMEOUT, "超时")),
    ]
    dec = F.FrameDecoder()
    got = dec.feed(F.iter_frames(msgs))
    assert got == msgs
    dec.finish()
    for m in got:
        M.validate(m)


# ---------------------------------------------------------------------------
# 结构校验
# ---------------------------------------------------------------------------


def test_unknown_message_type_rejected():
    with pytest.raises(ProtocolError) as ei:
        M.validate({"type": "WHO_KNOWS"})
    assert ei.value.code is ErrorCode.E_MALFORMED_FRAME


def test_missing_type_rejected():
    with pytest.raises(ProtocolError) as ei:
        M.validate({"version": "1.0"})
    assert ei.value.code is ErrorCode.E_MALFORMED_FRAME


def test_missing_required_field_reported():
    msg = M.make_request(command="runtime.status", session_id=SESS)
    del msg["session_id"]
    with pytest.raises(ProtocolError) as ei:
        M.validate(msg)
    assert ei.value.code is ErrorCode.E_BAD_ARGS
    assert "session_id" in ei.value.context["missing"]


def test_strict_mode_rejects_unknown_field():
    """严格模式防止两端字段名悄悄漂移。"""
    msg = M.make_ping(seq=1)
    msg["debug_note"] = "oops"
    with pytest.raises(ProtocolError) as ei:
        M.validate(msg, strict=True)
    assert ei.value.code is ErrorCode.E_BAD_ARGS
    assert "debug_note" in ei.value.context["unknown"]
    # 非严格模式放行
    assert M.validate(msg, strict=False) == "PING"


def test_request_with_unknown_command_rejected():
    msg = M.make_ping(seq=1)
    msg = {
        "version": PROTOCOL_VERSION, "type": "REQUEST",
        "request_id": "req_0000000000b1", "session_id": SESS,
        "timestamp": 1, "command": "runtime.hack_everything", "payload": {},
    }
    with pytest.raises(ProtocolError) as ei:
        M.validate(msg)
    assert ei.value.code is ErrorCode.E_UNKNOWN_CMD


def test_event_with_unknown_type_rejected():
    msg = M.make_event(
        event_type="RUNTIME_READY", session_id=SESS, source="runtime", pid=1, tid=1
    )
    msg["event_type"] = "SOMETHING_NEW"
    with pytest.raises(ProtocolError) as ei:
        M.validate(msg)
    assert ei.value.code is ErrorCode.E_BAD_ARGS


def test_ready_with_unknown_state_rejected():
    msg = M.make_ready(session_id=SESS)
    msg["state"] = "VIBING"
    with pytest.raises(ProtocolError) as ei:
        M.validate(msg)
    assert ei.value.code is ErrorCode.E_BAD_ARGS


def test_error_message_without_code_rejected():
    msg = M.make_error(error=ProtocolError(ErrorCode.E_INTERNAL, "内部错误"))
    msg["error"] = {"message": "没有 code"}
    with pytest.raises(ProtocolError) as ei:
        M.validate(msg)
    assert ei.value.code is ErrorCode.E_BAD_ARGS


def test_make_event_rejects_unknown_source():
    with pytest.raises(ProtocolError) as ei:
        M.make_event(
            event_type="RUNTIME_READY", session_id=SESS, source="telepathy", pid=1, tid=1
        )
    assert ei.value.code is ErrorCode.E_BAD_ARGS


def test_make_request_rejects_unknown_command():
    with pytest.raises(ProtocolError) as ei:
        M.make_request(command="nope.nope", session_id=SESS)
    assert ei.value.code is ErrorCode.E_UNKNOWN_CMD


# ---------------------------------------------------------------------------
# 版本校验
# ---------------------------------------------------------------------------


def test_protocol_version_of_normalizes_both_field_names():
    """HELLO 用 protocol，REQUEST 用 version —— 读取必须归一化。"""
    assert M.protocol_version_of(M.make_hello()) == PROTOCOL_VERSION
    assert (
        M.protocol_version_of(M.make_request(command="runtime.status", session_id=SESS))
        == PROTOCOL_VERSION
    )


def test_version_match_passes():
    M.check_protocol_version(M.make_hello())


def test_version_mismatch_raises_protocol_version_error():
    bad = M.make_hello(protocol="2.0")
    with pytest.raises(ProtocolError) as ei:
        M.check_protocol_version(bad)
    err = ei.value
    assert err.code is ErrorCode.ERROR_PROTOCOL_VERSION
    assert err.layer is ErrorLayer.PROTOCOL
    assert err.retryable is False
    assert err.context == {"expected": PROTOCOL_VERSION, "got": "2.0"}
    d = err.to_dict()
    assert d["layer"] == "protocol"
    assert d["next_step"]


def test_version_mismatch_serializes_to_valid_error_message():
    bad = M.make_hello(protocol="2.0")
    try:
        M.check_protocol_version(bad)
    except ProtocolError as err:
        wire = err.to_error_message()
    assert M.validate(wire) == "ERROR"
    assert wire["error"]["code"] == "ERROR_PROTOCOL_VERSION"
    assert wire["error"]["retryable"] is False


# ---------------------------------------------------------------------------
# READY 前置条件与 Session 失效
# ---------------------------------------------------------------------------


def test_command_before_ready_rejected():
    req = M.make_request(command="runtime.status", session_id=SESS)
    with pytest.raises(ProtocolError) as ei:
        M.assert_ready_for_command(req, link_ready=False, current_session_id=None)
    assert ei.value.code is ErrorCode.E_NOT_READY


def test_stale_session_rejected():
    """重连后旧 Session 必须失效（总基线 §9.4 冻结项）。"""
    old = M.make_request(command="runtime.status", session_id="sess_0000000000a0")
    with pytest.raises(ProtocolError) as ei:
        M.assert_ready_for_command(old, link_ready=True, current_session_id=SESS)
    err = ei.value
    assert err.code is ErrorCode.E_SESSION_STALE
    assert err.context["got"] == "sess_0000000000a0"
    assert err.context["current"] == SESS
    assert err.retryable is False


def test_ready_session_passes():
    req = M.make_request(command="runtime.status", session_id=SESS)
    M.assert_ready_for_command(req, link_ready=True, current_session_id=SESS)


# ---------------------------------------------------------------------------
# 能力声明与执行三态
# ---------------------------------------------------------------------------


def test_default_ready_capabilities_are_all_false():
    """默认能力必须全 false —— 不许凭空声称有能力。"""
    ready = M.make_ready(session_id=SESS)
    for group in ready["capabilities"].values():
        assert set(group.values()) == {False}


def test_https_decrypt_must_not_be_inferred():
    """抓到了 HTTPS ≠ 能解密。样例里 https_decrypt 必须是 false。"""
    ready = M.make_ready(session_id=SESS)
    assert ready["capabilities"]["network"]["https_decrypt"] is False


def test_session_state_enum_covers_documented_lifecycle():
    documented = {
        "CREATED", "STARTING", "RUNTIME_READY", "NETWORK_READY", "RUNNING",
        "PAUSED", "STOPPING", "CLOSED", "DEGRADED", "FAILED", "ERROR",
    }
    assert {s.value for s in SessionState} == documented


def test_commands_registry_non_empty():
    assert len(commands.ALL_COMMANDS) >= 70
