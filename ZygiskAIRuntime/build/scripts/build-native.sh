#!/usr/bin/env bash
# 构建本工程 native 层（Zygisk 模块 so），并把产物放到 Magisk 模块目录。
#
# 前置：
#   bash build/scripts/build-gum.sh arm64-v8a      # 产出 libgum.a
#
# 用法：
#   source build/config/toolchain.env
#   bash build/scripts/build-native.sh arm64-v8a
#
# 产物：
#   build/out/<abi>/libai_analyzer.so        （CMake 直接产物）
#   module/zygisk/<abi>.so                   （打包时用的落点，Zygisk 按 ABI 名加载）

set -euo pipefail

ABI="${1:-arm64-v8a}"
API_LEVEL="${ANDROID_API_LEVEL:-30}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [ -z "${ANDROID_NDK_HOME:-}" ] || [ ! -d "${ANDROID_NDK_HOME}" ]; then
  echo "ERROR: source build/config/toolchain.env first (ANDROID_NDK_HOME unset)" >&2
  exit 1
fi
if [ -z "${CMAKE_EXE:-}" ] || [ ! -f "${CMAKE_EXE}" ]; then
  echo "ERROR: source build/config/toolchain.env first (CMAKE_EXE unset)" >&2
  exit 1
fi

TOOLCHAIN="$ANDROID_NDK_HOME/build/cmake/android.toolchain.cmake"
BUILD_DIR="$ROOT/build/out/$ABI"

# cmake.exe 是 **Windows 原生程序**，必须收 D:/... 形式的路径。
# 而脚本里的 $ROOT 来自 Git Bash 的 pwd，是 /d/... 形式，直接传会报
#   CMake Error: The source directory "/d/..." does not exist.
# 这里做一个盘符转换（不依赖 cygpath，纯 bash 实现）。
towin() {
  local p="$1"
  if [[ "$p" == /[a-zA-Z]/* ]]; then
    printf '%s:%s' "$(printf '%s' "${p:1:1}" | tr '[:lower:]' '[:upper:]')" "${p:2}"
  else
    printf '%s' "$p"
  fi
}
ROOT_WIN="$(towin "$ROOT")"
BUILD_DIR_WIN="$(towin "$BUILD_DIR")"
TOOLCHAIN_WIN="$(towin "$TOOLCHAIN")"
OUT_SO="$BUILD_DIR/libai_analyzer.so"
MOD_SO="$ROOT/module/zygisk/$ABI.so"

# ninja 是 Windows 原生程序，cmake 需要知道它在哪（且必须是 D:/ 风格路径）。
NINJA_DIR="$(dirname "${NINJA_EXE:-}")"
[ -d "$NINJA_DIR" ] && PATH="$PATH:$NINJA_DIR"
export PATH

echo "== cmake configure ($ABI, api $API_LEVEL) =="
"$CMAKE_EXE" -S "$ROOT_WIN/native" -B "$BUILD_DIR_WIN" \
  -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE="$TOOLCHAIN_WIN" \
  -DCMAKE_MAKE_PROGRAM="${NINJA_EXE}" \
  -DANDROID_ABI="$ABI" \
  -DANDROID_PLATFORM="android-$API_LEVEL" \
  -DANDROID_STL=c++_static \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CXX_USE_RESPONSE_FILE_FOR_INCLUDES=ON \
  -DZAI_ENABLE_LSPLANT="${ZAI_ENABLE_LSPLANT:-ON}"

echo "== build (ninja) =="
# 这里**不用** `cmake --build`：
# LSPlant 用了 C++20 modules，CMake 会生成 clang-scan-deps 步骤（经 cmd.exe 调用）。
# 实测 `cmake --build` 的 jobserver 与它互相等待：ninja 进程在，但没有任何 clang 子进程，
# 整个构建挂住 26 分钟零进展。直接用 ninja 就正常。
# 路径同样必须是 Windows 风格，否则报 "is not a directory"。
"$NINJA_EXE" -C "$BUILD_DIR_WIN"

if [ ! -f "$OUT_SO" ]; then
  echo "ERROR: expected artifact not found: $OUT_SO" >&2
  exit 1
fi

mkdir -p "$ROOT/module/zygisk"
cp -f "$OUT_SO" "$MOD_SO"

echo "OK: $MOD_SO"
"$ANDROID_NDK_HOME/toolchains/llvm/prebuilt/windows-x86_64/bin/llvm-readelf.exe" -h "$MOD_SO" 2>/dev/null \
  | grep -E "Class|Machine|Type" || true
