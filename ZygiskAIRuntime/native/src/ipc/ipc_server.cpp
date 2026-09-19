// Runtime 侧 IPC 服务端实现。见 native/include/ipc/ipc_server.h。
//
// 实现纪律（与项目约定一致）：
//   - 只绑回环，绝不监听 0.0.0.0。
//   - 已实现的命令给真实数据；没实现的如实报 E_NOT_READY，不编造。
//   - capabilities 按真实能力上报，PC 侧据此摘工具。

#include "ipc/ipc_server.h"

#include <android/log.h>

#include <arpa/inet.h>
#include <dirent.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>

#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <thread>
#include <vector>

#include <json-glib/json-glib.h>

#include "common/log.h"
#include "ipc/frame.h"
#include "ipc/protocol_constants.h"

#define ZAI_LOG_TAG "ZAI:Ipc"
#define ZAI_LOGI(...) __android_log_print(ANDROID_LOG_INFO, ZAI_LOG_TAG, __VA_ARGS__)
#define ZAI_LOGW(...) __android_log_print(ANDROID_LOG_WARN, ZAI_LOG_TAG, __VA_ARGS__)
#define ZAI_LOGE(...) __android_log_print(ANDROID_LOG_ERROR, ZAI_LOG_TAG, __VA_ARGS__)

#ifndef MSG_NOSIGNAL
#define MSG_NOSIGNAL 0
#endif

