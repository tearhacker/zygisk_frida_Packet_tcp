// Runtime Core：进程内唯一的 Runtime 门面。
//
// 分层（对应《docs/90-历史归档/真正的工作.txt.md》§六）：
//
//     Runtime (本类)
//        ├── HookManager ──────┐
//        ├── MemoryManager ────┼──→ Backend 层
//        └── ProcessManager ───┘        ├── GumBackend  (Frida-Gum, Native)
//                                       └── ArtBackend  (LSPlant,   ART)
//
// 上层（IPC / 命令分发）只认识 Runtime，不认识 Frida-Gum / LSPlant。
// 未来把 Native Backend 换成 ShadowHook / ByteHook，本文件一行都不用改。
//
// ⚠️ M1 骨架代码，尚未编译验证（本机无 NDK）。

#pragma once

#include <memory>

#include "runtime/manager/hook_manager.h"
#include "runtime/manager/memory_manager.h"
#include "runtime/manager/process_manager.h"
#include "runtime/runtime_context.h"

namespace zai::runtime {

class Runtime {
public:
    static Runtime &instance();

    // 启动 Runtime：初始化两个 Backend + 三个 Manager。
    // 返回 false 表示启动失败，调用方必须如实上报，禁止假装成功。
    bool start(const RuntimeContext &ctx);

    // 停止并释放全部 Hook 与内存占用。
    void stop();

    bool is_ready() const;

    const RuntimeContext &context() const;

    HookManager &hooks();
    MemoryManager &memory();
    ProcessManager &process();

private:
    Runtime();
    ~Runtime();
    Runtime(const Runtime &) = delete;
    Runtime &operator=(const Runtime &) = delete;

    struct Impl;
    std::unique_ptr<Impl> impl_;
};

}  // namespace zai::runtime
