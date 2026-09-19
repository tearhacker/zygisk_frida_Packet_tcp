# -*- coding: utf-8 -*-
"""命令登记表与 FAST / JOB 分级。

依据：总基线 §10.7 Command Class · §14 MCP 工具全集。

为什么要分级
------------
不分级 = 分钟级重活期间 `ping / status / 日志` 全部排队
→ AI 误判掉线 → 触发更多重试 → 重试风暴。

FAST：毫秒~秒级，命令线程直接执行，立即返回。
JOB ：秒~分钟级，投 worker 线程，返回 job_id，走
      submit → job.status → job.result / job.cancel。

标注说明
--------
`spec_source=True` 表示分级由总基线 §10.7 **明确指定**；
False 表示总基线只给了规则未逐条列举，本表按同一语义归类。
"""

from __future__ import annotations

from dataclasses import dataclass

from .constants import CommandClass, FAST_COMMAND_TIMEOUT, JOB_COMMAND_TIMEOUT


@dataclass(frozen=True)
class CommandSpec:
    """一条命令的静态规格。"""

    name: str
    cls: CommandClass
    category: str
    """所属大类，对应总基线 §14 的 11 类。"""
    writes: bool = False
    """是否属于修改类操作。修改类必须过 Write Guard。"""
    destructive: bool = False
    """是否可能造成不可逆影响（用于 MCP annotations.destructiveHint）。"""
    spec_source: bool = False
    """分级是否由总基线 §10.7 明确指定。"""

    @property
    def timeout(self) -> int:
        return (
            FAST_COMMAND_TIMEOUT
            if self.cls is CommandClass.FAST
            else JOB_COMMAND_TIMEOUT
        )


# --- 总基线 §10.7 明确列举的命令 -------------------------------------------

_FAST_SPECIFIED = {
    "process.list",
    "process.info",
    "runtime.status",
    "memory.read",
    "network.connections",
    "network.dns",
    "packet.get",
}

_JOB_SPECIFIED = {
    "memory.dump",
    "packet.export",
    "apk.decompile",
    "network.capture_start",
    "runtime.trace",
}


def _spec(
    name: str,
    cls: CommandClass,
    category: str,
    writes: bool = False,
    destructive: bool = False,
) -> CommandSpec:
    return CommandSpec(
        name=name,
        cls=cls,
        category=category,
        writes=writes,
        destructive=destructive,
        spec_source=(name in _FAST_SPECIFIED or name in _JOB_SPECIFIED),
    )


F = CommandClass.FAST
J = CommandClass.JOB

