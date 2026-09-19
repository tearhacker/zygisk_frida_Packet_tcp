// Runtime Bootstrap 实现。
//
// 时机纪律（违反会直接导致 Hook 失效或进程崩溃）：
//   - preAppSpecialize  仍持有 zygote 权限：读配置 + 目标过滤
//   - postAppSpecialize 已进入 App sandbox：这里才拉起 Runtime
//   - DLCLOSE_MODULE_LIBRARY 只能在"确定不注入且未 Hook 任何函数"时使用
//
// ⚠️ M1 骨架代码，尚未编译验证（本机无 NDK）。

#include "bootstrap.h"

#include <android/log.h>
#include <unistd.h>

#include <cstdio>
#include <string>
#include <thread>

#include "runtime/runtime.h"

#define ZAI_LOG_TAG "ZAI:Bootstrap"
#define ZAI_LOGI(...) __android_log_print(ANDROID_LOG_INFO, ZAI_LOG_TAG, __VA_ARGS__)
#define ZAI_LOGW(...) __android_log_print(ANDROID_LOG_WARN, ZAI_LOG_TAG, __VA_ARGS__)
#define ZAI_LOGE(...) __android_log_print(ANDROID_LOG_ERROR, ZAI_LOG_TAG, __VA_ARGS__)

namespace zai::bootstrap {

namespace {

zygisk::Api *g_api = nullptr;
JNIEnv *g_env = nullptr;
TargetConfig g_target;

std::string jstring_to_utf8(JNIEnv *env, jstring value) {
    if (env == nullptr || value == nullptr) return {};
    const char *raw = env->GetStringUTFChars(value, nullptr);
    if (raw == nullptr) return {};
    std::string out(raw);
    env->ReleaseStringUTFChars(value, raw);
    return out;
}

}  // namespace

void on_load(zygisk::Api *api, JNIEnv *env) {
    g_api = api;
    g_env = env;
    ZAI_LOGI("module loaded (api v%d)", ZYGISK_API_VERSION);
}

// 兜底取进程名：读 /proc/self/cmdline（以 NUL 分隔，取第一段）。
// 不需要 JNI，因此永远安全 —— 最坏情况是拿不到名字，不会崩。
std::string read_cmdline_name() {
    std::FILE *f = std::fopen("/proc/self/cmdline", "re");
    if (f == nullptr) return {};
    char buf[512] = {0};
    const size_t n = std::fread(buf, 1, sizeof(buf) - 1, f);
    std::fclose(f);
    if (n == 0) return {};
    const std::string raw(buf, n);
    const size_t zero = raw.find('\0');
    return zero == std::string::npos ? raw : raw.substr(0, zero);
}

std::string read_process_name(const zygisk::AppSpecializeArgs *args) {
    // 主路径：args->nice_name，最准确。
    //
    // ⚠️ 它依赖 g_env（onLoad 时保存的 zygote JNIEnv）。Zygisk API v2 起
    //    不再给 specialize 回调传 JNIEnv，而 specialize 期间 JNI 是否仍可用
    //    并没有书面保证。若 g_env 此时已失效，GetStringUTFChars 会直接崩，
    //    而这段代码跑在**每一个 App 进程**里 —— 后果是整机的 App 都起不来。
    //    所以拿不到 nice_name 时不再硬走 JNI，退化到读 /proc/self/cmdline：
    //    退化最坏只是"名字不对 → 不匹配 → 不注入"，属于安全方向。
    if (args != nullptr) {
        const std::string name = jstring_to_utf8(g_env, args->nice_name);
        if (!name.empty()) return name;
    }
    return read_cmdline_name();
}

std::string trim(const std::string &s) {
    const char *ws = " \t\r\n";
    const size_t begin = s.find_first_not_of(ws);
    if (begin == std::string::npos) return {};
    const size_t end = s.find_last_not_of(ws);
    return s.substr(begin, end - begin + 1);
}

// 从 companion 的 socket 读回配置。stream socket 不保证一次读完，所以循环读到换行。
std::string read_config_from(int fd) {
    std::string out;
    char chunk[256];
    while (out.size() < sizeof(chunk) * 4) {
        const ssize_t n = read(fd, chunk, sizeof(chunk));
        if (n <= 0) break;
        out.append(chunk, static_cast<size_t>(n));
        if (out.find('\n') != std::string::npos) break;
    }
    return out;
}

TargetConfig load_target_config(zygisk::Api *api) {
    // 配置经 root companion 回传：App 进程读不到 /data/adb，
    // 所以由 companion（root 侧）读 /data/adb/modules/zygisk-ai-runtime/target.conf 再发回来。
    // preAppSpecialize 之后 Api 全部失效，配置必须在这里读完。
    TargetConfig cfg;  // 默认 enabled=false

    if (api == nullptr) return cfg;

    const int fd = api->connectCompanion();
    if (fd < 0) {
        ZAI_LOGW("connectCompanion failed — 走默认（不注入）");
        return cfg;
    }

    const std::string package = trim(read_config_from(fd));
    close(fd);

    if (package.empty()) {
        // 没有配置文件 = 不注入任何 App（安全默认，避免拖慢所有进程）
        return cfg;
    }

    cfg.enabled = true;
    cfg.package_name = package;
    ZAI_LOGI("target config: %s", package.c_str());
    return cfg;
}

bool should_inject(const std::string &package_name) {
    if (!g_target.enabled) return false;
    if (package_name.empty()) return false;
    return package_name == g_target.package_name;
}

void pre_app_specialize(zygisk::AppSpecializeArgs *args) {
    g_target = load_target_config(g_api);
    const std::string name = read_process_name(args);

    // 可观测性：骨架阶段 g_target.enabled 恒为 false（见 load_target_config），
    // 这意味着**不会注入任何进程**，模块加载完就 DLCLOSE 卸载。
    // 只靠 on_load 那一条日志很难判断"链路到底通没通"，
    // 所以测试构建打开这条 trace：每个 App 进程 specialize 时都留痕，
    // 证明 Zygisk 确实把本模块注入到了进程里、且过滤逻辑真的跑了。
    // 发布构建默认关闭（否则每个 App 启动都打一条，日志量太大）。
#ifdef ZAI_TRACE_BOOTSTRAP
    ZAI_LOGI("specialize: pid=%d name=%s target_enabled=%d",
             getpid(), name.c_str(), g_target.enabled ? 1 : 0);
#endif

    if (!should_inject(name)) {
        // 未 Hook 任何函数，可以安全卸载本模块。
        if (g_api != nullptr) {
            g_api->setOption(zygisk::DLCLOSE_MODULE_LIBRARY);
        }
        return;
    }

    ZAI_LOGI("target matched: %s", name.c_str());
    // 目标进程：绝不设置 DLCLOSE，否则 post 后代码被 unmap。
}

void post_app_specialize(const zygisk::AppSpecializeArgs *args) {
    const std::string name = read_process_name(args);
    if (!should_inject(name)) return;

    runtime::RuntimeContext ctx;
    ctx.package_name = name;
    ctx.pid = getpid();

    // Runtime 启动涉及 Frida-Gum / LSPlant 初始化，必须离开 specialize 线程，
    // 否则会阻塞 App 启动并被系统 ANR 掉。
    std::thread([ctx]() {
        if (!runtime::Runtime::instance().start(ctx)) {
            ZAI_LOGE("runtime start failed: %s", ctx.package_name.c_str());
        }
    }).detach();
}

}  // namespace zai::bootstrap
