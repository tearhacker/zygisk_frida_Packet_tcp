# -*- coding: utf-8 -*-
"""帧编解码边界测试。

覆盖施工手册 M0.2 强制要求的八种情形：
0 字节 / 1 字节 / 正常 / 大帧 / 非法长度 / 截断 / 多余数据 / 畸形 JSON
"""

from __future__ import annotations

import json
import struct

import pytest

from ai_analyzer.protocol import frame as F
from ai_analyzer.protocol import messages as M
from ai_analyzer.protocol.constants import FRAME_HEADER_SIZE, FRAME_MAX_PAYLOAD
from ai_analyzer.protocol.errors import ErrorCode, ProtocolError


def assert_frame_error(exc: ProtocolError) -> None:
    assert exc.code is ErrorCode.E_MALFORMED_FRAME
    assert exc.layer.value == "protocol"
    assert exc.retryable is False
    # 错误必须可行动：to_dict 必须给出 next_step
    assert exc.to_dict()["next_step"]


# ---------------------------------------------------------------------------
# 1. 0 字节
# ---------------------------------------------------------------------------


def test_empty_feed_yields_nothing():
    dec = F.FrameDecoder()
    assert dec.feed(b"") == []
    assert dec.buffered_bytes == 0
    dec.finish()  # 不应抛错


def test_empty_payload_rejected():
    with pytest.raises(ProtocolError) as ei:
        F.decode_payload(b"")
    assert_frame_error(ei.value)


def test_empty_payload_rejected_on_decode():
    with pytest.raises(ProtocolError) as ei:
        F.decode_frame(struct.pack(">I", 0))
    assert_frame_error(ei.value)


def test_empty_dict_is_a_valid_two_byte_payload():
    """`{}` 是合法的 2 字节 JSON —— 结构非法但成帧合法。"""
    blob = F.encode_frame({})
    assert len(blob) == FRAME_HEADER_SIZE + 2
    assert F.decode_frame(blob) == {}


# ---------------------------------------------------------------------------
# 2. 1 字节
# ---------------------------------------------------------------------------


def test_one_byte_is_buffered_not_error():
    dec = F.FrameDecoder()
    assert dec.feed(b"\x00") == []
    assert dec.buffered_bytes == 1


def test_one_byte_then_close_is_truncated():
    dec = F.FrameDecoder()
    dec.feed(b"\x00")
    with pytest.raises(ProtocolError) as ei:
        dec.finish()
    assert_frame_error(ei.value)


# ---------------------------------------------------------------------------
# 3. 正常
# ---------------------------------------------------------------------------


def test_roundtrip_normal():
    msg = M.make_ping(seq=3)
    blob = F.encode_frame(msg)
    assert F.decode_frame(blob) == msg

    dec = F.FrameDecoder()
    assert dec.feed(blob) == [msg]
    assert dec.buffered_bytes == 0


def test_header_is_big_endian_uint32():
    msg = M.make_ping(seq=1)
    body = F.encode_payload(msg)
    blob = F.encode_frame(msg)
    declared = struct.unpack(">I", blob[:4])[0]
    assert declared == len(body)
    assert blob[4:] == body
    # 小端解析必须得到不同结果，证明真的是大端
    assert struct.unpack("<I", blob[:4])[0] != declared or declared < 256


def test_utf8_payload_roundtrip():
    msg = M.make_event(
        event_type="RUNTIME_READY",
        session_id="sess_0000000000a1",
        source="runtime",
        payload={"备注": "中文载荷·含特殊符号 → ✓"},
        pid=1,
        tid=1,
    )
    assert F.decode_frame(F.encode_frame(msg)) == msg


def test_canonical_encoding_is_stable():
    a = F.encode_payload({"b": 1, "a": 2}, canonical=True)
    b = F.encode_payload({"a": 2, "b": 1}, canonical=True)
    assert a == b
    assert json.loads(a) == {"a": 2, "b": 1}


# ---------------------------------------------------------------------------
# 4. 大帧
# ---------------------------------------------------------------------------


def test_large_frame_within_limit():
    big = M.make_ping(seq=1)
    big["padding"] = "x" * (1 << 20)  # 1 MiB
    blob = F.encode_frame(big)
    assert len(blob) > (1 << 20)
    dec = F.FrameDecoder()
    out = dec.feed(blob)
    assert len(out) == 1
    assert out[0]["padding"] == big["padding"]


def test_frame_over_limit_rejected_on_encode():
    huge = {"type": "PING", "pad": "x" * (FRAME_MAX_PAYLOAD + 1)}
    with pytest.raises(ProtocolError) as ei:
        F.encode_frame(huge)
    assert_frame_error(ei.value)


# ---------------------------------------------------------------------------
# 5. 非法长度
# ---------------------------------------------------------------------------


def test_zero_declared_length_rejected():
    dec = F.FrameDecoder()
    with pytest.raises(ProtocolError) as ei:
        dec.feed(b"\x00\x00\x00\x00")
    assert_frame_error(ei.value)
    assert "0" in ei.value.message


