# -*- coding: utf-8 -*-
"""帧编解码。

线格式
------
    ┌────────────────┬──────────────────────────┐
    │ uint32 (4 字节) │ JSON payload (UTF-8)     │
    │ 网络字节序 = 大端 │ 长度由前 4 字节给出        │
    └────────────────┴──────────────────────────┘

依据：总基线 §10.1 传输 · 施工手册 §8 M0.2 Frame Codec。

边界必须全部处理（施工手册 M0.2 强制测试项）
------------------------------------------
0 字节 / 1 字节 / 正常 / 大帧 / 非法长度 / 截断 / 多余数据 / 畸形 JSON
"""

from __future__ import annotations

import json
import struct
from typing import Any, Iterable

from .constants import FRAME_HEADER_SIZE, FRAME_MAX_PAYLOAD
from .errors import ErrorCode, ProtocolError

_HEADER = struct.Struct(">I")
assert _HEADER.size == FRAME_HEADER_SIZE

DEFAULT_ENCODING = "utf-8"


# ---------------------------------------------------------------------------
# 编码
# ---------------------------------------------------------------------------


def encode_payload(payload: dict[str, Any], *, canonical: bool = False) -> bytes:
    """把消息 dict 序列化为 JSON 字节。

    canonical=True 时按键排序输出，用于生成黄金样例等需要逐字节稳定的场景。
    """
    text = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=canonical,
    )
    return text.encode(DEFAULT_ENCODING)


def encode_frame(payload: dict[str, Any], *, canonical: bool = False) -> bytes:
    """把消息 dict 编码成一帧（长度前缀 + JSON）。"""
    body = encode_payload(payload, canonical=canonical)
    if not body:
        raise ProtocolError(
            ErrorCode.E_MALFORMED_FRAME,
            "空 payload 不允许成帧",
            {"payload_bytes": 0},
        )
    if len(body) > FRAME_MAX_PAYLOAD:
        raise ProtocolError(
            ErrorCode.E_MALFORMED_FRAME,
            f"payload 超出上限：{len(body)} > {FRAME_MAX_PAYLOAD}",
            {"payload_bytes": len(body), "max": FRAME_MAX_PAYLOAD},
            next_step="大对象改走 Artifact Channel，只传 metadata + sha256",
        )
    return _HEADER.pack(len(body)) + body


def frame_length(frame: bytes) -> int:
    """读出帧头声明的 payload 长度。仅用于诊断，不做校验。"""
    if len(frame) < FRAME_HEADER_SIZE:
        raise ProtocolError(
            ErrorCode.E_MALFORMED_FRAME,
            f"帧头不足 {FRAME_HEADER_SIZE} 字节",
            {"got": len(frame)},
        )
    return _HEADER.unpack_from(frame, 0)[0]


# ---------------------------------------------------------------------------
# 解码
# ---------------------------------------------------------------------------


def decode_payload(body: bytes) -> dict[str, Any]:
    """JSON 字节 → dict。畸形 JSON 抛 E_MALFORMED_FRAME。"""
    if not body:
        raise ProtocolError(
            ErrorCode.E_MALFORMED_FRAME, "payload 为空", {"payload_bytes": 0}
        )
    try:
        obj = json.loads(body.decode(DEFAULT_ENCODING))
    except UnicodeDecodeError as exc:
        raise ProtocolError(
            ErrorCode.E_MALFORMED_FRAME,
            f"payload 不是合法 UTF-8：{exc}",
            {"payload_bytes": len(body)},
        ) from exc
    except json.JSONDecodeError as exc:
        preview = body[:64].decode(DEFAULT_ENCODING, errors="replace")
        raise ProtocolError(
            ErrorCode.E_MALFORMED_FRAME,
            f"畸形 JSON：{exc.msg}（位置 {exc.pos}）",
            {"payload_bytes": len(body), "preview": preview},
        ) from exc

    if not isinstance(obj, dict):
        raise ProtocolError(
            ErrorCode.E_MALFORMED_FRAME,
            f"payload 顶层必须是 JSON 对象，实际是 {type(obj).__name__}",
            {"type": type(obj).__name__},
        )
    return obj


