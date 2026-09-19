#!/usr/bin/env bash
# M2 Walking Skeleton —— 真机验证辅助脚本。
#
# 做什么：
#   1. 采集设备信息（ABI / Android 版本 / Magisk / Zygisk 状态），判断是否满足刷入前提
#   2. 把 Magisk 模块 zip 推到手机
#   3. 抓 logcat，按本模块的 tag 过滤，给出可核对的证据
#
# 不做什么（重要）：
#   - 不自动刷入、不自动重启、不修改系统分区。
#     Magisk 模块安装必须由 Magisk App 完成（脚本只能 push 文件）。
#   - 不做任何破坏性操作。
#
# 用法：
#   source build/config/toolchain.env     # 提供 ADB_EXE
#   bash scripts/verify_device.sh check    # 只采集信息，不做任何改动
#   bash scripts/verify_device.sh push     # 推 zip 到 /sdcard/Download/
#   bash scripts/verify_device.sh log      # 抓本模块的 logcat（Ctrl-C 结束）
#   bash scripts/verify_device.sh all      # check + push，然后提示手工安装
#
# ⚠️ 本机无 ARM64 设备，本脚本**未经实机运行验证**，只做了语法检查。

set -uo pipefail

ABI="${ABI:-arm64-v8a}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ZIP="$ROOT/build/out/zygisk-ai-runtime.zip"
MODULE_ID="zygisk-ai-runtime"
TAGS="ZAI:Zygisk ZAI:Gum ZAI:Runtime"

ADB="${ADB_EXE:-adb}"
if ! command -v "$ADB" >/dev/null 2>&1; then
    ADB="C:/Program Files/platform-tools/adb.exe"
fi

die() { echo "ERROR: $*" >&2; exit 1; }

require_device() {
    "$ADB" start-server >/dev/null 2>&1 || true
    local count
    count="$("$ADB" devices 2>/dev/null | grep -c $'\tdevice$')"
    [ "$count" -ge 1 ] || die "没有检测到 adb 设备（$ADB devices 为空）。请接线并授权 USB 调试。"
}

do_check() {
    require_device

    echo "=== 设备 ==="
    "$ADB" shell getprop ro.product.manufacturer 2>/dev/null | tr -d '\r'
    "$ADB" shell getprop ro.product.model 2>/dev/null | tr -d '\r'

    echo
    echo "=== 架构（必须包含 $ABI）==="
    local abilist
    abilist="$("$ADB" shell getprop ro.product.cpu.abilist 2>/dev/null | tr -d '\r')"
    echo "  ro.product.cpu.abilist = $abilist"
    case "$abilist" in
        *"$ABI"*) echo "  ✅ ABI 匹配" ;;
        *)        echo "  ❌ 设备不支持 $ABI，本模块刷入后 customize.sh 会 abort" ;;
    esac

    echo
    echo "=== Android / API ==="
    echo "  release = $("$ADB" shell getprop ro.build.version.release 2>/dev/null | tr -d '\r')  (sdk $("$ADB" shell getprop ro.build.version.sdk 2>/dev/null | tr -d '\r'))"

    echo
    echo "=== Magisk / Zygisk ==="
    local magisk_ver zygisk
    magisk_ver="$("$ADB" shell "su -c magisk -v" 2>/dev/null | tr -d '\r' | head -1)"
    echo "  magisk -v      = ${magisk_ver:-<取不到，可能未 root 或 su 被拒>}"
    # Zygisk 是否启用：magisk --sqlite 或直接看 zygisk 相关目录
    zygisk="$("$ADB" shell "su -c 'magisk --sqlite \"SELECT value FROM settings WHERE key=\\\"zygisk\\\"\"'" 2>/dev/null | tr -d '\r')"
    echo "  zygisk setting = ${zygisk:-<取不到>}"
    echo "  （Zygisk 必须在 Magisk 设置里开启，否则本模块不会被注入）"

    echo
    echo "=== 模块是否已安装 ==="
    if "$ADB" shell "su -c 'test -d /data/adb/modules/$MODULE_ID'" >/dev/null 2>&1; then
        echo "  ✅ 已安装：/data/adb/modules/$MODULE_ID"
        "$ADB" shell "su -c 'ls -l /data/adb/modules/$MODULE_ID'" 2>/dev/null | tr -d '\r' | sed 's/^/     /'
    else
        echo "  ⬜ 尚未安装"
    fi

    echo
    echo "=== 当前 disable / remove 标记 ==="
    "$ADB" shell "su -c 'ls /data/adb/modules/$MODULE_ID/disable  /data/adb/modules/$MODULE_ID/remove 2>/dev/null'" 2>/dev/null | tr -d '\r' | sed 's/^/     /'
    echo "  （若列了 disable 或 remove，模块不会生效）"
}

do_push() {
    [ -f "$ZIP" ] || die "找不到 $ZIP —— 先跑 python scripts/package.py"
    require_device
    echo "pushing $ZIP -> /sdcard/Download/"
    "$ADB" push "$ZIP" "/sdcard/Download/zygisk-ai-runtime.zip" || die "push 失败"
    echo
    echo "下一步（必须手工）："
    echo "  Magisk App → 模块 → 从本地安装 → 选 /sdcard/Download/zygisk-ai-runtime.zip"
    echo "  安装完成后重启，再跑："
    echo "      bash scripts/verify_device.sh log"
}

do_log() {
    require_device
    echo "抓 logcat，过滤：$(echo $TAGS | tr ' ' ',')"
    echo "（Ctrl-C 结束；若长时间无输出，说明模块没被加载）"
    echo
    # -s 静默其它 tag；同时保留 Magisk 的关键日志，便于区分"没注入"和"注入后崩"
    "$ADB" logcat -v brief -s $TAGS Magisk:V 2>/dev/null
}

case "${1:-all}" in
    check) do_check ;;
    push)  do_push ;;
    log)   do_log ;;
    all)   do_check; echo; do_push ;;
    *)     echo "用法: $0 {check|push|log|all}" >&2; exit 1 ;;
esac
