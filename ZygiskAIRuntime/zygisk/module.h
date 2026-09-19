// Zygisk 模块类声明。
//
// Zygisk 在本项目中的定位是 **Entry / Bootstrap**，不是分析逻辑载体：
//   - preAppSpecialize  仍持有 zygote 权限 → 读配置、做目标过滤
//   - postAppSpecialize 已进入 App sandbox → 拉起 Runtime
//
// 除这两件事以外的任何分析逻辑都不允许写进本层。
//
// ⚠️ M1 骨架代码，尚未编译验证（本机无 NDK）。

#pragma once

#include <jni.h>

// zygisk.hpp 的 pltHookRegister 用到 dev_t / ino_t，但它只 include <jni.h>，
// 而该头自带 "DO NOT MODIFY ANY CODE IN THIS HEADER"（Magisk 官方 API 头）。
// 因此每个包含它的地方都要先补 <sys/types.h>（bootstrap.h 里同样处理过）。
#include <sys/types.h>

#include "zygisk.hpp"

namespace zai {

class AIRuntimeModule : public zygisk::ModuleBase {
public:
    void onLoad(zygisk::Api *api, JNIEnv *env) override;
    void preAppSpecialize(zygisk::AppSpecializeArgs *args) override;
    void postAppSpecialize(const zygisk::AppSpecializeArgs *args) override;
    void preServerSpecialize(zygisk::ServerSpecializeArgs *args) override;
    void postServerSpecialize(const zygisk::ServerSpecializeArgs *args) override;

private:
    zygisk::Api *api_ = nullptr;
    JNIEnv *env_ = nullptr;
};

}  // namespace zai