def decode_frame(frame: bytes) -> dict[str, Any]:
    """完整一帧 → dict。

    帧尾有多余字节时抛错——这说明调用方切帧切错了，静默忽略会掩盖 bug。
    """
    if len(frame) < FRAME_HEADER_SIZE:
        raise ProtocolError(
            ErrorCode.E_MALFORMED_FRAME,
            f"帧不完整：只有 {len(frame)} 字节，连帧头都不够",
            {"got": len(frame), "need_header": FRAME_HEADER_SIZE},
        )
    declared = frame_length(frame)
    body = frame[FRAME_HEADER_SIZE:]
    if len(body) < declared:
        raise ProtocolError(
            ErrorCode.E_MALFORMED_FRAME,
            f"帧被截断：声明 {declared} 字节，实际只有 {len(body)} 字节",
            {"declared": declared, "actual": len(body)},
        )
    if len(body) > declared:
        raise ProtocolError(
            ErrorCode.E_MALFORMED_FRAME,
            f"帧尾有多余数据：声明 {declared} 字节，实际 {len(body)} 字节",
            {"declared": declared, "actual": len(body)},
        )
    return decode_payload(body)


# ---------------------------------------------------------------------------
# 流式解码器（TCP / UDS 上必须用这个）
# ---------------------------------------------------------------------------


class FrameDecoder:
    """增量式帧解码器。

    用法::

        dec = FrameDecoder()
        for message in dec.feed(chunk):   # 每次读到多少喂多少
            handle(message)
        dec.finish()                      # 连接关闭时调用，检查残留

    设计要点：
      - 一帧可能跨多次 feed（截断由缓冲区承接，不算错误）
      - 一次 feed 可能含多帧（"多余数据"在这里被正确切分，不算错误）
      - 非法长度立即抛错，不等待——否则恶意长度会撑爆内存
    """

    def __init__(self, *, max_payload: int = FRAME_MAX_PAYLOAD) -> None:
        self._buf = bytearray()
        self._max_payload = max_payload

    # -- 状态 -------------------------------------------------------------

    @property
    def buffered_bytes(self) -> int:
        """缓冲区中尚未组成完整帧的字节数。"""
        return len(self._buf)

    @property
    def has_partial(self) -> bool:
        return len(self._buf) > 0

    def reset(self) -> None:
        self._buf.clear()

    # -- 喂数据 -----------------------------------------------------------

    def feed(self, data: bytes) -> list[dict[str, Any]]:
        """喂入字节，返回本次能解出的全部完整消息。"""
        if data:
            self._buf.extend(data)

        out: list[dict[str, Any]] = []
        while True:
            if len(self._buf) < FRAME_HEADER_SIZE:
                break

            declared = _HEADER.unpack_from(self._buf, 0)[0]

            # 非法长度：立即失败，不等待。
            if declared == 0:
                raise ProtocolError(
                    ErrorCode.E_MALFORMED_FRAME,
                    "帧头声明长度为 0",
                    {"buffered": len(self._buf)},
                )
            if declared > self._max_payload:
                raise ProtocolError(
                    ErrorCode.E_MALFORMED_FRAME,
                    f"帧头声明长度非法：{declared} > {self._max_payload}",
                    {"declared": declared, "max": self._max_payload},
                    next_step="检查对端字节序或切帧逻辑；大对象走 Artifact Channel",
                )

            total = FRAME_HEADER_SIZE + declared
            if len(self._buf) < total:
                # 截断：正常现象，继续等后续字节
                break

            body = bytes(self._buf[FRAME_HEADER_SIZE:total])
            del self._buf[:total]
            out.append(decode_payload(body))

        return out

    def finish(self) -> None:
        """连接正常关闭时调用。缓冲区有残留说明对端发了一半就断了。"""
        if self._buf:
            raise ProtocolError(
                ErrorCode.E_MALFORMED_FRAME,
                f"连接关闭时缓冲区仍有 {len(self._buf)} 字节残留（不完整帧）",
                {"buffered": len(self._buf)},
            )


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------


def iter_frames(messages: Iterable[dict[str, Any]]) -> bytes:
    """把多条消息拼成一段字节流（测试与黄金样例用）。"""
    return b"".join(encode_frame(m) for m in messages)
