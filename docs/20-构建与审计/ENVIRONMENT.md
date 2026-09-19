# ENVIRONMENT —— PC 构建环境审计

**产出依据**：施工手册 P-1.4 · 专业开发技术指导总文档 §3.4
**审计日期**：2026-09-19
**审计方式**：逐项实机探测（`command -v` + `--version` + **全盘遍历**），**非人工填写**
**结论**：**P-1a PASS · P-1b 6/7 PASS**（唯一剩余阻塞是真机设备，详见 `BUILD_BLOCKERS.md`）

> 🔴 **本文件已于 2026-09-19 修正。** 首轮审计只探了 `PATH`，误判「NDK / CMake / Ninja 全缺」。
> 实际这三者**本来就装在机器上**（VS Professional 2026 自带 CMake + Ninja，
> 另有独立 NDK r27d），只是没进 `PATH`。修正依据见 §1 与 §6。

---

## 1. 工具链表

| Tool | Version | Path | Expected | Actual | 判定 |
|---|---|---|---|---|---|
| **Python**（venv） | 3.13.14 | `~/.workbuddy-ai/binaries/python/envs/default/Scripts/python.exe` | ≥ 3.11 | 3.13.14 | ✅ PASS |
| **Python**（managed） | 3.13.14 | `~/.workbuddy-ai/binaries/python/versions/3.13.12/python.exe` | ≥ 3.11 | 3.13.14 | ✅ PASS |
| **Git** | 2.55.0.windows.3 | `/mingw64/bin/git` | 任意 | 2.55.0 | ✅ PASS |
| **ADB** | 1.0.41 | `C:\Program Files\platform-tools\adb.exe` | 任意 | 1.0.41 | ✅ PASS |
| **JDK** | 21.0.11 LTS | `C:\Program Files\Common Files\Oracle\Java\javapath\java.exe` | ≥ 17 | 21.0.11 | ✅ PASS |
| **javac** | 21.0.11 | 同上 | ≥ 17 | 21.0.11 | ✅ PASS |
| **Node** | v22.22.2 | `~/.workbuddy-ai/binaries/node/versions/22.22.2-2/node.exe` | 任意 | 22.22.2 | ✅ PASS |
| **npm** | 10.9.7 | 同上 | 任意 | 10.9.7 | ✅ PASS |
| **Android SDK build-tools** | 33.0.1 / 36.1.0 / 37.0.0 | `%LOCALAPPDATA%\Android\Sdk\build-tools` | 任意 | 3 个版本 | ✅ PASS |
| **Android SDK platforms** | android-33 / 34 / 36.1 | `%LOCALAPPDATA%\Android\Sdk\platforms` | ≥ 34 | 3 个 | ✅ PASS |
| **platform-tools** | 1.0.41 | `%LOCALAPPDATA%\Android\Sdk\platform-tools` | 任意 | 完整 | ✅ PASS |
| **Android NDK** | **r27d**（27.3.13750724） | `D:\ProgramerDevelop\windowsNDK27` | **r27c+** | r27d ✅ | ✅ **PASS** |
| **clang**（随 NDK） | **18.0.4** | `…/windowsNDK27/toolchains/llvm/prebuilt/windows-x86_64/bin/` | 任意 | 18.0.4 | ✅ **PASS** |
| **CMake** | **4.3.1**（msvc1） | `D:\ProgramerDevelop\VS2026\SDK\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe` | **3.28+** | 4.3.1 ✅ | ✅ **PASS** |
| **Ninja** | **1.13.2** | `…\Microsoft\CMake\Ninja\ninja.exe` | 任意 | 1.13.2 | ✅ **PASS** |
| **Meson** | **1.12.0** | `~/.workbuddy-ai/binaries/python/envs/default/Scripts/meson.exe`（pip 装） | 任意 | 1.12.0 | ✅ **PASS** |
| **Visual Studio Professional** | **2026**（18.9.12120.119） | `D:\ProgramerDevelop\VS2026\SDK` | 任意 | 已装 | ✅ PASS |
| **Android Studio** | — | `D:\ProgramerDevelop\ASstudio`（含 jbr） | 任意 | 已装 | ✅ PASS |
| **MSVC（cl.exe / link.exe）** | **19.51.36256**（v145） | `D:\ProgramerDevelop\VS2026\SDK\VC\Tools\MSVC\14.51.36231\bin\Hostx64\x64` | 任意 | 可用 | ✅ **PASS**（meson 的 **build machine** 编译器） |
| **Windows SDK** | **10.0.26100.0** | **`D:\Windows Kits\10`** | 任意 | 已装 | ✅ **PASS** |
| **cmdline-tools**（sdkmanager） | — | `%LOCALAPPDATA%\Android\Sdk\cmdline-tools` | 任意 | **不存在** | ⚪ 非必需（NDK 已独立就位） |
| **pkg-config** | — | PATH | 任意 | **不存在** | 🟠 已用 `build/scripts/fake-pkg-config.py` 替身 |
| **setuptools**（base 3.13.12） | — | — | 任意 | 已装 | ✅ gdbus-codegen 需要 `distutils`（3.12+ 已移除） |
| **Gradle** | — | PATH | 任意 | 不存在 | ⚪ 本项目用 CMake，非必需 |

