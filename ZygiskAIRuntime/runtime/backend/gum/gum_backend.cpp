// Native Backend —— Frida-Gum 适配层实现。
//
// 【唯一允许出现 gum_* 调用的文件】
//
// 构建前提（M1 阻塞项）：
//   1. Frida-Gum 必须先由 build/scripts/build-gum.sh 用 meson 交叉编译出 libgum.a
//   2. 本机无 NDK / CMake，当前无法编译验证
//
// Frida-Gum 只能源码构建：devkit 仅由 github.com/frida/frida/releases/download/ 分发，
// 本机代理拒绝该域名。

#include "gum_backend.h"

#include <android/log.h>

#include <gum/gum.h>
#include <gum/guminterceptor.h>
#include <gum/gummodulemap.h>
#include <gum/gumprocess.h>

#include <cstring>

#define ZAI_LOG_TAG "ZAI:Gum"
#define ZAI_LOGI(...) __android_log_print(ANDROID_LOG_INFO, ZAI_LOG_TAG, __VA_ARGS__)
#define ZAI_LOGE(...) __android_log_print(ANDROID_LOG_ERROR, ZAI_LOG_TAG, __VA_ARGS__)

namespace zai::runtime::backend {

struct GumBackend::Impl {
    bool initialized = false;
    GumInterceptor *interceptor = nullptr;
    GumModuleMap *module_map = nullptr;
};

GumBackend::GumBackend() : impl_(new Impl()) {}
GumBackend::~GumBackend() { shutdown(); }

GumBackend &GumBackend::instance() {
    static GumBackend backend;
    return backend;
}

bool GumBackend::init() {
    if (impl_->initialized) return true;

    gum_init();
    impl_->interceptor = gum_interceptor_obtain();
    impl_->module_map = gum_module_map_new();
    impl_->initialized = true;

    ZAI_LOGI("gum initialized (interceptor=%p)", impl_->interceptor);
    return true;
}

void GumBackend::shutdown() {
    if (!impl_->initialized) return;

    if (impl_->module_map != nullptr) {
        g_object_unref(impl_->module_map);
        impl_->module_map = nullptr;
    }
    if (impl_->interceptor != nullptr) {
        g_object_unref(impl_->interceptor);
        impl_->interceptor = nullptr;
    }
    gum_deinit();
    impl_->initialized = false;
}

bool GumBackend::ready() const { return impl_->initialized; }

bool GumBackend::attach(void *address, void *replacement, void **original) {
    if (!impl_->initialized || impl_->interceptor == nullptr) return false;

    GumInvocationListener *listener = nullptr;  // 由调用方通过 GUM_ATTACH 回调构造

    // 17.18.0 的签名是
    //   gum_interceptor_attach (GumInterceptor * self, gpointer target,
    //                           GumInvocationListener * listener,
    //                           const GumAttachOptions * options)
    // 第 4 个参数在 17.x 变成了 **options**（可传 NULL），
    // 不再是旧版的 `void **original_trampoline`。
    // 原函数地址改由 GumInvocationListener 的 on_enter / on_leave 回调给出。
    const GumAttachReturn ret = gum_interceptor_attach(
        impl_->interceptor, address, listener, nullptr);
    (void) replacement;
    // TODO(M3): 经 listener 回调取到原函数地址后回填。
    if (original != nullptr) *original = nullptr;

    if (ret != GUM_ATTACH_OK) {
        ZAI_LOGE("gum_interceptor_attach failed at %p (ret=%d)", address, static_cast<int>(ret));
        return false;
    }
    return true;
}

bool GumBackend::detach(void *address) {
    if (!impl_->initialized || impl_->interceptor == nullptr) return false;

    GumInvocationListener *listener = nullptr;  // TODO(M3): 维护 address -> listener 映射
    gum_interceptor_detach(impl_->interceptor, listener);
    (void) address;
    return true;
}

bool GumBackend::read_memory(uintptr_t address, void *buffer, size_t length) const {
    if (!impl_->initialized || buffer == nullptr || length == 0) return false;

    // 17.18.0 的 gum_memory_read 签名是
    //   guint8 * gum_memory_read (gconstpointer address, gsize len, gsize * n_bytes_read)
    // 注意两点（骨架代码原来都写错了，源码构建时才暴露）：
    //   1. 返回的是**新分配的缓冲区**（调用方负责 g_free），不是 gboolean 成功标志；
    //   2. 参数顺序是 (address, len, n_bytes_read)，**没有**调用方的 buffer 参数。
    gsize n_read = 0;
    guint8 *data = gum_memory_read(reinterpret_cast<gconstpointer>(address),
                                   static_cast<gsize>(length), &n_read);
    if (data == nullptr) return false;

    const bool complete = (n_read == static_cast<gsize>(length));
    if (n_read > 0) {
        std::memcpy(buffer, data, static_cast<size_t>(n_read));
    }
    g_free(data);
    return complete;
}

bool GumBackend::write_memory(uintptr_t address, const void *buffer, size_t length) {
    if (!impl_->initialized || buffer == nullptr || length == 0) return false;

    // 只负责"写成功"，是否允许写由 MemoryManager 的 Write Guard 决定。
    return gum_memory_write(reinterpret_cast<gpointer>(address),
                            static_cast<const guint8 *>(buffer),
                            static_cast<gsize>(length)) != FALSE;
}

std::vector<ModuleInfo> GumBackend::list_modules() {
    std::vector<ModuleInfo> out;
    if (!impl_->initialized || impl_->module_map == nullptr) return out;

    // gum_module_map_foreach 是 C 回调，这里用 lambda 捕获 out。
    // TODO(M3): 确认 17.18.0 的遍历签名后补齐实现。
    return out;
}

std::vector<RangeInfo> GumBackend::list_ranges() {
    std::vector<RangeInfo> out;
    if (!impl_->initialized) return out;

    // TODO(M4): 走 gum_process_enumerate_ranges 或解析 /proc/self/maps。
    return out;
}

void *GumBackend::resolve_symbol(const std::string &module_name, const std::string &symbol) {
    if (!impl_->initialized) return nullptr;

    // 17.18.0 起符号查找是 **OO 风格**：先拿 GumModule*，再在它上面查符号。
    //   GumModule * gum_process_find_module_by_name (const gchar * name)
    //   GumAddress  gum_module_find_symbol_by_name  (GumModule * self, const gchar * symbol)
    // 旧代码按"全局函数名 + 模块名"调用，签名不存在，源码构建时才暴露。
    GumModule *module = gum_process_find_module_by_name(module_name.c_str());
    if (module == nullptr) return nullptr;

    const GumAddress addr = gum_module_find_symbol_by_name(module, symbol.c_str());
    g_object_unref(module);  // find_module_by_name 返回的是 owned reference

    if (addr == 0) return nullptr;
    return reinterpret_cast<void *>(addr);
}

}  // namespace zai::runtime::backend
