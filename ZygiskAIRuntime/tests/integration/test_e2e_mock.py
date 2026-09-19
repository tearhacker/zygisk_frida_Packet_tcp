# -*- coding: utf-8 -*-
"""端到端集成测试：Mock Runtime 后端 ↔ Host Bridge。

这是 MVP 的**主验收**：在无 NDK、无真机的条件下，
真实握手、真实命令往返、真实事件推送、真实断线重连全部跑通。

⚠️ 本测试证明的是 **Host 侧 MVP 成立**，
   不代表 Android 侧已实现 —— Android 侧代码尚未编译验证。
"""

from __future__ import annotations

import shutil
import socket
import tempfile
import time
from pathlib import Path

import pytest

from ai_analyzer.bridge import BridgeClient
from ai_analyzer.bridge import transport
from ai_analyzer.bridge.transport import HAS_AF_UNIX
from ai_analyzer.mock import MockRuntimeServer
from ai_analyzer.protocol import frame as F, messages as M
from ai_analyzer.protocol.constants import LinkState, SessionState
from ai_analyzer.protocol.errors import ErrorCode, ProtocolError


@pytest.fixture
def sock_dir():
    d = Path(tempfile.mkdtemp(prefix="zai"))
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def endpoint_spec(sock_dir: Path) -> str:
    """优先 UDS（总基线 §10.1 冻结方案）；宿主无 AF_UNIX 时回退 TCP 回环。"""
    if HAS_AF_UNIX:
        return f"unix:{sock_dir / 's.sock'}"
    return "tcp:127.0.0.1:0"


@pytest.fixture
def server(endpoint_spec: str):
    srv = MockRuntimeServer(endpoint_spec).start()
    try:
        yield srv
    finally:
        srv.stop()


@pytest.fixture
def make_server():
    """自管生命周期的 Mock 服务端工厂。"""
    created: list[MockRuntimeServer] = []

    def _make(spec: str) -> MockRuntimeServer:
        srv = MockRuntimeServer(spec).start()
        created.append(srv)
        return srv

    try:
        yield _make
    finally:
        for srv in created:
            srv.stop()


@pytest.fixture
def client(server: MockRuntimeServer):
    c = BridgeClient(
        server.endpoint,
        heartbeat_interval=0.3,
        heartbeat_timeout=1.5,
        auto_reconnect=False,
    )
    c.connect()
    try:
        yield c
    finally:
        c.close()


# ---------------------------------------------------------------------------
# 握手
# ---------------------------------------------------------------------------


def test_handshake_creates_session(client: BridgeClient):
    sess = client.session
    assert sess is not None
    assert sess.session_id.startswith("sess_")
    assert sess.state is SessionState.RUNNING
    assert sess.generation == 1
    assert client.link_state is LinkState.CONNECTED
    assert client.connected


def test_handshake_reports_capabilities_honestly(client: BridgeClient):
    sess = client.session
    assert sess.capability("runtime", "native_hook") is True
    assert sess.capability("runtime", "memory_read") is True
    assert sess.capability("network", "https_capture") is True
    # 冻结纪律：抓到 HTTPS ≠ 能解密
    assert sess.capability("network", "https_decrypt") is False
    # 未声明的能力一律视为不可用
    assert sess.capability("runtime", "teleport") is False


def test_connect_to_missing_endpoint_raises(sock_dir: Path):
    if HAS_AF_UNIX:
        spec = f"unix:{sock_dir / 'nope.sock'}"
    else:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        spec = f"tcp:127.0.0.1:{port}"

    c = BridgeClient(spec, auto_reconnect=False)
    with pytest.raises(ProtocolError) as ei:
        c.connect()
    assert ei.value.code is ErrorCode.E_NOT_READY
    assert ei.value.context["endpoint"] == spec


# ---------------------------------------------------------------------------
# 命令往返
# ---------------------------------------------------------------------------


def test_runtime_status_returns_real_payload(client: BridgeClient):
    resp = client.call("runtime.status")
    body = resp["payload"]
    assert resp["status"] == "ok"
    assert body["package"] == "com.example.target"
    assert body["pid"] == 18342
    assert body["abi"] == "arm64-v8a"
    assert body["runtime_ready"] is True
    assert body["modules_count"] >= 4


