// Memory Manager 实现。
//
// ⚠️ M1 骨架代码，尚未编译验证（本机无 NDK）。

#include "memory_manager.h"

#include <android/log.h>

#include "runtime/backend/gum/gum_backend.h"

#define ZAI_LOG_TAG "ZAI:Memory"
#define ZAI_LOGE(...) __android_log_print(ANDROID_LOG_ERROR, ZAI_LOG_TAG, __VA_ARGS__)

namespace zai::runtime {

using backend::GumBackend;

bool MemoryManager::read(uint64_t address, std::vector<uint8_t> &out, uint64_t length) const {
    if (length == 0) return false;
    out.resize(static_cast<size_t>(length));
    return GumBackend::instance().read_memory(static_cast<uintptr_t>(address), out.data(),
                                              static_cast<size_t>(length));
}

WriteResult MemoryManager::write(uint64_t address, const std::vector<uint8_t> &data, bool granted) {
    WriteResult result;
    if (data.empty()) {
        result.reason = "empty payload";
        return result;
    }
    result.accepted = true;

    if (!granted) {
        result.reason = "write guard not granted";
        return result;  // accepted=true, executed=false —— 三级状态如实上报
    }

    result.executed = GumBackend::instance().write_memory(
        static_cast<uintptr_t>(address), data.data(), data.size());
    if (!result.executed) {
        result.reason = "gum_memory_write failed";
        ZAI_LOGE("write failed at 0x%llx", static_cast<unsigned long long>(address));
        return result;
    }

    result.verified = verify_write(address, data);
    if (!result.verified) result.reason = "read-back mismatch";
    return result;
}

bool MemoryManager::verify_write(uint64_t address, const std::vector<uint8_t> &expected) const {
    std::vector<uint8_t> actual;
    if (!read(address, actual, expected.size())) return false;
    return actual == expected;
}

std::vector<uint64_t> MemoryManager::search(const std::string &pattern, uint64_t max_results) const {
    (void) pattern;
    (void) max_results;
    // TODO(M4): 走 gum_memory_scan / gum_process_enumerate_ranges 逐区扫描。
    return {};
}

std::vector<MemoryRegion> MemoryManager::regions() const {
    std::vector<MemoryRegion> out;
    for (const auto &range : GumBackend::instance().list_ranges()) {
        MemoryRegion region;
        region.base = range.base;
        region.size = range.size;
        region.protection = range.protection;
        region.file_path = range.file_path;
        out.push_back(region);
    }
    return out;
}

}  // namespace zai::runtime
