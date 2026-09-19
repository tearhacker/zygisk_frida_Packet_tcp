// Runtime Bootstrap 实现。
//
// 时机纪律（违反会直接导致 Hook 失效或进程崩溃）：
//   - preAppSpecialize  仍持有 zygote 权限：读配置 + 目标过滤
//   - postAppSpecialize 已进入 App sandbox：这里才拉起 Runtime
//   - DLCLOSE_MODULE_LIBRARY 只能在"确定不注入且未 Hook 任何函数"时使用
//
// ⚠️ M1 骨架代码，尚未编译验证（本机无 NDK）。

#include "bootstrap.h"

#include <sys/socket.h>
#include <unistd.h>

#include <android/log.h>

#include <cstdint>
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

// pre 阶段算出来、post 阶段直接消费的结果。
//
// 分开存两个而不是只存一个 bool：
//   post 阶段要给 Runtime 传进程名，而那时已经不能再去读 args / 用 JNI 了
//   （见 read_process_name 的注释），所以名字必须在 pre 阶段就落在这里。
bool g_inject = false;
std::string g_process_name;

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

// 只发不管对端是否已关闭：用 MSG_NOSIGNAL 避免 SIGPIPE 把宿主进程打死。
// 这段代码跑在别人的 App 进程里，一个 SIGPIPE 就是一次无声的崩溃。
bool send_all(int fd, const std::string &data) {
    size_t sent = 0;
    while (sent < data.size()) {
        const ssize_t n = ::send(fd, data.data() + sent, data.size() - sent, MSG_NOSIGNAL);
        if (n <= 0) return false;
        sent += static_cast<size_t>(n);
    }
    return true;
}

bool query_should_inject(zygisk::Api *api, const std::string &process_name) {
    // 拿不到进程名就无从判定，直接放弃 —— 比"猜一个"安全。
    if (api == nullptr || process_name.empty()) return false;

    const int fd = api->connectCompanion();
    if (fd < 0) {
        ZAI_LOGW("connectCompanion failed — 默认不注入");
        return false;
    }

    // 请求：[uint32 长度][进程名]，长度前缀协议见 bootstrap.h。
    const uint32_t len = static_cast<uint32_t>(process_name.size());
    std::string req;
    req.append(reinterpret_cast<const char *>(&len), sizeof(len));
    req += process_name;

    char answer = companion::kSkip;
    if (send_all(fd, req)) {
        const ssize_t got = ::read(fd, &answer, sizeof(answer));
        if (got != sizeof(answer)) {
            ZAI_LOGW("companion 无响应 — 默认不注入");
        }
    }
    ::close(fd);

    return answer == companion::kInject;
}

bool should_inject(const std::string &package_name) {
    if (!g_inject) return false;
    if (package_name.empty()) return false;
    return package_name == g_process_name;
}

void pre_app_specialize(zygisk::AppSpecializeArgs *args) {
    // ① 进程名必须在这一步取走。
    //    此刻 args->nice_name 与 onLoad 保存的 JNIEnv 都还有效；
    //    到了 postAppSpecialize 就没有保证了（见 read_process_name 注释）。
    g_process_name = read_process_name(args);

    // ② 判定交给 root 侧的 companion：配置在它那边读并可缓存，
    //    这里只拿一个字节的结果，一次往返。
    g_inject = query_should_inject(g_api, g_process_name);

    // 可观测性：只靠 onLoad 那一条日志判断不了"链路到底通没通"，
    // 所以测试构建打开这条 trace：每个 App 进程 specialize 时都留痕，
    // 证明 Zygisk 确实把本模块注入到了进程里、且过滤逻辑真的跑了。
    // 发布构建默认关闭（否则每个 App 启动都打一条，日志量太大）。
#ifdef ZAI_TRACE_BOOTSTRAP
    ZAI_LOGI("specialize: pid=%d name=%s inject=%d",
             getpid(), g_process_name.c_str(), g_inject ? 1 : 0);
#endif

    if (!g_inject) {
        // 未 Hook 任何函数，可以安全卸载本模块。
        //
        // 🔴 这一步不是可选优化。Magisk 在 fork 出来的**每一个** App 进程里
        //    都会先 dlopen 本 so，再回调 preAppSpecialize
        //    （native/src/core/zygisk/module.cpp 的 run_modules_pre）。
        //    不主动 DLCLOSE，这份十几 MB 的代码就会白白驻留在所有 App 进程里。
        if (g_api != nullptr) {
            g_api->setOption(zygisk::DLCLOSE_MODULE_LIBRARY);
        }
        return;
    }

    ZAI_LOGI("target matched: %s", g_process_name.c_str());
    // 目标进程：绝不设置 DLCLOSE，否则 post 之后代码被 unmap，Runtime 直接崩。
}

void post_app_specialize(const zygisk::AppSpecializeArgs * /*args*/) {
    // 这里刻意不碰 args、不碰 JNI：只用 pre 阶段缓存下来的结果。
    if (!g_inject) return;

    runtime::RuntimeContext ctx;
    ctx.package_name = g_process_name;
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
