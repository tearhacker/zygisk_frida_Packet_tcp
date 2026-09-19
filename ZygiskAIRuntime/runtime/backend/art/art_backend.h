// ART Backend —— Java / ART 层 Hook 能力。
//
// 职责边界（与 Native Backend 严格区分）：
//
//     Frida-Gum  → Native / C / C++ 层
//     LSPlant    → Java / ART 层
//
// 本类不碰任何 native 地址；native 侧一律走 GumBackend。
//
// 降级纪律：LSPlant 在 Android 8.x 存在已知 ART Hook 崩溃 issue，
// 必须按 SDK 级别分级降级（见 ../../../../docs/00-权威基线/项目总基线_v1.1.md §16.2 纪律 2）。
//
// ⚠️ M1 骨架代码，尚未编译验证（本机无 NDK）。

#pragma once

#include <jni.h>

namespace zai::runtime::backend {

class ArtBackend {
public:
    static ArtBackend &instance();

    // 需要 JNIEnv；在 Runtime 线程中调用，不能占用 specialize 线程。
    bool init(JNIEnv *env);
    void shutdown();

    // SDK 分级降级后的可用状态：不可用时必须如实返回 false，不得假装可用。
    bool available() const;

    bool hook_method(JNIEnv *env, jobject target_method, jobject hooker, jobject callback);
    bool unhook_method(JNIEnv *env, jobject target_method);
    bool deoptimize(JNIEnv *env, jobject method);

private:
    ArtBackend() = default;

    bool initialized_ = false;
    bool available_ = false;
};

}  // namespace zai::runtime::backend
