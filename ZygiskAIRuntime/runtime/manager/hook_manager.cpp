// Hook Manager 实现。
//
// ⚠️ M1 骨架代码，尚未编译验证（本机无 NDK）。

#include "hook_manager.h"

#include <mutex>

namespace zai::runtime {

namespace {
std::mutex g_mutex;
uint64_t g_seq = 0;
}  // namespace

HookRecord HookManager::create(const std::string &session_id, HookType type,
                               const std::string &module, const std::string &symbol,
                               uint64_t address) {
    std::lock_guard<std::mutex> guard(g_mutex);

    HookRecord record;
    record.hook_id = "hook_" + std::to_string(++g_seq);
    record.session_id = session_id;
    record.type = type;
    record.module = module;
    record.symbol = symbol;
    record.address = address;
    record.status = HookStatus::Pending;

    records_[record.hook_id] = record;
    return record;
}

bool HookManager::enable(const std::string &hook_id) {
    std::lock_guard<std::mutex> guard(g_mutex);
    auto it = records_.find(hook_id);
    if (it == records_.end()) return false;

    // TODO(M3): 按 type 分发到 GumBackend::attach 或 ArtBackend::hook_method，
    //           只有真正 attach 成功才置 Active，失败置 Failed 并填 error。
    it->second.status = HookStatus::Failed;
    it->second.error = "backend not wired (M3)";
    return false;
}

bool HookManager::disable(const std::string &hook_id) {
    std::lock_guard<std::mutex> guard(g_mutex);
    auto it = records_.find(hook_id);
    if (it == records_.end()) return false;

    it->second.status = HookStatus::Disabled;
    return true;
}

bool HookManager::remove(const std::string &hook_id) {
    std::lock_guard<std::mutex> guard(g_mutex);
    auto it = records_.find(hook_id);
    if (it == records_.end()) return false;

    // TODO(M3): 先 detach 再置 Removed。
    it->second.status = HookStatus::Removed;
    return true;
}

const HookRecord *HookManager::info(const std::string &hook_id) const {
    std::lock_guard<std::mutex> guard(g_mutex);
    auto it = records_.find(hook_id);
    return it == records_.end() ? nullptr : &it->second;
}

std::vector<HookRecord> HookManager::list() const {
    std::lock_guard<std::mutex> guard(g_mutex);
    std::vector<HookRecord> out;
    out.reserve(records_.size());
    for (const auto &entry : records_) out.push_back(entry.second);
    return out;
}

}  // namespace zai::runtime
