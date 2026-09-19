#!/system/bin/sh
# Magisk 模块安装期脚本。
# 只做架构校验与产物校验，不做任何注入动作（注入由 Zygisk 在运行时完成）。

ABI_LIST="arm64-v8a armeabi-v7a"

# ---------------------------------------------------------------------------
# 🔴 必须清掉 Magisk 留下的 "unloaded" 标记
#
# 官方开发者指南写得很明确：
#     zygisk/unloaded  <--- If exists, the native libraries are incompatible
# 一旦这个文件存在，magiskd 就不再把本模块的 so 交给 Zygisk 加载。
#
# 它是模块**加载失败一次**之后被写下来的，而且是永久性的 ——
# 于是会出现最折磨人的一类现象：模块目录在、so 在、安装全程没报错，
# 但模块从头到尾没被加载过一次，用户换成修好的包也照样不生效。
#
# 重新安装/升级时必须主动清掉它。
# ---------------------------------------------------------------------------
rm -f "$MODPATH/zygisk/unloaded"

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
#
# 🔴 必须只处理【目录】，不能碰到文件。
# 本模块的产物是扁平的 zygisk/<abi>.so（不是 zygisk/<abi>/ 目录）。
# 早期这里写的是 `[ -e "$dir" ] || continue`，于是 arm64-v8a.so 进了循环：
# basename = "arm64-v8a.so" 不在 ABI_LIST 里 → 命中通配分支 → rm -rf。
# 结果：ABI 校验（在删除之前）顺利通过、安装全程不报错、模块目录也在，
# 但 zygisk/ 被清空 → Zygisk 加载不到 so → Runtime 永不启动 → 60500 永远连不上。
# 属于"安装成功但功能是空的"最阴险的一类故障：现场看不到任何错误。
for dir in "$MODPATH"/zygisk/*; do
  [ -d "$dir" ] || continue
  base="$(basename "$dir")"
  case " $ABI_LIST " in
    *" $base "*) ;;
    *) rm -rf "$dir" ;;
  esac
done

# 清理后自检：前面两步之间任何一处改坏，都会把 so 弄没。
# 这里再数一次，数量归零就直接中止并说明原因 —— 宁可装不上，也不要装一个空壳。
SO_COUNT=0
KEPT=""
for f in "$MODPATH"/zygisk/*.so; do
  [ -f "$f" ] || continue

  # 顺手校验它确实是 ELF 文件（magic = 7f 45 4c 46 = ".ELF"）。
  #
  # 挡的是这一类事故：某个环节把空文件 / 文本 / 错变体的产物落成了
  # zygisk/<abi>.so。安装期看不出来，Zygisk 加载时才会失败，
  # 而失败之后又只留下一个 unloaded 标记 —— 排查成本极高。
  # 宁可在这里中止安装。
  magic="$(dd if="$f" bs=4 count=1 2>/dev/null | od -An -tx1 | tr -d ' \n')"
  if [ "$magic" != "7f454c46" ]; then
    abort "! $(basename "$f") 不是 ELF 文件 (magic=$magic)，中止以避免刷入坏模块"
  fi

  SO_COUNT=$((SO_COUNT + 1))
  KEPT="$KEPT $(basename "$f")"
done
if [ "$SO_COUNT" -eq 0 ]; then
  abort "! zygisk/ 下已无 .so（安装脚本自身清理逻辑有误），中止以避免刷入空壳模块"
fi
if command -v ui_print >/dev/null 2>&1; then
  ui_print "- Zygisk payload: $SO_COUNT so:$KEPT"

  # 默认配置里全是注释（= 不注入任何 App）。不提示的话，用户刷完模块的
  # 第一反应一定是"装了没反应" —— 因为空配置本来就不会有任何动作。
  # 把配置文件路径和"改完要重启 App"这两件事直接打在安装界面上。
  ui_print "- 目标包名配置: $MODPATH/target.conf"
  ui_print "- 现在默认是空的（不注入任何 App），改完需重启目标 App"
  ui_print "- 目标 App 不要放进 Magisk 排除列表(DenyList)，否则不会注入"
fi

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

# ---------------------------------------------------------------------------
# 🔴 zygisk/<abi>.so 必须带可执行位（2026-09-19 真机事故）
#
# 上面那轮循环对**目录**走的是
#     set_perm_recursive "$item" 0 0 0755 0644
# 这条命令会把目录设成 0755、而**目录里的文件一律 0644** ——
# 于是 zygisk/<abi>.so 也被刷成了 0644。
#
# linker 加载 native lib 时要以 PROT_EXEC 映射这段文件，缺 x 位 → dlopen 失败；
# 而 Zygisk 对"加载失败"这件事只在 zygisk/unloaded 留一个标记、不打任何日志，
# 现场表现是：模块装上了、目录在、so 在、安装全程零报错，但模块从不生效。
# 属于"安装成功但功能是空的"那一类，不特意查权限根本发现不了。
#
# 所以必须在递归之后**单独**把 so 的权限改回来（顺序不能反，反了会被覆盖）。
#
# 0755 足够：owner(root) rwx，其余 r-x，dlopen 只看得到 r+x。
# 0777 多出来的只是 group/other 写位，Android 上没有实际收益；
# 坚持要 777 就把下面的 0755 改成 0777（打包侧的 scripts/package.py --so-mode 同步改）。
# ---------------------------------------------------------------------------
for so in "$MODPATH"/zygisk/*.so; do
  [ -f "$so" ] || continue
  set_perm "$so" 0 0 0755
done

# 显式归零：本文件是被 source 的（不能 exit，那会把安装器一起干掉），
# 而 update-binary 的兜底路径用 `. customize.sh || abort` 接返回值。
# 上面循环的最后一条命令若返回非零（例如 chown 失败），会被误判为安装失败。
true
