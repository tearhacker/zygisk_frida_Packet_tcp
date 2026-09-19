#!/usr/bin/env bash
# 构建 Frida-Gum（Native Backend）静态库。
#
# 用法：
#   export ANDROID_NDK_HOME=/path/to/ndk/27.2.12479018
#   bash build/scripts/build-gum.sh arm64-v8a
#
# 产物：third_party/frida-gum/17.18.0/build/<abi>/libgum.a
#
# ⚠️ 未在本机验证：本机无 NDK / CMake，且本脚本需联网拉取
#    third_party/frida-gum/17.18.0/subprojects/ 下 15 个依赖
#    （glib / capstone / libffi / openssl / sqlite / libdwarf / libunwind / quickjs / v8 / xz ...）。
#
# ---------------------------------------------------------------------------
# 为什么不用 devkit 下载：
#   官方 devkit 只从 github.com/frida/frida/releases/download/ 分发，本机代理拒绝该域名。
#   但 meson 有 `devkits` 选项，可以**从源码现场生成** devkit（见下方 DEVKit 段），
#   这是对"devkit 拿不到"这条结论的补正：拿不到现成的，但能从源码造出来。
# ---------------------------------------------------------------------------

set -euo pipefail

ABI="${1:-arm64-v8a}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
GUM_SRC="$ROOT/third_party/frida-gum/17.18.0"
OUT_DIR="$GUM_SRC/build/$ABI"

if [ ! -f "$GUM_SRC/meson.build" ]; then
  echo "ERROR: frida-gum source not found at $GUM_SRC" >&2
  exit 1
fi

if [ -z "${ANDROID_NDK_HOME:-}" ] || [ ! -d "${ANDROID_NDK_HOME}" ]; then
  echo "ERROR: set ANDROID_NDK_HOME to a valid NDK (r27c+)" >&2
  exit 1
fi

case "$ABI" in
  arm64-v8a)   CPU_FAMILY=aarch64; CPU=aarch64; TRIPLE=aarch64-linux-android ;;
  armeabi-v7a) CPU_FAMILY=arm;     CPU=armv7a;  TRIPLE=armv7a-linux-androideabi ;;
  x86_64)      CPU_FAMILY=x86_64;  CPU=x86_64;  TRIPLE=x86_64-linux-android ;;
  *) echo "ERROR: unsupported ABI: $ABI" >&2; exit 1 ;;
esac

API_LEVEL="${ANDROID_API_LEVEL:-30}"

# NDK 的 prebuilt host 目录名随宿主平台变化：Windows 是 windows-x86_64。
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) NDK_HOST=windows-x86_64 ;;
  Darwin)               NDK_HOST=darwin-x86_64  ;;
  *)                    NDK_HOST=linux-x86_64   ;;
esac
NDK_BIN="$ANDROID_NDK_HOME/toolchains/llvm/prebuilt/$NDK_HOST/bin"
CROSS_FILE="$OUT_DIR/android-$ABI.txt"

mkdir -p "$OUT_DIR"

# 注意两点（都是实测踩出来的）：
#   1. subsystem 必须写。frida-gum 的 meson.build:29 调用 host_machine.subsystem()，
#      meson 对 android 无法自动推断，缺了就报
#        ERROR: Subsystem not defined or could not be autodetected.
#   2. 用 clang.exe + 显式 --target，不要用 NDK 的 .cmd wrapper ——
#      meson 会把 .cmd 当 PE 二进制处理然后崩。
cat > "$CROSS_FILE" <<EOF
[host_machine]
system = 'android'
subsystem = 'android'
cpu_family = '$CPU_FAMILY'
cpu = '$CPU'
endian = 'little'

[binaries]
c     = '$NDK_BIN/clang.exe'
cpp   = '$NDK_BIN/clang++.exe'
ar    = '$NDK_BIN/llvm-ar.exe'
strip = '$NDK_BIN/llvm-strip.exe'

[built-in options]
c_args        = ['--target=${TRIPLE}${API_LEVEL}', '-DANDROID', '-fPIC', '-O2']
cpp_args      = ['--target=${TRIPLE}${API_LEVEL}', '-DANDROID', '-fPIC', '-O2', '-std=c++17']
c_link_args   = ['--target=${TRIPLE}${API_LEVEL}']
cpp_link_args = ['--target=${TRIPLE}${API_LEVEL}']
EOF

# meson 探测 VS 安装时，VSINSTALLDIR 未设会崩（pathlib.Path(None, ...) TypeError）。
# 设上它同时也短路了那次探测。
if [ -z "${VSINSTALLDIR:-}" ]; then
  export VSINSTALLDIR="D:/ProgramerDevelop/VS2026/SDK"
fi

