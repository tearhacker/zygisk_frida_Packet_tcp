// Memory Manager：进程内存读写的唯一入口。
//
// 门禁纪律（../../../docs/00-权威基线/项目总基线_v1.1.md §12 Write Guard）：
//   - read / search / dump 是只读操作，可自由执行
//   - write 必须经过会话级授权，且写完后必须 read-back 校验
//   - "返回 200" ≠ "内存真的改了"，verified 必须由 read-back 证明
//
// ⚠️ M1 骨架代码，尚未编译验证（本机无 NDK）。

#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace zai::runtime {

struct MemoryRegion {
    uint64_t base = 0;
    uint64_t size = 0;
    std::string protection;
    std::string file_path;
};

struct WriteResult {
    bool accepted = false;  // 命令已被接受
    bool executed = false;  // 写入已执行
    bool verified = false;  // read-back 校验通过
    std::string reason;     // 失败原因，禁止空
};

class MemoryManager {
public:
    bool read(uint64_t address, std::vector<uint8_t> &out, uint64_t length) const;

    // 未经 Write Guard 授权必须先走 request_write_grant。
    WriteResult write(uint64_t address, const std::vector<uint8_t> &data, bool granted);

    std::vector<uint64_t> search(const std::string &pattern, uint64_t max_results = 100) const;
    std::vector<MemoryRegion> regions() const;

private:
    // read-back：把写入区域的真实内容读回来与期望值逐字节比对。
    bool verify_write(uint64_t address, const std::vector<uint8_t> &expected) const;
};

}  // namespace zai::runtime