def test_process_queries(client: BridgeClient):
    procs = client.call("process.list")["payload"]
    assert procs["total"] == 1
    assert procs["processes"][0]["is_target"] is True

    mods = client.call("process.modules")["payload"]
    names = [m["name"] for m in mods["modules"]]
    assert "libgame.so" in names
    # 地址必须是 "0x..." 字符串，不能用 number
    assert all(m["base"].startswith("0x") for m in mods["modules"])

    ths = client.call("process.threads")["payload"]
    assert ths["total"] == 4
    assert ths["threads"][0]["name"] == "main"


def test_session_and_device_queries(client: BridgeClient):
    caps = client.call("session.capabilities")["payload"]
    assert caps["capabilities"]["network"]["https_decrypt"] is False

    info = client.call("session.info")["payload"]
    assert info["session_id"] == client.session.session_id

    dev = client.call("device.info")["payload"]
    assert dev["zygisk"] == "enabled"
    assert dev["page_size"] == 4096


# ---------------------------------------------------------------------------
# 内存：校验器必须真的拦
# ---------------------------------------------------------------------------


def test_memory_read_mapped_address(client: BridgeClient):
    # libgame.so base = 0x7A3F1C0000，Mock 在 +0x2000 铺了可识别内容
    resp = client.call(
        "memory.read", {"address": "0x7a3f1c2000", "length": 16}
    )
    body = resp["payload"]
    assert body["address"] == "0x7a3f1c2000"
    assert body["length"] == 16
    assert body["module"] == "libgame.so"
    assert body["hex"].startswith("41492d414e414c595a45522d")
    assert "AI-ANALYZER-MOCK" in body["ascii"]


def test_memory_read_unmapped_address_is_refused(client: BridgeClient):
    """未映射地址必须 E_READ_FAILED，并且给出可用区间 —— 不能编假数据。"""
    with pytest.raises(ProtocolError) as ei:
        client.call("memory.read", {"address": "0xdeadbeef", "length": 16})
    err = ei.value
    assert err.code is ErrorCode.E_READ_FAILED
    assert err.context["mapped_ranges"]
    assert err.next_step


def test_memory_read_rejects_bad_length(client: BridgeClient):
    with pytest.raises(ProtocolError) as ei:
        client.call("memory.read", {"address": "0x7a3f1c2000", "length": 999999})
    assert ei.value.code is ErrorCode.E_BAD_ARGS


def test_memory_maps(client: BridgeClient):
    body = client.call("memory.maps")["payload"]
    assert body["total"] == 4
    assert body["maps"][0]["start"].startswith("0x")


# ---------------------------------------------------------------------------
# 禁止 Fake Success：Hook 必须给出三级证据
# ---------------------------------------------------------------------------


def test_runtime_hook_provides_three_level_evidence(client: BridgeClient):
    resp = client.call(
        "runtime.hook", {"module": "libgame.so", "address": "0x7a3f1c0040"}
    )
    body = resp["payload"]

    # status=ok 不够，必须有三级执行证据
    assert body["execution"] == {
        "accepted": True,
        "executed": True,
        "verified": True,
    }
    assert body["hook"]["status"] == "active"

    # verified 必须由真实事件支撑
    deadline = time.monotonic() + 3.0
    seen: set[str] = set()
    while time.monotonic() < deadline:
        seen = {e["event_type"] for e in client.events()}
        if {"HOOK_INSTALLED", "HOOK_ENTER", "HOOK_LEAVE"} <= seen:
            break
        time.sleep(0.05)

    assert {"HOOK_INSTALLED", "HOOK_ENTER", "HOOK_LEAVE"} <= seen

    enter = next(e for e in client.events() if e["event_type"] == "HOOK_ENTER")
    leave = next(e for e in client.events() if e["event_type"] == "HOOK_LEAVE")
    assert enter["payload"]["hook_id"] == leave["payload"]["hook_id"]
    assert enter["pid"] == 18342
    assert enter["tid"] is not None
    assert leave["payload"]["duration_us"] >= 0


