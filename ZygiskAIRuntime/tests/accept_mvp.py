# -*- coding: utf-8 -*-
"""M0 + Host/MVP 端到端验收。

跑法（在 ZygiskAIRuntime/ 下）::

    python tests/accept_mvp.py

它做的是**真实链路**，不是打勾清单：
  Mock Runtime 后端 → UDS/TCP → Bridge 握手 → MCP Server → 工具调用 → 真实返回
并在每一步打印可核对的事实（session_id、PID、地址、事件、错误码）。

⚠️ 本脚本证明的是 **Host 侧 MVP 成立**。
   Android 侧（libai_analyzer.so）尚未编译验证 —— 本机无 NDK/CMake。
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_analyzer.bridge.transport import HAS_AF_UNIX  # noqa: E402
from ai_analyzer.host import RuntimeBridge, SurfaceManager, build_server  # noqa: E402
from ai_analyzer.mock import MockRuntimeServer  # noqa: E402
from ai_analyzer.protocol.constants import LinkState  # noqa: E402
from ai_analyzer.protocol.errors import ProtocolError  # noqa: E402
from ai_analyzer.tools import EXPERT_GROUPS  # noqa: E402

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, PASS if ok else FAIL, detail))
    mark = "✓" if ok else "✗"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))
    return ok


def section(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


async def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="zai-accept"))
    spec = f"unix:{tmp / 's.sock'}" if HAS_AF_UNIX else "tcp:127.0.0.1:0"

    section("0. 环境")
    print(f"  Python      : {sys.version.split()[0]}")
    print(f"  AF_UNIX     : {HAS_AF_UNIX}")
    print(f"  端点        : {spec if HAS_AF_UNIX else 'tcp:127.0.0.1:0（回退，宿主无 AF_UNIX）'}")

    srv = MockRuntimeServer(spec).start()
    bridge = RuntimeBridge(srv.endpoint, auto_reconnect=True)

    try:
        # ------------------------------------------------------------------
        section("1. 握手：CONNECT → HELLO → HELLO_ACK → READY")
        bridge.connect()
        sess = bridge.session
        check("链路 CONNECTED", bridge.link_state is LinkState.CONNECTED, bridge.link_reason)
        check("Session 建立", sess is not None and sess.session_id.startswith("sess_"),
              sess.session_id if sess else "-")
        check("Session generation=1", bridge.client.sessions.generation == 1)
        # package / pid / abi / sdk 不在 READY 帧里（READY schema 已冻结），
        # 要拿这些事实得调 session.info —— 这里顺便验证这条链路。
        info = await bridge.call("session.info")
        print(f"  session.info → pid={info['pid']}  package={info['package']}  "
              f"abi={info['abi']}  sdk={info['sdk']}")
        check("session.info 返回上下文事实",
              info["pid"] == 18342 and info["package"] == "com.example.target")
        caps = bridge.capability_summary()
        print(f"  能力可用  : {caps['available']}")
        print(f"  能力不可用: {caps['unavailable']}")
        check("HTTPS 能力如实上报（https_decrypt=false）",
              "network.https_decrypt" in caps["unavailable"])

        # ------------------------------------------------------------------
        section("2. MCP Server 装配与分面")
        sm = SurfaceManager(mounted_groups=EXPERT_GROUPS)
        server, sm, registered = build_server(bridge, surfaces=sm, capabilities=bridge.capabilities())
        tools = await server.list_tools()
        check("list_tools() == 注册集", [t.name for t in tools] == registered,
              f"{len(registered)} 个工具")
        rep = sm.report(bridge.capabilities())
        check("Core ≤ 25", rep.core_count <= 25, f"core={rep.core_count}")
        print(f"  Core={rep.core_count}  Expert={rep.expert_count}  挂载组={list(rep.mounted_groups)}")
        print(f"  能力齐备时摘除 {len(rep.removed)} 个（Mock 全能力，本就不该摘）")

        # 用降级能力集演示门禁：内存能力关掉 → 相关工具必须消失
        degraded = {
            "runtime": {"native_hook": True, "java_hook": False, "memory_read": False,
                        "memory_write": False, "stacktrace": False},
            "network": {"capture": True, "http": True, "https_capture": True,
                        "https_decrypt": False, "packet_intercept": False},
        }
        drep = sm.report(degraded)
        removed_map = {r.tool: r for r in drep.removed}
        expect_removed = {"memory.read", "memory.search", "memory.maps", "memory.dump",
                          "packet.modify"}
        check("能力降级时相关工具被摘除",
              expect_removed <= set(removed_map),
              f"摘除 {len(drep.removed)} 个：{sorted(removed_map)[:6]}…")
        sample = removed_map.get("memory.read")
        check("摘除通知带原因与缺失能力",
              bool(sample and sample.missing_capabilities),
              f"memory.read ← {list(sample.missing_capabilities) if sample else '-'}")
        check("能力齐备的工具不受影响",
              "runtime.status" in drep.visible_names and "device.list" in drep.visible_names)

        # ------------------------------------------------------------------
        section("3. 只读命令：真实往返")
        status = (await server.call_tool("runtime.status", {})).structured_content
        print(f"  runtime.status → state={status['state']} pid={status['pid']} "
              f"modules={status['modules_count']} threads={status['threads_count']}")
        check("runtime.status 返回真实 payload", status["pid"] == 18342 and status["runtime_ready"])

        mods = (await server.call_tool("process.modules", {})).structured_content
        names = [m["name"] for m in mods["modules"]]
        print(f"  process.modules → {names}")
        check("模块基址是 '0x...' 字符串",
              all(m["base"].startswith("0x") for m in mods["modules"]))

        ths = (await server.call_tool("process.threads", {})).structured_content
        check("process.threads 返回线程表", ths["total"] == 4,
              ", ".join(f"{t['tid']}:{t['name']}" for t in ths["threads"]))

        conns = (await server.call_tool("network.connections", {})).structured_content
        print(f"  network.connections → {conns['total']} 条，首条 {conns['connections'][0]['remote']}")
        check("连接表含 connection_id（关联用的桥梁）",
              conns["connections"][0]["connection_id"].startswith("conn_"))

        # ------------------------------------------------------------------
        section("4. 内存：校验器必须真的拦")
        r = (await server.call_tool(
            "memory.read", {"address": "0x7a3f1c2000", "length": 16}
        )).structured_content
        print(f"  memory.read(0x7a3f1c2000,16) → module={r['module']} ascii={r['ascii']!r}")
        check("已映射地址读成功且归属模块正确", r["module"] == "libgame.so" and "AI-ANALYZER" in r["ascii"])

        try:
            await server.call_tool("memory.read", {"address": "0xdeadbeef", "length": 16})
            check("未映射地址被拒绝", False, "竟然返回了数据")
        except Exception as exc:  # noqa: BLE001
            payload = _payload(exc)
            check("未映射地址被拒绝（E_READ_FAILED + 可用区间）",
                  payload["code"] == "E_READ_FAILED" and bool(payload["context"]["mapped_ranges"]),
                  f"{len(payload['context']['mapped_ranges'])} 个可用区间")

        # ------------------------------------------------------------------
        section("5. 禁止 Fake Success：Hook 必须有三级证据")
        hook = (await server.call_tool(
            "runtime.hook", {"module": "libgame.so", "address": "0x7a3f1c0040"}
        )).structured_content
        print(f"  runtime.hook → hook_id={hook['hook']['hook_id']}")
        print(f"    execution = {hook['execution']}")
        print(f"    events    = {hook['events_observed']}")
        check("execution 三态齐备", hook["execution"] == {
            "accepted": True, "executed": True, "verified": True})

        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            seen = {e["event_type"] for e in bridge.events()}
            if {"HOOK_INSTALLED", "HOOK_ENTER", "HOOK_LEAVE"} <= seen:
                break
            await asyncio.sleep(0.05)
        seen = {e["event_type"] for e in bridge.events()}
        check("verified 由真实事件支撑", {"HOOK_INSTALLED", "HOOK_ENTER", "HOOK_LEAVE"} <= seen,
              f"收到 {sorted(seen)}")
        enter = next(e for e in bridge.events() if e["event_type"] == "HOOK_ENTER")
        print(f"  HOOK_ENTER: pid={enter['pid']} tid={enter['tid']} payload={enter['payload']}")

        # ------------------------------------------------------------------
        section("6. 大对象不进协议 JSON")
        pkt = (await server.call_tool(
            "packet.get", {"packet_id": "pkt_0000000000e1", "include_hex": False}
        )).structured_content["packet"]
        print(f"  packet.get(include_hex=false) → length={pkt['length']} sha256={pkt['sha256'][:16]}…")
        check("metadata-only 不含 hex", "hex" not in pkt and len(pkt["sha256"]) == 64)

        # ------------------------------------------------------------------
        section("7. JOB 命令流程")
        job = (await server.call_tool(
            "memory.dump", {"address": "0x7a3f1c2000", "length": 4096}
        )).structured_content
        job_id = job["job_id"]
        print(f"  memory.dump → job_id={job_id}")
        result = bridge.client.await_job(job_id, poll_interval=0.05, timeout=5.0)
        print(f"  job 终态 = {result['state']}  result={json.dumps(result.get('result'), ensure_ascii=False)}")
        check("JOB submit → status → result 收敛", result["state"] == "completed")

        # ------------------------------------------------------------------
        section("8. 错误分层：协议层 vs 执行层")
        try:
            await server.call_tool("memory.read", {"address": "not-an-address"})
            check("协议层错误走 JSON-RPC error", False, "没有抛错")
        except Exception as exc:  # noqa: BLE001
            from mcp.shared.exceptions import MCPError
            ok = isinstance(exc, MCPError) and exc.data["layer"] == "protocol"
            check("协议层错误走 JSON-RPC error", ok,
                  f"{type(exc).__name__} code={getattr(exc, 'code', '-')}")

        try:
            await server.call_tool("runtime.trace", {"module": "libgame.so", "address": "0x1"})
            check("执行层失败走 isError 结果", False, "没有抛错")
        except Exception as exc:  # noqa: BLE001
            from mcp.server.mcpserver.exceptions import ToolError
            payload = _payload(exc)
            check("执行层失败走 isError 结果", isinstance(exc, ToolError)
                  and payload["layer"] == "execution",
                  f"{payload['code']} next_step={payload['next_step']!r}")

        # ------------------------------------------------------------------
        section("9. 断线重连：旧 Session 必须失效")
        old_id = bridge.session.session_id
        old_gen = bridge.client.sessions.generation
        srv.drop_connections()
        await asyncio.sleep(0.3)
        check("链路进入 DISCONNECTED", bridge.link_state is LinkState.DISCONNECTED,
              bridge.link_reason)

        reconnected = False
        deadline = time.monotonic() + 25.0
        while time.monotonic() < deadline:
            if (bridge.link_state is LinkState.CONNECTED
                    and bridge.client.sessions.generation > old_gen):
                reconnected = True
                break
            await asyncio.sleep(0.1)

        check("自动重连成功", reconnected,
              f"generation {old_gen} → {bridge.client.sessions.generation}")
        new_id = bridge.session.session_id
        check("重连后 session_id 变化", new_id != old_id, f"{old_id} → {new_id}")
        check("旧 Session 已失效", not bridge.client.sessions.is_current(old_id)
              and old_id in bridge.client.sessions.history)
        check("重连后 Mock 侧握手次数 ≥2", srv.handshake_count >= 2,
              f"handshake_count={srv.handshake_count}")

        ok = (await server.call_tool("runtime.status", {})).structured_content
        check("新 Session 可用", ok["pid"] == 18342)

        # ------------------------------------------------------------------
        section("10. 汇总")
        passed = sum(1 for _, s, _ in results if s == PASS)
        failed = sum(1 for _, s, _ in results if s == FAIL)
        print(f"  通过 {passed} / {passed + failed}")
        for name, status, detail in results:
            if status == FAIL:
                print(f"    ✗ {name} — {detail}")
        print()
        if failed == 0:
            print("  M0 + Host/MVP 验收：全部通过")
            print("  ⚠️  这证明的是 Host 侧 MVP 成立；Android 侧（libai_analyzer.so）仍未编译。")
        else:
            print(f"  M0 + Host/MVP 验收：{failed} 项未通过")
        return 0 if failed == 0 else 1

    finally:
        bridge.close()
        srv.stop()
        shutil.rmtree(tmp, ignore_errors=True)


def _payload(exc: BaseException) -> dict:
    cur: BaseException | None = exc
    while cur is not None:
        text = str(cur)
        start = text.find("{")
        if start >= 0:
            try:
                return json.loads(text[start:])
            except json.JSONDecodeError:
                pass
        cur = cur.__cause__
    return {"code": "?", "layer": "?", "next_step": "?"}


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
