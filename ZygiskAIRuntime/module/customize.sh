#!/system/bin/sh
# Magisk 模块安装期脚本。
# 只做架构校验与产物校验，不做任何注入动作（注入由 Zygisk 在运行时完成）。

ABI_LIST="arm64-v8a armeabi-v7a"

# 至少要有一个 ABI 的产物。
#
# 刻意不做成"列表里每个都必须存在"：模块允许只构建其中一个 ABI
# （例如只出 arm64），硬要求齐全会让单一 ABI 的包装不上。
# 但一个都没有必须中止 —— 那刷进去就是个空壳。
ABI_FOUND=0
for abi in $ABI_LIST; do
  if [ -f "$MODPATH/zygisk/$abi.so" ]; then
    ABI_FOUND=1
  fi
done
if [ "$ABI_FOUND" != "1" ]; then
  abort "! No zygisk/<abi>.so found — build first (see ZygiskAIRuntime/README.md)"
fi

# 只允许本模块需要的 ABI 目录留下，其余移除。
for dir in "$MODPATH"/zygisk/*; do
  [ -e "$dir" ] || continue
  base="$(basename "$dir")"
  case " $ABI_LIST " in
    *" $base "*) ;;
    *) rm -rf "$dir" ;;
  esac
done

# 逐个设置权限，但**必须跳过 webroot**。
#
# KernelSU 官方文档明确警告：安装时 KSU 会自行设置 webroot 目录的权限与
# SELinux context，「如果不知道自己在做什么，请不要自行设置该目录的权限」。
# 这里若沿用原来的 set_perm_recursive "$MODPATH"，会把 KSU 设好的 context
# 与权限一起覆盖掉，结果是模块 WebUI 在管理器里加载失败（页面打不开）。
#
# 同时顺手修正权限粒度：脚本 0755，其它文件 0644（原来整棵树的文件都是 0644）。
for item in "$MODPATH"/*; do
  [ -e "$item" ] || continue
  [ "$(basename "$item")" = "webroot" ] && continue
  if [ -d "$item" ]; then
    set_perm_recursive "$item" 0 0 0755 0644
  else
    case "$item" in
      *.sh) set_perm "$item" 0 0 0755 ;;
      *)    set_perm "$item" 0 0 0644 ;;
    esac
  fi
done