namespace zai {
namespace ipc {
namespace {

// ---------------------------------------------------------------------------
// 全局状态
// ---------------------------------------------------------------------------

std::atomic<bool> g_running{false};
std::atomic<int> g_listen_fd{-1};
std::atomic<int> g_port{0};
std::atomic<bool> g_gum_ready{false};
std::atomic<long long> g_start_monotonic_ms{0};

std::string g_package;
std::string g_session_id;
std::thread g_thread;

long long now_ms() {
    struct timespec ts {};
    clock_gettime(CLOCK_REALTIME, &ts);
    return static_cast<long long>(ts.tv_sec) * 1000 + ts.tv_nsec / 1000000;
}

long long monotonic_ms() {
    struct timespec ts {};
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return static_cast<long long>(ts.tv_sec) * 1000 + ts.tv_nsec / 1000000;
}

std::string make_session_id() {
    // 与 PC 侧 new_session_id() 形态一致：sess_ + 12 位十六进制。
    char buf[32];
    unsigned int hi = static_cast<unsigned int>(now_ms() & 0xFFFFFFFFu);
    unsigned int lo = static_cast<unsigned int>(getpid());
    std::snprintf(buf, sizeof(buf), "sess_%08x%04x", hi, lo & 0xFFFFu);
    return std::string(buf);
}

// ---------------------------------------------------------------------------
// 内存映射表
// ---------------------------------------------------------------------------

struct MapEntry {
    uint64_t start = 0;
    uint64_t end = 0;
    std::string perms;
    std::string path;
};

std::vector<MapEntry> read_maps() {
    std::vector<MapEntry> out;
    std::FILE *f = std::fopen("/proc/self/maps", "re");
    if (f == nullptr) return out;

    char line[1024];
    while (std::fgets(line, sizeof(line), f) != nullptr) {
        unsigned long long s = 0, e = 0;
        char perms[8] = {0};
        char path[512] = {0};
        // 格式：start-end perms offset dev inode [path]
        if (std::sscanf(line, "%llx-%llx %7s %*s %*s %*s %511[^\n]", &s, &e, perms, path) >= 3) {
            MapEntry m;
            m.start = s;
            m.end = e;
            m.perms = perms;
            m.path = path;
            // 去掉前导空格
            const size_t b = m.path.find_first_not_of(' ');
            m.path = (b == std::string::npos) ? "" : m.path.substr(b);
            out.push_back(m);
        }
    }
    std::fclose(f);
    return out;
}

const MapEntry *find_map(const std::vector<MapEntry> &maps, uint64_t addr) {
    for (const auto &m : maps) {
        if (addr >= m.start && addr < m.end) return &m;
    }
    return nullptr;
}

// ---------------------------------------------------------------------------
// JSON 生成辅助
// ---------------------------------------------------------------------------

std::string node_to_string(JsonNode *node) {
    JsonGenerator *gen = json_generator_new();
    json_generator_set_root(gen, node);
    gsize len = 0;
    gchar *data = json_generator_to_data(gen, &len);
    std::string out(data ? data : "", data ? static_cast<size_t>(len) : 0);
    if (data) g_free(data);
    g_object_unref(gen);
    return out;
}

// 真实能力：按本文件实际实现了哪些命令来填，不许乐观。
void add_capabilities(JsonBuilder *b) {
    json_builder_set_member_name(b, "runtime");
    json_builder_begin_object(b);
    json_builder_set_member_name(b, "native_hook");
    json_builder_add_boolean_value(b, FALSE);  // Hook 命令尚未接线
    json_builder_set_member_name(b, "java_hook");
    json_builder_add_boolean_value(b, FALSE);  // LSPlant 未集成
    json_builder_set_member_name(b, "memory_read");
    json_builder_add_boolean_value(b, TRUE);   // 已实现
    json_builder_set_member_name(b, "memory_write");
    json_builder_add_boolean_value(b, FALSE);  // 未实现
    json_builder_set_member_name(b, "stacktrace");
    json_builder_add_boolean_value(b, FALSE);  // 未实现
    json_builder_end_object(b);

    json_builder_set_member_name(b, "network");
    json_builder_begin_object(b);
    json_builder_set_member_name(b, "capture");
    json_builder_add_boolean_value(b, FALSE);
    json_builder_set_member_name(b, "http");
    json_builder_add_boolean_value(b, FALSE);
    json_builder_set_member_name(b, "https_capture");
    json_builder_add_boolean_value(b, FALSE);
    json_builder_set_member_name(b, "https_decrypt");
    json_builder_add_boolean_value(b, FALSE);
    json_builder_set_member_name(b, "packet_intercept");
    json_builder_add_boolean_value(b, FALSE);
    json_builder_end_object(b);
}

std::string build_hello_ack(const std::string &session_id) {
    JsonBuilder *b = json_builder_new();
    json_builder_begin_object(b);
    json_builder_set_member_name(b, "type");
    json_builder_add_string_value(b, ZAI_MSG_HELLO_ACK);
    json_builder_set_member_name(b, "protocol");
    json_builder_add_string_value(b, ZAI_PROTOCOL_VERSION);
    json_builder_set_member_name(b, "server");
    json_builder_add_string_value(b, ZAI_SERVER_NAME);
    json_builder_set_member_name(b, "server_version");
    json_builder_add_string_value(b, ZAI_SERVER_VERSION);
    json_builder_set_member_name(b, "session_id");
    json_builder_add_string_value(b, session_id.c_str());
    json_builder_set_member_name(b, "capabilities");
    json_builder_begin_array(b);
    json_builder_add_string_value(b, "runtime");
    json_builder_add_string_value(b, "memory");
    json_builder_end_array(b);
    json_builder_end_object(b);
    JsonNode *root = json_builder_get_root(b);
    std::string out = node_to_string(root);
    json_node_unref(root);
    g_object_unref(b);
    return out;
}

std::string build_ready(const std::string &session_id) {
    JsonBuilder *b = json_builder_new();
    json_builder_begin_object(b);
    json_builder_set_member_name(b, "version");
    json_builder_add_string_value(b, ZAI_PROTOCOL_VERSION);
    json_builder_set_member_name(b, "type");
    json_builder_add_string_value(b, ZAI_MSG_READY);
    json_builder_set_member_name(b, "session_id");
    json_builder_add_string_value(b, session_id.c_str());
    json_builder_set_member_name(b, "timestamp");
    json_builder_add_int_value(b, now_ms());
    json_builder_set_member_name(b, "state");
    json_builder_add_string_value(b, ZAI_SESSION_STATE_RUNNING);
    json_builder_set_member_name(b, "capabilities");
    json_builder_begin_object(b);
    add_capabilities(b);
    json_builder_end_object(b);
    json_builder_end_object(b);
    JsonNode *root = json_builder_get_root(b);
    std::string out = node_to_string(root);
    json_node_unref(root);
    g_object_unref(b);
    return out;
}

std::string build_pong(int seq) {
    JsonBuilder *b = json_builder_new();
    json_builder_begin_object(b);
    json_builder_set_member_name(b, "type");
    json_builder_add_string_value(b, ZAI_MSG_PONG);
    json_builder_set_member_name(b, "seq");
    json_builder_add_int_value(b, seq);
    json_builder_end_object(b);
    JsonNode *root = json_builder_get_root(b);
    std::string out = node_to_string(root);
    json_node_unref(root);
    g_object_unref(b);
    return out;
}

std::string build_response(const std::string &request_id, const std::string &session_id,
                           const char *status, const char *code, JsonNode *payload) {
    JsonBuilder *b = json_builder_new();
    json_builder_begin_object(b);
    json_builder_set_member_name(b, "version");
    json_builder_add_string_value(b, ZAI_PROTOCOL_VERSION);
    json_builder_set_member_name(b, "type");
    json_builder_add_string_value(b, ZAI_MSG_RESPONSE);
    json_builder_set_member_name(b, "request_id");
    json_builder_add_string_value(b, request_id.c_str());
    json_builder_set_member_name(b, "session_id");
    json_builder_add_string_value(b, session_id.c_str());
    json_builder_set_member_name(b, "timestamp");
    json_builder_add_int_value(b, now_ms());
    json_builder_set_member_name(b, "status");
    json_builder_add_string_value(b, status);
    json_builder_set_member_name(b, "code");
    json_builder_add_string_value(b, code);
    json_builder_set_member_name(b, "payload");
    if (payload != nullptr) {
        json_builder_add_value(b, json_node_ref(payload));
    } else {
        json_builder_begin_object(b);
        json_builder_end_object(b);
    }
    json_builder_end_object(b);
    JsonNode *root = json_builder_get_root(b);
    std::string out = node_to_string(root);
    json_node_unref(root);
    g_object_unref(b);
    return out;
}

std::string error_response(const std::string &request_id, const std::string &session_id,
                           const char *code, const char *message) {
    JsonBuilder *b = json_builder_new();
    json_builder_begin_object(b);
    json_builder_set_member_name(b, "code");
    json_builder_add_string_value(b, code);
    json_builder_set_member_name(b, "message");
    json_builder_add_string_value(b, message);
    json_builder_end_object(b);
    JsonNode *payload = json_builder_get_root(b);
    std::string out = build_response(request_id, session_id, "error", code, payload);
    json_node_unref(payload);
    g_object_unref(b);
    return out;
}

// ---------------------------------------------------------------------------
// 命令实现
// ---------------------------------------------------------------------------

// 未实现的命令统一如实上报，绝不返回看起来正常的假数据。
JsonNode *not_implemented(const char *command) {
    JsonBuilder *b = json_builder_new();
    json_builder_begin_object(b);
    json_builder_set_member_name(b, "reason");
    json_builder_add_string_value(b, "not implemented");
    json_builder_set_member_name(b, "command");
    json_builder_add_string_value(b, command);
    json_builder_set_member_name(b, "note");
    json_builder_add_string_value(b, "Android 侧 M2 尚未实现该命令");
    json_builder_end_object(b);
    JsonNode *n = json_builder_get_root(b);
    g_object_unref(b);
    return n;
}

JsonNode *cmd_session_info() {
    JsonBuilder *b = json_builder_new();
    json_builder_begin_object(b);
    json_builder_set_member_name(b, "session_id");
    json_builder_add_string_value(b, g_session_id.c_str());
    json_builder_set_member_name(b, "state");
    json_builder_add_string_value(b, ZAI_SESSION_STATE_RUNNING);
    json_builder_set_member_name(b, "package");
    json_builder_add_string_value(b, g_package.c_str());
    json_builder_set_member_name(b, "pid");
    json_builder_add_int_value(b, getpid());
    json_builder_set_member_name(b, "uid");
    json_builder_add_int_value(b, getuid());
    json_builder_set_member_name(b, "abi");
    json_builder_add_string_value(b,
#if defined(__aarch64__)
        "arm64-v8a"
#elif defined(__arm__)
        "armeabi-v7a"
#else
        "unknown"
#endif
    );
    json_builder_set_member_name(b, "sdk");
    json_builder_add_int_value(b, __ANDROID_API__);
    json_builder_set_member_name(b, "uptime_ms");
    json_builder_add_int_value(b, monotonic_ms() - g_start_monotonic_ms.load());
    json_builder_set_member_name(b, "capabilities");
    json_builder_begin_object(b);
    add_capabilities(b);
    json_builder_end_object(b);
    json_builder_end_object(b);
    JsonNode *n = json_builder_get_root(b);
    g_object_unref(b);
    return n;
}

JsonNode *cmd_session_capabilities() {
    JsonBuilder *b = json_builder_new();
    json_builder_begin_object(b);
    json_builder_set_member_name(b, "capabilities");
    json_builder_begin_object(b);
    add_capabilities(b);
    json_builder_end_object(b);
    json_builder_set_member_name(b, "available");
    json_builder_begin_array(b);
    json_builder_add_string_value(b, "runtime.memory_read");
    json_builder_end_array(b);
    json_builder_set_member_name(b, "unavailable");
    json_builder_begin_array(b);
    const char *off[] = {"runtime.native_hook", "runtime.java_hook", "runtime.memory_write",
                         "runtime.stacktrace",  "network.capture",   "network.http",
                         "network.https_capture", "network.https_decrypt",
                         "network.packet_intercept"};
    for (const char *k : off) json_builder_add_string_value(b, k);
    json_builder_end_array(b);
    json_builder_set_member_name(b, "note");
    json_builder_add_string_value(b, "能力为 false 表示不可用；相关工具不应被调用");
    json_builder_end_object(b);
    JsonNode *n = json_builder_get_root(b);
    g_object_unref(b);
    return n;
}

JsonNode *cmd_session_list() {
    JsonBuilder *b = json_builder_new();
    json_builder_begin_object(b);
    json_builder_set_member_name(b, "total");
    json_builder_add_int_value(b, 1);
    json_builder_set_member_name(b, "sessions");
    json_builder_begin_array(b);
    json_builder_begin_object(b);
    json_builder_set_member_name(b, "session_id");
    json_builder_add_string_value(b, g_session_id.c_str());
    json_builder_set_member_name(b, "state");
    json_builder_add_string_value(b, ZAI_SESSION_STATE_RUNNING);
    json_builder_set_member_name(b, "package");
    json_builder_add_string_value(b, g_package.c_str());
    json_builder_set_member_name(b, "pid");
    json_builder_add_int_value(b, getpid());
    json_builder_end_object(b);
    json_builder_end_array(b);
    json_builder_end_object(b);
    JsonNode *n = json_builder_get_root(b);
    g_object_unref(b);
    return n;
}

JsonNode *cmd_process_info() {
    JsonBuilder *b = json_builder_new();
    json_builder_begin_object(b);
    json_builder_set_member_name(b, "pid");
    json_builder_add_int_value(b, getpid());
    json_builder_set_member_name(b, "package");
    json_builder_add_string_value(b, g_package.c_str());
    json_builder_set_member_name(b, "uid");
    json_builder_add_int_value(b, getuid());
    json_builder_set_member_name(b, "abi");
    json_builder_add_string_value(b,
#if defined(__aarch64__)
        "arm64-v8a"
#else
        "armeabi-v7a"
#endif
    );
    json_builder_set_member_name(b, "sdk");
    json_builder_add_int_value(b, __ANDROID_API__);

    // 线程数：/proc/self/task 下的目录数
    int threads = 0;
    if (DIR *d = opendir("/proc/self/task")) {
        while (readdir(d) != nullptr) threads++;
        closedir(d);
        threads = threads > 2 ? threads - 2 : 0;  // 去掉 . 与 ..
    }
    json_builder_set_member_name(b, "threads");
    json_builder_add_int_value(b, threads);

    int modules = 0;
    for (const auto &m : read_maps()) {
        if (!m.path.empty() && m.path.find(".so") != std::string::npos) modules++;
    }
    json_builder_set_member_name(b, "modules");
    json_builder_add_int_value(b, modules);

    json_builder_set_member_name(b, "uptime_ms");
    json_builder_add_int_value(b, monotonic_ms() - g_start_monotonic_ms.load());
    json_builder_end_object(b);
    JsonNode *n = json_builder_get_root(b);
    g_object_unref(b);
    return n;
}

JsonNode *cmd_process_list() {
    JsonBuilder *b = json_builder_new();
    json_builder_begin_object(b);
    json_builder_set_member_name(b, "total");
    json_builder_add_int_value(b, 1);
    json_builder_set_member_name(b, "truncated");
    json_builder_add_boolean_value(b, FALSE);
    json_builder_set_member_name(b, "processes");
    json_builder_begin_array(b);
    json_builder_begin_object(b);
    json_builder_set_member_name(b, "pid");
    json_builder_add_int_value(b, getpid());
    json_builder_set_member_name(b, "package");
    json_builder_add_string_value(b, g_package.c_str());
    json_builder_set_member_name(b, "uid");
    json_builder_add_int_value(b, getuid());
    json_builder_set_member_name(b, "process_name");
    json_builder_add_string_value(b, g_package.c_str());
    json_builder_set_member_name(b, "is_target");
    json_builder_add_boolean_value(b, TRUE);
    json_builder_end_object(b);
    json_builder_end_array(b);
    json_builder_end_object(b);
    JsonNode *n = json_builder_get_root(b);
    g_object_unref(b);
    return n;
}

JsonNode *cmd_process_modules() {
    struct Mod {
        std::string name;
        std::string path;
        std::string perms;
        uint64_t start = 0;
        uint64_t size = 0;
    };

    // 先收集再构建：JsonBuilder 是流式的，total 必须在写数组之前就知道。
    std::vector<Mod> mods;
    std::string last_path;
    for (const auto &m : read_maps()) {
        // 同一 so 有多段映射（r-xp / r--p / rw-p），按路径去重，保留第一段作为基址。
        if (m.path.empty() || m.path == last_path) continue;
        if (m.path.find(".so") == std::string::npos) continue;
        last_path = m.path;

        const size_t slash = m.path.find_last_of('/');
        Mod mo;
        mo.name = (slash == std::string::npos) ? m.path : m.path.substr(slash + 1);
        mo.path = m.path;
        mo.perms = m.perms;
        mo.start = m.start;
        mo.size = m.end - m.start;
        mods.push_back(std::move(mo));
    }

    JsonBuilder *b = json_builder_new();
    json_builder_begin_object(b);
    json_builder_set_member_name(b, "total");
    json_builder_add_int_value(b, static_cast<gint64>(mods.size()));
    json_builder_set_member_name(b, "truncated");
    json_builder_add_boolean_value(b, FALSE);
    json_builder_set_member_name(b, "modules");
    json_builder_begin_array(b);
    for (const auto &mo : mods) {
        char base[32];
        std::snprintf(base, sizeof(base), "0x%llx", static_cast<unsigned long long>(mo.start));
        json_builder_begin_object(b);
        json_builder_set_member_name(b, "name");
        json_builder_add_string_value(b, mo.name.c_str());
        json_builder_set_member_name(b, "path");
        json_builder_add_string_value(b, mo.path.c_str());
        json_builder_set_member_name(b, "base");
        json_builder_add_string_value(b, base);
        json_builder_set_member_name(b, "size");
        json_builder_add_int_value(b, static_cast<gint64>(mo.size));
        json_builder_set_member_name(b, "permissions");
        json_builder_add_string_value(b, mo.perms.c_str());
        json_builder_end_object(b);
    }
    json_builder_end_array(b);
    json_builder_end_object(b);
    JsonNode *n = json_builder_get_root(b);
    g_object_unref(b);
    return n;
}

// 读 /proc/self/task/<tid>/comm 得到线程名。失败返回空串。
std::string read_thread_name(const std::string &tid) {
    const std::string p = "/proc/self/task/" + tid + "/comm";
    std::FILE *f = std::fopen(p.c_str(), "re");
    if (f == nullptr) return "";
    char buf[256] = {0};
    if (std::fgets(buf, sizeof(buf), f) == nullptr) {
        std::fclose(f);
        return "";
    }
    std::fclose(f);
    std::string s(buf);
    // comm 以换行结尾
    const size_t e = s.find_last_not_of(" \t\r\n");
    return (e == std::string::npos) ? "" : s.substr(0, e + 1);
}

// 解析 /proc/<pid>/stat 的第三个字段（进程状态字符，如 R/S/D）。
// 格式：pid (comm) state ... —— comm 里可能有空格和括号，所以找**最后一个** ')'。
char read_thread_state(const std::string &tid) {
    const std::string p = "/proc/self/task/" + tid + "/stat";
    std::FILE *f = std::fopen(p.c_str(), "re");
    if (f == nullptr) return '?';
    char buf[1024] = {0};
    if (std::fgets(buf, sizeof(buf), f) == nullptr) {
        std::fclose(f);
        return '?';
    }
    std::fclose(f);
    const std::string s(buf);
    const size_t r = s.find_last_of(')');
    if (r == std::string::npos) return '?';
    const size_t b = s.find_first_not_of(' ', r + 1);
    return (b == std::string::npos) ? '?' : s[b];
}

JsonNode *cmd_process_threads() {
    std::vector<std::string> tids;
    if (DIR *d = opendir("/proc/self/task")) {
        struct dirent *ent;
        while ((ent = readdir(d)) != nullptr) {
            const std::string name(ent->d_name);
            // 只要纯数字目录项，跳过 "." / ".."
            if (name.empty() || name[0] < '0' || name[0] > '9') continue;
            tids.push_back(name);
        }
        closedir(d);
    }

    JsonBuilder *b = json_builder_new();
    json_builder_begin_object(b);
    json_builder_set_member_name(b, "total");
    json_builder_add_int_value(b, static_cast<gint64>(tids.size()));
    json_builder_set_member_name(b, "truncated");
    json_builder_add_boolean_value(b, FALSE);
    json_builder_set_member_name(b, "threads");
    json_builder_begin_array(b);
    for (const auto &tid : tids) {
        const std::string tname = read_thread_name(tid);
        const char st = read_thread_state(tid);
        char state[2] = {st, '\0'};
        json_builder_begin_object(b);
        json_builder_set_member_name(b, "tid");
        json_builder_add_int_value(b, std::strtol(tid.c_str(), nullptr, 10));
        json_builder_set_member_name(b, "name");
        json_builder_add_string_value(b, tname.c_str());
        json_builder_set_member_name(b, "state");
        json_builder_add_string_value(b, state);
        json_builder_end_object(b);
    }
    json_builder_end_array(b);
    json_builder_end_object(b);
    JsonNode *n = json_builder_get_root(b);
    g_object_unref(b);
    return n;
}

// 与 PC 侧 mock 的 _cmd_memory_maps 结构一致：{total, maps:[{module,start,end,permissions}]}
JsonNode *cmd_memory_maps() {
    const auto maps = read_maps();

    JsonBuilder *b = json_builder_new();
    json_builder_begin_object(b);
    json_builder_set_member_name(b, "total");
    json_builder_add_int_value(b, static_cast<gint64>(maps.size()));
    json_builder_set_member_name(b, "maps");
    json_builder_begin_array(b);
    for (const auto &m : maps) {
        char start[32], end[32];
        std::snprintf(start, sizeof(start), "0x%llx", static_cast<unsigned long long>(m.start));
        std::snprintf(end, sizeof(end), "0x%llx", static_cast<unsigned long long>(m.end));

        // 匿名映射没有路径，module 给空串而不是臆造一个名字。
        const size_t slash = m.path.find_last_of('/');
        const std::string mod =
            m.path.empty() ? "" : ((slash == std::string::npos) ? m.path : m.path.substr(slash + 1));

        json_builder_begin_object(b);
        json_builder_set_member_name(b, "module");
        json_builder_add_string_value(b, mod.c_str());
        json_builder_set_member_name(b, "start");
        json_builder_add_string_value(b, start);
        json_builder_set_member_name(b, "end");
        json_builder_add_string_value(b, end);
        json_builder_set_member_name(b, "permissions");
        json_builder_add_string_value(b, m.perms.c_str());
        json_builder_end_object(b);
    }
    json_builder_end_array(b);
    json_builder_end_object(b);
    JsonNode *n = json_builder_get_root(b);
    g_object_unref(b);
    return n;
}

JsonNode *cmd_runtime_status() {
    JsonBuilder *b = json_builder_new();
    json_builder_begin_object(b);
    json_builder_set_member_name(b, "ready");
    json_builder_add_boolean_value(b, g_gum_ready.load() ? TRUE : FALSE);
    json_builder_set_member_name(b, "gum_initialized");
    json_builder_add_boolean_value(b, g_gum_ready.load() ? TRUE : FALSE);
    json_builder_set_member_name(b, "lsplant_enabled");
    json_builder_add_boolean_value(b, FALSE);
    json_builder_set_member_name(b, "ipc_running");
    json_builder_add_boolean_value(b, g_running.load() ? TRUE : FALSE);
    json_builder_set_member_name(b, "ipc_port");
    json_builder_add_int_value(b, g_port.load());
    json_builder_set_member_name(b, "package");
    json_builder_add_string_value(b, g_package.c_str());
    json_builder_end_object(b);
    JsonNode *n = json_builder_get_root(b);
    g_object_unref(b);
    return n;
}

JsonNode *cmd_memory_read(JsonObject *payload, std::string *err) {
    const char *addr_s = json_object_has_member(payload, "address")
                             ? json_object_get_string_member(payload, "address")
                             : nullptr;
    if (addr_s == nullptr) {
        *err = "缺少 address";
        return nullptr;
    }

    gint64 length = 16;
    if (json_object_has_member(payload, "length")) {
        length = json_object_get_int_member(payload, "length");
    }
    if (length <= 0 || length > 4096) {
        *err = "length 必须在 1..4096";
        return nullptr;
    }

    const uint64_t addr = std::strtoull(addr_s, nullptr, 0);
    if (addr == 0) {
        *err = "address 无法解析";
        return nullptr;
    }

    // 必须先确认整段都落在可读映射里，否则 memcpy 会 SIGSEGV 把游戏打崩。
    const auto maps = read_maps();
    const MapEntry *m = find_map(maps, addr);
    if (m == nullptr) {
        *err = "地址不在任何映射区间内";
        return nullptr;
    }
    if (m->perms.empty() || m->perms[0] != 'r') {
        *err = "所在区间不可读";
        return nullptr;
    }
    if (addr + static_cast<uint64_t>(length) > m->end) {
        *err = "读取范围越过映射区间末尾";
        return nullptr;
    }

    std::vector<uint8_t> buf(static_cast<size_t>(length));
    std::memcpy(buf.data(), reinterpret_cast<const void *>(addr), buf.size());

    static const char kHex[] = "0123456789abcdef";
    std::string hex;
    hex.reserve(buf.size() * 2);
    std::string ascii;
    ascii.reserve(buf.size());
    for (uint8_t byte : buf) {
        hex.push_back(kHex[byte >> 4]);
        hex.push_back(kHex[byte & 0x0F]);
        ascii.push_back((byte >= 0x20 && byte < 0x7F) ? static_cast<char>(byte) : '.');
    }

    const size_t slash = m->path.find_last_of('/');
    const std::string mod_name =
        m->path.empty() ? "" : ((slash == std::string::npos) ? m->path : m->path.substr(slash + 1));

    JsonBuilder *b = json_builder_new();
    json_builder_begin_object(b);
    json_builder_set_member_name(b, "address");
    json_builder_add_string_value(b, addr_s);
    json_builder_set_member_name(b, "length");
    json_builder_add_int_value(b, length);
    json_builder_set_member_name(b, "hex");
    json_builder_add_string_value(b, hex.c_str());
    json_builder_set_member_name(b, "ascii");
    json_builder_add_string_value(b, ascii.c_str());
    json_builder_set_member_name(b, "module");
    json_builder_add_string_value(b, mod_name.c_str());
    json_builder_set_member_name(b, "permissions");
    json_builder_add_string_value(b, m->perms.c_str());
    json_builder_end_object(b);
    JsonNode *n = json_builder_get_root(b);
    g_object_unref(b);
    return n;
}

// ---------------------------------------------------------------------------
// 请求分发
// ---------------------------------------------------------------------------

std::string handle_request(const std::string &command, JsonObject *payload_obj,
                           const std::string &request_id) {
    if (command == "session.info") {
        JsonNode *p = cmd_session_info();
        std::string out = build_response(request_id, g_session_id, "ok", "OK", p);
        json_node_unref(p);
        return out;
    }
    if (command == "session.capabilities") {
        JsonNode *p = cmd_session_capabilities();
        std::string out = build_response(request_id, g_session_id, "ok", "OK", p);
        json_node_unref(p);
        return out;
    }
    if (command == "session.list") {
        JsonNode *p = cmd_session_list();
        std::string out = build_response(request_id, g_session_id, "ok", "OK", p);
        json_node_unref(p);
        return out;
    }
    if (command == "process.info") {
        JsonNode *p = cmd_process_info();
        std::string out = build_response(request_id, g_session_id, "ok", "OK", p);
        json_node_unref(p);
        return out;
    }
    if (command == "process.list") {
        JsonNode *p = cmd_process_list();
        std::string out = build_response(request_id, g_session_id, "ok", "OK", p);
        json_node_unref(p);
        return out;
    }
    if (command == "process.modules") {
        JsonNode *p = cmd_process_modules();
        std::string out = build_response(request_id, g_session_id, "ok", "OK", p);
        json_node_unref(p);
        return out;
    }
    if (command == "process.threads") {
        JsonNode *p = cmd_process_threads();
        std::string out = build_response(request_id, g_session_id, "ok", "OK", p);
        json_node_unref(p);
        return out;
    }
    if (command == "memory.maps") {
        JsonNode *p = cmd_memory_maps();
        std::string out = build_response(request_id, g_session_id, "ok", "OK", p);
        json_node_unref(p);
        return out;
    }
    if (command == "runtime.status") {
        JsonNode *p = cmd_runtime_status();
        std::string out = build_response(request_id, g_session_id, "ok", "OK", p);
        json_node_unref(p);
        return out;
    }
    if (command == "memory.read") {
        std::string err;
        JsonNode *p = cmd_memory_read(payload_obj, &err);
        if (p == nullptr) {
            return error_response(request_id, g_session_id, ZAI_ERR_BAD_ARGS, err.c_str());
        }
        std::string out = build_response(request_id, g_session_id, "ok", "OK", p);
        json_node_unref(p);
        return out;
    }

    // 已知但尚未实现 —— 如实报错，不返回假数据。
    const char *known_not_impl[] = {"memory.dump",     "memory.write",
                                    "network.connections", "network.dns",
                                    "packet.get",      "packet.list",      "artifact.get",
                                    "artifact.list",   "device.info",      "device.list",
                                    "device.root_status", "job.status",     "job.result",
                                    "job.cancel",      "runtime.hook",     "runtime.hook_info",
                                    "runtime.unhook"};
    for (const char *k : known_not_impl) {
        if (command == k) {
            JsonNode *p = not_implemented(k);
            std::string out = build_response(request_id, g_session_id, "error", ZAI_ERR_NOT_READY, p);
            json_node_unref(p);
            return out;
        }
    }

    return error_response(request_id, g_session_id, ZAI_ERR_UNKNOWN_CMD, "未知命令");
}

// ---------------------------------------------------------------------------
// 连接处理
// ---------------------------------------------------------------------------

void handle_connection(int fd) {
    std::string err;

    // 1) 等 HELLO
    std::string raw;
    if (!recv_frame(fd, &raw, &err)) {
        ZAI_LOGW("握手失败（读 HELLO）：%s", err.c_str());
        ::close(fd);
        return;
    }

    GError *gerr = nullptr;
    JsonParser *parser = json_parser_new();
    if (!json_parser_load_from_data(parser, raw.c_str(), static_cast<gssize>(raw.size()), &gerr)) {
        ZAI_LOGW("HELLO 解析失败：%s", gerr ? gerr->message : "unknown");
        if (gerr) g_error_free(gerr);
        g_object_unref(parser);
        ::close(fd);
        return;
    }
    JsonNode *root = json_parser_get_root(parser);
    JsonObject *obj = json_node_get_object(root);
    const char *type = json_object_has_member(obj, "type")
                           ? json_object_get_string_member(obj, "type")
                           : "";
    if (std::strcmp(type, ZAI_MSG_HELLO) != 0) {
        ZAI_LOGW("首帧不是 HELLO，收到 %s", type);
        g_object_unref(parser);
        ::close(fd);
        return;
    }
    g_object_unref(parser);

    g_session_id = make_session_id();

    // 2) HELLO_ACK + 3) READY（PC 侧握手时序要求连续两帧）
    if (!send_frame(fd, build_hello_ack(g_session_id), &err) ||
        !send_frame(fd, build_ready(g_session_id), &err)) {
        ZAI_LOGW("握手应答发送失败：%s", err.c_str());
        ::close(fd);
        return;
    }
    ZAI_LOGI("握手完成 sid=%s pkg=%s", g_session_id.c_str(), g_package.c_str());

    // 4) 命令循环
    while (g_running.load()) {
        std::string msg;
        if (!recv_frame(fd, &msg, &err)) {
            ZAI_LOGI("连接结束：%s", err.c_str());
            break;
        }

        JsonParser *p = json_parser_new();
        if (!json_parser_load_from_data(p, msg.c_str(), static_cast<gssize>(msg.size()), nullptr)) {
            g_object_unref(p);
            std::string e = error_response("", g_session_id, ZAI_ERR_MALFORMED_FRAME, "无法解析的 JSON");
            if (!send_frame(fd, e, &err)) break;
            continue;
        }
        JsonObject *o = json_node_get_object(json_parser_get_root(p));
        const char *mtype = json_object_has_member(o, "type")
                                ? json_object_get_string_member(o, "type")
                                : "";

        if (std::strcmp(mtype, ZAI_MSG_PING) == 0) {
            int seq = json_object_has_member(o, "seq") ? json_object_get_int_member(o, "seq") : 0;
            if (!send_frame(fd, build_pong(seq), &err)) {
                g_object_unref(p);
                break;
            }
        } else if (std::strcmp(mtype, ZAI_MSG_REQUEST) == 0) {
            const char *cmd = json_object_has_member(o, "command")
                                  ? json_object_get_string_member(o, "command")
                                  : "";
            const char *rid = json_object_has_member(o, "request_id")
                                  ? json_object_get_string_member(o, "request_id")
                                  : "";
            JsonObject *pl = json_object_has_member(o, "payload")
                                 ? json_object_get_object_member(o, "payload")
                                 : nullptr;
            std::string resp = handle_request(cmd, pl, rid);
            if (!send_frame(fd, resp, &err)) {
                g_object_unref(p);
                break;
            }
        } else {
            ZAI_LOGW("忽略未知消息类型 %s", mtype);
        }
        g_object_unref(p);
    }

    ::close(fd);
}

void accept_loop(int listen_fd) {
    while (g_running.load()) {
        struct sockaddr_in addr {};
        socklen_t len = sizeof(addr);
        const int fd = ::accept(listen_fd, reinterpret_cast<struct sockaddr *>(&addr), &len);
        if (fd < 0) {
            if (g_running.load()) ZAI_LOGW("accept 失败：%s", std::strerror(errno));
            break;
        }
        // 只接受一个客户端。当前架构一个 Session 绑一个进程，
        // 多客户端需要 Session 升格（见多进程需求文档），先不做。
        handle_connection(fd);
    }
}

}  // namespace

// ---------------------------------------------------------------------------
// 公开接口
// ---------------------------------------------------------------------------

void set_context(const std::string &package, bool gum_ready) {
    g_package = package;
    g_gum_ready.store(gum_ready);
}

bool start(int port) {
    if (g_running.load()) return true;

    const int fd = ::socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) {
        ZAI_LOGE("socket 创建失败：%s", std::strerror(errno));
        return false;
    }

