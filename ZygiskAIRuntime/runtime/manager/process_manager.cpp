// Process Manager 实现。
//
// ⚠️ M1 骨架代码，尚未编译验证（本机无 NDK）。

#include "process_manager.h"

#include <dirent.h>
#include <unistd.h>

#include <fstream>

#include "runtime/backend/gum/gum_backend.h"

namespace zai::runtime {

using backend::GumBackend;

int ProcessManager::pid() const { return getpid(); }

std::vector<ThreadInfo> ProcessManager::threads() const {
    std::vector<ThreadInfo> out;
    // /proc/self/task 下每个子目录名即 TID。
    if (DIR *dir = opendir("/proc/self/task")) {
        while (struct dirent *entry = readdir(dir)) {
            const std::string name(entry->d_name);
            if (name == "." || name == "..") continue;
            ThreadInfo info;
            info.tid = std::stoi(name);
            std::ifstream comm("/proc/self/task/" + name + "/comm");
            if (comm) std::getline(comm, info.name);
            out.push_back(info);
        }
        closedir(dir);
    }
    return out;
}

std::vector<ModuleEntry> ProcessManager::modules() const {
    if (cached_modules_.empty()) {
        for (const auto &mod : GumBackend::instance().list_modules()) {
            ModuleEntry entry;
            entry.name = mod.name;
            entry.path = mod.path;
            entry.base = mod.base;
            entry.size = mod.size;
            cached_modules_.push_back(entry);
        }
    }
    return cached_modules_;
}

void ProcessManager::refresh_modules() { cached_modules_.clear(); }

}  // namespace zai::runtime
