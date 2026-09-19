# -*- coding: utf-8 -*-
"""协议常量单一源。

本文件是 IPC 协议的**唯一常量源**。
Android 侧对应头文件 `native/include/ipc/protocol_constants.h` 必须与本文件逐项一致，
`tests/protocol/test_constants.py` 会解析该头文件并交叉校验，不一致直接测试失败。

依据：
  - 总基线 §10 Protocol Layer v1 · 附录 A 协议常量单一源
  - 施工手册 §8 M0.1 constants

纪律：新增常量前必须先确认是否已有定义；文档引用常量名，不重复数值。
"""

from __future__ import annotations

from enum import Enum

# ---------------------------------------------------------------------------
# 协议版本
# ---------------------------------------------------------------------------

PROTOCOL_VERSION = "1.0"
"""协议版本。版本不匹配 → ERROR_PROTOCOL_VERSION，且禁止进入 READY。"""

SERVER_NAME = "ai-analyzer"
SERVER_VERSION = "1.0.0"
CLIENT_NAME = "mcp-server"
CLIENT_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# 帧格式
# ---------------------------------------------------------------------------

FRAME_HEADER_SIZE = 4
"""帧头字节数：4 字节 uint32，payload 长度，网络字节序（大端）。"""

FRAME_MAX_PAYLOAD = 8 * 1024 * 1024
"""单帧 payload 上限 8 MiB。超过视为非法帧，防止恶意长度导致内存爆炸。

总基线 §13 规定大文件（PCAP / dump / trace）走 Artifact Channel，
不进协议 JSON；此上限是给正常 metadata 帧留的充足余量。
"""

# ---------------------------------------------------------------------------
# 超时与心跳
# ---------------------------------------------------------------------------

HEARTBEAT_INTERVAL = 5
"""心跳发送间隔（秒）。"""

HEARTBEAT_TIMEOUT = 30
"""心跳超时（秒）。超时进入 DEGRADED，连续超时进入 DISCONNECTED。"""

FAST_COMMAND_TIMEOUT = 10
"""FAST 命令超时（秒）。毫秒~秒级命令。"""

JOB_COMMAND_TIMEOUT = 300
"""JOB 命令超时（秒）。秒~分钟级命令。"""

SESSION_IDLE_TIMEOUT = 600
"""Session 空闲超时（秒）。禁止无限持有 Session。"""

CONNECT_TIMEOUT = 10
"""建立 UDS 连接的超时（秒）。"""

# ---------------------------------------------------------------------------
# 重连退避
# ---------------------------------------------------------------------------

RECONNECT_BACKOFF = (1, 2, 4, 8, 16, 30)
"""指数退避序列（秒），最后一项为上限，此后一直用它。

上限存在的理由：防止疯狂重连占满事件循环。
"""

RECONNECT_BACKOFF_MAX = RECONNECT_BACKOFF[-1]

SESSION_ID_INVALIDATE_ON_RECONNECT = True
"""重连必须使所有 session_id 立即失效。

总基线 §9.4 冻结项：重连**不恢复**旧 Session。
理由：允许沿用旧 sessionId 会让 AI 在幽灵数据上连续推理。
"""

# ---------------------------------------------------------------------------
# 写操作闸门
# ---------------------------------------------------------------------------

WRITE_CONFIRM_DEFAULT = False
"""Write Guard 的 confirm 参数默认值。默认不确认，必须显式开启。"""

# ---------------------------------------------------------------------------
# 工具面
# ---------------------------------------------------------------------------

MAX_RESPONSE_TOKENS = 4096
"""单工具响应 token 上限。违反视为 bug。"""

MAX_RESIDENT_TOOLS = 25
"""Core Surface 常驻工具上限。"""

MAX_TOOLS_HARD_LIMIT = 45
"""工具总数硬上限。"""

# ---------------------------------------------------------------------------
# 消息类型
# ---------------------------------------------------------------------------


class MessageType(str, Enum):
    """协议消息类型。九种，每种必须有 schema。"""

    HELLO = "HELLO"
    HELLO_ACK = "HELLO_ACK"
    READY = "READY"
    REQUEST = "REQUEST"
    RESPONSE = "RESPONSE"
    EVENT = "EVENT"
    PING = "PING"
    PONG = "PONG"
    ERROR = "ERROR"


# ---------------------------------------------------------------------------
# 命令分级
# ---------------------------------------------------------------------------


class CommandClass(str, Enum):
    """命令分级。不分级 = 分钟级重活期间 ping/status 全部排队 → AI 误判掉线。"""

    FAST = "FAST"
    JOB = "JOB"


# ---------------------------------------------------------------------------
# Session 状态
# ---------------------------------------------------------------------------


class SessionState(str, Enum):
    """Session 生命周期状态。Session 是唯一状态边界。"""

    CREATED = "CREATED"
    STARTING = "STARTING"
    RUNTIME_READY = "RUNTIME_READY"
    NETWORK_READY = "NETWORK_READY"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPING = "STOPPING"
    CLOSED = "CLOSED"
    # 异常分支
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    ERROR = "ERROR"


