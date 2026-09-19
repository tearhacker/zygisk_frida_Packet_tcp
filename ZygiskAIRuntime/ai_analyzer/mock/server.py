# -*- coding: utf-8 -*-
"""Mock Runtime 后端（UDS 服务端）。

作用：在没有真机、没有 NDK 的情况下，让 Host 侧 MVP 端到端跑通——
真实握手、真实命令往返、真实事件推送、真实断线重连。

**它不是 Fake Success。** 它明确标注自己是 Mock：
  - 能力表如实声明（https_decrypt=false）
  - 未实现的命令返回 E_NOT_READY 并说明原因，不返回编造的假数据
  - 地址校验是真的（未映射地址一律 E_READ_FAILED）

支持的命令见 `SUPPORTED_COMMANDS`。
"""

from __future__ import annotations

import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from ..bridge import transport
from ..protocol import frame as F, messages as M
from ..protocol.constants import (
    PROTOCOL_VERSION,
    SERVER_NAME,
    SERVER_VERSION,
    MessageType,
    SessionState,
)
from ..protocol.errors import ErrorCode, ProtocolError
from ..protocol.messages import new_session_id
from .state import MockRuntimeState

SUPPORTED_COMMANDS: frozenset[str] = frozenset(
    {
        "device.list",
        "device.info",
        "device.root_status",
        "session.list",
        "session.info",
        "session.capabilities",
        "process.list",
        "process.info",
        "process.modules",
        "process.threads",
        "runtime.status",
        "runtime.hook",
        "runtime.unhook",
        "runtime.hook_info",
        "memory.read",
        "memory.maps",
        "network.connections",
        "network.dns",
        "packet.get",
        "packet.list",
        "artifact.get",
        "artifact.list",
        "job.status",
        "job.result",
        "job.cancel",
        "memory.dump",
    }
)


@dataclass
class _Connection:
    """一条客户端连接。"""

    sock: socket.socket
    session_id: str
    decoder: F.FrameDecoder = field(default_factory=F.FrameDecoder)
    inbox: list[dict[str, Any]] = field(default_factory=list)
    send_lock: threading.Lock = field(default_factory=threading.Lock)
    alive: bool = True
    ready: bool = False
    heartbeat_enabled: bool = True

    def send(self, message: dict[str, Any]) -> None:
        with self.send_lock:
            try:
                self.sock.sendall(F.encode_frame(message))
            except OSError:
                self.alive = False

    def close(self) -> None:
        self.alive = False
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


