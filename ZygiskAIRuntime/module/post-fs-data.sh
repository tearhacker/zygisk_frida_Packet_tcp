#!/system/bin/sh
# post-fs-data 阶段：模块目录可用，但 Zygote 尚未启动。
# 本模块不需要在此阶段做任何事——Runtime 由 Zygisk 在进程 specialize 时拉起。
# 保留空脚本以满足 Magisk 模块结构约定。
exit 0
