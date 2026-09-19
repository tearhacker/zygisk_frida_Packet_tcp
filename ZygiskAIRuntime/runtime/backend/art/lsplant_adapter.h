// LSPlant 适配层 —— 唯一允许直接调用 lsplant:: API 的地方。
//
// LSPlant 是 **LGPL-3.0**，构建时必须产出独立的 `liblsplant.so` 并动态链接，
// 禁止静态嵌入（见 ../../../../docs/00-权威基线/LICENSES.md 约束 #1）。
//
// ⚠️ M1 骨架代码，尚未编译验证（本机无 NDK）。

#pragma once

#include <jni.h>

namespace zai::runtime::backend::lsplant_adapter {

// lsplant::Init 的包装。需要 JNIEnv 与 ClassLoader 才能解析 ART 符号。
bool init(JNIEnv *env);

// 已初始化则返回 true。
bool ready();

// Hook 一个 Java 方法。hooker_object 由调用方持有强引用，不可在 Hook 期间被 GC。
bool hook(JNIEnv *env, jobject target_method, jobject hooker_object, jobject callback_method);

// 反优化：把已 JIT/AOT 编译的方法打回解释执行，使 Hook 生效。
bool deoptimize(JNIEnv *env, jobject method);

// 还原目标方法。
bool unhook(JNIEnv *env, jobject target_method);

}  // namespace zai::runtime::backend::lsplant_adapter