_ALL: tuple[CommandSpec, ...] = (
    # --- 01 Device -------------------------------------------------------
    _spec("device.list", F, "device"),
    _spec("device.info", F, "device"),
    _spec("device.root_status", F, "device"),
    _spec("device.shell", J, "device", writes=True, destructive=True),
    _spec("device.reboot", J, "device", writes=True, destructive=True),
    # --- 02 APK ----------------------------------------------------------
    _spec("apk.list", F, "apk"),
    _spec("apk.install", J, "apk", writes=True),
    _spec("apk.uninstall", J, "apk", writes=True, destructive=True),
    _spec("apk.launch", J, "apk", writes=True),
    _spec("apk.stop", J, "apk", writes=True),
    _spec("apk.manifest", J, "apk"),
    _spec("apk.permissions", J, "apk"),
    _spec("apk.decompile", J, "apk"),
    _spec("apk.search", J, "apk"),
    # --- 03 Session ------------------------------------------------------
    _spec("session.list", F, "session"),
    _spec("session.info", F, "session"),
    _spec("session.capabilities", F, "session"),
    # --- 04 Process ------------------------------------------------------
    _spec("process.list", F, "process"),
    _spec("process.info", F, "process"),
    _spec("process.threads", F, "process"),
    _spec("process.modules", F, "process"),
    # --- 05 Runtime ------------------------------------------------------
    _spec("runtime.status", F, "runtime"),
    _spec("runtime.attach", J, "runtime", writes=True),
    _spec("runtime.enumerate_classes", J, "runtime"),
    _spec("runtime.enumerate_methods", J, "runtime"),
    _spec("runtime.enumerate_modules", F, "runtime"),
    _spec("runtime.hook", F, "runtime", writes=True),
    _spec("runtime.unhook", F, "runtime", writes=True),
    _spec("runtime.hook_enable", F, "runtime", writes=True),
    _spec("runtime.hook_disable", F, "runtime", writes=True),
    _spec("runtime.hook_info", F, "runtime"),
    _spec("runtime.trace", J, "runtime", writes=True),
    _spec("runtime.stacktrace", F, "runtime"),
    # --- 06 Memory -------------------------------------------------------
    _spec("memory.maps", F, "memory"),
    _spec("memory.read", F, "memory"),
    _spec("memory.write", F, "memory", writes=True),
    _spec("memory.search", J, "memory"),
    _spec("memory.dump", J, "memory"),
    _spec("memory.compare", J, "memory"),
    _spec("memory.pointer_scan", J, "memory"),
    # --- 07 Network ------------------------------------------------------
    _spec("network.capture_start", J, "network", writes=True),
    _spec("network.capture_stop", J, "network", writes=True),
    _spec("network.connections", F, "network"),
    _spec("network.dns", F, "network"),
    _spec("network.http", F, "network"),
    _spec("network.https", F, "network"),
    _spec("network.websocket", F, "network"),
    _spec("network.intercept_start", J, "network", writes=True),
    _spec("network.intercept_stop", J, "network", writes=True),
    # --- 08 Packet -------------------------------------------------------
    _spec("packet.list", F, "packet"),
    _spec("packet.get", F, "packet"),
    _spec("packet.hex", F, "packet"),
    _spec("packet.decode", J, "packet"),
    _spec("packet.filter", F, "packet"),
    _spec("packet.modify", J, "packet", writes=True),
    _spec("packet.intercept", J, "packet", writes=True),
    _spec("packet.forward", F, "packet", writes=True),
    _spec("packet.drop", F, "packet", writes=True, destructive=True),
    _spec("packet.replay", J, "packet", writes=True),
    _spec("packet.export", J, "packet"),
    # --- 09 Automation ---------------------------------------------------
    _spec("rule.create", F, "automation", writes=True),
    _spec("rule.delete", F, "automation", writes=True),
    _spec("rule.list", F, "automation"),
    _spec("breakpoint.create", F, "automation", writes=True),
    _spec("breakpoint.remove", F, "automation", writes=True),
    _spec("workflow.create", F, "automation", writes=True),
    _spec("workflow.run", J, "automation", writes=True),
    _spec("workflow.stop", F, "automation", writes=True),
    # --- 10 Analysis -----------------------------------------------------
    _spec("analysis.correlate", J, "analysis"),
    _spec("analysis.trace_request", J, "analysis"),
    _spec("analysis.find_callers", J, "analysis"),
    _spec("analysis.find_network_source", J, "analysis"),
    _spec("analysis.report", J, "analysis"),
    # --- 11 Artifact -----------------------------------------------------
    _spec("artifact.get", F, "artifact"),
    _spec("artifact.list", F, "artifact"),
    _spec("artifact.export", J, "artifact"),
    # --- 12 Job（JOB 命令的统一出口，见总基线 §10.7）--------------------
    _spec("job.status", F, "job"),
    _spec("job.result", F, "job"),
    _spec("job.cancel", F, "job", writes=True, destructive=True),
)

COMMANDS: dict[str, CommandSpec] = {s.name: s for s in _ALL}

assert len(COMMANDS) == len(_ALL), "命令名重复"

ALL_COMMANDS: tuple[str, ...] = tuple(s.name for s in _ALL)

FAST_COMMANDS: tuple[str, ...] = tuple(
    s.name for s in _ALL if s.cls is CommandClass.FAST
)

JOB_COMMANDS: tuple[str, ...] = tuple(
    s.name for s in _ALL if s.cls is CommandClass.JOB
)

CATEGORIES: tuple[str, ...] = tuple(dict.fromkeys(s.category for s in _ALL))

# ---------------------------------------------------------------------------
# Write Guard 覆盖范围
# ---------------------------------------------------------------------------

WRITE_GUARDED_COMMANDS: frozenset[str] = frozenset(
    {
        "memory.write",
        "packet.modify",
    }
)
"""总基线 §12.1 明确列举的、必须过 Write Guard 的**命令**。

§12.1 还列出了另外两类"修改类操作"，它们不是独立命令，
而是通过参数触发的同一闸门：

  - runtime hook modification（参数 / 返回值改写）
      → 走 `runtime.hook` 的 modify 参数
  - network response modification
      → 走 `packet.modify` 的 response 通道

因此判定"是否需要 Write Guard"时不能只看命令名，
必须同时检查请求 payload 的写意图标志。见 `needs_write_guard()`。
"""

WRITE_INTENT_FLAGS: tuple[str, ...] = (
    "modify",
    "modify_arguments",
    "modify_return",
    "write",
    "confirm",
)


def command_class(name: str) -> CommandClass | None:
    spec = COMMANDS.get(name)
    return spec.cls if spec else None


def is_known(name: str) -> bool:
    return name in COMMANDS


def is_write_guarded(name: str, payload: dict | None = None) -> bool:
    """判断一次调用是否需要走 Write Guard。

    命令名命中 §12.1 列举的写命令，或 payload 带写意图标志，均需过闸门。
    """
    if name in WRITE_GUARDED_COMMANDS:
        return True
    if payload:
        if any(payload.get(flag) for flag in WRITE_INTENT_FLAGS):
            return True
    return False


def by_category(category: str) -> tuple[CommandSpec, ...]:
    return tuple(s for s in _ALL if s.category == category)
