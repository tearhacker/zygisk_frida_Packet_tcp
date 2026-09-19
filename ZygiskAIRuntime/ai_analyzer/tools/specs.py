# -*- coding: utf-8 -*-
"""全部 MCP 工具的规格（契约数据）。

依据：总基线 §11.2 Core Surface（常驻 ≤25）· §11.3 Expert Surface（动态挂载）· §14 工具全集。

纪律
----
- **不为了省工具数量砍功能**：功能数量 ≠ 常驻工具数量，超出部分走 Expert 动态挂载。
- **description 必须含**：use_case（何时调）、important_notes（前置 / 易错 / 下一步）、耗时档位。
- **inputSchema 全部 `additionalProperties=false`**，可选参数带 default，数值标 min/max。
- **能力不满足的工具由 Surface Manager 主动摘除**，不是等 AI 调了才报错。

分面统计：Core 25 · Expert 10，合计 35。
"""

from __future__ import annotations

from .spec import (
    ADDRESS,
    ADDRESS_OR_INT,
    Latency,
    Surface,
    ToolSpec,
    list_of,
    obj,
)

# ---------------------------------------------------------------------------
# 通用 schema 片段
# ---------------------------------------------------------------------------

CAPABILITIES = obj(
    {
        "runtime": obj(
            {
                "native_hook": {"type": "boolean"},
                "java_hook": {"type": "boolean"},
                "memory_read": {"type": "boolean"},
                "memory_write": {"type": "boolean"},
                "stacktrace": {"type": "boolean"},
            },
            strict=False,
        ),
        "network": obj(
            {
                "capture": {"type": "boolean"},
                "http": {"type": "boolean"},
                "https_capture": {"type": "boolean"},
                "https_decrypt": {"type": "boolean"},
                "packet_intercept": {"type": "boolean"},
            },
            strict=False,
        ),
    },
    ("runtime", "network"),
    strict=False,
)

SESSION_SUMMARY = obj(
    {
        "session_id": {"type": "string"},
        "state": {"type": "string"},
        "package": {"type": ["string", "null"]},
        "pid": {"type": ["integer", "null"]},
        "uptime_ms": {"type": "integer"},
    },
    ("session_id", "state"),
    strict=False,
)

MODULE_ITEM = obj(
    {
        "name": {"type": "string"},
        "path": {"type": "string"},
        "base": {"type": "string", "description": "'0x...' 字符串"},
        "size": {"type": "integer"},
        "permissions": {"type": "string"},
    },
    ("name", "base", "size"),
    strict=False,
)

THREAD_ITEM = obj(
    {
        "tid": {"type": "integer"},
        "name": {"type": "string"},
        "state": {"type": "string"},
    },
    ("tid", "name"),
    strict=False,
)

CONNECTION_ITEM = obj(
    {
        "connection_id": {"type": "string"},
        "pid": {"type": ["integer", "null"]},
        "protocol": {"type": "string"},
        "local": {"type": "string"},
        "remote": {"type": "string"},
        "state": {"type": "string"},
    },
    ("connection_id", "protocol", "remote"),
    strict=False,
)

PACKET_ITEM = obj(
    {
        "packet_id": {"type": "string"},
        "timestamp": {"type": "integer"},
        "direction": {"type": "string", "enum": ["inbound", "outbound"]},
        "protocol": {"type": "string"},
        "length": {"type": "integer", "minimum": 0},
        "connection_id": {"type": "string"},
        "sha256": {"type": ["string", "null"]},
        "hex": {"type": "string", "description": "仅 include_hex=true 时返回"},
    },
    ("packet_id", "length"),
    strict=False,
)

EXECUTION_TRIAD = obj(
    {
        "accepted": {"type": "boolean", "description": "请求已受理"},
        "executed": {"type": "boolean", "description": "已实际执行"},
        "verified": {"type": "boolean", "description": "已验证真实生效（禁止把 accepted 当 verified）"},
    },
    ("accepted", "executed", "verified"),
    strict=False,
)

ARTIFACT_ITEM = obj(
    {
        "artifact_id": {"type": "string"},
        "type": {"type": "string"},
        "size": {"type": "integer"},
        "path": {"type": "string"},
        "sha256": {"type": "string"},
        "created_at": {"type": "integer"},
    },
    ("artifact_id", "type", "size"),
    strict=False,
)

