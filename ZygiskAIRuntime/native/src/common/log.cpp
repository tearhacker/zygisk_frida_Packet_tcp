// 进程内日志实现。
//
// ⚠️ M1 骨架代码，尚未编译验证（本机无 NDK）。

#include "common/log.h"

namespace zai::common {

const char *error_code_to_text(int code) {
    switch (code) {
        case 0:  return "ok";
        case 1:  return "bad_request";
        case 2:  return "not_found";
        case 3:  return "permission_denied";     // Write Guard 未授权
        case 4:  return "backend_unavailable";   // Gum / LSPlant 不可用
        case 5:  return "execution_failed";      // 已接受但执行失败
        case 6:  return "verification_failed";   // 已执行但 read-back 不通过
        case 7:  return "session_invalid";       // 重连后旧 Session 失效
        default: return "unknown";
    }
}

}  // namespace zai::common