def test_runtime_hook_unknown_module_gives_candidates(client: BridgeClient):
    with pytest.raises(ProtocolError) as ei:
        client.call("runtime.hook", {"module": "libnope.so", "address": "0x1"})
    err = ei.value
    assert err.code is ErrorCode.E_NOT_FOUND
    assert "libgame.so" in err.context["candidates"]


def test_runtime_hook_missing_args(client: BridgeClient):
    with pytest.raises(ProtocolError) as ei:
        client.call("runtime.hook", {"module": "libgame.so"})
    assert ei.value.code is ErrorCode.E_BAD_ARGS


def test_unhook_then_info(client: BridgeClient):
    hook_id = client.call(
        "runtime.hook", {"module": "libgame.so", "address": "0x7a3f1c0040"}
    )["payload"]["hook"]["hook_id"]

    info = client.call("runtime.hook_info", {"hook_id": hook_id})["payload"]
    assert info["hook"]["hook_id"] == hook_id

    client.call("runtime.unhook", {"hook_id": hook_id})
    info2 = client.call("runtime.hook_info", {"hook_id": hook_id})["payload"]
    assert info2["hook"]["status"] == "removed"


# ---------------------------------------------------------------------------
# 事件通道
# ---------------------------------------------------------------------------


def test_runtime_ready_event_pushed_on_session_start(client: BridgeClient):
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        if any(e["event_type"] == "RUNTIME_READY" for e in client.events()):
            break
        time.sleep(0.05)
    evt = next(e for e in client.events() if e["event_type"] == "RUNTIME_READY")
    assert evt["source"] == "runtime"
    assert evt["session_id"] == client.session.session_id
    assert evt["payload"]["package"] == "com.example.target"
    M.validate(evt, strict=True)


def test_external_event_injection(client: BridgeClient, server: MockRuntimeServer):
    n = server.emit_event(
        "HTTP_REQUEST",
        source="network",
        payload={"method": "POST", "url": "/login", "host": "api.example.com"},
    )
    assert n == 1
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        if any(e["event_type"] == "HTTP_REQUEST" for e in client.events()):
            break
        time.sleep(0.05)
    evt = next(e for e in client.events() if e["event_type"] == "HTTP_REQUEST")
    assert evt["payload"]["url"] == "/login"


# ---------------------------------------------------------------------------
# 错误路径
# ---------------------------------------------------------------------------


def test_unknown_command_rejected_client_side(client: BridgeClient):
    with pytest.raises(ProtocolError) as ei:
        client.call("runtime.do_magic")
    assert ei.value.code is ErrorCode.E_UNKNOWN_CMD


def test_mock_unsupported_command_reports_capability_unavailable(client: BridgeClient):
    """未实现的命令必须如实说"没实现"，不能返回编造的假数据。

    Mock 对未实现命令回 RESPONSE(status=error)，Bridge 把它转成执行层错误 —— 
    这正是 MCP 侧应返回的 isError 工具结果。
    """
    with pytest.raises(ProtocolError) as ei:
        client.call("apk.decompile", {"package": "com.example.target"})
    err = ei.value
    assert err.code is ErrorCode.E_NOT_READY
    assert err.layer.value == "execution"
    body = err.context["response"]
    assert body["reason"] == "capability unavailable"
    assert body["command"] == "apk.decompile"
    assert "note" in body


def test_packet_get_unknown_id_gives_candidates(client: BridgeClient):
    with pytest.raises(ProtocolError) as ei:
        client.call("packet.get", {"packet_id": "pkt_nope"})
    err = ei.value
    assert err.code is ErrorCode.E_NOT_FOUND
    assert err.context["candidate_count"] == 2
    assert "pkt_0000000000e1" in err.context["candidates"]


