// ART Backend 实现。
//
// ⚠️ M1 骨架代码，尚未编译验证（本机无 NDK）。

#include "art_backend.h"

#include <android/log.h>

#include "lsplant_adapter.h"

#define ZAI_LOG_TAG "ZAI:Art"
#define ZAI_LOGI(...) __android_log_print(ANDROID_LOG_INFO, ZAI_LOG_TAG, __VA_ARGS__)
#define ZAI_LOGW(...) __android_log_print(ANDROID_LOG_WARN, ZAI_LOG_TAG, __VA_ARGS__)

namespace zai::runtime::backend {

ArtBackend &ArtBackend::instance() {
    static ArtBackend backend;
    return backend;
}

bool ArtBackend::init(JNIEnv *env) {
    if (initialized_) return available_;
    initialized_ = true;

    // Android 8.x（SDK 26/27）上 LSPlant 存在已知 ART Hook 崩溃 issue。
    // TODO(M3): 从 runtime context 取 sdk_int 做真实分级，
    //           低版本走"禁用 ART Hook、仅 Native 可用"的降级路径。
    available_ = lsplant_adapter::init(env);

    if (!available_) {
        ZAI_LOGW("art backend unavailable, java hook disabled");
    } else {
        ZAI_LOGI("art backend ready");
    }
    return available_;
}

void ArtBackend::shutdown() {
    // LSPlant 的 Hook 随进程消亡，不做显式反初始化。
    available_ = false;
    initialized_ = false;
}

bool ArtBackend::available() const { return available_; }

bool ArtBackend::hook_method(JNIEnv *env, jobject target_method, jobject hooker, jobject callback) {
    if (!available_) return false;
    return lsplant_adapter::hook(env, target_method, hooker, callback);
}

bool ArtBackend::unhook_method(JNIEnv *env, jobject target_method) {
    if (!available_) return false;
    return lsplant_adapter::unhook(env, target_method);
}

bool ArtBackend::deoptimize(JNIEnv *env, jobject method) {
    if (!available_) return false;
    return lsplant_adapter::deoptimize(env, method);
}

}  // namespace zai::runtime::backend
