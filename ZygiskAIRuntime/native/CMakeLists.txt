# Zygisk AI Runtime —— 主构建（CMake + NDK）
#
# 🔴 构建前置条件（本机当前不满足，见 ../README.md 构建状态）：
#   1. NDK r27c+ 与 CMake 3.28+（本机未安装）
#   2. CMake ≥ 3.28 的原因：LSPlant 提供 `lsplant.ixx`（C++20 modules），
#      低于 3.28 的 CMake 无法驱动 module 编译
#   3. Frida-Gum 必须先由 ../build/scripts/build-gum.sh 构建出 libgum.a
#
# 用法：
#   cmake -S native -B build/out/arm64-v8a \
#     -DCMAKE_TOOLCHAIN_FILE=$ANDROID_NDK/build/cmake/android.toolchain.cmake \
#     -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-30
#   cmake --build build/out/arm64-v8a
#
# 产物：libai_analyzer.so → 拷到 module/zygisk/<abi>.so 由 Zygisk 加载

cmake_minimum_required(VERSION 3.28)
project(ai_analyzer CXX C)

# LSPlant 自带 CMakeLists 用 C++23；本项目代码向下兼容，统一跟随 23。
set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_C_STANDARD 11)

set(ZAI_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/..")
set(ZAI_ABI "${ANDROID_ABI}")

if(NOT ZAI_ABI)
    set(ZAI_ABI "arm64-v8a")   # 首发 ABI
endif()

# ---------------------------------------------------------------------------
# 1. Frida-Gum（Native Backend）—— 预构建静态库
#
#    静态链接是允许的：Frida-Gum 为 wxWindows Library Licence 3.1。
#    devkit 拿不到（releases/download 域名被代理拒绝），只能源码构建。
# ---------------------------------------------------------------------------
set(GUM_ROOT "${ZAI_ROOT}/third_party/frida-gum/17.18.0")
set(GUM_BUILD_DIR "${GUM_ROOT}/build/${ZAI_ABI}" CACHE PATH "build-gum.sh 的输出目录")
set(GUM_LIB "${GUM_BUILD_DIR}/libgum.a")

if(NOT EXISTS "${GUM_LIB}")
    message(FATAL_ERROR
        "libgum.a not found at ${GUM_LIB}. "
        "Run ../build/scripts/build-gum.sh ${ZAI_ABI} first.")
endif()

add_library(gum STATIC IMPORTED)
set_target_properties(gum PROPERTIES IMPORTED_LOCATION "${GUM_LIB}")

# gum 真正使用的 include 目录 + 它依赖的那些静态库。
#
# 不能靠 GLOB 猜：实测漏了两处，会直接编译不过 ——
#   1. capstone 的头文件在 subprojects/capstone/include/**capstone**/ 下，
#      只挂 include 会得到 gumdefs.h:12: fatal error: 'capstone.h' file not found
#   2. glib 的头文件分散在 glib/ · gobject/ · gio/ · gmodule/ 各自子目录，
#      且 glibconfig.h 一类是 meson **生成在 builddir 里** 的，源码树上没有。
#
# 权威来源是 meson 自己的编译命令，由 build/scripts/gen_gum_include_dirs.py 从
# builddir/compile_commands.json 提取到 build/generated/gum_includes.cmake。
set(GUM_GENERATED_CMAKE "${ZAI_ROOT}/build/generated/gum_includes.cmake")
if(EXISTS "${GUM_GENERATED_CMAKE}")
    include("${GUM_GENERATED_CMAKE}")
else()
    set(GUM_INCLUDE_DIRS "")
    set(GUM_DEP_LIBS "")
    message(WARNING
        "${GUM_GENERATED_CMAKE} not found. "
        "Run: python build/scripts/gen_gum_include_dirs.py")
endif()

# Gum 依赖 glib / capstone / libffi / json-glib / openssl 等 subprojects。
#
# ⚠️ 头文件位置有两个坑（实测发现）：
#   1. build-gum.sh 只 `mkdir` 了空的 ${GUM_BUILD_DIR}/include，**没有往里拷头文件**，
#      所以只挂这一个目录等于没挂。
#   2. 真正的头文件在**源码树**的 subprojects/<name>/include 下
#      （例如 capstone.h 在 subprojects/capstone/include/capstone/），
#      以及 meson builddir 的 subprojects/<name>/include。
# 因此四个位置全部挂上，缺一个就会出现
#   gumdefs.h: fatal error: 'capstone.h' file not found
# 注意：GUM_INCLUDE_DIRS 这个名字**不要在这里 set** ——
# 它会由上面 include 进来的 build/generated/gum_includes.cmake 提供完整列表。
# 这里只保留 GLOB 出来的 subproject include 作为兜底（GUM_SUBPROJECT_INCLUDE_DIRS）。

# ---------------------------------------------------------------------------
# 过滤掉会**遮蔽编译器自带标准头**的 include 目录。
#
# 实测踩过：subprojects/tinycc/include 下放着 tinycc 自己的 C 标准头
# （stddef.h / stdarg.h / stdbool.h / float.h ...）。一旦把它挂进 -I，
#   clang 的 stddef.h 就被遮蔽 → 全局 nullptr_t 不再有定义 →
#   libc++ 的 <string> / <string_view> 全线炸：
#     error: unknown type name 'nullptr_t'
#     error: only functions can have deleted definitions
#   （报错点离真实原因很远，很容易误判成工具链坏了。）
# ---------------------------------------------------------------------------
function(zai_filter_unsafe_includes out_var)
    set(_safe "")
    foreach(_d IN LISTS ARGN)
        set(_bad FALSE)
        foreach(_h IN ITEMS stddef.h stdarg.h stdbool.h float.h stdint.h stdalign.h stdnoreturn.h)
            if(EXISTS "${_d}/${_h}")
                set(_bad TRUE)
            endif()
        endforeach()
        if(NOT _bad)
            list(APPEND _safe "${_d}")
        endif()
    endforeach()
    set(${out_var} "${_safe}" PARENT_SCOPE)
endfunction()

zai_filter_unsafe_includes(GUM_SAFE_INCLUDES
    ${GUM_INCLUDE_DIRS}
    ${GUM_SUBPROJECT_INCLUDE_DIRS}
)
file(GLOB GUM_SUBPROJECT_INCLUDE_DIRS
    "${GUM_BUILD_DIR}/subprojects/*/include"
    "${GUM_ROOT}/subprojects/*/include"
)
message(STATUS "gum include dirs: ${GUM_BUILD_DIR}/include + ${GUM_SUBPROJECT_INCLUDE_DIRS}")

# ---------------------------------------------------------------------------
# 2. LSPlant（ART Backend）—— 必须 SHARED
#
#    🔴 LSPlant 是 LGPL-3.0，静态嵌入会触发"允许用户替换并重链接"义务。
#       这里强制 LSPLANT_BUILD_SHARED=ON，产出独立 liblsplant.so。
#       详见 ../../docs/LICENSES.md 约束 #1。
# ---------------------------------------------------------------------------
set(LSPLANT_BUILD_SHARED ON CACHE BOOL "" FORCE)

# ---------------------------------------------------------------------------
# ZAI_ENABLE_LSPLANT：是否构建并链接 LSPlant（ART / Java Hook 后端）
#
# 默认 ON。**当前本机需要临时置 OFF 才能编出产物**，原因是第三方源码与工具链不兼容：
#   LSPlant master 的 art_method.cxx 用了很重的 C++20/23 模板元编程
#   （`_sym.hook->* []<MemBackup auto backup>(...)` 模板 lambda），
#   NDK r27d 的 clang 18 把 backup 解析成了 hook_helper.hpp:256 那个**无参** lambda：
#     error: too many arguments to function call, expected 0, have 1
#     error: called object type 'auto (lambda ... ::*)() const -> void' is not a function
#   按 STRUCTURE.md 的边界规则，third_party 源码不得修改，所以只能先关掉。
#
# 关掉**不会造成功能损失**：lsplant_adapter.cpp 目前没有任何真实 lsplant:: 调用
# （全是 TODO(M3)），ART 后端本来就是 M3 才接线。
# 本构建仍然是真实的 arm64 Zygisk 模块，Frida-Gum 已静态链入。
#
# 恢复条件：换 NDK r28+（clang ≥19），或把 LSPlant 固定到与 clang 18 兼容的 tag。
# ---------------------------------------------------------------------------
option(ZAI_ENABLE_LSPLANT "Build and link LSPlant (ART backend)" ON)
# LSPLANT_STANDALONE 必须为 OFF。
#
# 它的语义是「用外部提供的 libc++（find_package(cxx)）构建」，不是「独立于 Java 侧」。
# 打开会让 LSPlant 的 CMakeLists 执行 find_package(cxx REQUIRED CONFIG)，
# 而 LSPlant 仓库里并不含 cxx 包（只有 external/dex_builder），
# 本机也没有 libc++ 的 CMake 包 —— 直接报：
#   Could not find a package configuration file provided by "cxx"
# NDK 交叉编译场景应当用 NDK 自带的 STL，因此保持 OFF，且不加 FORCE，
# 留出命令行覆盖的余地。
set(LSPLANT_STANDALONE OFF CACHE BOOL "Use an external libc++ package; must stay OFF for NDK builds")
set(ANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES ON CACHE BOOL "" FORCE)  # Android 15+ 16KB 页
# ⚠️ 这一行原来无条件把 ANDROID_STL 设成 c++_shared（本意是给 LSPlant 这个独立
# shared lib 用的），但 `set(... CACHE ... FORCE)` 是**全局**的，
# 关掉 LSPlant 后它依然生效，结果本模块也跟着依赖 libc++_shared.so。
#
# 后果很实际：模块是被 Zygisk 在 zygote 里 dlopen 的，
# 一旦运行环境里没有 libc++_shared.so，模块直接加载失败（而且报错很不直观）。
# 本模块自身必须静态链 STL。
if(ZAI_ENABLE_LSPLANT)
    set(ANDROID_STL "c++_shared" CACHE STRING "" FORCE)
else()
    set(ANDROID_STL "c++_static" CACHE STRING "" FORCE)
endif()

if(ZAI_ENABLE_LSPLANT)
    add_subdirectory(
        "${ZAI_ROOT}/third_party/lsplant/lsplant/src/main/jni"
        "${CMAKE_BINARY_DIR}/lsplant"
    )
else()
    message(WARNING
        "ZAI_ENABLE_LSPLANT=OFF —— 不构建 LSPlant，ART / Java Hook 后端在本构建中不可用"
        "（LSPlant master 与 NDK clang 18 不兼容，详见本文件注释）。"
        "Runtime / Gum / Zygisk 注入链路不受影响。")
endif()

# ---------------------------------------------------------------------------
# 3. 本工程源码
# ---------------------------------------------------------------------------
add_library(ai_analyzer SHARED
    # --- Zygisk Host（Entry / Bootstrap，不含分析逻辑）---
    "${ZAI_ROOT}/zygisk/module.cpp"
    "${ZAI_ROOT}/zygisk/entry.cpp"
    "${ZAI_ROOT}/zygisk/bootstrap.cpp"

    # --- Runtime Core ---
    "${ZAI_ROOT}/runtime/runtime.cpp"
    "${ZAI_ROOT}/runtime/backend/gum/gum_backend.cpp"
    "${ZAI_ROOT}/runtime/backend/art/art_backend.cpp"
    "${ZAI_ROOT}/runtime/backend/art/lsplant_adapter.cpp"
    "${ZAI_ROOT}/runtime/manager/hook_manager.cpp"
    "${ZAI_ROOT}/runtime/manager/memory_manager.cpp"
    "${ZAI_ROOT}/runtime/manager/process_manager.cpp"

    # --- Native 能力层 ---
    src/common/log.cpp
)

target_include_directories(ai_analyzer PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}/include"
    # 使 #include "runtime/runtime.h" 成立。
    # ⚠️ 把工程根目录挂进 -I 有一个坑：Windows 文件系统**大小写不敏感**，
    #    根目录下任何与标准头同名的文件都会抢先被 #include 命中。
    #    实测踩过：根目录的 VERSION 文件被 C++20 标准头 #include <version> 匹配，
    #    于是 libc++ 的 __config 没能正确展开，报
    #      error: use of undeclared identifier 'nullptr_t'
    #    现已改名 VERSION.txt。**不要再往工程根目录加与标准头同名的文件。**
    "${ZAI_ROOT}"
    "${GUM_ROOT}"                     # <gum/gum.h>
    ${GUM_SAFE_INCLUDES}
    "${ZAI_ROOT}/third_party/lsplant/lsplant/src/main/jni/include"
)

