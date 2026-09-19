// Process Manager：进程 / 线程 / 模块的事实来源。
//
// 只提供"查询"，不提供"控制"（起停线程、kill 进程属于控制面，M5 再定）。
//
// ⚠️ M1 骨架代码，尚未编译验证（本机无 NDK）。

#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace zai::runtime {

struct ThreadInfo {
    int tid = -1;
    std::string name;
};

struct ModuleEntry {
    std::string name;
    std::string path;
    uint64_t base = 0;
    uint64_t size = 0;
};

class ProcessManager {
public:
    int pid() const;
    std::vector<ThreadInfo> threads() const;
    std::vector<ModuleEntry> modules() const;
    void refresh_modules();

private:
    mutable std::vector<ModuleEntry> cached_modules_;
};

}  // namespace zai::runtime
