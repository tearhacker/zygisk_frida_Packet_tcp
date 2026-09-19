// Runtime 上下文：一次进程内运行所需的全部环境事实。
//
// 上下文是只读事实的载体（包名 / PID / ABI / SDK / Session），
// 不持有任何 Backend 句柄，避免上下文变成上帝对象。
//
// ⚠️ M1 骨架代码，尚未编译验证（本机无 NDK）。

#pragma once

#include <string>

namespace zai::runtime {

struct RuntimeContext {
    std::string package_name;
    std::string session_id;  // 连接建立后由 Host 下发；重连即换新，不复用旧值
    int pid = -1;
    int sdk_int = 0;         // Android SDK 级别，用于 ART Backend 降级判断
    std::string abi;         // arm64-v8a / armeabi-v7a / x86_64
};

}  // namespace zai::runtime