def test_packet_metadata_does_not_embed_big_payload(client: BridgeClient):
    body = client.call("packet.get", {"packet_id": "pkt_0000000000e1"})["payload"]
    pkt = body["packet"]
    assert pkt["length"] == 384
    assert len(pkt["sha256"]) == 64

    meta = client.call(
        "packet.get", {"packet_id": "pkt_0000000000e1", "include_hex": False}
    )["payload"]["packet"]
    assert "hex" not in meta
    assert meta["sha256"] == pkt["sha256"]


# ---------------------------------------------------------------------------
# JOB 命令
# ---------------------------------------------------------------------------


def test_job_flow_submit_status_result(client: BridgeClient):
    job_id = client.submit_job("memory.dump", {"address": "0x7a3f1c2000", "length": 4096})
    assert job_id.startswith("job_")

    status = client.call("job.status", {"job_id": job_id})["payload"]
    assert status["job_id"] == job_id
    assert status["state"] in ("running", "completed")

    result = client.await_job(job_id, poll_interval=0.05, timeout=5.0)
    assert result["state"] == "completed"
    assert result["result"]["note"].startswith("Mock 后端")


def test_job_cancel(client: BridgeClient):
    job_id = client.submit_job("memory.dump", {"address": "0x7a3f1c2000", "length": 16})
    out = client.call("job.cancel", {"job_id": job_id})["payload"]
    assert out["state"] == "cancelled"


# ---------------------------------------------------------------------------
# 协议版本不匹配：禁止进入 READY
# ---------------------------------------------------------------------------


def test_version_mismatch_blocks_ready(server: MockRuntimeServer):
    raw = transport.connect(transport.parse_endpoint(server.endpoint), 5.0)
    try:
        raw.sendall(F.encode_frame(M.make_hello(protocol="2.0")))
        dec = F.FrameDecoder()
        msgs: list[dict] = []
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            try:
                data = raw.recv(65536)
            except socket.timeout:
                break
            if not data:
                break
            msgs.extend(dec.feed(data))
            if msgs:
                break
        assert msgs, "服务端没有任何应答"
        first = msgs[0]
        assert M.message_type_of(first) == "ERROR"
        assert first["error"]["code"] == "ERROR_PROTOCOL_VERSION"
        assert first["error"]["layer"] == "protocol"
        assert first["error"]["retryable"] is False
        # 关键：不得出现 READY
        assert all(M.message_type_of(m) != "READY" for m in msgs)
    finally:
        raw.close()


# ---------------------------------------------------------------------------
# 心跳与链路状态
# ---------------------------------------------------------------------------


def test_heartbeat_keeps_link_connected(client: BridgeClient):
    time.sleep(1.2)
    assert client.link_state is LinkState.CONNECTED
    assert client.rtt_ms is not None
    assert client.rtt_ms >= 0


def test_heartbeat_timeout_degrades_then_disconnects(make_server, endpoint_spec: str):
    srv = make_server(endpoint_spec)
    c = BridgeClient(
        srv.endpoint,
        heartbeat_interval=0.2,
        heartbeat_timeout=0.4,
        auto_reconnect=False,
    )
    try:
        c.connect()
        assert c.link_state is LinkState.CONNECTED

        srv.set_heartbeat_enabled(False)

        assert c.wait_for_link(LinkState.DEGRADED, timeout=6.0), (
            f"未进入 DEGRADED，当前 {c.link_state.value}：{c.link_reason}"
        )
        assert "心跳" in c.link_reason

        assert c.wait_for_link(LinkState.DISCONNECTED, timeout=6.0), (
            f"未进入 DISCONNECTED，当前 {c.link_state.value}：{c.link_reason}"
        )
        assert c.session.state is SessionState.DEGRADED
    finally:
        c.close()


def test_call_after_disconnect_reports_not_ready(make_server, endpoint_spec: str):
    srv = make_server(endpoint_spec)
    c = BridgeClient(srv.endpoint, heartbeat_interval=0.2, heartbeat_timeout=0.4,
                     auto_reconnect=False)
    try:
        c.connect()
        srv.drop_connections()
        assert c.wait_for_link(LinkState.DISCONNECTED, timeout=5.0)
        with pytest.raises(ProtocolError) as ei:
            c.call("runtime.status")
        assert ei.value.code is ErrorCode.E_NOT_READY
    finally:
        c.close()


