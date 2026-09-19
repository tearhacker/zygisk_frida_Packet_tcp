// 帧编解码实现。见 native/include/ipc/frame.h 的线格式说明。

#include "ipc/frame.h"

#include <arpa/inet.h>
#include <cerrno>
#include <cstring>
#include <unistd.h>

#include <sys/socket.h>
#include <sys/types.h>

#include "ipc/protocol_constants.h"

namespace zai {
namespace ipc {
namespace {

// MSG_NOSIGNAL：对端已关闭时不要被 SIGPIPE 打死。
bool send_all(int fd, const void *buf, size_t n) {
    const uint8_t *p = static_cast<const uint8_t *>(buf);
    size_t sent = 0;
    while (sent < n) {
        const ssize_t k = ::send(fd, p + sent, n - sent, MSG_NOSIGNAL);
        if (k <= 0) return false;
        sent += static_cast<size_t>(k);
    }
    return true;
}

// 必须读满 n 字节：stream socket 不保证一次读完。
bool recv_exact(int fd, void *buf, size_t n) {
    uint8_t *p = static_cast<uint8_t *>(buf);
    size_t got = 0;
    while (got < n) {
        const ssize_t k = ::recv(fd, p + got, n - got, 0);
        if (k <= 0) return false;  // 0 = 对端关闭，<0 = 出错
        got += static_cast<size_t>(k);
    }
    return true;
}

std::string errno_text(const char *what) {
    return std::string(what) + ": " + std::strerror(errno);
}

}  // namespace

bool send_frame(int fd, const std::string &payload, std::string *err) {
    if (payload.size() > static_cast<size_t>(ZAI_FRAME_MAX_PAYLOAD)) {
        if (err) *err = "payload 超过单帧上限";
        return false;
    }

    const uint32_t len = htonl(static_cast<uint32_t>(payload.size()));
    if (!send_all(fd, &len, ZAI_FRAME_HEADER_SIZE)) {
        if (err) *err = errno_text("send header failed");
        return false;
    }
    if (!payload.empty() && !send_all(fd, payload.data(), payload.size())) {
        if (err) *err = errno_text("send body failed");
        return false;
    }
    return true;
}

bool recv_frame(int fd, std::string *out, std::string *err) {
    uint32_t net_len = 0;
    if (!recv_exact(fd, &net_len, ZAI_FRAME_HEADER_SIZE)) {
        if (err) *err = errno_text("recv header failed");
        return false;
    }

    const uint32_t len = ntohl(net_len);
    if (len > static_cast<uint32_t>(ZAI_FRAME_MAX_PAYLOAD)) {
        if (err) *err = "非法帧长度（超过上限）";
        return false;
    }

    if (out == nullptr) {
        if (err) *err = "out 为空";
        return false;
    }

    out->assign(len, '\0');
    if (len > 0 && !recv_exact(fd, &(*out)[0], len)) {
        if (err) *err = errno_text("recv body failed");
        return false;
    }
    return true;
}

}  // namespace ipc
}  // namespace zai
