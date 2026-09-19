# -*- coding: utf-8 -*-
"""Host Bridge —— 与 Android Runtime 的连接管理。

依据：总基线 §10 Protocol Layer v1 · §9.4 重连规则 · §19.3 阻塞 I/O 必须隔离。

职责
----
    connect / send / receive / close
    HELLO → HELLO_ACK → READY 握手
    独立线程心跳（PING / PONG），不得阻塞普通命令
    指数退避重连 1→2→4→8→16→30s，重连后旧 Session 强制失效
    FAST / JOB 命令分发
    事件缓冲与回调

线程模型
--------
    reader   线程：唯一持有 socket 读端，负责解帧与分发
    heartbeat 线程：定时发 PING、判定 DEGRADED / DISCONNECTED
    reconnect 线程：链路断开后按退避序列重连

`call()` 是阻塞调用。MCP Server 侧必须用 `acall()`（内部 asyncio.to_thread），
直接同步调用会卡死事件循环，导致 progress / cancel / 其他工具全部停摆。
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

from ..protocol import commands, frame as F, messages as M
from ..protocol.constants import (
    CLIENT_NAME,
    CLIENT_VERSION,
    CONNECT_TIMEOUT,
    HEARTBEAT_INTERVAL,
    HEARTBEAT_TIMEOUT,
    PROTOCOL_VERSION,
    RECONNECT_BACKOFF,
    LinkState,
    SessionState,
)
from ..protocol.errors import ErrorCode, ProtocolError
from . import transport
from .session import Session, SessionManager

EVENT_BUFFER_SIZE = 512


@dataclass
class _Pending:
    """一次在途请求的等待槽。"""

    request_id: str
    command: str
    event: threading.Event = field(default_factory=threading.Event)
    response: dict[str, Any] | None = None
    error: ProtocolError | None = None

    def resolve(self, response: dict[str, Any]) -> None:
        self.response = response
        self.event.set()

    def fail(self, error: ProtocolError) -> None:
        self.error = error
        self.event.set()


class BridgeClient:
    """与 Android 侧 Runtime 的 IPC 客户端。"""

    def __init__(
        self,
        endpoint: str,
        *,
        connect_timeout: float = CONNECT_TIMEOUT,
        heartbeat_interval: float = HEARTBEAT_INTERVAL,
        heartbeat_timeout: float = HEARTBEAT_TIMEOUT,
        auto_reconnect: bool = True,
        on_event: Callable[[dict[str, Any]], None] | None = None,
        on_link_change: Callable[[LinkState, str], None] | None = None,
    ) -> None:
        self._endpoint = transport.parse_endpoint(endpoint)
        self._connect_timeout = connect_timeout
        self._heartbeat_interval = heartbeat_interval
        self._heartbeat_timeout = heartbeat_timeout
        self._auto_reconnect = auto_reconnect

        self._on_event = on_event
        self._on_link_change = on_link_change

        self._sock: socket.socket | None = None
        self._decoder = F.FrameDecoder()
        self._inbox: deque[dict[str, Any]] = deque()
        self._events: deque[dict[str, Any]] = deque(maxlen=EVENT_BUFFER_SIZE)
        self._pending: dict[str, _Pending] = {}

        self._send_lock = threading.Lock()
        self._state_lock = threading.RLock()

        self._sessions = SessionManager()
        self._link = LinkState.DISCONNECTED
        self._link_reason = "未连接"

        self._closing = False
        self._threads: list[threading.Thread] = []
        self._reconnecting = False

        self._ping_seq = 0
        self._pong_seq = -1
        self._last_pong = time.monotonic()
        self._missed = 0
        self._last_rtt_ms: float | None = None

    # ------------------------------------------------------------------
    # 状态读取
    # ------------------------------------------------------------------

    @property
    def endpoint(self) -> str:
        """端点字符串（unix:... 或 tcp:host:port）。"""
        return self._endpoint.raw

    @property
    def link_state(self) -> LinkState:
        return self._link

    @property
    def link_reason(self) -> str:
        return self._link_reason

    @property
    def session(self) -> Session | None:
        return self._sessions.current

    @property
    def sessions(self) -> SessionManager:
        return self._sessions

    @property
    def connected(self) -> bool:
        return self._link in (LinkState.CONNECTED, LinkState.DEGRADED)

    @property
    def rtt_ms(self) -> float | None:
        return self._last_rtt_ms

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def connect(self) -> Session:
        """建立连接并完成握手。返回新建的 Session。"""
        with self._state_lock:
            self._closing = False
            self._open_socket()
            try:
                sess = self._handshake()
            except Exception:
                self._close_socket()
                raise
            self._link = LinkState.CONNECTED
            self._link_reason = "握手完成"
            self._last_pong = time.monotonic()
            self._missed = 0
            self._start_threads()
        self._notify_link(LinkState.CONNECTED, "握手完成")
        return sess

    def close(self) -> None:
        self._closing = True
        self._close_socket()
        self._fail_all_pending(
            ProtocolError(
                ErrorCode.E_TIMEOUT, "客户端已关闭", {}, next_step="重新 connect"
            )
        )
        for t in self._threads:
            t.join(timeout=2.0)
        self._threads.clear()
        self._sessions.close(SessionState.CLOSED)
        self._set_link(LinkState.DISCONNECTED, "客户端已关闭")

    def __enter__(self) -> "BridgeClient":
        self.connect()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # 握手
    # ------------------------------------------------------------------

    def _open_socket(self) -> None:
        sock = transport.connect(self._endpoint, self._connect_timeout)
        sock.settimeout(None)
        self._sock = sock
        self._decoder = F.FrameDecoder()
        self._inbox.clear()

    def _handshake(self) -> Session:
        self._send(M.make_hello(client=CLIENT_NAME, client_version=CLIENT_VERSION))

        ack = self._await_message(self._connect_timeout)
        if M.message_type_of(ack) != "HELLO_ACK":
            raise ProtocolError(
                ErrorCode.E_MALFORMED_FRAME,
                f"握手失败：期望 HELLO_ACK，收到 {M.message_type_of(ack)}",
                {"got": M.message_type_of(ack)},
            )
        M.check_protocol_version(ack, expected=PROTOCOL_VERSION)

        ready = self._await_message(self._connect_timeout)
        if M.message_type_of(ready) != "READY":
            raise ProtocolError(
                ErrorCode.E_MALFORMED_FRAME,
                f"握手失败：期望 READY，收到 {M.message_type_of(ready)}",
                {"got": M.message_type_of(ready)},
            )
        M.check_protocol_version(ready, expected=PROTOCOL_VERSION)
        M.validate(ready, strict=False)

        session_id = ack["session_id"]
        if ready.get("session_id") != session_id:
            raise ProtocolError(
                ErrorCode.E_MALFORMED_FRAME,
                "HELLO_ACK 与 READY 的 session_id 不一致",
                {"ack": session_id, "ready": ready.get("session_id")},
            )

        return self._sessions.open(
            session_id,
            state=SessionState(ready["state"]),
            capabilities=ready.get("capabilities") or {},
        )

    # ------------------------------------------------------------------
    # 收发
    # ------------------------------------------------------------------

    def _send(self, message: dict[str, Any]) -> None:
        sock = self._sock
        if sock is None:
            raise ProtocolError(
                ErrorCode.E_NOT_READY, "链路未建立，无法发送", {}, next_step="先 connect"
            )
        blob = F.encode_frame(message)
        with self._send_lock:
            try:
                sock.sendall(blob)
            except OSError as exc:
                self._on_link_lost(f"发送失败：{exc}")
                raise ProtocolError(
                    ErrorCode.E_TIMEOUT,
                    f"发送失败：{exc}",
                    {"command": message.get("command")},
                ) from exc

    def _pump_once(self, timeout: float | None) -> bool:
        """从 socket 读一块并解帧。返回 False 表示对端关闭。"""
        sock = self._sock
        if sock is None:
            return False
        if timeout is not None:
            sock.settimeout(timeout)
        data = sock.recv(65536)
        if not data:
            return False
        for msg in self._decoder.feed(data):
            self._inbox.append(msg)
        return True

    def _await_message(self, timeout: float) -> dict[str, Any]:
        """同步等待下一条消息。仅用于握手阶段（此时尚无 reader 线程）。"""
        deadline = time.monotonic() + timeout
        while not self._inbox:
            remain = deadline - time.monotonic()
            if remain <= 0:
                raise ProtocolError(
                    ErrorCode.E_TIMEOUT,
                    f"等待消息超时（{timeout}s）",
                    {"endpoint": self._endpoint.raw},
                    next_step="检查 Runtime 是否已就绪",
                )
            try:
                if not self._pump_once(remain):
                    raise ProtocolError(
                        ErrorCode.E_TIMEOUT,
                        "握手期间对端关闭了连接",
                        {"endpoint": self._endpoint.raw},
                    )
            except socket.timeout:
                raise ProtocolError(
                    ErrorCode.E_TIMEOUT,
                    f"等待消息超时（{timeout}s）",
                    {"endpoint": self._endpoint.raw},
                ) from None
            except OSError as exc:
                raise ProtocolError(
                    ErrorCode.E_TIMEOUT, f"读取失败：{exc}", {}
                ) from exc
        return self._inbox.popleft()

    # ------------------------------------------------------------------
    # 命令调用
    # ------------------------------------------------------------------

    def call(
        self,
        command: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """同步下发一条命令。**会阻塞**。

        MCP Server 侧请改用 `acall()`。
        """
        spec = commands.COMMANDS.get(command)
        if spec is None:
            raise ProtocolError(
                ErrorCode.E_UNKNOWN_CMD,
                f"未知命令：{command}",
                {"command": command},
                next_step="改用 commands.ALL_COMMANDS 中的命令",
            )
        if not self.connected:
            raise ProtocolError(
                ErrorCode.E_NOT_READY,
                f"链路不可用（{self._link.value}）：{self._link_reason}",
                {"link": self._link.value},
                next_step="等待自动重连完成，或重新 connect",
            )

        sess = self._sessions.require()
        req = M.make_request(command=command, payload=payload, session_id=sess.session_id)
        slot = _Pending(request_id=req["request_id"], command=command)
        self._pending[slot.request_id] = slot
        try:
            self._send(req)
        except Exception:
            self._pending.pop(slot.request_id, None)
            raise

        wait = timeout if timeout is not None else float(spec.timeout)
        if not slot.event.wait(wait):
            self._pending.pop(slot.request_id, None)
            raise ProtocolError(
                ErrorCode.E_TIMEOUT,
                f"命令 {command} 超时（{wait}s）",
                {"command": command, "timeout_s": wait, "cls": spec.cls.value},
                next_step="先探活（runtime.status），确认后端未卡死",
            )

        self._sessions.touch()
        if slot.error is not None:
            raise slot.error
        assert slot.response is not None
        if slot.response.get("status") == "error":
            raise ProtocolError(
                ErrorCode(slot.response.get("code", "E_INTERNAL"))
                if slot.response.get("code") in {c.value for c in ErrorCode}
                else ErrorCode.E_INTERNAL,
                f"命令 {command} 返回错误",
                {"response": slot.response.get("payload")},
            )
        return slot.response

    async def acall(
        self,
        command: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """异步版 `call()`。阻塞 I/O 必须丢线程池，否则卡死事件循环。"""
        return await asyncio.to_thread(self.call, command, payload, timeout=timeout)

    def submit_job(
        self, command: str, payload: dict[str, Any] | None = None
    ) -> str:
        """提交 JOB 命令，返回 job_id。"""
        resp = self.call(command, payload)
        job_id = (resp.get("payload") or {}).get("job_id")
        if not job_id:
            raise ProtocolError(
                ErrorCode.E_INTERNAL,
                f"命令 {command} 未返回 job_id",
                {"command": command},
            )
        return job_id

    def await_job(
        self,
        job_id: str,
        *,
        poll_interval: float = 0.2,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """轮询 job.status 直到终态。"""
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            resp = self.call("job.status", {"job_id": job_id})
            body = resp.get("payload") or {}
            state = body.get("state")
            if state in ("completed", "failed", "cancelled"):
                return body
            if deadline is not None and time.monotonic() > deadline:
                raise ProtocolError(
                    ErrorCode.E_TIMEOUT,
                    f"job {job_id} 等待超时",
                    {"job_id": job_id, "state": state},
                )
            time.sleep(poll_interval)

    # ------------------------------------------------------------------
    # 事件
    # ------------------------------------------------------------------

    def events(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        items = list(self._events)
        return items[-limit:] if limit else items

    def drain_events(self) -> list[dict[str, Any]]:
        items = list(self._events)
        self._events.clear()
        return items

    # ------------------------------------------------------------------
    # 线程
    # ------------------------------------------------------------------

    def _start_threads(self) -> None:
        for name, target in (
            ("zai-reader", self._reader_loop),
            ("zai-heartbeat", self._heartbeat_loop),
        ):
            t = threading.Thread(target=target, name=name, daemon=True)
            t.start()
            self._threads.append(t)

    def _reader_loop(self) -> None:
        while not self._closing:
            try:
                if not self._pump_once(0.5):
                    self._on_link_lost("对端关闭连接")
                    return
            except socket.timeout:
                continue
            except OSError as exc:
                self._on_link_lost(f"读取失败：{exc}")
                return
            while self._inbox:
                self._dispatch(self._inbox.popleft())

    def _dispatch(self, msg: dict[str, Any]) -> None:
        mtype = M.message_type_of(msg)

        if mtype == "PONG":
            self._last_pong = time.monotonic()
            self._missed = 0
            self._pong_seq = int(msg.get("seq", -1))
            self._sessions.touch()
            if self._link is LinkState.DEGRADED:
                self._set_link(LinkState.CONNECTED, "心跳恢复")
            return

        if mtype == "PING":
            # 服务端也可能主动心跳，必须回
            try:
                self._send(M.make_pong(seq=int(msg.get("seq", 0))))
            except ProtocolError:
                pass
            return

        if mtype == "RESPONSE":
            slot = self._pending.pop(msg.get("request_id", ""), None)
            if slot is not None:
                slot.resolve(msg)
            return

        if mtype == "ERROR":
            slot = self._pending.pop(msg.get("request_id") or "", None)
            err = msg.get("error") or {}
            code_raw = err.get("code")
            code = (
                ErrorCode(code_raw)
                if code_raw in {c.value for c in ErrorCode}
                else ErrorCode.E_INTERNAL
            )
            perr = ProtocolError(
                code,
                err.get("message", "对端返回错误"),
                dict(err.get("context") or {}),
                next_step=err.get("next_step"),
            )
            if slot is not None:
                slot.fail(perr)
            return

        if mtype == "EVENT":
            self._events.append(msg)
            self._sessions.touch()
            if self._on_event is not None:
                try:
                    self._on_event(msg)
                except Exception:  # noqa: BLE001 - 回调异常不得拖垮 reader 线程
                    pass
            return

        # HELLO_ACK / READY 在握手后不应再出现，忽略但不崩

    def _heartbeat_loop(self) -> None:
        while not self._closing:
            time.sleep(self._heartbeat_interval)
            if self._closing or not self.connected:
                continue

            self._ping_seq += 1
            sent_at = time.monotonic()
            try:
                self._send(M.make_ping(seq=self._ping_seq))
            except ProtocolError:
                continue

            # 等一个间隔再判定，避免刚发出就误判
            time.sleep(min(self._heartbeat_interval, 1.0))
            if self._pong_seq >= self._ping_seq:
                self._last_rtt_ms = (time.monotonic() - sent_at) * 1000.0
                self._missed = 0
                continue

            age = time.monotonic() - self._last_pong
            if age <= self._heartbeat_timeout:
                continue

            self._missed += 1
            if self._missed == 1:
                self._set_link(
                    LinkState.DEGRADED,
                    f"心跳超时 {age:.0f}s（未收到 PONG）",
                )
            else:
                self._on_link_lost(f"连续 {self._missed} 次心跳超时")

    # ------------------------------------------------------------------
    # 链路事件与重连
    # ------------------------------------------------------------------

    def _set_link(self, state: LinkState, reason: str) -> None:
        if self._link is state and self._link_reason == reason:
            return
        self._link = state
        self._link_reason = reason
        self._notify_link(state, reason)

    def _notify_link(self, state: LinkState, reason: str) -> None:
        if self._on_link_change is not None:
            try:
                self._on_link_change(state, reason)
            except Exception:  # noqa: BLE001
                pass

    def _on_link_lost(self, reason: str) -> None:
        with self._state_lock:
            if self._closing:
                return
            self._link = LinkState.DISCONNECTED
            self._link_reason = reason
        self._sessions.degrade(reason)
        self._fail_all_pending(
            ProtocolError(
                ErrorCode.E_SESSION_STALE,
                f"连接已断开（{reason}）。已自动重连后请重试。",
                {"session_id": self._sessions.current.session_id
                 if self._sessions.current else None},
                next_step="重连完成后重新发起；旧 session_id 已失效",
            )
        )
        self._notify_link(LinkState.DISCONNECTED, reason)

        if self._auto_reconnect and not self._reconnecting:
            self._reconnecting = True
            t = threading.Thread(
                target=self._reconnect_loop, name="zai-reconnect", daemon=True
            )
            t.start()
            self._threads.append(t)

    def _fail_all_pending(self, error: ProtocolError) -> None:
        for slot in list(self._pending.values()):
            slot.fail(error)
        self._pending.clear()

    def _close_socket(self) -> None:
        sock, self._sock = self._sock, None
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass

    def _reconnect_loop(self) -> None:
        """指数退避重连。上限防止疯狂重连占满事件循环。"""
        attempt = 0
        try:
            while not self._closing:
                delay = RECONNECT_BACKOFF[min(attempt, len(RECONNECT_BACKOFF) - 1)]
                self._link_reason = f"{attempt + 1} 次重连将在 {delay}s 后尝试"
                if self._sleep_interruptible(delay):
                    return
                self._close_socket()
                try:
                    self.connect()
                    return
                except Exception as exc:  # noqa: BLE001
                    attempt += 1
                    self._link_reason = f"重连失败：{exc}"
        finally:
            self._reconnecting = False

    def _sleep_interruptible(self, seconds: float) -> bool:
        """可被 close() 打断的 sleep。返回 True 表示应中止。"""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self._closing:
                return True
            time.sleep(min(0.1, end - time.monotonic()))
        return self._closing

    # ------------------------------------------------------------------
    # 测试辅助
    # ------------------------------------------------------------------

    def wait_for_link(self, state: LinkState, timeout: float = 10.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._link is state:
                return True
            time.sleep(0.05)
        return False

    def wait_for_session_generation(self, generation: int, timeout: float = 15.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._sessions.generation >= generation:
                return True
            time.sleep(0.05)
        return False