# ---------------------------------------------------------------------------
# 重连：不恢复旧 Session
# ---------------------------------------------------------------------------


def test_reconnect_creates_new_session_and_invalidates_old(make_server, endpoint_spec: str):
    srv = make_server(endpoint_spec)
    c = BridgeClient(
        srv.endpoint,
        heartbeat_interval=0.2,
        heartbeat_timeout=0.4,
        auto_reconnect=True,
    )
    try:
        c.connect()
        first = c.session.session_id
        assert c.sessions.generation == 1

        srv.drop_connections()

        # 自动重连后必须产生新 Session
        assert c.wait_for_session_generation(2, timeout=20.0), (
            f"未产生新 Session，generation={c.sessions.generation}"
        )
        assert c.wait_for_link(LinkState.CONNECTED, timeout=20.0)

        second = c.session.session_id
        assert second != first, "重连后 session_id 必须变化"
        assert c.sessions.generation == 2
        assert not c.sessions.is_current(first)
        assert first in c.sessions.history

        # 新 Session 必须可用
        assert c.call("runtime.status")["status"] == "ok"
        assert srv.handshake_count >= 2
    finally:
        c.close()


def test_link_lost_fails_pending_and_reports_loudly(make_server, endpoint_spec: str):
    """链路丢失时：在途调用必须被显式失败，后续调用报明确错误 —— 不能静默吞掉。"""
    srv = make_server(endpoint_spec)
    c = BridgeClient(srv.endpoint, heartbeat_interval=0.2, heartbeat_timeout=0.4,
                     auto_reconnect=False)
    try:
        c.connect()
        # 塞一个永远不会被满足的在途请求，然后掐断链路
        slot_holder: dict = {}

        def pending_call() -> None:
            try:
                c.call("runtime.status", timeout=5.0)
            except ProtocolError as exc:
                slot_holder["error"] = exc

        import threading

        t = threading.Thread(target=pending_call, daemon=True)
        t.start()
        # 等槽位真的注册好再掐链路，否则会漏掉这次在途调用（竞态）
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and not c._pending:  # noqa: SLF001
            time.sleep(0.01)
        assert c._pending, "在途请求未注册，测试前提不成立"  # noqa: SLF001

        c._on_link_lost("测试注入")  # noqa: SLF001 - 模拟链路丢失
        t.join(timeout=3.0)

        err = slot_holder.get("error")
        assert err is not None, "在途调用没有被显式失败"
        assert err.code is ErrorCode.E_SESSION_STALE
        assert "重连" in err.message

        # 后续调用报 E_NOT_READY
        with pytest.raises(ProtocolError) as ei:
            c.call("runtime.status")
        assert ei.value.code is ErrorCode.E_NOT_READY
    finally:
        c.close()


# ---------------------------------------------------------------------------
# Session 看门狗
# ---------------------------------------------------------------------------


def test_session_idle_timeout_closes_session():
    """禁止无限持有 Session：忘记关闭的代价必须是"自动过期"。

    直接测 SessionManager，不经过活跃的心跳（心跳会持续刷新活跃时间，
    让这个测试变得不确定）。
    """
    from ai_analyzer.bridge import SessionManager

    sm = SessionManager(idle_timeout=0.2)
    sm.open("sess_0000000000a1", state=SessionState.RUNNING)
    assert sm.current is not None
    assert sm.current.idle_seconds < 0.2
    assert sm.sweep() is False

    time.sleep(0.25)
    assert sm.sweep() is True
    assert sm.current is None
    assert "sess_0000000000a1" in sm.history

    with pytest.raises(ProtocolError) as ei:
        sm.require()
    assert ei.value.code is ErrorCode.E_NOT_READY
    assert ei.value.retryable is True


def test_async_wrapper_does_not_block_event_loop(client: BridgeClient):
    import asyncio

    async def main() -> dict:
        return await client.acall("runtime.status")

    resp = asyncio.run(main())
    assert resp["payload"]["pid"] == 18342
