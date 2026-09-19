// IPC 协议常量 —— Android 侧镜像。
//
// ⚠️ 本文件是 `mcp/protocol/constants.py` 的**镜像**，不是独立来源。
//    唯一常量源是 Python 侧；本文件必须与其逐项一致。
//
//    一致性由 `tests/protocol/test_constants.py` 强制校验：
//    测试会解析本文件的 #define 与 enum，和 Python 常量逐一比对，
//    任何一项不一致 → 测试失败。
//
// 依据：总基线 §10 Protocol Layer v1 · 附录 A 协议常量单一源
//      施工手册 §8 M0.1 constants
//
// 纪律：新增常量前先确认 Python 侧是否已有定义；改这里之前先改 Python 侧。

#pragma once

#include <cstdint>

namespace zai {
namespace protocol {

// ---------------------------------------------------------------------------
// 协议版本
// ---------------------------------------------------------------------------

#define ZAI_PROTOCOL_VERSION        "1.0"
#define ZAI_SERVER_NAME             "ai-analyzer"
#define ZAI_SERVER_VERSION          "1.0.0"
#define ZAI_CLIENT_NAME             "mcp-server"
#define ZAI_CLIENT_VERSION          "1.0.0"

// ---------------------------------------------------------------------------
// 帧格式
// ---------------------------------------------------------------------------

// 帧头字节数：4 字节 uint32，payload 长度，网络字节序（大端）。
#define ZAI_FRAME_HEADER_SIZE       4

// 单帧 payload 上限 8 MiB。超过视为非法帧。
#define ZAI_FRAME_MAX_PAYLOAD       (8 * 1024 * 1024)

// ---------------------------------------------------------------------------
// 超时与心跳（单位：秒）
// ---------------------------------------------------------------------------

#define ZAI_HEARTBEAT_INTERVAL      5
#define ZAI_HEARTBEAT_TIMEOUT       30
#define ZAI_FAST_COMMAND_TIMEOUT    10
#define ZAI_JOB_COMMAND_TIMEOUT     300
#define ZAI_SESSION_IDLE_TIMEOUT    600
#define ZAI_CONNECT_TIMEOUT         10

// ---------------------------------------------------------------------------
// 重连退避（单位：秒，最后一项为上限）
// ---------------------------------------------------------------------------

#define ZAI_RECONNECT_BACKOFF       { 1, 2, 4, 8, 16, 30 }
#define ZAI_RECONNECT_BACKOFF_MAX   30

// 重连必须使所有 session_id 立即失效。总基线 §9.4 冻结项。
#define ZAI_SESSION_ID_INVALIDATE_ON_RECONNECT  1

// ---------------------------------------------------------------------------
// 写操作闸门
// ---------------------------------------------------------------------------

// Write Guard 的 confirm 默认值：默认不确认。
#define ZAI_WRITE_CONFIRM_DEFAULT   0

// ---------------------------------------------------------------------------
// 工具面
// ---------------------------------------------------------------------------

#define ZAI_MAX_RESPONSE_TOKENS     4096
#define ZAI_MAX_RESIDENT_TOOLS      25
#define ZAI_MAX_TOOLS_HARD_LIMIT    45

// ---------------------------------------------------------------------------
// 消息类型
// ---------------------------------------------------------------------------

enum class MessageType : int {
    HELLO     = 1,
    HELLO_ACK = 2,
    READY     = 3,
    REQUEST   = 4,
    RESPONSE  = 5,
    EVENT     = 6,
    PING      = 7,
    PONG      = 8,
    ERROR     = 9,
};

// 线上表示用字符串，与 Python 侧 MessageType.value 一致。
#define ZAI_MSG_HELLO       "HELLO"
#define ZAI_MSG_HELLO_ACK   "HELLO_ACK"
#define ZAI_MSG_READY       "READY"
#define ZAI_MSG_REQUEST     "REQUEST"
#define ZAI_MSG_RESPONSE    "RESPONSE"
#define ZAI_MSG_EVENT       "EVENT"
#define ZAI_MSG_PING        "PING"
#define ZAI_MSG_PONG        "PONG"
#define ZAI_MSG_ERROR       "ERROR"

// ---------------------------------------------------------------------------
// 命令分级
// ---------------------------------------------------------------------------

enum class CommandClass : int {
    FAST = 0,
    JOB  = 1,
};

// ---------------------------------------------------------------------------
// Session 状态
// ---------------------------------------------------------------------------

enum class SessionState : int {
    CREATED       = 1,
    STARTING      = 2,
    RUNTIME_READY = 3,
    NETWORK_READY = 4,
    RUNNING       = 5,
    PAUSED        = 6,
    STOPPING      = 7,
    CLOSED        = 8,
    DEGRADED      = 9,
    FAILED        = 10,
    ERROR         = 11,
};

#define ZAI_SESSION_STATE_CREATED        "CREATED"
#define ZAI_SESSION_STATE_STARTING       "STARTING"
#define ZAI_SESSION_STATE_RUNTIME_READY  "RUNTIME_READY"
#define ZAI_SESSION_STATE_NETWORK_READY  "NETWORK_READY"
#define ZAI_SESSION_STATE_RUNNING        "RUNNING"
#define ZAI_SESSION_STATE_PAUSED         "PAUSED"
#define ZAI_SESSION_STATE_STOPPING       "STOPPING"
#define ZAI_SESSION_STATE_CLOSED         "CLOSED"
#define ZAI_SESSION_STATE_DEGRADED       "DEGRADED"
#define ZAI_SESSION_STATE_FAILED         "FAILED"
#define ZAI_SESSION_STATE_ERROR          "ERROR"

// ---------------------------------------------------------------------------
// 链路状态
// ---------------------------------------------------------------------------

enum class LinkState : int {
    DISCONNECTED = 0,
    CONNECTING   = 1,
    CONNECTED    = 2,
    DEGRADED     = 3,
};

// ---------------------------------------------------------------------------
// 执行三态（禁止 Fake Success）
// ---------------------------------------------------------------------------

enum class ExecutionState : int {
    ACCEPTED = 0,
    EXECUTED = 1,
    VERIFIED = 2,
};

// ---------------------------------------------------------------------------
// HTTPS 五级能力状态（禁止跨级推断）
// ---------------------------------------------------------------------------

enum class HttpsCapability : int {
    CAPTURED      = 0,
    DECODED       = 1,
    DECRYPTED     = 2,
    INTERCEPTABLE = 3,
    MODIFIABLE    = 4,
};

// ---------------------------------------------------------------------------
// 错误码（稳定契约，发布后只增不改义）
// ---------------------------------------------------------------------------

#define ZAI_ERR_PROTOCOL_VERSION   "ERROR_PROTOCOL_VERSION"
#define ZAI_ERR_BAD_ARGS           "E_BAD_ARGS"
#define ZAI_ERR_UNKNOWN_CMD        "E_UNKNOWN_CMD"
#define ZAI_ERR_MALFORMED_FRAME    "E_MALFORMED_FRAME"
#define ZAI_ERR_NOT_READY          "E_NOT_READY"
#define ZAI_ERR_SESSION_STALE      "E_SESSION_STALE"
#define ZAI_ERR_READ_FAILED        "E_READ_FAILED"
#define ZAI_ERR_WRITE_FAILED       "E_WRITE_FAILED"
#define ZAI_ERR_MAP_STALE          "E_MAP_STALE"
#define ZAI_ERR_TIMEOUT            "E_TIMEOUT"
#define ZAI_ERR_CANCELLED          "E_CANCELLED"
#define ZAI_ERR_NOT_FOUND          "E_NOT_FOUND"
#define ZAI_ERR_PERMISSION_DENIED  "E_PERMISSION_DENIED"
#define ZAI_ERR_INTERNAL           "E_INTERNAL"

// ---------------------------------------------------------------------------
// 默认 IPC 端点
// ---------------------------------------------------------------------------

#define ZAI_DEFAULT_SOCKET_PATH     "/data/local/tmp/ai-analyzer/analyzer.sock"

}  // namespace protocol
}  // namespace zai
