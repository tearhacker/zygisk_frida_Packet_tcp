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
#include <vector>

// zygisk.hpp 的 pltHookRegister 用到 dev_t / ino_t，但它只 include <jni.h>，
// 而该头自带 "DO NOT MODIFY ANY CODE IN THIS HEADER"（Magisk 官方 API 头）。
// 因此在使用方补齐 <sys/types.h>，不要去改第三方头文件。
#include <sys/types.h>

#include "zygisk.hpp"

namespace zai::bootstrap {

// 目标过滤配置。来自模块目录的 target 配置文件。
//
// ✅ 支持多包名：target.conf 每行一个包名（`#` 开头为注释，空行忽略）。
//    命中集合中任意一个包名即注入该进程 —— 用于「一个游戏主包 + 多个子进程 /
//    多开 / SDK 伴随进程」的场景，以及同时挂多个游戏。
//
// ⚠️ 时机约束：配置在 preAppSpecialize（进程 fork 出来的那一刻）读取一次，
//    之后不再重新读。所以改完 target.conf 必须**重启目标 App** 才生效，
//    运行中改文件对已存在的进程无效。这是 Zygisk 的固有约束。
struct TargetConfig {
    bool enabled = false;
    std::vector<std::string> packages;

    // 判定包名是否在目标集合内。数量级很小（通常 < 20），线性查找足够。
    bool matches(const std::string &package_name) const {
        for (const auto &p : packages) {
            if (p == package_name) return true;
        }
        return false;
    }
};

// ---------------------------------------------------------------------------
// App 进程 <-> root companion 的查询协议
//
//   请求：[uint32 进程名长度][进程名字节]
//   响应：单字节 '1' = 是目标，注入；'0' = 不是目标
//
// 为什么把判定放到 companion 侧（而不是 App 侧拉配置再自己比）：
//   1. 配置只有一份往返：App 侧不需要先把整个 target.conf 拉回来再解析；
//   2. companion 常驻在 root 守护进程里，可以缓存文件内容并对 mtime 做校验，
//      不必每个 App 启动都去 /data/adb 下读一次文件；
//   3. 目标判定规则将来要扩展（子进程后缀、UID 过滤等）时，只改一处。
//
// 为什么用长度前缀而不是"读到 EOF 为止"：
//   依赖 shutdown(fd, SHUT_WR) 的半关闭语义在不同 Android 版本/不同
//   socket 类型上行为并不完全一致，用显式长度更稳。
//   uint32 用原生字节序：zygiskd 的 32/64 位实例与对应位宽的 App 进程配对，
//   两端 ABI 一致，不存在大小端差异。
// ---------------------------------------------------------------------------
namespace companion {

// '1' / '0'，与上面的协议一致。
constexpr char kInject = '1';
constexpr char kSkip = '0';

}  // namespace companion

// onLoad：模块被 dlopen 后立即回调，只做句柄保存。
void on_load(zygisk::Api *api, JNIEnv *env);

// preAppSpecialize：仍持有 zygote 权限，可 connectCompanion / getModuleDir。
//
// 在这里完成两件事，且只在这里做：
//   1. 取进程名（此刻 args->nice_name 与 onLoad 给的 JNIEnv 都还可用）
//   2. 向 companion 问一次"要不要注入"
// 结果缓存到模块内部状态，供 postAppSpecialize 使用。
void pre_app_specialize(zygisk::AppSpecializeArgs *args);

// postAppSpecialize：已进入 App sandbox，这里才真正拉起 Runtime。
//
// ⚠️ 本函数不再触碰 args / JNIEnv，只用 pre 阶段缓存下来的判定结果与进程名。
//    原因见 bootstrap.cpp 中 read_process_name 的注释：post 阶段 JNI 的可用性
//    没有任何书面保证，而这段代码跑在每一个 App 进程里。
void post_app_specialize(const zygisk::AppSpecializeArgs *args);

// 判定当前进程是否需要注入。只按包名过滤，不做任何 Hook。
bool should_inject(const std::string &package_name);

// 向 root companion 查询"这个进程要不要注入"。
// 失败（连不上守护 / 协议异常）一律返回 false —— 宁可不注入，也不能误伤别的进程。
bool query_should_inject(zygisk::Api *api, const std::string &process_name);

// 从 AppSpecializeArgs 取进程名。
// ⚠️ 只在 preAppSpecialize 阶段调用（依赖 JNI）。
std::string read_process_name(const zygisk::AppSpecializeArgs *args);

}  // namespace zai::bootstrap
