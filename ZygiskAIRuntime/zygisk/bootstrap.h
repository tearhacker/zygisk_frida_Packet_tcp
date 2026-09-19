// Runtime Bootstrap：Zygisk 层与 Runtime Core 之间唯一的桥。
//
// 职责边界：
//   1. 目标过滤（哪些进程需要注入）
//   2. 在正确的时机拉起 Runtime
//   3. 把 Zygisk Api / JNIEnv 交给 Runtime
//
// 本层不允许出现 Hook、内存读写、协议编解码等任何具体分析逻辑。
//
// ⚠️ M1 骨架代码，尚未编译验证（本机无 NDK）。

#pragma once

#include <jni.h>

#include <string>

// zygisk.hpp 的 pltHookRegister 用到 dev_t / ino_t，但它只 include <jni.h>，
// 而该头自带 "DO NOT MODIFY ANY CODE IN THIS HEADER"（Magisk 官方 API 头）。
// 因此在使用方补齐 <sys/types.h>，不要去改第三方头文件。
#include <sys/types.h>

#include "zygisk.hpp"

namespace zai::bootstrap {

// 目标过滤配置。来自模块目录的 target 配置文件，尚未实现读取（M2）。
struct TargetConfig {
    bool enabled = false;
    std::string package_name;
};

// onLoad：模块被 dlopen 后立即回调，只做句柄保存。
void on_load(zygisk::Api *api, JNIEnv *env);

// preAppSpecialize：仍持有 zygote 权限，可 connectCompanion / getModuleDir。
// 在这里判定目标并决定是否保留本模块。
void pre_app_specialize(zygisk::AppSpecializeArgs *args);

// postAppSpecialize：已进入 App sandbox，这里才真正拉起 Runtime。
void post_app_specialize(const zygisk::AppSpecializeArgs *args);

// 判定当前进程是否需要注入。只按包名过滤，不做任何 Hook。
bool should_inject(const std::string &package_name);

// 读取模块目录下的目标配置。
// TODO(M2): 经 api->connectCompanion() 拿 module dir fd 后读取。
TargetConfig load_target_config(zygisk::Api *api);

// 从 AppSpecializeArgs 取进程名。
std::string read_process_name(const zygisk::AppSpecializeArgs *args);

}  // namespace zai::bootstrap
