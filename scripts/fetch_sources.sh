#!/usr/bin/env bash
# Android AI Dynamic Analysis Platform —— 第三方源码拉取脚本
# 用法：bash scripts/fetch_sources.sh
#
# 通道：**codeload zip**，不用 git clone。
#   本机代理对 github.com 的 git 协议不稳定（间歇 502 / Empty reply from server），
#   而 codeload.github.com 的 zip 通道稳定。代价是本地没有 .git，无法 git pull。
#   releases/download 域名同样被代理拒绝 —— 二进制与官方 devkit 都拿不到。
#
# 落位（2026-09-19 改版）：
#   核心 2 个  → ZygiskAIRuntime/third_party/
#   其余全部  → external/（外置，不进核心工程树）
#   锁定表    → docs/00-权威基线/SOURCE_LOCK.md（手工维护，本脚本只产原始日志）
#
# 产物日志：external/_fetch_log.tsv

set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXTERNAL="$ROOT/external"
CORE="$ROOT/ZygiskAIRuntime/third_party"
TMP="$(mktemp -d)"
LOG="$EXTERNAL/_fetch_log.tsv"

mkdir -p "$EXTERNAL" "$CORE"
: > "$LOG"
printf 'name\trepo\tref\ttarget\tstatus\tsize_mb\n' >> "$LOG"

# fetch_zip <name> <owner/repo> <ref> <解压后目标目录>
#   ref 为空则取默认分支 HEAD
fetch_zip() {
  local name="$1" repo="$2" ref="$3" dest="$4"
  echo ">>> [$name] $repo @ ${ref:-HEAD}"

  if [ -d "$dest" ] && [ -n "$(ls -A "$dest" 2>/dev/null)" ]; then
    echo "    已存在，跳过"
    printf '%s\t%s\t%s\t%s\tSKIP_EXISTING\t-\n' "$name" "$repo" "${ref:-HEAD}" "$dest" >> "$LOG"
    return 0
  fi

  local url zip rc
  if [ -n "$ref" ]; then
    url="https://codeload.github.com/$repo/zip/refs/tags/$ref"
  else
    url="https://codeload.github.com/$repo/zip/refs/heads/master"
  fi
  zip="$TMP/$name.zip"

  curl -sSL --retry 3 --retry-all-errors -o "$zip" "$url" || true
  if [ ! -s "$zip" ]; then
    # 有些仓库默认分支是 main
    url="https://codeload.github.com/$repo/zip/refs/heads/main"
    curl -sSL --retry 3 --retry-all-errors -o "$zip" "$url" || true
  fi
  rc=$?

  if [ ! -s "$zip" ]; then
    echo "    FAILED (empty download)"
    printf '%s\t%s\t%s\t%s\tFAILED\t-\n' "$name" "$repo" "${ref:-HEAD}" "$dest" >> "$LOG"
    return 1
  fi

  mkdir -p "$dest"
  unzip -qo "$zip" -d "$TMP/$name" || {
    echo "    FAILED (unzip)"
    printf '%s\t%s\t%s\t%s\tFAILED\t-\n' "$name" "$repo" "${ref:-HEAD}" "$dest" >> "$LOG"
    return 1
  }

  # zip 顶层是 <repo>-<ref>/，把内容提出来，去掉这层包装
  local inner
  inner="$(find "$TMP/$name" -maxdepth 1 -mindepth 1 -type d | head -1)"
  cp -a "$inner"/. "$dest"/
  rm -rf "$TMP/$name" "$zip"

  local size
  size=$(du -sm "$dest" 2>/dev/null | cut -f1)
  echo "    OK  size=${size}MB"
  printf '%s\t%s\t%s\t%s\tOK\t%s\n' "$name" "$repo" "${ref:-HEAD}" "$dest" "$size" >> "$LOG"
  return 0
}

echo "=================================================="
echo " Phase A —— 核心 2 个（进 ZygiskAIRuntime/third_party/）"
echo "=================================================="
fetch_zip "frida-gum" "frida/frida-gum" "17.18.0" "$CORE/frida-gum/17.18.0"
fetch_zip "lsplant"   "LSPosed/LSPlant" ""        "$CORE/lsplant"

echo "=================================================="
echo " Phase B —— 外置（external/）"
echo "=================================================="
fetch_zip "zygisk-module-sample" "topjohnwu/zygisk-module-sample"   "" "$EXTERNAL/zygisk/zygisk-module-sample"
fetch_zip "mitmproxy"            "mitmproxy/mitmproxy"              "" "$EXTERNAL/network/mitmproxy"
fetch_zip "pcapdroid"            "emanuele-f/PCAPdroid"             "" "$EXTERNAL/network/pcapdroid"
fetch_zip "netbare"              "MegatronKing/NetBare-Android"     "" "$EXTERNAL/network/netbare"
fetch_zip "jadx"                 "skylot/jadx"                      "" "$EXTERNAL/analysis/jadx"
fetch_zip "apktool"              "iBotPeaches/Apktool"              "" "$EXTERNAL/analysis/apktool"
fetch_zip "rizin"                "rizinorg/rizin"                   "" "$EXTERNAL/analysis/rizin"
fetch_zip "r2frida"              "nowsecure/r2frida"                "" "$EXTERNAL/analysis/r2frida"
fetch_zip "mobsf"                "MobSF/Mobile-Security-Framework-MobSF" "" "$EXTERNAL/analysis/mobsf"
fetch_zip "mcp-python-sdk"       "modelcontextprotocol/python-sdk"  "v2.2.0" "$EXTERNAL/mcp/python-sdk"
fetch_zip "mcp-specification"    "modelcontextprotocol/specification" "" "$EXTERNAL/mcp/specification"

rm -rf "$TMP"
echo "=================================================="
echo " DONE —— 日志：external/_fetch_log.tsv"
echo " 注意：zip 快照无 .git，锁定表的 commit 列来自 git ls-remote，需手工回填。"
echo "=================================================="
cat "$LOG"
