// LSPlant 适配层实现 —— 唯一允许直接调用 lsplant:: API 的文件。
//
// 依赖形态：动态链接 `liblsplant.so`（LGPL-3.0 强制，不可静态嵌入）。
//
// ⚠️ M1 骨架代码，尚未编译验证（本机无 NDK）。

#include "lsplant_adapter.h"

#include <android/log.h>

#include <lsplant.hpp>

#define ZAI_LOG_TAG "ZAI:LSPlant"
#define ZAI_LOGI(...) __android_log_print(ANDROID_LOG_INFO, ZAI_LOG_TAG, __VA_ARGS__)
#define ZAI_LOGE(...) __android_log_print(ANDROID_LOG_ERROR, ZAI_LOG_TAG, __VA_ARGS__)

namespace zai::runtime::backend::lsplant_adapter {

namespace {
bool g_ready = false;
}

bool init(JNIEnv *env) {
    if (g_ready) return true;
    if (env == nullptr) return false;

    // lsplant::Init 需要 ART 的 symbol resolver，由 hook_info 传入。
    // TODO(M3): 按 17.x 之后的新签名补齐 InitInfo 构造（含 sdk level / debuggable）。
    // g_ready = lsplant::Init(env, info);
    (void) env;
    ZAI_LOGE("lsplant::Init not wired yet (M3)");
    return false;
}

bool ready() { return g_ready; }

bool hook(JNIEnv *env, jobject target_method, jobject hooker_object, jobject callback_method) {
    if (!g_ready || env == nullptr) return false;
    if (target_method == nullptr || hooker_object == nullptr || callback_method == nullptr) {
        return false;
    }

    // TODO(M3): 调 lsplant::Hook(env, target_method, hooker_object, callback_method)
    //           并区分返回 nullptr（失败）与返回原方法（成功）两种结果。
    return false;
}

bool deoptimize(JNIEnv *env, jobject method) {
    if (!g_ready || env == nullptr || method == nullptr) return false;
    // TODO(M3): lsplant::Deoptimize(env, method)
    return false;
}

bool unhook(JNIEnv *env, jobject target_method) {
    if (!g_ready || env == nullptr || target_method == nullptr) return false;
    // TODO(M3): lsplant::UnHook(env, target_method)
    return false;
}

}  // namespace zai::runtime::backend::lsplant_adapter
