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

set_perm_recursive "$MODPATH" 0 0 0755 0644
