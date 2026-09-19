// Zygisk 模块类实现。所有逻辑委托给 bootstrap，本文件不做任何分析动作。
//
// ⚠️ M1 骨架代码，尚未编译验证（本机无 NDK）。

#include "module.h"

#include <android/log.h>

#include "bootstrap.h"

#define ZAI_LOG_TAG "ZAI:Zygisk"
#define ZAI_LOGI(...) __android_log_print(ANDROID_LOG_INFO, ZAI_LOG_TAG, __VA_ARGS__)
#define ZAI_LOGW(...) __android_log_print(ANDROID_LOG_WARN, ZAI_LOG_TAG, __VA_ARGS__)

namespace zai {

void AIRuntimeModule::onLoad(zygisk::Api *api, JNIEnv *env) {
    api_ = api;
    env_ = env;
    bootstrap::on_load(api, env);
}

void AIRuntimeModule::preAppSpecialize(zygisk::AppSpecializeArgs *args) {
    if (api_ == nullptr || args == nullptr) return;
    bootstrap::pre_app_specialize(args);
}

void AIRuntimeModule::postAppSpecialize(const zygisk::AppSpecializeArgs *args) {
    if (args == nullptr) return;
    bootstrap::post_app_specialize(args);
}

void AIRuntimeModule::preServerSpecialize(zygisk::ServerSpecializeArgs *) {
    // system_server 不在分析范围内，明确不注入。
    ZAI_LOGI("system_server skipped");
    if (api_ != nullptr) {
        api_->setOption(zygisk::DLCLOSE_MODULE_LIBRARY);
    }
}

void AIRuntimeModule::postServerSpecialize(const zygisk::ServerSpecializeArgs *) {
    ZAI_LOGW("system_server should never reach postServerSpecialize");
}

}  // namespace zai