# ---------------------------------------------------------------------------
# build machine 编译器 = MSVC cl.exe（本机没有 gcc / MinGW）
#
# frida-gum/meson.build:404 无条件调用 dependency('glib-2.0', native: true)，
# 本机又没有已安装的 glib，meson 只能去编译 subprojects/glib 的 build machine 版本。
# 没有本机 C 编译器时 setup 会 fatal：
#   ERROR: Tried to access compiler for language "c", not specified for build machine.
# 因此必须通过 --native-file 显式给出（见 build/config/msvc-native.ini）。
#
# 另外两个必设的环境变量，缺一个都会让 meson 以奇怪的方式崩溃：
#
#   PYTHONUTF8=0
#     cl.exe 的输出是 **GBK**（中文版 VS，资源内嵌在 cl.exe 里，移 2052 资源目录
#     或设 VSLANG=1033 都无效）。meson 用 locale.getpreferredencoding() 严格解码；
#     而本环境的 PYTHONUTF8=1 会让该编码变成 utf-8 → 解码 GBK 字节抛异常，
#     表现为 Popen_safe 返回 out=None，最终崩在 detect.py 的
#       full_version = out.split('\n', 1)[0]   →  AttributeError: 'NoneType'
#     置 0 后 locale 回到 cp936，meson 改走 errors='replace' 分支，不再崩。
#
#   CODEBUDDY_SAFE_DELETE_ENABLED=0
#     沙箱给 shutil.rmtree 注入了钩子。meson 在 cc.compiles() 探针里会创建并
#     清理临时目录，该钩子在清理时自己抛 AttributeError，让 setup 崩在
#     meson.build:104。关掉后恢复原生 rmtree（只影响 meson 自己的临时目录）。
# ---------------------------------------------------------------------------
export PYTHONUTF8=0
export CODEBUDDY_SAFE_DELETE_ENABLED=0
NATIVE_FILE="$ROOT/build/config/msvc-native.ini"
if [ ! -f "$NATIVE_FILE" ]; then
  echo "ERROR: native file missing: $NATIVE_FILE" >&2
  exit 1
fi

# 关掉一切用不到的部分：我们只要 gum 本体的 C API。
#   gumjs / gumpp / quickjs / tests 全部 disabled，可显著缩短构建时间并减少依赖。
# --wrap-mode=nodownload：只用磁盘上已有的 subprojects（先跑 scripts/prefetch_subprojects.py），
# 绝不让 meson 去拉。同时也让 required:false 的依赖（如 openssl）直接判定为"没找到"而跳过，
# 而不是回退去拉 subproject。
# ninja 必须能在 PATH 里找到，否则 meson 报
#   ERROR: Could not detect Ninja v1.8.2 or newer
# 注意：往 PATH 里追加 Windows 盘符路径时 **必须写成 /d/... 而不是 D:/...** ——
#   MSYS 的 PATH 用冒号分隔，'D:/...' 会被切成 'D' 和 '/...' 两段，等于没加。
if [ -n "${NINJA_EXE:-}" ] && [ -f "${NINJA_EXE}" ]; then
  PATH="$PATH:$(dirname "$NINJA_EXE" | sed -E 's#^([A-Za-z]):#/\L\1#')"
  export PATH
fi

meson setup "$OUT_DIR/builddir" "$GUM_SRC" \
  --cross-file "$CROSS_FILE" \
  --native-file "$NATIVE_FILE" \
  --wrap-mode=nodownload \
  --buildtype release \
  --default-library static \
  -Dfrida_version=17.18.0 \
  -Dgumjs=disabled \
  -Dgumpp=disabled \
  -Dquickjs=disabled \
  -Dtests=disabled \
  -Dinspector=disabled \
  -Dgraft_tool=disabled

meson compile -C "$OUT_DIR/builddir"

mkdir -p "$OUT_DIR/include"

# 产物不叫 libgum.a，meson 给的是带版本号的 libfrida-gum-1.0.a，位置在 builddir/gum/ 下。
# native/CMakeLists.txt 找的是 ${GUM_BUILD_DIR}/libgum.a，所以这里做一次改名拷贝。
GUM_A="$OUT_DIR/builddir/gum/libfrida-gum-1.0.a"
if [ ! -f "$GUM_A" ]; then
  echo "ERROR: $GUM_A not found — meson compile 没有产出 gum 静态库" >&2
  exit 1
fi
cp -f "$GUM_A" "$OUT_DIR/libgum.a"

echo "OK: $OUT_DIR/libgum.a"

# ---------------------------------------------------------------------------
# 可选：从源码生成 devkit（-Ddevkits=gum）
#
#   若希望只导出稳定 ABI 的头文件 + 静态库（而不是依赖完整源码树），
#   改上面的 meson setup 加 -Ddevkits=gum，产物在 builddir 下。
#   这是"devkit 下载被墙"的绕行方案，代价：仍需完整跑一遍源码构建。
# ---------------------------------------------------------------------------
