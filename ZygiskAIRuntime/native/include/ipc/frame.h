// IPC 帧编解码 —— Android 侧。
//
// 线格式（与 PC 侧 ai_analyzer/protocol/frame.py 严格一致）：
//
//     ┌────────────────┬──────────────────────────┐
//     │ uint32 (4 字节) │ JSON payload (UTF-8)     │
//     │ 网络字节序 = 大端 │ 长度由前 4 字节给出        │
//     └────────────────┴──────────────────────────┘
//
// 依据：总基线 §10.1 传输 · 施工手册 §8 M0.2 Frame Codec。
//
// 边界必须全部处理（施工手册 M0.2 强制测试项）：
//   0 字节 / 1 字节 / 正常 / 大帧 / 非法长度 / 截断 / 多余数据 / 畸形 JSON
//
// 本层只管**字节**，不管 JSON 语义 —— 解析交给 ipc_server。

#pragma once

#include <cstdint>
#include <string>

namespace zai {
namespace ipc {

// 发送一帧。payload 超过 ZAI_FRAME_MAX_PAYLOAD 直接拒绝，不做分片。
// 失败时 err 给出原因（含 errno 文本），调用方负责上报。
bool send_frame(int fd, const std::string &payload, std::string *err);

// 接收一帧。连接对端关闭（recv 返回 0）也按失败处理，由调用方判定是否属正常退出。
bool recv_frame(int fd, std::string *out, std::string *err);

}  // namespace ipc
}  // namespace zai