JOB_STATE = {
    "type": "string",
    "enum": ["running", "completed", "failed", "cancelled"],
}

# ---------------------------------------------------------------------------
# Core Surface（常驻 ≤25）
# ---------------------------------------------------------------------------

CORE_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="device.list",
        title="列出设备",
        description=(
            "use_case：会话开始前确认有哪些可用设备。"
            "notes：只读，不改设备状态。"
            "next_step：拿到 serial 后调 device.info 或 apk.list。"
        ),
        command="device.list",
        surface=Surface.CORE,
        latency=Latency.FAST,
        read_only=True,
        destructive=False,
        idempotent=True,
        input_schema=obj({}),
        output_schema=obj(
            {"total": {"type": "integer"}, "devices": list_of(obj({}, strict=False))},
            ("total", "devices"),
            strict=False,
        ),
    ),
    ToolSpec(
        name="device.info",
        title="设备详情",
        description=(
            "use_case：确认 root / Magisk / Zygisk / ABI / 页大小，判断能否做动态分析。"
            "notes：Zygisk 未启用时后续所有 Runtime 能力都不可用。"
            "next_step：Zygisk 就绪则调 apk.launch 起目标 App。"
        ),
        command="device.info",
        surface=Surface.CORE,
        latency=Latency.FAST,
        read_only=True,
        destructive=False,
        idempotent=True,
        input_schema=obj({}),
        output_schema=obj(
            {
                "serial": {"type": "string"},
                "abi": {"type": "string"},
                "api": {"type": "integer"},
                "page_size": {"type": "integer"},
                "zygisk": {"type": "string"},
                "selinux": {"type": "string"},
                "rooted": {"type": "boolean"},
            },
            ("abi", "rooted"),
            strict=False,
        ),
    ),
    ToolSpec(
        name="apk.list",
        title="列出已安装应用",
        description=(
            "use_case：挑出要分析的目标 App。"
            "notes：只读。"
            "next_step：用 apk.launch 启动目标包名。"
        ),
        command="apk.list",
        surface=Surface.CORE,
        latency=Latency.FAST,
        read_only=True,
        destructive=False,
        idempotent=True,
        input_schema=obj(
            {"brief": {"type": "boolean", "default": True, "description": "只回统计 + 前 N 条摘要"}}
        ),
        output_schema=obj(
            {"total": {"type": "integer"}, "truncated": {"type": "boolean"}},
            ("total", "truncated"),
            strict=False,
        ),
    ),
    ToolSpec(
        name="apk.launch",
        title="启动目标应用",
        description=(
            "use_case：启动 App 并触发 Zygisk 自动进入，是整条链路的起点。"
            "notes：启动后 Runtime 与 Session 是**异步**出现的，不要立刻查 Session，"
            "应先轮询 session.list。"
            "next_step：session.list 确认 Session 出现，再调 session.capabilities。"
        ),
        command="apk.launch",
        surface=Surface.CORE,
        latency=Latency.SLOW,
        read_only=False,
        destructive=True,
        idempotent=False,
        input_schema=obj(
            {"package": {"type": "string", "minLength": 1, "description": "目标包名"}},
            ("package",),
        ),
        output_schema=obj(
            {"package": {"type": "string"}, "launched": {"type": "boolean"}},
            ("package",),
            strict=False,
        ),
    ),
    ToolSpec(
        name="apk.stop",
        title="停止目标应用",
        description=(
            "use_case：结束分析，或强制重启以重跑启动链。"
            "notes：会连带 Session 进入 DEGRADED → CLOSED。"
            "next_step：需要继续分析就重新 apk.launch。"
        ),
        command="apk.stop",
        surface=Surface.CORE,
        latency=Latency.MEDIUM,
        read_only=False,
        destructive=True,
        idempotent=True,
        input_schema=obj({"package": {"type": "string", "minLength": 1}}, ("package",)),
        output_schema=obj(
            {"package": {"type": "string"}, "stopped": {"type": "boolean"}},
            ("package",),
            strict=False,
        ),
    ),
    ToolSpec(
        name="session.list",
        title="列出会话",
        description=(
            "use_case：确认目标 App 的 Session 是否已出现。"
            "notes：**重连后 session_id 一定会变**，旧 id 已失效，不要复用。"
            "next_step：session.info 或 session.capabilities。"
        ),
        command="session.list",
        surface=Surface.CORE,
        latency=Latency.FAST,
        read_only=True,
        destructive=False,
        idempotent=True,
        input_schema=obj({}),
        output_schema=obj(
            {"total": {"type": "integer"}, "sessions": list_of(SESSION_SUMMARY)},
            ("total", "sessions"),
            strict=False,
        ),
    ),
    ToolSpec(
        name="session.info",
        title="会话详情",
        description=(
            "use_case：取当前 Session 的包名 / PID / ABI / SDK / 运行时长。"
            "notes：只读。"
            "next_step：需要判断能做什么就调 session.capabilities。"
        ),
        command="session.info",
        surface=Surface.CORE,
        latency=Latency.FAST,
        read_only=True,
        destructive=False,
        idempotent=True,
        input_schema=obj({}),
        output_schema=obj(
            {
                "session_id": {"type": "string"},
                "state": {"type": "string"},
                "package": {"type": ["string", "null"]},
                "pid": {"type": ["integer", "null"]},
                "abi": {"type": ["string", "null"]},
                "sdk": {"type": ["integer", "null"]},
                "uptime_ms": {"type": "integer"},
            },
            ("session_id", "state"),
            strict=False,
        ),
    ),
    ToolSpec(
        name="session.capabilities",
        title="会话能力",
        description=(
            "use_case：**决定下一步做什么之前必须先调这个**。"
            "notes：能力为 false 表示不可用，相关工具已被摘除。"
            "尤其注意 https_decrypt=false 时不要声称能看明文。"
            "next_step：按返回的能力选择工具，不要试不可用的。"
        ),
        command="session.capabilities",
        surface=Surface.CORE,
        latency=Latency.FAST,
        read_only=True,
        destructive=False,
        idempotent=True,
        input_schema=obj({}),
        output_schema=obj(
            {"capabilities": CAPABILITIES, "note": {"type": "string"}},
            ("capabilities",),
            strict=False,
        ),
    ),
    ToolSpec(
        name="process.list",
        title="列出进程",
        description=(
            "use_case：确认目标进程是否存在及其 PID。"
            "notes：只读。is_target=true 的那条就是目标 App。"
            "next_step：process.modules 取模块基址。"
        ),
        command="process.list",
        surface=Surface.CORE,
        latency=Latency.FAST,
        read_only=True,
        destructive=False,
        idempotent=True,
        input_schema=obj({"brief": {"type": "boolean", "default": True}}),
        output_schema=obj(
            {
                "total": {"type": "integer"},
                "truncated": {"type": "boolean"},
                "processes": list_of(obj({}, strict=False)),
            },
            ("total",),
            strict=False,
        ),
    ),
    ToolSpec(
        name="process.info",
        title="进程详情",
        description=(
            "use_case：取 PID / UID / ABI / SDK / 线程数 / 模块数。"
            "notes：只读。"
            "next_step：process.modules 或 process.threads。"
        ),
        command="process.info",
        surface=Surface.CORE,
        latency=Latency.FAST,
        read_only=True,
        destructive=False,
        idempotent=True,
        input_schema=obj({}),
        output_schema=obj(
            {
                "pid": {"type": "integer"},
                "package": {"type": "string"},
                "abi": {"type": "string"},
                "threads": {"type": "integer"},
                "modules": {"type": "integer"},
            },
            ("pid",),
            strict=False,
        ),
    ),
    ToolSpec(
        name="process.modules",
        title="列出模块映射",
        description=(
            "use_case：**做 Hook 或内存读之前必须调**，拿模块基址。"
            "notes：base 是 '0x...' 字符串。地址算好后用 memory.read 或 runtime.hook。"
            "模块名或基址在 SO 加载后可能变化，此时报 E_MAP_STALE，需重新调用本工具。"
            "next_step：runtime.hook / memory.read。"
        ),
        command="process.modules",
        surface=Surface.CORE,
        latency=Latency.FAST,
        read_only=True,
        destructive=False,
        idempotent=True,
        input_schema=obj(
            {"name_contains": {"type": ["string", "null"], "default": None,
                               "description": "按名字过滤，null 表示不过滤"}}
        ),
        output_schema=obj(
            {
                "total": {"type": "integer"},
                "truncated": {"type": "boolean"},
                "modules": list_of(MODULE_ITEM),
            },
            ("total", "modules"),
            strict=False,
        ),
    ),
    ToolSpec(
        name="process.threads",
        title="列出线程",
        description=(
            "use_case：定位目标线程，为 Hook 事件与网络事件做关联。"
            "notes：只读。tid 是后续 correlation 的关键字段。"
            "next_step：与 packet.get / runtime.hook 的 tid 对齐。"
        ),
        command="process.threads",
        surface=Surface.CORE,
        latency=Latency.FAST,
        read_only=True,
        destructive=False,
        idempotent=True,
        input_schema=obj({}),
        output_schema=obj(
            {
                "total": {"type": "integer"},
                "truncated": {"type": "boolean"},
                "threads": list_of(THREAD_ITEM),
            },
            ("total", "threads"),
            strict=False,
        ),
    ),
    ToolSpec(
        name="runtime.status",
        title="运行时状态",
        description=(
            "use_case：探活。任何超时或异常之后先调这个，判断后端是卡住还是已死。"
            "notes：只读，最便宜的一次调用。"
            "next_step：正常则继续业务；异常则查 session.list 是否已失效。"
        ),
        command="runtime.status",
        surface=Surface.CORE,
        latency=Latency.FAST,
        read_only=True,
        destructive=False,
        idempotent=True,
        input_schema=obj({}),
        output_schema=obj(
            {
                "state": {"type": "string"},
                "pid": {"type": "integer"},
                "package": {"type": "string"},
                "abi": {"type": "string"},
                "runtime_ready": {"type": "boolean"},
                "network_ready": {"type": "boolean"},
                "hooks_active": {"type": "integer"},
                "modules_count": {"type": "integer"},
                "threads_count": {"type": "integer"},
            },
            ("state", "pid", "runtime_ready"),
            strict=False,
        ),
    ),
    ToolSpec(
        name="runtime.hook",
        title="安装 Hook",
        description=(
            "use_case：对运行中 App 的目标函数装 Hook，App 不重启。"
            "notes：需要 module + address。"
            "🔴 返回 status=ok **不算成功** —— 必须看 execution.verified 与 events_observed；"
            "verified 由真实 HOOK_ENTER / HOOK_LEAVE 事件支撑。"
            "next_step：读事件或调 runtime.hook_info 确认状态。"
        ),
        command="runtime.hook",
        surface=Surface.CORE,
        latency=Latency.FAST,
        read_only=False,
        destructive=True,
        idempotent=False,
        requires=(("runtime", "native_hook"),),
        input_schema=obj(
            {
                "module": {"type": "string", "minLength": 1},
                "address": ADDRESS,
            },
            ("module", "address"),
        ),
        output_schema=obj(
            {
                "hook": obj({}, strict=False),
                "execution": EXECUTION_TRIAD,
                "events_observed": list_of({"type": "string"}),
            },
            ("execution",),
            strict=False,
        ),
    ),
    ToolSpec(
        name="runtime.unhook",
        title="移除 Hook",
        description=(
            "use_case：分析完成后清理 Hook，避免残留影响目标 App 行为。"
            "notes：需要 hook_id，可从 runtime.hook 返回或 runtime.hook_info 取得。"
            "next_step：runtime.hook_info 确认 status=removed。"
        ),
        command="runtime.unhook",
        surface=Surface.CORE,
        latency=Latency.FAST,
        read_only=False,
        destructive=True,
        idempotent=True,
        input_schema=obj({"hook_id": {"type": "string", "minLength": 1}}, ("hook_id",)),
        output_schema=obj(
            {"hook_id": {"type": "string"}, "status": {"type": "string"},
             "execution": EXECUTION_TRIAD},
            ("hook_id", "status"),
            strict=False,
        ),
    ),
    ToolSpec(
        name="runtime.trace",
        title="函数追踪",
        description=(
            "use_case：对某个函数做一段时间内的调用追踪，收集调用序列。"
            "notes：JOB 命令，秒~分钟级，返回 job_id。"
            "next_step：用 job.status 轮询，完成后 job.result 取产物。"
        ),
        command="runtime.trace",
        surface=Surface.CORE,
        latency=Latency.SLOW,
        read_only=False,
        destructive=False,
        idempotent=False,
        requires=(("runtime", "native_hook"),),
        input_schema=obj(
            {
                "module": {"type": "string"},
                "address": ADDRESS,
                "duration_ms": {"type": "integer", "minimum": 100, "maximum": 300000,
                                "default": 5000},
            },
            ("module", "address"),
        ),
        output_schema=obj({"job_id": {"type": "string"}}, ("job_id",), strict=False),
    ),
    ToolSpec(
        name="memory.read",
        title="读内存",
        description=(
            "use_case：读取目标进程指定地址的字节。"
            "notes：地址必须落在已映射区间且区间可读，否则 E_READ_FAILED 并返回可用区间。"
            "单次上限 4096 字节。"
            "next_step：需要大块数据改用 memory.dump（JOB）。"
        ),
        command="memory.read",
        surface=Surface.CORE,
        latency=Latency.FAST,
        read_only=True,
        destructive=False,
        idempotent=True,
        requires=(("runtime", "memory_read"),),
        input_schema=obj(
            {
                "address": ADDRESS,
                "length": {"type": "integer", "minimum": 1, "maximum": 4096, "default": 16},
            },
            ("address",),
        ),
        output_schema=obj(
            {
                "address": {"type": "string"},
                "length": {"type": "integer"},
                "hex": {"type": "string"},
                "ascii": {"type": "string"},
                "module": {"type": ["string", "null"]},
            },
            ("address", "length", "hex"),
            strict=False,
        ),
    ),
    ToolSpec(
        name="memory.write",
        title="写内存",
        description=(
            "use_case：修改目标进程内存（授权测试场景）。"
            "notes：🔴 高风险。必须走 Write Guard：validate → preview → backup → confirm → "
            "execute → verify。confirm 默认 false，必须显式传 true。"
            "返回必须含 original / new / verified 三项。"
            "next_step：verified=false 时不要声称成功，需回滚并换地址。"
        ),
        command="memory.write",
        surface=Surface.CORE,
        latency=Latency.FAST,
        read_only=False,
        destructive=True,
        idempotent=False,
        requires=(("runtime", "memory_write"),),
        input_schema=obj(
            {
                "address": ADDRESS,
                "hex": {"type": "string", "pattern": r"^[0-9a-fA-F]+$",
                        "description": "要写入的字节，十六进制字符串"},
                "confirm": {"type": "boolean", "default": False,
                            "description": "Write Guard 显式确认，默认 false"},
            },
            ("address", "hex"),
        ),
        output_schema=obj(
            {
                "address": {"type": "string"},
                "original": {"type": "string"},
                "new": {"type": "string"},
                "verified": {"type": "boolean"},
                "execution": EXECUTION_TRIAD,
            },
            ("address", "verified"),
            strict=False,
        ),
    ),
    ToolSpec(
        name="memory.search",
        title="搜索内存",
        description=(
            "use_case：按特征找地址（先找候选，再验证候选）。"
            "notes：0 命中时不要下「不存在」的结论 —— 返回里带搜索范围与放宽建议。"
            "next_step：用返回的候选地址调 memory.read 验证。"
        ),
        command="memory.search",
        surface=Surface.CORE,
        latency=Latency.MEDIUM,
        read_only=True,
        destructive=False,
        idempotent=True,
        requires=(("runtime", "memory_read"),),
        input_schema=obj(
            {
                "pattern": {"type": "string", "minLength": 1,
                            "description": "十六进制字节串，或明文字符串"},
                "as_text": {"type": "boolean", "default": False},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 256, "default": 32},
            },
            ("pattern",),
        ),
        output_schema=obj(
            {"total": {"type": "integer"}, "matches": list_of(obj({}, strict=False))},
            ("total",),
            strict=False,
        ),
    ),
    ToolSpec(
        name="network.capture_start",
        title="开始抓包",
        description=(
            "use_case：开始网络捕获，之后才有 Packet 与连接数据。"
            "notes：JOB 命令，秒级启动，返回 job_id。"
            "抓到了 ≠ 能解密，HTTPS 能力请以 session.capabilities 为准。"
            "next_step：job.status 等就绪，然后 network.connections。"
        ),
        command="network.capture_start",
        surface=Surface.CORE,
        latency=Latency.SLOW,
        read_only=False,
        destructive=False,
        idempotent=True,
        requires=(("network", "capture"),),
        input_schema=obj(
            {
                "pcap": {"type": "boolean", "default": False,
                         "description": "是否同时落 PCAP 产物（走 Artifact 通道）"}
            }
        ),
        output_schema=obj({"job_id": {"type": "string"}}, ("job_id",), strict=False),
    ),
    ToolSpec(
        name="network.capture_stop",
        title="停止抓包",
        description=(
            "use_case：结束捕获并落盘产物。"
            "notes：产物走 Artifact 通道，返回 artifact_id + sha256，不进协议 JSON。"
            "next_step：artifact.get 取元数据，需要内容走独立通道拉取。"
        ),
        command="network.capture_stop",
        surface=Surface.CORE,
        latency=Latency.MEDIUM,
        read_only=False,
        destructive=False,
        idempotent=True,
        requires=(("network", "capture"),),
        input_schema=obj({}),
        output_schema=obj(
            {"stopped": {"type": "boolean"}, "artifact_id": {"type": ["string", "null"]}},
            ("stopped",),
            strict=False,
        ),
    ),
    ToolSpec(
        name="network.connections",
        title="列出网络连接",
        description=(
            "use_case：看 App 当前有哪些连接，是抓包之外最轻量的网络视图。"
            "notes：只读。connection_id 是后续关联 Packet 与 Runtime 的桥梁。"
            "next_step：packet.get 取具体包，或与 process.threads 做关联。"
        ),
        command="network.connections",
        surface=Surface.CORE,
        latency=Latency.FAST,
        read_only=True,
        destructive=False,
        idempotent=True,
        requires=(("network", "capture"),),
        input_schema=obj({"brief": {"type": "boolean", "default": False}}),
        output_schema=obj(
            {
                "total": {"type": "integer"},
                "truncated": {"type": "boolean"},
                "connections": list_of(CONNECTION_ITEM),
            },
            ("total", "connections"),
            strict=False,
        ),
    ),
    ToolSpec(
        name="packet.get",
        title="取数据包",
        description=(
            "use_case：取一个包的元数据与内容。"
            "notes：默认返回 hex；大 body 用 include_hex=false 只取 metadata + sha256。"
            "未命中时返回候选 id 与数量，不要据此断定包不存在。"
            "next_step：packet.decode 解析结构，或 packet.modify 改包。"
        ),
        command="packet.get",
        surface=Surface.CORE,
        latency=Latency.FAST,
        read_only=True,
        destructive=False,
        idempotent=True,
        requires=(("network", "capture"),),
        input_schema=obj(
            {
                "packet_id": {"type": "string", "minLength": 1},
                "include_hex": {"type": "boolean", "default": True},
            },
            ("packet_id",),
        ),
        output_schema=obj({"packet": PACKET_ITEM}, ("packet",), strict=False),
    ),
    ToolSpec(
        name="packet.modify",
        title="修改数据包",
        description=(
            "use_case：改包并转发（授权测试场景）。"
            "notes：🔴 必须走 Write Guard。返回 original_hex / modified_hex / offset / "
            "changed_length；协议禁止长度变化时直接拒绝，不得偷偷截断。"
            "next_step：观察下游是否真的收到修改后的字节。"
        ),
        command="packet.modify",
        surface=Surface.CORE,
        latency=Latency.SLOW,
        read_only=False,
        destructive=True,
        idempotent=False,
        requires=(("network", "packet_intercept"),),
        input_schema=obj(
            {
                "packet_id": {"type": "string", "minLength": 1},
                "offset": {"type": "integer", "minimum": 0, "maximum": 1048576},
                "hex": {"type": "string", "pattern": r"^[0-9a-fA-F]*$"},
                "confirm": {"type": "boolean", "default": False},
            },
            ("packet_id", "offset", "hex"),
        ),
        output_schema=obj(
            {
                "packet_id": {"type": "string"},
                "original_hex": {"type": "string"},
                "modified_hex": {"type": "string"},
                "changed_length": {"type": "integer"},
                "verified": {"type": "boolean"},
            },
            ("packet_id", "verified"),
            strict=False,
        ),
    ),
    ToolSpec(
        name="artifact.get",
        title="取产物元数据",
        description=(
            "use_case：按 artifact_id 取大对象的元数据（类型 / 大小 / 路径 / sha256）。"
            "notes：🔴 大文件**永远不进协议 JSON**。要内容请走独立通道拉取并校验 sha256。"
            "next_step：拉取后校验 sha256，不匹配即判定任务失败。"
        ),
        command="artifact.get",
        surface=Surface.CORE,
        latency=Latency.FAST,
        read_only=True,
        destructive=False,
        idempotent=True,
        input_schema=obj(
            {"artifact_id": {"type": "string", "minLength": 1}}, ("artifact_id",)
        ),
        output_schema=obj({"artifact": ARTIFACT_ITEM}, ("artifact",), strict=False),
    ),
)

