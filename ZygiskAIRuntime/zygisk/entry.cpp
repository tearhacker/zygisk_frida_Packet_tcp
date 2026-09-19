// Zygisk 注册入口。
//
// REGISTER_ZYGISK_MODULE 展开出 zygisk_module_entry，是 Magisk 加载本 so 的唯一入口符号。
// REGISTER_ZYGISK_COMPANION 展开出 zygisk_companion_entry，运行在 root 守护进程，
// 用于完成"读模块目录配置"这类需要 root 权限的动作（M2 接线）。
//
// ⚠️ M1 骨架代码，尚未编译验证（本机无 NDK）。

#include <android/log.h>

#include <sys/socket.h>
#include <unistd.h>

#include <cstdio>
#include <string>

#include "module.h"

REGISTER_ZYGISK_MODULE(zai::AIRuntimeModule)

namespace {

// 目标配置文件。模块 id 固定，所以可以直接写死 Magisk 的模块目录路径。
//
// ⚠️ 为什么必须由 companion 来读：App 进程**读不到** /data/adb（目录权限），
//    而 companion 运行在 root 侧有权限。所以流程是
//      companion(root) 读文件 → 经 socket 回传 → App 进程拿到配置
//    这是 Zygisk 的固有约束，不是可选设计。
constexpr const char *kTargetConf = "/data/adb/modules/zygisk-ai-runtime/target.conf";

// 只发不管对端是否已关闭：用 MSG_NOSIGNAL 避免 SIGPIPE 把进程打死。
void send_all(int fd, const std::string &data) {
    size_t sent = 0;
    while (sent < data.size()) {
        const ssize_t n = ::send(fd, data.data() + sent, data.size() - sent, MSG_NOSIGNAL);
        if (n <= 0) break;
        sent += static_cast<size_t>(n);
    }
}

std::string trim(const std::string &s) {
    const char *ws = " \t\r\n";
    const size_t begin = s.find_first_not_of(ws);
    if (begin == std::string::npos) return {};
    const size_t end = s.find_last_not_of(ws);
    return s.substr(begin, end - begin + 1);
}

// 取第一个「非空且非 # 注释」的行作为目标包名。
std::string read_target_package() {
    std::FILE *f = std::fopen(kTargetConf, "re");
    if (f == nullptr) return {};

    std::string picked;
    char line[512];
    while (std::fgets(line, sizeof(line), f) != nullptr) {
        const std::string s = trim(line);
        if (s.empty() || s[0] == '#') continue;
        picked = s;
        break;
    }
    std::fclose(f);
    return picked;
}

// Root companion：与 bootstrap::load_target_config 配套。
// 注意：此函数会并发执行（多个 App 同时 specialize），因此**不能**有共享可写状态；
// 这里只读一个文件，天然是安全的。
void companion_handler(int socket) {
    std::string out;
    if (socket >= 0) {
        const std::string package = read_target_package();
        // 回传格式：包名 + 换行。没有配置就发空串 —— App 侧据此判定 enabled=false。
        out = package + "\n";
        send_all(socket, out);
        __android_log_print(ANDROID_LOG_DEBUG, "ZAI:Companion",
                            "target.conf -> %s", package.empty() ? "<empty>" : package.c_str());
        ::close(socket);
    }
}

}  // namespace

REGISTER_ZYGISK_COMPANION(companion_handler)
