# -*- coding: utf-8 -*-
"""工具处理层（L5 注册层的薄封装）。

纪律
----
- **薄封装**：只做「参数整理 → 转发 → 结果整形」，不写业务逻辑。
- 方法签名必须与 `specs.py` 的 `input_schema` 逐项一致 —— 由
  `tests/mcp/test_tool_surface.py` 反向校验（SDK 从签名派生 schema，签名漂了测试就红）。
- 阻塞调用一律走 `RuntimeBridge.call()`（内部 asyncio.to_thread 隔离）。
"""

from __future__ import annotations

from typing import Any

from ..host.runtime_bridge import RuntimeBridge


class ToolHandlers:
    """全部工具的实现。一个方法对应一个工具，方法名 = 工具名把点换成下划线。"""

    def __init__(self, bridge: RuntimeBridge) -> None:
        self.bridge = bridge

    # ------------------------------------------------------------------
    # 01 Device
    # ------------------------------------------------------------------

    async def device_list(self) -> dict[str, Any]:
        return await self.bridge.call("device.list")

    async def device_info(self) -> dict[str, Any]:
        return await self.bridge.call("device.info")

    # ------------------------------------------------------------------
    # 02 APK
    # ------------------------------------------------------------------

    async def apk_list(self, brief: bool = True) -> dict[str, Any]:
        return await self.bridge.call("apk.list", {"brief": brief})

    async def apk_launch(self, package: str) -> dict[str, Any]:
        return await self.bridge.call("apk.launch", {"package": package})

    async def apk_stop(self, package: str) -> dict[str, Any]:
        return await self.bridge.call("apk.stop", {"package": package})

    # ------------------------------------------------------------------
    # 03 Session
    # ------------------------------------------------------------------

    async def session_list(self) -> dict[str, Any]:
        return await self.bridge.call("session.list")

    async def session_info(self) -> dict[str, Any]:
        return await self.bridge.call("session.info")

    async def session_capabilities(self) -> dict[str, Any]:
        body = await self.bridge.call("session.capabilities")
        summary = self.bridge.capability_summary()
        body.setdefault(
            "note",
            "capabilities 为 false 的能力不可用，相关工具已从可见集摘除；"
            "https_decrypt=false 表示拿不到 HTTPS 明文，不要声称已解密",
        )
        body["available"] = summary["available"]
        body["unavailable"] = summary["unavailable"]
        return body

    # ------------------------------------------------------------------
    # 04 Process
    # ------------------------------------------------------------------

    async def process_list(self, brief: bool = True) -> dict[str, Any]:
        return await self.bridge.call("process.list", {"brief": brief})

    async def process_info(self) -> dict[str, Any]:
        return await self.bridge.call("process.info")

    async def process_modules(self, name_contains: str | None = None) -> dict[str, Any]:
        body = await self.bridge.call("process.modules")
        if name_contains:
            all_mods = body.get("modules") or []
            kept = [m for m in all_mods if name_contains in (m.get("name") or "")]
            body = {
                **body,
                "modules": kept,
                "total": len(kept),
                "filtered_from": len(all_mods),
                "filter": name_contains,
            }
            if not kept:
                body["note"] = (
                    f"过滤 {name_contains!r} 无命中。这不是「模块不存在」的证据 —— "
                    f"完整模块列表共 {len(all_mods)} 个，可去掉 name_contains 再查。"
                )
                body["candidates"] = [m.get("name") for m in all_mods]
        return body

    async def process_threads(self) -> dict[str, Any]:
        return await self.bridge.call("process.threads")

    # ------------------------------------------------------------------
    # 05 Runtime
    # ------------------------------------------------------------------

    async def runtime_status(self) -> dict[str, Any]:
        return await self.bridge.call("runtime.status")

    async def runtime_hook(self, module: str, address: str) -> dict[str, Any]:
        return await self.bridge.call(
            "runtime.hook", {"module": module, "address": address}
        )

    async def runtime_unhook(self, hook_id: str) -> dict[str, Any]:
        return await self.bridge.call("runtime.unhook", {"hook_id": hook_id})

    async def runtime_trace(
        self, module: str, address: str, duration_ms: int = 5000
    ) -> dict[str, Any]:
        return await self.bridge.call(
            "runtime.trace",
            {"module": module, "address": address, "duration_ms": duration_ms},
        )

    # ------------------------------------------------------------------
    # 06 Memory
    # ------------------------------------------------------------------

    async def memory_read(self, address: str, length: int = 16) -> dict[str, Any]:
        return await self.bridge.call("memory.read", {"address": address, "length": length})

    async def memory_write(
        self, address: str, hex: str, confirm: bool = False
    ) -> dict[str, Any]:
        # Write Guard：confirm 默认 false，必须显式开启
        return await self.bridge.call(
            "memory.write", {"address": address, "hex": hex, "confirm": confirm}
        )

    async def memory_search(
        self, pattern: str, as_text: bool = False, max_results: int = 32
    ) -> dict[str, Any]:
        return await self.bridge.call(
            "memory.search",
            {"pattern": pattern, "as_text": as_text, "max_results": max_results},
        )

    async def memory_maps(self) -> dict[str, Any]:
        return await self.bridge.call("memory.maps")

    async def memory_dump(self, address: str, length: int) -> dict[str, Any]:
        return await self.bridge.call("memory.dump", {"address": address, "length": length})

    # ------------------------------------------------------------------
    # 07 Network
    # ------------------------------------------------------------------

    async def network_capture_start(self, pcap: bool = False) -> dict[str, Any]:
        return await self.bridge.call("network.capture_start", {"pcap": pcap})

    async def network_capture_stop(self) -> dict[str, Any]:
        return await self.bridge.call("network.capture_stop")

    async def network_connections(self, brief: bool = False) -> dict[str, Any]:
        return await self.bridge.call("network.connections", {"brief": brief})

    async def network_dns(self) -> dict[str, Any]:
        return await self.bridge.call("network.dns")

    # ------------------------------------------------------------------
    # 08 Packet
    # ------------------------------------------------------------------

    async def packet_list(
        self, connection_id: str | None = None, limit: int = 50
    ) -> dict[str, Any]:
        body = await self.bridge.call("packet.list", {"connection_id": connection_id})
        pkts = body.get("packets") or []
        if connection_id:
            pkts = [p for p in pkts if p.get("connection_id") == connection_id]
        if len(pkts) > limit:
            body = {**body, "packets": pkts[:limit], "truncated": True,
                    "next_cursor": pkts[limit - 1].get("packet_id")}
        else:
            body = {**body, "packets": pkts, "truncated": False}
        body["total"] = len(pkts)
        return body

    async def packet_get(self, packet_id: str, include_hex: bool = True) -> dict[str, Any]:
        return await self.bridge.call(
            "packet.get", {"packet_id": packet_id, "include_hex": include_hex}
        )

    async def packet_hex(
        self, packet_id: str, offset: int = 0, length: int = 256
    ) -> dict[str, Any]:
        body = await self.bridge.call("packet.get", {"packet_id": packet_id})
        pkt = body.get("packet") or {}
        full = pkt.get("hex") or ""
        window = full[offset * 2 : (offset + length) * 2]
        return {
            "packet_id": packet_id,
            "offset": offset,
            "length": len(window) // 2,
            "hex": window,
            "ascii": "".join(
                chr(b) if 32 <= b < 127 else "."
                for b in bytes.fromhex(window) if window
            ),
            "total_length": pkt.get("length", 0),
        }

    async def packet_modify(
        self, packet_id: str, offset: int, hex: str, confirm: bool = False
    ) -> dict[str, Any]:
        return await self.bridge.call(
            "packet.modify",
            {"packet_id": packet_id, "offset": offset, "hex": hex, "confirm": confirm},
        )

    async def packet_export(
        self, connection_id: str | None = None, format: str = "pcap"
    ) -> dict[str, Any]:
        return await self.bridge.call(
            "packet.export", {"connection_id": connection_id, "format": format}
        )

    # ------------------------------------------------------------------
    # 09 Artifact
    # ------------------------------------------------------------------

    async def artifact_get(self, artifact_id: str) -> dict[str, Any]:
        return await self.bridge.call("artifact.get", {"artifact_id": artifact_id})

    async def artifact_list(self) -> dict[str, Any]:
        return await self.bridge.call("artifact.list")

    # ------------------------------------------------------------------
    # 10 Job
    # ------------------------------------------------------------------

    async def job_status(self, job_id: str) -> dict[str, Any]:
        return await self.bridge.call("job.status", {"job_id": job_id})

    async def job_result(self, job_id: str) -> dict[str, Any]:
        return await self.bridge.call("job.result", {"job_id": job_id})

    async def job_cancel(self, job_id: str) -> dict[str, Any]:
        return await self.bridge.call("job.cancel", {"job_id": job_id})


def method_name_for(tool_name: str) -> str:
    """工具名 → 处理方法名。device.list → device_list。"""
    return tool_name.replace(".", "_")