### 1.1 两条容易踩空的环境事实

**① Windows SDK 不在 C 盘，在 `D:\Windows Kits\10`。**
`C:\Program Files (x86)\Windows Kits` 是空的，而 MSVC 的 include 目录里连 `stdio.h` 都没有
（cl.exe 单独拿出来是"裸"的）。`vcvarsall.bat` 又跑不了（cmd.exe 被安全策略禁用），
所以 `INCLUDE` / `LIB` 必须**手工拼**，已固化进 `build/config/toolchain.env` 的 MSVC 段。

**② pkg-config 不存在，但 meson 的 build machine 依赖查找会用。**
只影响一处：`frida-gum/meson.build:404` 的 `dependency('glib-2.0', native: true)`。
替身只认 glib 家族，其余模块一律返回"未找到"，不会误伤其它依赖判断。

## 2. 环境变量

| 变量 | 期望 | 实际 | 判定 |
|---|---|---|---|
| `ANDROID_NDK_HOME` | 指向 NDK 根 | **unset**（NDK 本体存在） | 🟠 WARN |
| `ANDROID_HOME` | 指向 SDK 根 | **unset** | 🟠 WARN |
| `ANDROID_SDK_ROOT` | 指向 SDK 根 | **unset** | 🟠 WARN |

> 环境变量未设**不阻塞 M1** —— 已把实测路径固化到
> `ZygiskAIRuntime/build/config/toolchain.env`，`source` 一下即可：

```bash
source ZygiskAIRuntime/build/config/toolchain.env
# → ANDROID_NDK_HOME / CMAKE_EXE / NINJA_EXE / MESON_EXE / ADB_EXE 全部就位
```

> ⚠️ **踩过的坑**：`cmake.exe` / `ninja.exe` 是 Windows 原生程序，
> 必须传 **Windows 风格路径**（`D:/…`）。传 Git Bash 的 `/d/…` 会报
> `no such file or directory`。

## 3. CMake 版本下限为什么是 3.28

不是随意定的：

```text
LSPlant 要求 C++23 + C++20 modules（源码里有 lsplant.ixx）
  → CMake 必须 ≥ 3.28 才支持 C++20 modules 的 Android 交叉编译
  → 3.22（曾被短暂装过又按要求删除）不够用
```

## 4. 工具链端到端验证（2026-09-19 实测通过）

不只看版本号，实际编译验证过：