# ---------------------------------------------------------------------------
# 连接状态
# ---------------------------------------------------------------------------


class LinkState(str, Enum):
    """链路状态。CONNECTED → DEGRADED（单次超时）→ DISCONNECTED（连续超时）。"""

    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    DEGRADED = "DEGRADED"


# ---------------------------------------------------------------------------
# 执行三态（禁止 Fake Success）
# ---------------------------------------------------------------------------


class ExecutionState(str, Enum):
    """执行型工具必须区分三级，禁止把 accepted 当 verified 上报。"""

    ACCEPTED = "accepted"
    EXECUTED = "executed"
    VERIFIED = "verified"


# ---------------------------------------------------------------------------
# HTTPS 五级能力状态（禁止跨级推断）
# ---------------------------------------------------------------------------


class HttpsCapability(str, Enum):
    """HTTPS 能力五级。抓到了 ≠ 解密了 ≠ 能改。逐级如实上报。"""

    CAPTURED = "captured"
    DECODED = "decoded"
    DECRYPTED = "decrypted"
    INTERCEPTABLE = "interceptable"
    MODIFIABLE = "modifiable"


# ---------------------------------------------------------------------------
# 事件类型
# ---------------------------------------------------------------------------

EVENT_TYPES_P0 = (
    "PROCESS_STARTED",
    "AGENT_CONNECTED",
    "RUNTIME_READY",
    "MODULE_LOADED",
    "THREAD_CREATED",
    "HOOK_ENTER",
    "HOOK_LEAVE",
    "NETWORK_CONNECTED",
    "HTTP_REQUEST",
    "HTTP_RESPONSE",
    "PACKET_CAPTURED",
)
"""第一批事件（P0）。"""

EVENT_TYPES_P1 = (
    "DEX_LOADED",
    "CLASS_LOADED",
    "JNI_CALL",
    "SO_LOADED",
    "MEMORY_CHANGED",
    "WEBSOCKET_FRAME",
    "HOOK_INSTALLED",
    "PACKET_MODIFIED",
    "PACKET_REPLAYED",
)
"""第二批事件（P1）。"""

EVENT_TYPES = EVENT_TYPES_P0 + EVENT_TYPES_P1
"""事件类型全集。"""

# ---------------------------------------------------------------------------
# 能力声明（Session 启动后必须如实报告能力）
# ---------------------------------------------------------------------------

CAPABILITY_KEYS_RUNTIME = (
    "native_hook",
    "java_hook",
    "memory_read",
    "memory_write",
    "stacktrace",
)

CAPABILITY_KEYS_NETWORK = (
    "capture",
    "http",
    "https_capture",
    "https_decrypt",
    "packet_intercept",
)

# ---------------------------------------------------------------------------
# 默认 IPC 端点
# ---------------------------------------------------------------------------
#
# 传输层：总基线 §10.1 冻结的是 **Unix Domain Socket**。
# 但 Windows 上的 CPython 可能没有 `socket.AF_UNIX`（本机 3.13.14 即如此），
# 而真机部署本来也要经 `adb forward tcp:<port>` 落到设备侧 UDS。
# 因此协议层与 Bridge 支持两种端点，UDS 优先，TCP 回环作为等价回退：
#
#     unix:/data/local/tmp/ai-analyzer/analyzer.sock
#     tcp:127.0.0.1:60500
#
# 帧格式、消息格式、握手流程两种传输完全一致 —— 传输层不改变协议。
#
# TCP 端点由项目所有者 2026-09-19 裁定为 127.0.0.1:60500（原为 27901）。
# 固定绑定回环：Runtime 带 root 能力，监听 0.0.0.0 等于把设备内存读写权限
# 开给同一网段的任何人，故不提供 host 覆盖项。
#
# 真机用法（PC 侧转发到设备）：
#     adb forward tcp:60500 tcp:60500
#     python -m ai_analyzer.host --endpoint tcp:127.0.0.1:60500

TRANSPORT_UNIX = "unix"
TRANSPORT_TCP = "tcp"

DEFAULT_SOCKET_PATH = "/data/local/tmp/ai-analyzer/analyzer.sock"
"""设备侧 UDS 路径（冻结方案）。"""

DEFAULT_LOCAL_SOCKET_PATH = ".ai-analyzer/analyzer.sock"
"""本机（Mock / 开发）UDS 路径，相对工程根。"""

DEFAULT_TCP_HOST = "127.0.0.1"
"""TCP 端点绑定地址。固定回环，不得改为 0.0.0.0。"""

DEFAULT_TCP_PORT = 60500
"""TCP 端点端口。2026-09-19 裁定（取代原 27901）。"""

DEFAULT_TCP_ENDPOINT = f"tcp:{DEFAULT_TCP_HOST}:{DEFAULT_TCP_PORT}"
"""TCP 回环端点。用于无 AF_UNIX 的宿主，或 adb forward 到设备侧。"""

ENDPOINT_SCHEME_SEP = ":"
