#!/system/bin/sh
# late_start service 阶段：boot 完成、Zygote 已起。
#
# TODO(M2): 这里将启动 root companion 对应的守护侧，
#           负责读取模块目录里的 target 配置并回传给目标进程
#           （对应 zygisk/entry.cpp 的 companion_handler）。
#
# 当前阶段不启动任何常驻进程，避免引入额外的开机负担。
exit 0