# ---------------------------------------------------------------------------
# Expert Surface（按需动态挂载）
# ---------------------------------------------------------------------------

EXPERT_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="memory.maps",
        title="内存映射表",
        description=(
            "use_case：查看完整映射区间，定位可读/可写段。"
            "notes：比 process.modules 更细，含权限。"
            "next_step：按 start/end 选地址再 memory.read。"
        ),
        command="memory.maps",
        surface=Surface.EXPERT,
        group="Memory+",
        latency=Latency.FAST,
        read_only=True,
        destructive=False,
        idempotent=True,
        requires=(("runtime", "memory_read"),),
        input_schema=obj({}),
        output_schema=obj(
            {"total": {"type": "integer"}, "maps": list_of(obj({}, strict=False))},
            ("total",),
            strict=False,
        ),
    ),
    ToolSpec(
        name="memory.dump",
        title="转储内存",
        description=(
            "use_case：把一段内存落成产物供离线分析。"
            "notes：JOB 命令。产物走 Artifact 通道，只回 metadata + sha256。"
            "next_step：job.status 轮询，完成后 artifact.get 取元数据。"
        ),
        command="memory.dump",
        surface=Surface.EXPERT,
        group="Memory+",
        latency=Latency.SLOW,
        read_only=True,
        destructive=False,
        idempotent=False,
        requires=(("runtime", "memory_read"),),
        input_schema=obj(
            {
                "address": ADDRESS,
                "length": {"type": "integer", "minimum": 1, "maximum": 67108864},
            },
            ("address", "length"),
        ),
        output_schema=obj({"job_id": {"type": "string"}}, ("job_id",), strict=False),
    ),
    ToolSpec(
        name="network.dns",
        title="DNS 查询记录",
        description=(
            "use_case：看 App 解析了哪些域名，快速摸清后端清单。"
            "notes：只读。"
            "next_step：按域名过滤 packet.list。"
        ),
        command="network.dns",
        surface=Surface.EXPERT,
        group="Network+",
        latency=Latency.FAST,
        read_only=True,
        destructive=False,
        idempotent=True,
        requires=(("network", "capture"),),
        input_schema=obj({}),
        output_schema=obj(
            {"total": {"type": "integer"}, "queries": list_of(obj({}, strict=False))},
            ("total",),
            strict=False,
        ),
    ),
    ToolSpec(
        name="packet.list",
        title="列出数据包",
        description=(
            "use_case：批量看包，配合过滤缩小范围。"
            "notes：只读。大结果分页。"
            "next_step：packet.get 取具体包内容。"
        ),
        command="packet.list",
        surface=Surface.EXPERT,
        group="Packet+",
        latency=Latency.FAST,
        read_only=True,
        destructive=False,
        idempotent=True,
        requires=(("network", "capture"),),
        input_schema=obj(
            {
                "connection_id": {"type": ["string", "null"], "default": None},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
            }
        ),
        output_schema=obj(
            {
                "total": {"type": "integer"},
                "truncated": {"type": "boolean"},
                "packets": list_of(PACKET_ITEM),
            },
            ("total", "packets"),
            strict=False,
        ),
    ),
    ToolSpec(
        name="packet.hex",
        title="包 HEX 视图",
        description=(
            "use_case：以偏移 + HEX + ASCII 形式看包内容，便于逐字节定位。"
            "notes：只读。大包请用 offset/length 分段看。"
            "next_step：确定 offset 后用 packet.modify 改。"
        ),
        command="packet.hex",
        surface=Surface.EXPERT,
        group="Packet+",
        latency=Latency.FAST,
        read_only=True,
        destructive=False,
        idempotent=True,
        requires=(("network", "capture"),),
        input_schema=obj(
            {
                "packet_id": {"type": "string", "minLength": 1},
                "offset": {"type": "integer", "minimum": 0, "maximum": 1048576, "default": 0},
                "length": {"type": "integer", "minimum": 1, "maximum": 4096, "default": 256},
            },
            ("packet_id",),
        ),
        output_schema=obj(
            {"packet_id": {"type": "string"}, "offset": {"type": "integer"},
             "hex": {"type": "string"}},
            ("packet_id", "hex"),
            strict=False,
        ),
    ),
    ToolSpec(
        name="packet.export",
        title="导出数据包",
        description=(
            "use_case：把筛选出的包导出成产物（PCAP / JSON）。"
            "notes：JOB 命令。产物走 Artifact 通道。"
            "next_step：job.status → artifact.get。"
        ),
        command="packet.export",
        surface=Surface.EXPERT,
        group="Packet+",
        latency=Latency.SLOW,
        read_only=True,
        destructive=False,
        idempotent=False,
        requires=(("network", "capture"),),
        input_schema=obj(
            {"connection_id": {"type": ["string", "null"], "default": None},
             "format": {"type": "string", "enum": ["pcap", "json"], "default": "pcap"}}
        ),
        output_schema=obj({"job_id": {"type": "string"}}, ("job_id",), strict=False),
    ),
    ToolSpec(
        name="artifact.list",
        title="列出产物",
        description=(
            "use_case：查看本次会话已产生的产物。"
            "notes：只读。"
            "next_step：artifact.get 取元数据。"
        ),
        command="artifact.list",
        surface=Surface.EXPERT,
        group="Artifact+",
        latency=Latency.FAST,
        read_only=True,
        destructive=False,
        idempotent=True,
        input_schema=obj({}),
        output_schema=obj(
            {"total": {"type": "integer"}, "artifacts": list_of(ARTIFACT_ITEM)},
            ("total", "artifacts"),
            strict=False,
        ),
    ),
    ToolSpec(
        name="job.status",
        title="任务状态",
        description=(
            "use_case：轮询 JOB 命令进度。"
            "notes：running 时返回 suggested_wait_ms，按它等，不要密集轮询。"
            "next_step：completed 后调 job.result。"
        ),
        command="job.status",
        surface=Surface.EXPERT,
        group="Job",
        latency=Latency.FAST,
        read_only=True,
        destructive=False,
        idempotent=True,
        input_schema=obj({"job_id": {"type": "string", "minLength": 1}}, ("job_id",)),
        output_schema=obj(
            {
                "job_id": {"type": "string"},
                "state": JOB_STATE,
                "progress": {"type": "number", "minimum": 0, "maximum": 1},
                "elapsed_ms": {"type": "integer"},
                "suggested_wait_ms": {"type": "integer"},
            },
            ("job_id", "state", "progress"),
            strict=False,
        ),
    ),
    ToolSpec(
        name="job.result",
        title="任务结果",
        description=(
            "use_case：取 JOB 命令的最终结果。"
            "notes：未完成时返回 E_NOT_READY，先继续轮询 job.status。"
            "next_step：结果里若含 artifact_id，用 artifact.get 取元数据。"
        ),
        command="job.result",
        surface=Surface.EXPERT,
        group="Job",
        latency=Latency.FAST,
        read_only=True,
        destructive=False,
        idempotent=True,
        input_schema=obj({"job_id": {"type": "string", "minLength": 1}}, ("job_id",)),
        output_schema=obj(
            {"job_id": {"type": "string"}, "state": JOB_STATE,
             "result": obj({}, strict=False)},
            ("job_id", "state"),
            strict=False,
        ),
    ),
    ToolSpec(
        name="job.cancel",
        title="取消任务",
        description=(
            "use_case：终止不再需要的 JOB 命令，释放后端资源。"
            "notes：已进入终态的 job 不会因取消而回滚。"
            "next_step：无需后续动作。"
        ),
        command="job.cancel",
        surface=Surface.EXPERT,
        group="Job",
        latency=Latency.FAST,
        read_only=False,
        destructive=True,
        idempotent=True,
        input_schema=obj({"job_id": {"type": "string", "minLength": 1}}, ("job_id",)),
        output_schema=obj(
            {"job_id": {"type": "string"}, "state": JOB_STATE},
            ("job_id", "state"),
            strict=False,
        ),
    ),
)

ALL_SPECS: tuple[ToolSpec, ...] = CORE_SPECS + EXPERT_SPECS
"""全部工具规格。Core 25 + Expert 10 = 35。"""

SPECS_BY_NAME: dict[str, ToolSpec] = {s.name: s for s in ALL_SPECS}

assert len(SPECS_BY_NAME) == len(ALL_SPECS), "工具名重复"

EXPERT_GROUPS: tuple[str, ...] = tuple(
    dict.fromkeys(s.group for s in EXPERT_SPECS if s.group)
)
