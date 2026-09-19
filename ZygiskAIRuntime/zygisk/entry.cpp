// Zygisk 注册入口。
//
// REGISTER_ZYGISK_MODULE 展开出 zygisk_module_entry —— Magisk 在每一个 App /
// system_server 进程里 dlopen 本 so 后 dlsym 的唯一入口符号。
// REGISTER_ZYGISK_COMPANION 展开出 zygisk_companion_entry —— 运行在 root 守护
// 进程（zygiskd）里，负责回答"这个进程要不要注入"。
//
// 为什么判定必须放在 companion 而不是 App 侧：
//   App 进程读不到 /data/adb（目录权限），只有 root 侧的 companion 能读模块的
//   target.conf。这是 Zygisk 的固有约束，不是可选设计。

#include <android/log.h>

#include <sys/socket.h>
#include <sys/stat.h>
#include <unistd.h>

#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>

#include "bootstrap.h"
#include "module.h"

REGISTER_ZYGISK_MODULE(zai::AIRuntimeModule)

using zai::bootstrap::companion::kInject;
using zai::bootstrap::companion::kSkip;

namespace {

// 目标配置文件。模块 id 固定，所以可以直接写死 Magisk 的模块目录路径。
constexpr const char *kTargetConf = "/data/adb/modules/zygisk-packettool-tearhacker/target.conf";

// 只发不管对端是否已关闭：用 MSG_NOSIGNAL 避免 SIGPIPE 把进程打死。
void send_all(int fd, const std::string &data) {
    size_t sent = 0;
    while (sent < data.size()) {
        const ssize_t n = ::send(fd, data.data() + sent, data.size() - sent, MSG_NOSIGNAL);
        if (n <= 0) break;
        sent += static_cast<size_t>(n);
    }
}

bool read_exact(int fd, char *buf, size_t n) {
    size_t got = 0;
    while (got < n) {
        const ssize_t r = ::read(fd, buf + got, n - got);
        if (r <= 0) return false;  // 0 = 对端关闭，<0 = 出错
        got += static_cast<size_t>(r);
    }
    return true;
}

std::string trim(const std::string &s) {
    const char *ws = " \t\r\n";
    const size_t begin = s.find_first_not_of(ws);
    if (begin == std::string::npos) return {};
    const size_t end = s.find_last_not_of(ws);
    return s.substr(begin, end - begin + 1);
}

// 取所有「非空且非 # 注释」的行作为目标包名集合。
//
// ✅ 多包名：一行一个包名，全部返回。空集合 = 不注入任何 App。
// 去重但保持文件里的原始顺序（便于日志对照）。
std::vector<std::string> read_target_packages() {
    std::vector<std::string> out;
    std::FILE *f = std::fopen(kTargetConf, "re");
    if (f == nullptr) return out;

    char line[512];
    while (std::fgets(line, sizeof(line), f) != nullptr) {
        const std::string s = trim(line);
        if (s.empty() || s[0] == '#') continue;
        bool dup = false;
        for (const auto &x : out) {
            if (x == s) { dup = true; break; }
        }
        if (!dup) out.push_back(s);
    }
    std::fclose(f);
    return out;
}

// ---------------------------------------------------------------------------
// 配置缓存
//
// zygiskd 是常驻进程，而 companion 会在**每一次** App specialize 时被调用一次。
// 每个 App 启动都去 /data/adb 下 fopen 一遍显然没必要，但也不能永远不重读
// （用户改了 target.conf 得能生效）。
//
// 因此按 (mtime, size) 判断文件是否被改过，改过才重读。
// 并发安全：zygiskd 是单线程 poll 循环串行调用 companion_handler，
// 不存在同时进入的情况；真要将来改成并发，这里需要加锁。
// ---------------------------------------------------------------------------
struct TargetCache {
    bool loaded = false;
    time_t mtime = 0;
    off_t size = 0;
    std::vector<std::string> packages;
};

const std::vector<std::string> &target_packages() {
    static TargetCache cache;

    struct stat st{};
    const bool have_stat = ::stat(kTargetConf, &st) == 0;

    if (cache.loaded && have_stat && st.st_mtime == cache.mtime && st.st_size == cache.size) {
        return cache.packages;
    }

    cache.packages = read_target_packages();
    cache.loaded = true;
    if (have_stat) {
        cache.mtime = st.st_mtime;
        cache.size = st.st_size;
    }
    __android_log_print(ANDROID_LOG_DEBUG, "ZAI:Companion", "target.conf -> %zu pkg%s",
                        cache.packages.size(), cache.packages.empty() ? " (empty)" : "");
    return cache.packages;
}

bool is_target(const std::string &process_name) {
    if (process_name.empty()) return false;
    for (const auto &p : target_packages()) {
        if (p == process_name) return true;
    }
    return false;
}

// Root companion：供 bootstrap::query_should_inject 调用。
//
// 协议（详见 zygisk/bootstrap.h）：
//   请求：[uint32 长度][进程名]
//   响应：单字节 '1' / '0'
void companion_handler(int socket) {
    if (socket < 0) return;

    uint32_t len = 0;
    std::string name;
    if (read_exact(socket, reinterpret_cast<char *>(&len), sizeof(len)) && len > 0 && len < 4096) {
        name.resize(len);
        if (!read_exact(socket, &name[0], len)) name.clear();
    }

    const bool hit = is_target(name);
    __android_log_print(ANDROID_LOG_DEBUG, "ZAI:Companion", "query [%s] -> %s",
                        name.c_str(), hit ? "inject" : "skip");

    send_all(socket, std::string(1, hit ? kInject : kSkip));
    ::close(socket);
}

}  // namespace

REGISTER_ZYGISK_COMPANION(companion_handler)
