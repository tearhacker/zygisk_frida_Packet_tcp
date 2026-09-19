// 进程内日志。统一走 android logcat，tag 前缀 ZAI:。
//
// ⚠️ M1 骨架代码，尚未编译验证（本机无 NDK）。

#pragma once

#include <android/log.h>

#define ZAI_LOG_TAG "ZAI"
#define ZAI_LOGV(...) __android_log_print(ANDROID_LOG_VERBOSE, ZAI_LOG_TAG, __VA_ARGS__)
#define ZAI_LOGD(...) __android_log_print(ANDROID_LOG_DEBUG, ZAI_LOG_TAG, __VA_ARGS__)
#define ZAI_LOGI(...) __android_log_print(ANDROID_LOG_INFO, ZAI_LOG_TAG, __VA_ARGS__)
#define ZAI_LOGW(...) __android_log_print(ANDROID_LOG_WARN, ZAI_LOG_TAG, __VA_ARGS__)
#define ZAI_LOGE(...) __android_log_print(ANDROID_LOG_ERROR, ZAI_LOG_TAG, __VA_ARGS__)

namespace zai::common {

// 把错误码转成可读文本，供错误分层上报使用。
const char *error_code_to_text(int code);

}  // namespace zai::common