# ZAI_TRACE_BOOTSTRAP：在每个 App 进程 specialize 时打一条日志。
#
# 用途：骨架阶段 load_target_config() 恒返回 enabled=false，模块加载后即 DLCLOSE，
#       只靠 on_load 一条日志无法确认"Zygisk 注入链路是否真的通了"。
#       打开后每个 App 启动都会留痕，便于在真机上确认模块确实被注入并执行了过滤。
# 默认：Debug（测试版）自动打开，Release 关闭 —— 否则日志量太大。
option(ZAI_TRACE_BOOTSTRAP "Log every app specialize (verbose)" OFF)

if(ZAI_TRACE_BOOTSTRAP OR CMAKE_BUILD_TYPE STREQUAL "Debug")
    message(STATUS "ZAI_TRACE_BOOTSTRAP=1 (verbose bootstrap logging)")
    target_compile_definitions(ai_analyzer PRIVATE ZAI_TRACE_BOOTSTRAP=1)
endif()

target_compile_definitions(ai_analyzer PRIVATE
    ZAI_MODULE_NAME="ai_analyzer"
)

# Zygisk 模块 so 要被 zygote dlopen，STL 静态链接避免依赖 libc++_shared.so 的加载时机。
set_target_properties(ai_analyzer PROPERTIES
    ANDROID_STL "c++_static"
    CXX_VISIBILITY_PRESET hidden
    VISIBILITY_INLINES_HIDDEN ON
    # 关掉 C++20 modules 依赖扫描（clang-scan-deps）。
    # 两个原因：
    #   1. 本 target **不使用** modules —— modules 只被 LSPlant 用（lsplant.ixx 等），
    #      它有自己的 target，不受这里影响。
    #   2. 必须关，否则编译不过：CMake 把 scan-deps 包在 **cmd.exe /C** 里执行，
    #      而 cmd.exe 的命令行上限是 **8192 字符**（不是 CreateProcess 的 32767）。
    #      本项目要挂 ~100 个 gum/glib 的 include 目录，且工程路径含中文（很长），
    #      拼出来的命令必然超限，ninja 直接报「命令行太长」。
    #      -DCMAKE_CXX_USE_RESPONSE_FILE_FOR_INCLUDES=ON 对这条自定义命令不生效。
    CXX_SCAN_FOR_MODULES OFF
)

# libgum.a **不含** glib / capstone / libffi / json-glib / libunwind / libdwarf / xz，
# 这些必须由 GUM_DEP_LIBS 一起链进来，否则链接期满屏 undefined symbol。
# 静态库之间存在循环依赖，用 --start-group/--end-group 让链接器反复扫描。
target_link_libraries(ai_analyzer PRIVATE
    -Wl,--start-group
    gum
    ${GUM_DEP_LIBS}
    -Wl,--end-group
    log
    dl
)

if(ZAI_ENABLE_LSPLANT)
    target_link_libraries(ai_analyzer PRIVATE lsplant)
endif()