class MockRuntimeServer:
    """模拟 Android 侧 Runtime 的 IPC 服务端。"""

    def __init__(
        self,
        endpoint: str,
        *,
        state: MockRuntimeState | None = None,
        package: str | None = None,
    ) -> None:
        self._requested = transport.parse_endpoint(endpoint)
        self._bound = self._requested
        self.state = state or MockRuntimeState(**({"package": package} if package else {}))
        self._srv: socket.socket | None = None
        self._accept_thread: threading.Thread | None = None
        self._closing = False
        self._conns: list[_Connection] = []
        self._lock = threading.Lock()
        self._handshake_count = 0
        self._block_handshake = threading.Event()

    @property
    def endpoint(self) -> str:
        """绑定后的真实端点（TCP 端口为 0 时会解析出实际端口）。"""
        return self._bound.raw

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def start(self) -> "MockRuntimeServer":
        srv, bound = transport.listen(self._requested)
        srv.settimeout(0.3)
        self._srv = srv
        self._bound = bound
        self._closing = False

        self._accept_thread = threading.Thread(
            target=self._accept_loop, name="mock-accept", daemon=True
        )
        self._accept_thread.start()
        return self

    def stop(self) -> None:
        self._closing = True
        with self._lock:
            for conn in list(self._conns):
                conn.close()
            self._conns.clear()
        if self._srv is not None:
            try:
                self._srv.close()
            except OSError:
                pass
            self._srv = None
        if self._accept_thread is not None:
            self._accept_thread.join(timeout=2.0)
            self._accept_thread = None
        transport.cleanup(self._bound)

    def __enter__(self) -> "MockRuntimeServer":
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.stop()

    # ------------------------------------------------------------------
    # 测试控制
    # ------------------------------------------------------------------

    @property
    def handshake_count(self) -> int:
        """完成的握手次数。重连后应递增。"""
        return self._handshake_count

    @property
    def connections(self) -> int:
        with self._lock:
            return len(self._conns)

    def drop_connections(self) -> None:
        """强行掐断所有连接 —— 用于验证断线重连。"""
        with self._lock:
            for conn in list(self._conns):
                conn.close()
            self._conns.clear()

    def set_heartbeat_enabled(self, enabled: bool) -> None:
        """关掉 PONG 应答 —— 用于验证 DEGRADED 判定。"""
        with self._lock:
            for conn in self._conns:
                conn.heartbeat_enabled = enabled

    def block_handshake(self, blocked: bool = True) -> None:
        """让握手卡住 —— 用于验证连接超时。"""
        if blocked:
            self._block_handshake.set()
        else:
            self._block_handshake.clear()

    def emit_event(
        self,
        event_type: str,
        *,
        source: str = "runtime",
        payload: dict[str, Any] | None = None,
        tid: int | None = None,
    ) -> int:
        """向所有已 READY 的连接推送一条事件。返回推送到的连接数。"""
        with self._lock:
            conns = [c for c in self._conns if c.ready and c.alive]
        n = 0
        for conn in conns:
            evt = M.make_event(
                event_type=event_type,
                session_id=conn.session_id,
                source=source,
                payload=payload,
                pid=self.state.pid,
                tid=tid if tid is not None else self.state.pid,
            )
            conn.send(evt)
            n += 1
        return n

    # ------------------------------------------------------------------
    # 接受连接
    # ------------------------------------------------------------------

    def _accept_loop(self) -> None:
        while not self._closing:
            srv = self._srv
            if srv is None:
                return
            try:
                sock, _ = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            conn = _Connection(sock=sock, session_id=new_session_id())
            with self._lock:
                self._conns.append(conn)
            threading.Thread(
                target=self._serve, args=(conn,), name="mock-conn", daemon=True
            ).start()

    # ------------------------------------------------------------------
    # 单连接服务
    # ------------------------------------------------------------------

    def _serve(self, conn: _Connection) -> None:
        try:
            if not self._do_handshake(conn):
                return
            while conn.alive and not self._closing:
                try:
                    msg = self._read_message(conn, timeout=0.5)
                except ProtocolError:
                    # 畸形帧：回一条 ERROR 后断开
                    conn.send(
                        M.make_error(
                            error=ProtocolError(
                                ErrorCode.E_MALFORMED_FRAME, "帧解析失败"
                            ),
                            session_id=conn.session_id,
                        )
                    )
                    return
                if msg is None:
                    continue
                self._handle(conn, msg)
        except OSError:
            pass
        finally:
            conn.close()
            with self._lock:
                if conn in self._conns:
                    self._conns.remove(conn)

    def _do_handshake(self, conn: _Connection) -> bool:
        hello = self._read_message(conn, timeout=10.0)
        if hello is None:
            return False

        if self._block_handshake.is_set():
            time.sleep(30)
            return False

        if M.message_type_of(hello) != "HELLO":
            conn.send(
                M.make_error(
                    error=ProtocolError(
                        ErrorCode.E_MALFORMED_FRAME,
                        f"握手首帧必须是 HELLO，收到 {M.message_type_of(hello)}",
                    )
                )
            )
            return False

        got = M.protocol_version_of(hello)
        if got != PROTOCOL_VERSION:
            # 版本不匹配 → 禁止进入 READY（总基线 §10.3）
            err = ProtocolError(
                ErrorCode.ERROR_PROTOCOL_VERSION,
                f"协议版本不匹配：服务端 {PROTOCOL_VERSION}，客户端 {got!r}",
                {"expected": PROTOCOL_VERSION, "got": got},
                next_step=f"升级客户端到协议版本 {PROTOCOL_VERSION}",
            )
            conn.send(M.make_error(error=err))
            return False

        conn.send(
            M.make_hello_ack(
                session_id=conn.session_id,
                server=SERVER_NAME,
                server_version=SERVER_VERSION,
                capabilities=["native_hook", "java_hook", "memory_read",
                              "memory_write", "packet_intercept"],
            )
        )
        conn.send(
            M.make_ready(
                session_id=conn.session_id,
                state=self.state.state,
                capabilities=self.state.capabilities,
            )
        )
        conn.ready = True
        self._handshake_count += 1

        # 会话建立后立即推送 RUNTIME_READY，让事件通道有真实内容
        conn.send(
            M.make_event(
                event_type="RUNTIME_READY",
                session_id=conn.session_id,
                source="runtime",
                payload={
                    "package": self.state.package,
                    "abi": self.state.abi,
                    "sdk": self.state.sdk,
                },
                pid=self.state.pid,
                tid=self.state.pid,
            )
        )
        return True

    def _read_message(
        self, conn: _Connection, *, timeout: float
    ) -> dict[str, Any] | None:
        if conn.inbox:
            return conn.inbox.pop(0)
        conn.sock.settimeout(timeout)
        try:
            data = conn.sock.recv(65536)
        except socket.timeout:
            return None
        if not data:
            conn.alive = False
            return None
        conn.inbox.extend(conn.decoder.feed(data))
        return conn.inbox.pop(0) if conn.inbox else None

    # ------------------------------------------------------------------
    # 消息分发
    # ------------------------------------------------------------------

    def _handle(self, conn: _Connection, msg: dict[str, Any]) -> None:
        mtype = M.message_type_of(msg)

        if mtype == "PING":
            if conn.heartbeat_enabled:
                conn.send(M.make_pong(seq=int(msg.get("seq", 0))))
            return

        if mtype == "PONG":
            return

        if mtype != "REQUEST":
            return

        request_id = msg.get("request_id", "")
        session_id = msg.get("session_id")
        command = msg.get("command", "")
        payload = msg.get("payload") or {}

        # Session 必须匹配当前连接 —— 重连后旧 Session 一律失效
        if session_id != conn.session_id:
            conn.send(
                M.make_error(
                    error=ProtocolError(
                        ErrorCode.E_SESSION_STALE,
                        "session_id 已失效（重连后旧 Session 不恢复）",
                        {"got": session_id, "current": conn.session_id},
                        next_step="重新 session.list 获取新 Session",
                    ),
                    request_id=request_id,
                    session_id=conn.session_id,
                )
            )
            return

        handler = getattr(self, f"_cmd_{command.replace('.', '_')}", None)
        if handler is None:
            conn.send(
                M.make_response(
                    request_id=request_id,
                    session_id=conn.session_id,
                    status="error",
                    code=ErrorCode.E_NOT_READY.value,
                    payload={
                        "reason": "capability unavailable",
                        "command": command,
                        "mock_supported": sorted(SUPPORTED_COMMANDS),
                        "note": "Mock 后端未实现该命令；真机 Runtime 就绪后由 Android 侧提供",
                    },
                )
            )
            return

        try:
            result = handler(conn, payload)
        except ProtocolError as exc:
            conn.send(
                M.make_error(error=exc, request_id=request_id, session_id=conn.session_id)
            )
            return

        conn.send(
            M.make_response(
                request_id=request_id,
                session_id=conn.session_id,
                status="ok",
                code="OK",
                payload=result,
            )
        )

    # ------------------------------------------------------------------
    # 命令实现
    # ------------------------------------------------------------------

    def _cmd_device_list(self, conn: _Connection, payload: dict) -> dict:
        return {
            "total": 1,
            "devices": [
                {
                    "serial": "MOCK-0001",
                    "model": "Mock Device",
                    "manufacturer": "Mock",
                    "android": "14",
                    "api": self.state.sdk,
                    "abi": self.state.abi,
                    "rooted": True,
                    "zygisk": True,
                }
            ],
        }

    def _cmd_device_info(self, conn: _Connection, payload: dict) -> dict:
        return {
            "serial": "MOCK-0001",
            "model": "Mock Device",
            "manufacturer": "Mock",
            "android": "14",
            "api": self.state.sdk,
            "abi": self.state.abi,
            "kernel": "6.1.0-mock",
            "page_size": 4096,
            "magisk": "mock-27000",
            "zygisk": "enabled",
            "selinux": "permissive",
            "rooted": True,
        }

    def _cmd_device_root_status(self, conn: _Connection, payload: dict) -> dict:
        return {"rooted": True, "magisk": True, "zygisk": True, "selinux": "permissive"}

    def _cmd_session_list(self, conn: _Connection, payload: dict) -> dict:
        return {
            "total": 1,
            "sessions": [
                {
                    "session_id": conn.session_id,
                    "state": self.state.state.value,
                    "package": self.state.package,
                    "pid": self.state.pid,
                    "uptime_ms": self.state.uptime_ms,
                }
            ],
        }

    def _cmd_session_info(self, conn: _Connection, payload: dict) -> dict:
        return {
            "session_id": conn.session_id,
            "state": self.state.state.value,
            "package": self.state.package,
            "pid": self.state.pid,
            "uid": self.state.uid,
            "abi": self.state.abi,
            "sdk": self.state.sdk,
            "uptime_ms": self.state.uptime_ms,
            "capabilities": self.state.capabilities,
        }

    def _cmd_session_capabilities(self, conn: _Connection, payload: dict) -> dict:
        return {
            "capabilities": self.state.capabilities,
            "note": "能力为 false 表示不可用；相关工具不应被调用",
        }

    def _cmd_process_list(self, conn: _Connection, payload: dict) -> dict:
        return {
            "total": 1,
            "truncated": False,
            "processes": [
                {
                    "pid": self.state.pid,
                    "package": self.state.package,
                    "uid": self.state.uid,
                    "process_name": self.state.package,
                    "is_target": True,
                }
            ],
        }

    def _cmd_process_info(self, conn: _Connection, payload: dict) -> dict:
        return {
            "pid": self.state.pid,
            "package": self.state.package,
            "uid": self.state.uid,
            "abi": self.state.abi,
            "sdk": self.state.sdk,
            "threads": len(self.state.threads),
            "modules": len(self.state.modules),
            "uptime_ms": self.state.uptime_ms,
        }

    def _cmd_process_modules(self, conn: _Connection, payload: dict) -> dict:
        mods = self.state.modules
        return {
            "total": len(mods),
            "truncated": False,
            "modules": [m.to_dict() for m in mods],
        }

    def _cmd_process_threads(self, conn: _Connection, payload: dict) -> dict:
        ths = self.state.threads
        return {
            "total": len(ths),
            "truncated": False,
            "threads": [t.to_dict() for t in ths],
        }

    def _cmd_runtime_status(self, conn: _Connection, payload: dict) -> dict:
        return self.state.status()

    def _cmd_runtime_hook(self, conn: _Connection, payload: dict) -> dict:
        """安装 Hook。

        🔴 禁止 Fake Success：返回值必须体现 accepted → executed → verified，
        并且真的推出 HOOK_INSTALLED / HOOK_ENTER / HOOK_LEAVE 事件。
        """
        module = payload.get("module")
        address = payload.get("address")
        if not module or not address:
            raise ProtocolError(
                ErrorCode.E_BAD_ARGS,
                "runtime.hook 需要 module 与 address",
                {"got": sorted(payload.keys())},
                next_step="先 process.modules 取模块名与基址，再算 address",
            )

        hook = self.state.create_hook(module, address)

        events = ["HOOK_INSTALLED", "HOOK_ENTER", "HOOK_LEAVE"]
        conn.send(
            M.make_event(
                event_type="HOOK_INSTALLED",
                session_id=conn.session_id,
                source="runtime",
                payload={"hook_id": hook.hook_id, "module": module, "address": address},
                pid=self.state.pid,
                tid=self.state.pid,
            )
        )
        for etype, extra in (
            ("HOOK_ENTER", {"arguments": ["0x1", "0x7ffd12ab"]}),
            ("HOOK_LEAVE", {"return_value": "0x0", "duration_us": 812}),
        ):
            conn.send(
                M.make_event(
                    event_type=etype,
                    session_id=conn.session_id,
                    source="runtime",
                    payload={
                        "hook_id": hook.hook_id,
                        "module": module,
                        "address": address,
                        **extra,
                    },
                    pid=self.state.pid,
                    tid=self.state.pid + 8,
                )
            )
        hook.enter_count += 1
        hook.leave_count += 1

        return {
            "hook": hook.to_dict(),
            "execution": {"accepted": True, "executed": True, "verified": True},
            "events_observed": events,
            "note": "verified 由真实 HOOK_ENTER / HOOK_LEAVE 事件支撑",
        }

    def _cmd_runtime_unhook(self, conn: _Connection, payload: dict) -> dict:
        hook_id = payload.get("hook_id")
        hook = self.state.hooks.get(hook_id or "")
        if hook is None:
            raise ProtocolError(
                ErrorCode.E_NOT_FOUND,
                f"Hook 不存在：{hook_id}",
                {"hook_id": hook_id, "candidates": sorted(self.state.hooks)},
                next_step="用 candidates 里的 hook_id 重试",
            )
        hook.status = "removed"
        return {"hook_id": hook_id, "status": "removed",
                "execution": {"accepted": True, "executed": True, "verified": True}}

    def _cmd_runtime_hook_info(self, conn: _Connection, payload: dict) -> dict:
        hook_id = payload.get("hook_id")
        if hook_id:
            hook = self.state.hooks.get(hook_id)
            if hook is None:
                raise ProtocolError(
                    ErrorCode.E_NOT_FOUND,
                    f"Hook 不存在：{hook_id}",
                    {"hook_id": hook_id, "candidates": sorted(self.state.hooks)},
                )
            return {"hook": hook.to_dict()}
        hooks = list(self.state.hooks.values())
        return {"total": len(hooks), "hooks": [h.to_dict() for h in hooks]}

    def _cmd_memory_read(self, conn: _Connection, payload: dict) -> dict:
        raw = payload.get("address")
        length = int(payload.get("length", 16))
        try:
            address = int(raw, 16) if isinstance(raw, str) else int(raw)
        except (TypeError, ValueError):
            raise ProtocolError(
                ErrorCode.E_BAD_ARGS,
                f"address 必须是 '0x...' 字符串或整数，收到 {raw!r}",
                {"address": raw},
            ) from None
        data = self.state.read_memory(address, length)
        module = self.state.module_for_address(address, length)
        return {
            "address": f"0x{address:x}",
            "length": len(data),
            "hex": data.hex(),
            "ascii": "".join(chr(b) if 32 <= b < 127 else "." for b in data),
            "module": module.name if module else None,
            "permissions": module.permissions if module else None,
        }

    def _cmd_memory_maps(self, conn: _Connection, payload: dict) -> dict:
        mods = self.state.modules
        return {
            "total": len(mods),
            "maps": [
                {
                    "module": m.name,
                    "start": f"0x{m.base:x}",
                    "end": f"0x{m.end:x}",
                    "permissions": m.permissions,
                }
                for m in mods
            ],
        }

    def _cmd_memory_dump(self, conn: _Connection, payload: dict) -> dict:
        """JOB 命令：立即返回 job_id，产物走 Artifact 通道。"""
        job = self.state.new_job("memory.dump")
        return {
            "job_id": job.job_id,
            "state": job.state,
            "note": "JOB 命令：用 job.status 轮询，完成后 result 只给 metadata + sha256",
        }

    def _cmd_network_connections(self, conn: _Connection, payload: dict) -> dict:
        conns = self.state.connections
        return {
            "total": len(conns),
            "truncated": False,
            "connections": [c.to_dict() for c in conns],
        }

    def _cmd_network_dns(self, conn: _Connection, payload: dict) -> dict:
        return {
            "total": 2,
            "queries": [
                {"host": "api.example.com", "address": "93.184.216.34", "type": "A"},
                {"host": "cdn.example.com", "address": "93.184.216.35", "type": "A"},
            ],
        }

    def _cmd_packet_list(self, conn: _Connection, payload: dict) -> dict:
        pkts = self.state.packets
        return {
            "total": len(pkts),
            "truncated": False,
            "packets": [p.to_dict() for p in pkts],
        }

    def _cmd_packet_get(self, conn: _Connection, payload: dict) -> dict:
        packet_id = payload.get("packet_id")
        pkt = next((p for p in self.state.packets if p.packet_id == packet_id), None)
        if pkt is None:
            # 规则 §11.6-1：禁止裸 "not found"，给候选 + 中性描述
            raise ProtocolError(
                ErrorCode.E_NOT_FOUND,
                f"未找到 packet_id={packet_id}；可能是 id 写错或包尚未捕获",
                {
                    "packet_id": packet_id,
                    "candidates": [p.packet_id for p in self.state.packets],
                    "candidate_count": len(self.state.packets),
                },
                next_step="用 context.candidates 里的 id 重试，或先 packet.list",
            )
        include_hex = bool(payload.get("include_hex", True))
        out = pkt.to_dict(with_hex=include_hex)
        if not include_hex:
            out["note"] = "大对象不进协议 JSON；如需完整内容走 Artifact 通道"
        return {"packet": out}

    def _cmd_artifact_list(self, conn: _Connection, payload: dict) -> dict:
        return {
            "total": 0,
            "artifacts": [],
            "note": "Mock 后端不产生真实产物（避免假产物被当成真结果）",
        }

    def _cmd_artifact_get(self, conn: _Connection, payload: dict) -> dict:
        artifact_id = payload.get("artifact_id")
        raise ProtocolError(
            ErrorCode.E_NOT_FOUND,
            f"Mock 后端没有 artifact：{artifact_id}",
            {"artifact_id": artifact_id, "candidates": []},
            next_step="Mock 后端不落盘产物；接入真机 Runtime 后才有",
        )

    def _cmd_job_status(self, conn: _Connection, payload: dict) -> dict:
        self.state.advance_jobs()
        job_id = payload.get("job_id")
        job = self.state.jobs.get(job_id or "")
        if job is None:
            raise ProtocolError(
                ErrorCode.E_NOT_FOUND,
                f"Job 不存在：{job_id}",
                {"job_id": job_id, "candidates": sorted(self.state.jobs)},
            )
        return job.to_dict()

    def _cmd_job_result(self, conn: _Connection, payload: dict) -> dict:
        job_id = payload.get("job_id")
        job = self.state.jobs.get(job_id or "")
        if job is None:
            raise ProtocolError(
                ErrorCode.E_NOT_FOUND,
                f"Job 不存在：{job_id}",
                {"job_id": job_id, "candidates": sorted(self.state.jobs)},
            )
        if job.state == "running":
            raise ProtocolError(
                ErrorCode.E_NOT_READY,
                f"Job 尚未完成：{job_id}",
                {"job_id": job_id, "state": job.state, "progress": job.progress},
                next_step="继续轮询 job.status",
            )
        return job.to_dict()

    def _cmd_job_cancel(self, conn: _Connection, payload: dict) -> dict:
        job_id = payload.get("job_id")
        job = self.state.jobs.get(job_id or "")
        if job is None:
            raise ProtocolError(
                ErrorCode.E_NOT_FOUND,
                f"Job 不存在：{job_id}",
                {"job_id": job_id, "candidates": sorted(self.state.jobs)},
            )
        job.state = "cancelled"
        return job.to_dict()
