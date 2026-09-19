# -*- coding: utf-8 -*-
"""传输层抽象：Unix Domain Socket 与 TCP 回环。

为什么需要两种传输
------------------
总基线 §10.1 冻结的传输是 **Unix Domain Socket**。但有两类现实约束：

1. **宿主可能没有 AF_UNIX**。Windows 上的 CPython 不一定编译进
   `socket.AF_UNIX`（本机 3.13.14 即没有）。这不是协议问题，是宿主能力问题。
2. **真机部署本来就要跨进程边界**。PC 侧连设备侧 UDS，标准做法是
   `adb forward tcp:<port> tcp:<port>`，本地落成 TCP 回环。

因此：**帧格式、消息格式、握手流程、心跳、重连在两种传输上完全一致**，
传输层只决定字节往哪送。UDS 优先，TCP 回环是等价回退。

端点写法
--------
    unix:/data/local/tmp/ai-analyzer/analyzer.sock     设备侧 UDS
    unix:/tmp/zai.sock                                 本机 UDS
    /tmp/zai.sock                                      裸路径，等价 unix:
    tcp:127.0.0.1:27901                                TCP 回环
    tcp:127.0.0.1:0                                    服务端用：绑定临时端口
"""

from __future__ import annotations

import socket
from dataclasses import dataclass

from ..protocol.constants import (
    DEFAULT_TCP_ENDPOINT,
    TRANSPORT_TCP,
    TRANSPORT_UNIX,
)
from ..protocol.errors import ErrorCode, ProtocolError

HAS_AF_UNIX = hasattr(socket, "AF_UNIX")


@dataclass(frozen=True)
class Endpoint:
    """解析后的端点。"""

    kind: str
    raw: str
    path: str | None = None
    host: str | None = None
    port: int | None = None

    @property
    def is_unix(self) -> bool:
        return self.kind == TRANSPORT_UNIX

    @property
    def is_ephemeral(self) -> bool:
        return self.kind == TRANSPORT_TCP and self.port == 0

    def with_port(self, port: int) -> "Endpoint":
        return Endpoint(
            kind=self.kind,
            raw=f"{TRANSPORT_TCP}:{self.host}:{port}",
            host=self.host,
            port=port,
        )

    def __str__(self) -> str:
        return self.raw


def parse_endpoint(spec: str) -> Endpoint:
    """解析端点字符串。"""
    if not spec:
        raise ProtocolError(
            ErrorCode.E_BAD_ARGS, "端点不能为空", {}, next_step="给出 unix: 或 tcp: 端点"
        )

    if spec.startswith(f"{TRANSPORT_TCP}:"):
        rest = spec[len(TRANSPORT_TCP) + 1 :]
        if ":" not in rest:
            raise ProtocolError(
                ErrorCode.E_BAD_ARGS,
                f"TCP 端点必须写成 tcp:host:port，收到 {spec!r}",
                {"spec": spec},
            )
        host, _, port_raw = rest.rpartition(":")
        try:
            port = int(port_raw)
        except ValueError:
            raise ProtocolError(
                ErrorCode.E_BAD_ARGS,
                f"TCP 端口不是整数：{port_raw!r}",
                {"spec": spec},
            ) from None
        if not (0 <= port <= 65535):
            raise ProtocolError(
                ErrorCode.E_BAD_ARGS, f"TCP 端口越界：{port}", {"spec": spec}
            )
        return Endpoint(kind=TRANSPORT_TCP, raw=spec, host=host or "127.0.0.1", port=port)

    if spec.startswith(f"{TRANSPORT_UNIX}:"):
        return Endpoint(kind=TRANSPORT_UNIX, raw=spec, path=spec[len(TRANSPORT_UNIX) + 1 :])

    # 裸字符串按 UDS 路径处理（与 DEFAULT_SOCKET_PATH 一致）
    return Endpoint(kind=TRANSPORT_UNIX, raw=f"{TRANSPORT_UNIX}:{spec}", path=spec)


def _require_af_unix(ep: Endpoint) -> None:
    if not HAS_AF_UNIX:
        raise ProtocolError(
            ErrorCode.E_NOT_READY,
            "当前 Python 运行时不支持 AF_UNIX（Windows 上的常见情况）",
            {"endpoint": ep.raw, "python_has_af_unix": False},
            next_step=(
                "改用 TCP 回环端点，例如 " + DEFAULT_TCP_ENDPOINT
                + "；真机场景用 adb forward tcp:<port> tcp:<port> 转发设备侧 UDS"
            ),
        )


def connect(ep: Endpoint, timeout: float) -> socket.socket:
    """建立连接。"""
    if ep.is_unix:
        _require_af_unix(ep)
        assert ep.path is not None
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect(ep.path)
        except (FileNotFoundError, ConnectionRefusedError, socket.timeout, OSError) as exc:
            sock.close()
            raise ProtocolError(
                ErrorCode.E_NOT_READY,
                f"无法连接到 Runtime：{exc}",
                {"endpoint": ep.raw, "kind": ep.kind},
                next_step="确认目标 App 已启动、Runtime 已拉起、端点正确",
            ) from exc
        return sock

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((ep.host, ep.port))
    except (ConnectionRefusedError, socket.timeout, OSError) as exc:
        sock.close()
        raise ProtocolError(
            ErrorCode.E_NOT_READY,
            f"无法连接到 Runtime：{exc}",
            {"endpoint": ep.raw, "kind": ep.kind},
            next_step="确认 Runtime 已启动；真机场景先 adb forward",
        ) from exc
    return sock


def listen(ep: Endpoint, backlog: int = 8) -> tuple[socket.socket, Endpoint]:
    """监听。TCP 端口为 0 时返回绑定后的真实端点。"""
    if ep.is_unix:
        _require_af_unix(ep)
        assert ep.path is not None
        from pathlib import Path

        p = Path(ep.path)
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists():
            p.unlink()
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(ep.path)
        srv.listen(backlog)
        return srv, ep

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((ep.host, ep.port))
    srv.listen(backlog)
    actual = srv.getsockname()[1]
    return srv, ep.with_port(actual)


def cleanup(ep: Endpoint) -> None:
    """清理端点残留（UDS 需要删文件）。"""
    if not ep.is_unix or not ep.path:
        return
    import os

    try:
        os.unlink(ep.path)
    except OSError:
        pass