def test_oversized_declared_length_rejected_immediately():
    """非法长度必须立即失败，不能等 —— 否则恶意长度会撑爆内存。"""
    dec = F.FrameDecoder()
    with pytest.raises(ProtocolError) as ei:
        dec.feed(struct.pack(">I", FRAME_MAX_PAYLOAD + 1))
    assert_frame_error(ei.value)
    assert ei.value.context["declared"] == FRAME_MAX_PAYLOAD + 1


def test_huge_declared_length_rejected():
    dec = F.FrameDecoder()
    with pytest.raises(ProtocolError) as ei:
        dec.feed(b"\xff\xff\xff\xff")
    assert_frame_error(ei.value)


# ---------------------------------------------------------------------------
# 6. 截断
# ---------------------------------------------------------------------------


def test_truncated_body_waits_for_more():
    msg = M.make_ping(seq=9)
    blob = F.encode_frame(msg)
    dec = F.FrameDecoder()
    assert dec.feed(blob[:-1]) == []
    assert dec.buffered_bytes == len(blob) - 1
    assert dec.feed(blob[-1:]) == [msg]


def test_truncated_then_close_raises():
    blob = F.encode_frame(M.make_ping(seq=1))
    dec = F.FrameDecoder()
    dec.feed(blob[: FRAME_HEADER_SIZE + 3])
    with pytest.raises(ProtocolError) as ei:
        dec.finish()
    assert_frame_error(ei.value)


def test_decode_frame_truncated_raises():
    blob = F.encode_frame(M.make_ping(seq=1))
    with pytest.raises(ProtocolError) as ei:
        F.decode_frame(blob[:-2])
    assert_frame_error(ei.value)
    assert "截断" in ei.value.message


def test_decode_frame_too_short_for_header():
    with pytest.raises(ProtocolError) as ei:
        F.decode_frame(b"\x00\x00")
    assert_frame_error(ei.value)


# ---------------------------------------------------------------------------
# 7. 多余数据
# ---------------------------------------------------------------------------


def test_multiple_frames_in_one_feed():
    msgs = [M.make_ping(seq=i) for i in range(3)]
    dec = F.FrameDecoder()
    out = dec.feed(F.iter_frames(msgs))
    assert out == msgs
    assert dec.buffered_bytes == 0


def test_extra_bytes_after_frame_rejected_by_decode_frame():
    blob = F.encode_frame(M.make_ping(seq=1)) + b"\xde\xad\xbe\xef"
    with pytest.raises(ProtocolError) as ei:
        F.decode_frame(blob)
    assert_frame_error(ei.value)
    assert "多余" in ei.value.message


def test_byte_by_byte_stream_reassembles():
    msgs = [M.make_ping(seq=1), M.make_pong(seq=1), M.make_ping(seq=2)]
    blob = F.iter_frames(msgs)
    dec = F.FrameDecoder()
    got = []
    for i in range(len(blob)):
        got.extend(dec.feed(blob[i : i + 1]))
    assert got == msgs
    dec.finish()


def test_reset_clears_partial():
    dec = F.FrameDecoder()
    dec.feed(b"\x00\x00")
    assert dec.has_partial
    dec.reset()
    assert not dec.has_partial
    dec.finish()


# ---------------------------------------------------------------------------
# 8. 畸形 JSON
# ---------------------------------------------------------------------------


def test_malformed_json_rejected():
    body = b"{not json"
    blob = struct.pack(">I", len(body)) + body
    dec = F.FrameDecoder()
    with pytest.raises(ProtocolError) as ei:
        dec.feed(blob)
    assert_frame_error(ei.value)
    assert ei.value.context["preview"].startswith("{not json")


def test_invalid_utf8_rejected():
    body = b"\xff\xfe\xfd"
    blob = struct.pack(">I", len(body)) + body
    with pytest.raises(ProtocolError) as ei:
        F.decode_frame(blob)
    assert_frame_error(ei.value)


@pytest.mark.parametrize("body", [b"[1,2,3]", b'"hello"', b"42", b"null", b"true"])
def test_non_object_json_rejected(body):
    """payload 顶层必须是 JSON 对象 —— 消息一定是 object。"""
    blob = struct.pack(">I", len(body)) + body
    with pytest.raises(ProtocolError) as ei:
        F.decode_frame(blob)
    assert_frame_error(ei.value)
    assert "JSON 对象" in ei.value.message


def test_error_after_malformed_does_not_corrupt_decoder_state():
    """畸形帧之后，缓冲区必须被清干净，不污染后续帧。"""
    bad_body = b"{oops"
    bad = struct.pack(">I", len(bad_body)) + bad_body
    dec = F.FrameDecoder()
    with pytest.raises(ProtocolError):
        dec.feed(bad)
    # 解码器已消耗掉整帧（含头部），缓冲区应为空
    assert dec.buffered_bytes == 0
    good = M.make_ping(seq=5)
    assert dec.feed(F.encode_frame(good)) == [good]