```text
① 直接交叉编译 C++23 → aarch64
   aarch64-linux-android30-clang++ -std=c++23 -fPIC -c probe.cpp
   → probe.o 69560 bytes，llvm-readelf: ELF64 / Machine: AArch64        ✅

② CMake + Ninja + NDK toolchain 端到端出共享库
   cmake -G Ninja -DCMAKE_TOOLCHAIN_FILE=<NDK>/build/cmake/android.toolchain.cmake \
         -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-30
   → libprobe.so 693440 bytes，ELF64 / DYN (Shared object) / AArch64     ✅
```

③ **真实项目产物**（2026-09-19，M1 完成）
```
meson 交叉编译 Frida-Gum 17.18.0            → 1089/1089 目标全部完成
   产出 gum/libfrida-gum-1.0.a（改名 libgum.a）
CMake 构建本工程 native 层 + 链接 gum        → libai_analyzer.so
   → ELF64 / DYN (Shared object) / AArch64，13.5 MB
   → 导出 zygisk_module_entry · zygisk_companion_entry
打包                                        → build/out/zygisk-ai-runtime.zip
```
**这是端到端的真实验证：不只是工具链能跑，是项目真的编出了可刷的 Magisk 模块。**

**结论：Android 交叉编译链完全可用，M1 无环境阻塞。**

NDK r27d 关键能力核验：

```text
clang 18.0.4                              → 满足 LSPlant 的 C++23 + C++20 modules
build/cmake/android.toolchain.cmake       → 存在
ANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES       → 存在（flags.cmake，Android 15+ 16KB 页）
aarch64-linux-android* 目标               → 60 个（API 21~35 全档）
ndk-build.cmd                             → 存在（Android.mk 备选路径可用）
```

## 5. Host 侧 Python 依赖（已就位）

| 包 | 版本 | 用途 | 状态 |
|---|---|---|---|
| `mcp` | **2.2.0** | MCP Server（正好是 SOURCE_LOCK 锁定版本） | ✅ 已装 |
| `pytest` | 9.1.1 | 测试运行器 | ✅ 已装 |
| `jsonschema` | 4.26.0 | 契约 schema 校验 | ✅ 已装 |
| `meson` | **1.12.0** | Frida-Gum 构建（meson 工程） | ✅ 已装（pip，不污染系统） |

venv 位置：`C:\Users\52334\.workbuddy-ai\binaries\python\envs\default`

## 6. 首轮误判的原因（留作教训）

首轮审计用 `command -v cmake` / `command -v ninja` 探 PATH，全部 MISS，于是判定「全缺」。
实际上：

```text
CMake 4.3.1  → 藏在 VS Professional 2026 的 IDE 扩展目录里，从不进 PATH
Ninja 1.13.2 → 同上，与 CMake 同目录
NDK r27d     → 解压在 D:\ProgramerDevelop\windowsNDK27，非 SDK 默认位置
Meson        → 确实没有，但 pip 一条命令即可（装进 venv，不污染系统）
```

**教训：探测构建工具不能只查 PATH，必须遍历 IDE 安装目录与自定义解压位置。**
审计方法已据此修正 —— 本文件 §1 的数据来自全盘遍历。

## 7. 判定

```text
P-1a（PC 侧可判定项）   ✅ PASS
    Python / Git / JDK / Node / Android SDK / ADB 齐备
    足以支撑：协议契约、Host 侧、MCP Server、Mock 后端、全部测试

P-1b（Android 构建项）  ✅ 6/7 PASS —— 唯一剩余阻塞是真机设备
    NDK ✅ r27d · CMake ✅ 4.3.1 · Ninja ✅ 1.13.2 · Meson ✅ 1.12.0
    clang ✅ 18.0.4 · 端到端编译验证 ✅
    设备 ❌ 无（见 DEVICE_MATRIX.md）
```

> **M1（编译 `libai_analyzer.so`）现在没有环境阻塞。**
> 唯一被卡住的是 M2 及之后需要真机的阶段。
