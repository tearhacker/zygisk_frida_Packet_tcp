# -*- coding: utf-8 -*-
"""Mock Runtime 的状态模型。

模拟一个运行中的目标 App：进程、模块映射、线程、Hook、网络连接、Packet、Job。

设计纪律
--------
1. **不声称没有的能力**：能力表如实声明，`https_decrypt` 默认 false。
2. **执行型命令必须能给出三级证据**：`runtime.hook` 要产生
   HOOK_INSTALLED / HOOK_ENTER / HOOK_LEAVE 真实事件，不能只返回 status=ok。
3. **地址必须真的在映射区间内**：`memory.read` 对未映射地址返回 E_READ_FAILED，
   而不是编一段假数据。
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any

from ..protocol.constants import SessionState
from ..protocol.errors import ErrorCode, ProtocolError
from ..protocol.messages import new_job_id

# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

TARGET_PACKAGE = "com.example.target"
TARGET_PID = 18342
TARGET_UID = 10234


@dataclass
class MockModule:
    name: str
    path: str
    base: int
    size: int
    permissions: str = "r-xp"

    @property
    def end(self) -> int:
        return self.base + self.size

    def contains(self, address: int, length: int = 1) -> bool:
        return self.base <= address and address + length <= self.end

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "base": f"0x{self.base:x}",
            "size": self.size,
            "permissions": self.permissions,
        }


@dataclass
class MockThread:
    tid: int
    name: str
    state: str = "R"

    def to_dict(self) -> dict[str, Any]:
        return {"tid": self.tid, "name": self.name, "state": self.state}


@dataclass
class MockConnection:
    connection_id: str
    protocol: str
    local: str
    remote: str
    state: str
    pid: int = TARGET_PID

    def to_dict(self) -> dict[str, Any]:
        return {
            "connection_id": self.connection_id,
            "pid": self.pid,
            "protocol": self.protocol,
            "local": self.local,
            "remote": self.remote,
            "state": self.state,
        }


@dataclass
class MockPacket:
    packet_id: str
    direction: str
    protocol: str
    length: int
    connection_id: str
    payload: bytes
    timestamp: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self, *, with_hex: bool = False) -> dict[str, Any]:
        """大对象不进协议 JSON —— 默认只给 metadata + sha256。"""
        out: dict[str, Any] = {
            "packet_id": self.packet_id,
            "timestamp": self.timestamp,
            "direction": self.direction,
            "protocol": self.protocol,
            "length": self.length,
            "connection_id": self.connection_id,
            "sha256": hashlib.sha256(self.payload).hexdigest(),
        }
        if with_hex:
            out["hex"] = self.payload.hex()
        return out


@dataclass
class MockJob:
    job_id: str
    command: str
    state: str = "running"
    progress: float = 0.0
    created_at: float = field(default_factory=time.monotonic)
    result: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "job_id": self.job_id,
            "command": self.command,
            "state": self.state,
            "progress": round(self.progress, 3),
            "elapsed_ms": int((time.monotonic() - self.created_at) * 1000),
        }
        if self.state == "running":
            out["suggested_wait_ms"] = 200
        if self.result is not None:
            out["result"] = self.result
        return out


@dataclass
class MockHook:
    hook_id: str
    module: str
    address: str
    status: str = "active"
    enter_count: int = 0
    leave_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "hook_id": self.hook_id,
            "module": self.module,
            "address": self.address,
            "status": self.status,
            "enter_count": self.enter_count,
            "leave_count": self.leave_count,
        }


# ---------------------------------------------------------------------------
# 运行时状态
# ---------------------------------------------------------------------------


class MockRuntimeState:
    """一个运行中的目标 App 的完整模拟状态。"""

    def __init__(
        self,
        *,
        package: str = TARGET_PACKAGE,
        pid: int = TARGET_PID,
        uid: int = TARGET_UID,
        abi: str = "arm64-v8a",
        sdk: int = 34,
    ) -> None:
        self.package = package
        self.pid = pid
        self.uid = uid
        self.abi = abi
        self.sdk = sdk
        self.started_at = time.monotonic()
        self.state = SessionState.RUNNING

        self.modules: list[MockModule] = [
            MockModule("libc.so", "/apex/com.android.runtime/lib64/bionic/libc.so",
                       0x7A00000000, 0x200000),
            MockModule("libart.so", "/apex/com.android.art/lib64/libart.so",
                       0x7A20000000, 0x800000),
            MockModule("libgame.so", f"/data/app/{package}/lib/arm64/libgame.so",
                       0x7A3F1C0000, 0x400000),
            MockModule("libnetwork.so", f"/data/app/{package}/lib/arm64/libnetwork.so",
                       0x7A50000000, 0x180000),
        ]
        self.threads: list[MockThread] = [
            MockThread(self.pid, "main", "R"),
            MockThread(self.pid + 8, "Jit thread pool", "S"),
            MockThread(self.pid + 9, "Signal Catcher", "S"),
            MockThread(self.pid + 18, "RenderThread", "S"),
        ]
        self.connections: list[MockConnection] = [
            MockConnection("conn_0000000000f1", "TCP", "10.0.0.5:41234",
                           "93.184.216.34:443", "ESTABLISHED"),
            MockConnection("conn_0000000000f2", "TCP", "10.0.0.5:41240",
                           "8.8.8.8:53", "ESTABLISHED"),
        ]
        self.packets: list[MockPacket] = [
            MockPacket("pkt_0000000000e1", "outbound", "TCP", 384,
                       "conn_0000000000f1",
                       b"POST /login HTTP/1.1\r\nHost: api.example.com\r\n\r\n"),
            MockPacket("pkt_0000000000e2", "inbound", "TCP", 128,
                       "conn_0000000000f1", b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}"),
        ]
        self.hooks: dict[str, MockHook] = {}
        self.jobs: dict[str, MockJob] = {}

        # 地址 → 真实内容。memory.read 只能读到这里的地址。
        self._memory: dict[int, bytes] = {}
        for offset, blob in (
            (0x0000, b"\x7fELF\x02\x01\x01\x00"),
            (0x1000, bytes(range(64))),
            (0x2000, b"AI-ANALYZER-MOCK-BLOCK-" * 4),
        ):
            self._memory[0x7A3F1C0000 + offset] = blob

        # 能力表：如实声明，不许声称没有的能力
        self.capabilities: dict[str, dict[str, bool]] = {
            "runtime": {
                "native_hook": True,
                "java_hook": True,
                "memory_read": True,
                "memory_write": True,
                "stacktrace": True,
            },
            "network": {
                "capture": True,
                "http": True,
                "https_capture": True,
                # 🔴 Mock 不解密 —— 如实上报 false，禁止跨级推断
                "https_decrypt": False,
                "packet_intercept": True,
            },
        }

    # -- 查询 -------------------------------------------------------------

    @property
    def uptime_ms(self) -> int:
        return int((time.monotonic() - self.started_at) * 1000)

    def find_module(self, name: str) -> MockModule | None:
        return next((m for m in self.modules if m.name == name), None)

    def module_for_address(self, address: int, length: int = 1) -> MockModule | None:
        return next((m for m in self.modules if m.contains(address, length)), None)

    def read_memory(self, address: int, length: int) -> bytes:
        """带映射与权限校验的读取。校验器独立于写路径。"""
        if length <= 0:
            raise ProtocolError(
                ErrorCode.E_BAD_ARGS, f"length 必须为正：{length}", {"length": length}
            )
        if length > 4096:
            raise ProtocolError(
                ErrorCode.E_BAD_ARGS,
                f"单次读取上限 4096 字节，收到 {length}",
                {"length": length},
                next_step="分批读取，或改用 memory.dump 走 Artifact 通道",
            )
        module = self.module_for_address(address, length)
        if module is None:
            raise ProtocolError(
                ErrorCode.E_READ_FAILED,
                f"地址 0x{address:x} 未落在任何已映射区间",
                {"address": f"0x{address:x}", "length": length,
                 "mapped_ranges": [f"0x{m.base:x}-0x{m.end:x}" for m in self.modules]},
                next_step="先用 process.modules 取模块基址，再计算实际地址",
            )
        if "r" not in module.permissions:
            raise ProtocolError(
                ErrorCode.E_PERMISSION_DENIED,
                f"区间 {module.name} 不可读（权限 {module.permissions}）",
                {"module": module.name, "permissions": module.permissions},
            )
        chunk = self._memory.get(address)
        if chunk is None:
            # 区间已映射但 Mock 没铺内容 —— 返回零页，而不是谎报失败
            return b"\x00" * length
        return (chunk + b"\x00" * length)[:length]

    def status(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "pid": self.pid,
            "package": self.package,
            "abi": self.abi,
            "sdk": self.sdk,
            "uptime_ms": self.uptime_ms,
            "runtime_ready": self.state
            in (SessionState.RUNTIME_READY, SessionState.RUNNING),
            "network_ready": True,
            "hooks_active": sum(1 for h in self.hooks.values() if h.status == "active"),
            "modules_count": len(self.modules),
            "threads_count": len(self.threads),
            "connections_count": len(self.connections),
            "packets_count": len(self.packets),
        }

    # -- 变更 -------------------------------------------------------------

    def create_hook(self, module_name: str, address: str) -> MockHook:
        module = self.find_module(module_name)
        if module is None:
            raise ProtocolError(
                ErrorCode.E_NOT_FOUND,
                f"模块 {module_name} 不在当前映射表",
                {"module": module_name,
                 "candidates": [m.name for m in self.modules]},
                next_step="先 process.modules 确认模块名；候选已附在 context.candidates",
            )
        hook_id = f"hook_{len(self.hooks) + 1:012x}"
        hook = MockHook(hook_id=hook_id, module=module_name, address=address)
        self.hooks[hook_id] = hook
        return hook

    def new_job(self, command: str) -> MockJob:
        job = MockJob(job_id=new_job_id(), command=command)
        self.jobs[job.job_id] = job
        return job

    def advance_jobs(self) -> None:
        """把 Mock 里的 job 推进一步，让 await_job 能收敛。"""
        for job in self.jobs.values():
            if job.state != "running":
                continue
            job.progress = min(1.0, job.progress + 0.5)
            if job.progress >= 1.0:
                job.state = "completed"
                job.result = {
                    "note": "Mock 后端，未产生真实产物",
                    "artifact_id": None,
                }
