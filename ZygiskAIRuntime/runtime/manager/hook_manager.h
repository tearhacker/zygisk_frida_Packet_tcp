// Hook Manager：Hook 生命周期的唯一管理者。
//
// 状态机（对应 ../../../docs/00-权威基线/项目总基线_v1.1.md §5.3）：
//
//     pending → active ⇄ disabled → removed
//                  └──→ failed
//
// 上层只调本类；Native 地址走 GumBackend，Java 方法走 ArtBackend，
// 两条路径在 hook_id 层面统一。
//
// ⚠️ M1 骨架代码，尚未编译验证（本机无 NDK）。

#pragma once

#include <cstdint>
#include <string>
#include <unordered_map>
#include <vector>

namespace zai::runtime {

enum class HookStatus {
    Pending,
    Active,
    Disabled,
    Removed,
    Failed,
};

enum class HookType {
    Native,
    Java,
};

struct HookRecord {
    std::string hook_id;
    std::string session_id;
    HookType type = HookType::Native;
    std::string module;    // Native: libxxx.so / Java: 类名
    std::string symbol;    // Native: 符号名 / Java: 方法名
    uint64_t address = 0;  // Native 专用
    HookStatus status = HookStatus::Pending;
    std::string error;     // Failed 时必须给出原因，禁止空错误
};

class HookManager {
public:
    // create 只登记并返回 pending，真正 attach 成功后才转 Active。
    // 不允许 create 直接返回成功 —— 那是 Fake Success。
    HookRecord create(const std::string &session_id, HookType type,
                      const std::string &module, const std::string &symbol,
                      uint64_t address);

    bool enable(const std::string &hook_id);
    bool disable(const std::string &hook_id);
    bool remove(const std::string &hook_id);

    // info 找不到时返回 nullptr，不返回一条假记录。
    const HookRecord *info(const std::string &hook_id) const;
    std::vector<HookRecord> list() const;

private:
    std::unordered_map<std::string, HookRecord> records_;
};

}  // namespace zai::runtime