    int reuse = 1;
    ::setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));

    struct sockaddr_in addr {};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(static_cast<uint16_t>(port));
    // ⚠️ 固定绑回环。Runtime 带 root，绑 0.0.0.0 等于把内存读写开给同网段。
    addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);

    if (::bind(fd, reinterpret_cast<struct sockaddr *>(&addr), sizeof(addr)) < 0) {
        ZAI_LOGE("bind 127.0.0.1:%d 失败：%s", port, std::strerror(errno));
        ::close(fd);
        return false;
    }
    if (::listen(fd, 4) < 0) {
        ZAI_LOGE("listen 失败：%s", std::strerror(errno));
        ::close(fd);
        return false;
    }

    g_listen_fd.store(fd);
    g_port.store(port);
    g_start_monotonic_ms.store(monotonic_ms());
    g_running.store(true);
    g_session_id = make_session_id();

    g_thread = std::thread(accept_loop, fd);
    ZAI_LOGI("IPC 监听 127.0.0.1:%d（仅回环）pkg=%s", port, g_package.c_str());
    return true;
}

void stop() {
    if (!g_running.load()) return;
    g_running.store(false);

    const int fd = g_listen_fd.exchange(-1);
    if (fd >= 0) {
        ::shutdown(fd, SHUT_RDWR);
        ::close(fd);
    }
    if (g_thread.joinable()) g_thread.join();
    g_port.store(0);
    ZAI_LOGI("IPC 已停止");
}

bool is_running() { return g_running.load(); }

int port() { return g_port.load(); }

}  // namespace ipc
}  // namespace zai
