// Runtime 侧 IPC 服务端 —— M2 真机闭环的第 2 段。
//
// 职责：在目标进程内监听回环端口，接受 PC 侧 ai_analyzer 的连接，
//       完成 HELLO → HELLO_ACK → READY 握手，处理 PING/PONG 心跳与 REQUEST/RESPONSE。
//
// ⚠️ 两个硬约束：
//
//   1. **只能绑定回环**。Runtime 跑在带 root 能力的进程里，监听 0.0.0.0
//      等于把本机内存读写权限开给同一网段的任何人。真机接入走 PC 侧
//      `adb forward tcp:60500 tcp:60500`，不需要对外暴露。
//
//   2. **禁止 Fake Success**。已实现的命令返回真实数据；未实现的命令如实报
//      E_NOT_READY，绝不编造。capabilities 也要如实上报 false ——
//      PC 侧 Tool Surface 会据此摘除对应工具，而不是等 AI 调了才报错。
//
// 依据：总基线 §10 Protocol Layer v1 · 施工手册 §8

#pragma once

#include <atomic>
#include <cstdint>
#include <string>

namespace zai {
namespace ipc {

// 由 Runtime 在启动 IPC 之前注入上下文。
// 刻意不 include runtime 头：本层只接受数据，不反向依赖 Runtime，
// 避免 Zygisk 层 / Runtime 层 / IPC 层出现循环依赖。
void set_context(const std::string &package, bool gum_ready);

// 启动监听线程。非阻塞，返回 true 只代表监听已建立。
bool start(int port);

// 停止监听并关闭所有连接。可重复调用。
void stop();

// 监听线程是否还在跑。
bool is_running();

// 当前监听端口（未启动时返回 0）。
int port();

}  // namespace ipc
}  // namespace zai
