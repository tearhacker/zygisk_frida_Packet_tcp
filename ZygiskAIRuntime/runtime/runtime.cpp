// Runtime Core 实现。
//
// 启动顺序（顺序错了会在 ART 未就绪时 Hook，直接崩进程）：
//
//     1. GumBackend::init()        Native 能力，可在任意线程
//     2. ArtBackend::init(env)     ART 能力，必须有 JNIEnv
//     3. Manager 就绪              Hook / Memory / Process
//     4. IPC 连接                  M2 接线
//
// 任一步失败都要如实返回 false，禁止部分成功后对外报成功。
//
// ⚠️ M1 骨架代码，尚未编译验证（本机无 NDK）。

#include "runtime.h"

#include <android/log.h>

#include "runtime/backend/art/art_backend.h"
#include "runtime/backend/gum/gum_backend.h"

#define ZAI_LOG_TAG "ZAI:Runtime"
#define ZAI_LOGI(...) __android_log_print(ANDROID_LOG_INFO, ZAI_LOG_TAG, __VA_ARGS__)
#define ZAI_LOGE(...) __android_log_print(ANDROID_LOG_ERROR, ZAI_LOG_TAG, __VA_ARGS__)

namespace zai::runtime {

using backend::ArtBackend;
using backend::GumBackend;

struct Runtime::Impl {
    RuntimeContext ctx;
    bool ready = false;
    HookManager hooks;
    MemoryManager memory;
    ProcessManager process;
};

Runtime &Runtime::instance() {
    static Runtime runtime;
    return runtime;
}

Runtime::Runtime() : impl_(new Impl()) {}
Runtime::~Runtime() { stop(); }

bool Runtime::start(const RuntimeContext &ctx) {
    if (impl_->ready) return true;
    impl_->ctx = ctx;

    if (!GumBackend::instance().init()) {
        ZAI_LOGE("native backend init failed, pkg=%s", ctx.package_name.c_str());
        // Native 都起不来就没有 Runtime，直接失败，不做降级。
        return false;
    }

    // TODO(M2): ART 初始化需要 JNIEnv。方案是在 JNI_OnLoad 里缓存 JavaVM，
    //           这里 GetEnv → 失败则 AttachCurrentThread → 用后 Detach。
    //           postAppSpecialize 传进来的 JNIEnv 在 detach 出去的线程里不可用。
    // ArtBackend::instance().init(env);

    impl_->ready = true;
    ZAI_LOGI("runtime ready: pkg=%s pid=%d", ctx.package_name.c_str(), ctx.pid);
    return true;
}

void Runtime::stop() {
    if (!impl_->ready) return;
    impl_->ready = false;

    ArtBackend::instance().shutdown();
    GumBackend::instance().shutdown();
    ZAI_LOGI("runtime stopped");
}

bool Runtime::is_ready() const { return impl_->ready; }

const RuntimeContext &Runtime::context() const { return impl_->ctx; }

HookManager &Runtime::hooks() { return impl_->hooks; }
MemoryManager &Runtime::memory() { return impl_->memory; }
ProcessManager &Runtime::process() { return impl_->process; }

}  // namespace zai::runtime
