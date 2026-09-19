// Native Backend —— Frida-Gum 适配层。
//
// 这是**整个项目里唯一允许出现 gum_* 调用的地方**。
// 上层（HookManager / MemoryManager）只见本文件的接口，不见 Frida-Gum。
//
// 头文件刻意不 include <gum/gum.h>：
//   Frida-Gum 需要 meson 先构建出 gum.h 及依赖，头文件暴露会污染所有 TU 的编译依赖。
//
// ⚠️ M1 骨架代码，尚未编译验证（本机无 NDK，Frida-Gum 未构建）。

#pragma once

#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

namespace zai::runtime::backend {

struct ModuleInfo {
    std::string name;
    std::string path;
    uintptr_t base = 0;
    size_t size = 0;
};

struct RangeInfo {
    uintptr_t base = 0;
    size_t size = 0;
    std::string protection;  // rwxp
    std::string file_path;
};

class GumBackend {
public:
    static GumBackend &instance();

    // gum_init / gum_deinit 必须由同一个 Backend 配对调用。
    bool init();
    void shutdown();
    bool ready() const;

    // --- Hook ---
    // attach 后 *original 指向跳板，可回调原函数。
    bool attach(void *address, void *replacement, void **original);
    bool detach(void *address);

    // --- Memory ---
    // read_memory / write_memory 是最底层原语，不自带任何门禁；
    // 门禁由上层 MemoryManager 按 Write Guard 规则施加。
    bool read_memory(uintptr_t address, void *buffer, size_t length) const;
    bool write_memory(uintptr_t address, const void *buffer, size_t length);

    // --- Module / Range ---
    std::vector<ModuleInfo> list_modules();
    std::vector<RangeInfo> list_ranges();
    void *resolve_symbol(const std::string &module_name, const std::string &symbol);

private:
    GumBackend();
    ~GumBackend();
    GumBackend(const GumBackend &) = delete;
    GumBackend &operator=(const GumBackend &) = delete;

    struct Impl;
    std::unique_ptr<Impl> impl_;
};

}  // namespace zai::runtime::backend
