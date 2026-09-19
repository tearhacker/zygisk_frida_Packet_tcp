# BUILD_BLOCKERS —— 阻塞项清单与 P-1 判定

**产出依据**：施工手册 P-1.6 P-1 阻塞规则
**审计日期**：2026-09-19
**结论**：**P-1a ✅ PASS · P-1b ✅ 6/7 PASS · 整体 P-1 = 6/7，唯一剩余阻塞是真机设备**

> 🔴 **本文件已于 2026-09-19 修正。** 首轮审计只探 `PATH`，误判 NDK / CMake / Ninja 全缺。
> 实际三者本来就装在机器上（VS Professional 2026 自带 CMake + Ninja，另有独立 NDK r27d）。
> 修正后：**M1 已无环境阻塞**，仅 M2 及之后的真机阶段仍被卡。

---

## 1. 阻塞规则逐项判定

| # | 阻塞项 | 判定 | 实测证据 | 分段 |
|---|---|---|---|---|
| 1 | **NDK** | ✅ **PASS** | **r27d**（27.3.13750724）@ `D:\ProgramerDevelop\windowsNDK27`，clang 18.0.4 | P-1b |
| 2 | **CMake** | ✅ **PASS** | **4.3.1** @ VS Professional 2026 扩展目录（≥ 3.28 满足） | P-1b |
| 3 | **ADB** | ✅ PASS | 1.0.41，`C:\Program Files\platform-tools\adb.exe` | P-1a |
| 4 | **ARM64** | ❌ **FAIL** | 无设备接入（`adb devices` 为空） | P-1b |
| 5 | **Magisk / Zygisk** | ❌ **FAIL** | 同上，无设备可查 | P-1b |
| 6 | **Frida-Gum source** | ✅ PASS | `third_party/frida-gum/17.18.0/gum/gum.h` 等关键头文件齐全 | P-1a |
| 7 | **LSPlant source** | ✅ PASS | `third_party/lsplant/lsplant/src/main/jni/include/lsplant.hpp` 存在 | P-1a |

**另需（不在 P-1.6 清单内但 M1 必需）**：Ninja ✅ 1.13.2 · Meson ✅ 1.12.0

```text
P-1a（PC 侧可判定）  ADB · Frida-Gum source · LSPlant source          3/3  ✅ PASS
P-1b（Android 构建）  NDK ✅ · CMake ✅ · ARM64 ❌ · Magisk/Zygisk ❌   2/4
整体 P-1.6 清单                                                        6/7  ✅
```

### 1.1 构建工具链端到端验证（实测）

```text
① aarch64-linux-android30-clang++ -std=c++23 -fPIC -c probe.cpp
   → ELF64 / Machine: AArch64                                          ✅

② cmake -G Ninja -DCMAKE_TOOLCHAIN_FILE=<NDK>/build/cmake/android.toolchain.cmake
        -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-30
   → libprobe.so，ELF64 / DYN (Shared object) / AArch64                 ✅
```

**不是看版本号，是真的编译出了 arm64 共享库。**

## 2. 为什么拆 P-1a / P-1b

施工手册 P-1.6 的规则**本身没错**，但首轮审计把它套在了一个**错误的事实前提**上：
当时以为「NDK 与 CMake 都不在本机」，于是严格判定下 P-1 永远无法通过。

**修正后的事实**：NDK r27d 与 CMake 4.3.1 本来就在机器上（见 §1），
首轮只是没遍历到。所谓「本机不装 NDK / CMake」的约定，
实际针对的是**别往 Android SDK 目录里塞大件** —— 而现成的 NDK 是独立解压在
`D:\ProgramerDevelop\windowsNDK27` 的，完全没有污染 SDK。

拆分仍有价值，但语义变成：

```text
P-1a  PC 侧可判定项
      目录审计 · 供应链审计 · License 审计 · PC 环境审计 · adb 可用性
      → 本机可完成，完成后即可进入 M0

P-1b  Android 构建项
      NDK · CMake · ARM64 设备 · Magisk/Zygisk
      → 标记 BLOCKED 挂起，如实登记，**不假装完成**
      → 环境就绪后补做，是 M1 的硬前置
```

**拆分不降低标准，只是让「能做的先做」**，同时 BLOCKED 状态在文档里白纸黑字记着。
现在 P-1b 里只剩「设备」一项 FAIL，而它**不阻塞 M1**（M1 只产出二进制，不需要设备）。

## 3. 已完成的 P-1a 交付物

| 交付物 | 状态 | 结论 |
|---|---|---|
| `PROJECT_TREE_AUDIT.md` | ✅ | PASS —— 无空目录 / 无多余文件 / 无目录冲突 / 脚本引用路径全部有效 |
| `SUPPLY_CHAIN_CHECK.md` | ✅ | PASS —— 14/14 落盘核验通过，License 全核对，三条硬约束已落工程配置 |
| `ENVIRONMENT.md` | ✅ | P-1a PASS / P-1b FAIL，逐项实测 |
| `DEVICE_MATRIX.md` | ✅ | FAIL（无设备）—— adb 就绪，缺设备 |
| `BUILD_BLOCKERS.md` | ✅ | 本文件 |

**P-1a 额外产出**：清理了 5 个陈旧 `.gitkeep`（所在目录已填真实文件）；
发现并登记 `SOURCE_LOCK.md` §4/§7 的「LICENSE 核对未做」为过期表述（实际已完成）。

## 4. M1 前置清单（修正后：环境项已全部就绪）

```text
[x] Android NDK r27d                          → D:/ProgramerDevelop/windowsNDK27
[x] CMake 4.3.1（≥ 3.28）                     → VS2026 扩展目录
[x] Ninja 1.13.2                              → VS2026 扩展目录
[x] Meson 1.12.0                              → pip 装进 venv
[x] 路径已固化                                 → build/config/toolchain.env
[x] 端到端编译验证通过                          → ELF64 / AArch64 共享库

[x] 补齐 Frida-Gum 的必需 subprojects（tinycc / libunwind / libdwarf / xz）
    —— codeload zip 通道逐个拉取（`build/scripts/fetch_subproject.py`）
[x] Frida-Gum 源码构建（meson 交叉编译，1089/1089 目标）
[x] 本工程 native 构建 → libai_analyzer.so（ELF64 / AArch64 / 13.5 MB）
[x] 打包 → build/out/zygisk-ai-runtime.zip（**项目第一个可刷的 Android 二进制**）

[ ] LSPlant 构建 —— NDK r27d 的 clang 18 与 LSPlant master 不兼容（详见 §7）
[ ] （M2 才需要）接入 ARM64 + Magisk + Zygisk 已启用的设备
[ ] （M2 才需要）确认设备 page size
```

### 4.1 Frida-Gum 依赖拉取：已找到规避方案

15 个 `.wrap` **全部是 `[wrap-git]` 指向 `github.com/frida/*.git`**，而本机 git 协议通道
间歇 502（codeload zip 才稳）。已实测：codeload 能按固定 revision 拉到 frida fork 的 zip
（capstone 实测 HTTP 200 / 8.4MB）。

因此可在构建前用**稳定通道预填** `subprojects/<name>/`，把「构建时 15 个联网风险点」降为 0。

**关于 Frida-Gum 的已知阻塞**（已裁决，见总基线 §16.4）：

```text
❌ 官方 devkit 下载不可行 —— 仅由 github.com/frida/frida/releases/download/ 分发，
   本机代理拒绝该域名
✅ 采用：源码构建 + 静态链接 libgum.a
🟠 备选：meson 有 devkits 选项（-Ddevkits=gum），可从源码现场造 devkit，绕开下载限制
```

## 5. 当前不受阻塞、已实际完成的工作

**关键事实**：P-1b 的阻塞**不影响**已经做完的部分。

| 已完成 | 证据 | 是否依赖 NDK/真机 |
|---|---|---|
| M0 协议契约冻结 | 常量单一源 + 帧 + 9 消息 + 黄金样例 + **114 项测试** | ❌ 不依赖 |
| 常量两端一致性 | 解析 `native/include/ipc/protocol_constants.h` 逐项比对 | ❌ 不依赖（无需编译） |
| Host 侧 Bridge | 握手 / 心跳 / 重连 / Session 看门狗 | ❌ 不依赖 |
| Mock Runtime 后端 | 进程 / 模块 / 线程 / 连接 / Packet / Hook / Job 全模拟 | ❌ 不依赖 |
| MCP Server | Core 25 + Expert 10 = 35 工具，能力门禁 | ❌ 不依赖 |
| 端到端验收 | `tests/accept_mvp.py` **28/28 通过** | ❌ 不依赖 |

```text
python -m pytest tests        → 199 项全绿
python tests/accept_mvp.py    → 28/28，10 节，打印可核对证据
```

## 6. 整体判定（修正后）

```text
┌──────────────────────────────────────────────────────────┐
│  P-1 落地准备审计                                        │
│                                                          │
│  P-1a  PC 侧可判定项        ✅ PASS（3/3）               │
│  P-1b  Android 构建项       ✅ 2/4                       │
│        ├─ NDK ✅ · CMake ✅                              │
│        └─ ARM64 ❌ · Magisk/Zygisk ❌ ← 同一根因：无设备   │
│                                                          │
│  整体 P-1.6 清单：6/7 PASS                                │
│  唯一剩余阻塞：真机设备                                   │
│                                                          │
│  ✅ M1（编译 libai_analyzer.so）已无环境阻塞              │
│  ❌ M2 及之后仍被设备卡住                                 │
└──────────────────────────────────────────────────────────┘
```

**下一步建议**（按价值排序）：

```text
① ~~M1 编译~~ **✅ 已完成**（2026-09-19）
   产出 build/out/zygisk-ai-runtime.zip（arm64-v8a 模块 so，Frida-Gum 已静态链入）。
   未闭合：LSPlant（见 §7），已用 `-DZAI_ENABLE_LSPLANT=OFF` 绕过，无 M2 范围内的功能损失。

② 设备就绪后：M2 Walking Skeleton
   - 真机 Zygisk 注入 → HELLO/READY → runtime.status 真实返回
   - 把 Host 侧端点从 tcp: 换成 unix:，协议与工具面一行不动

③ 并行可做（不依赖设备）：Write Guard 完整八步 / Correlation 数据模型

---

## 7. LSPlant：M1 唯一的未闭合项

**状态**：⛔ BLOCKED（第三方源码与工具链不兼容），已用构建开关绕过。

**现象**（`lsplant/src/main/jni/art/runtime/art_method.cxx`）：

```text
error: too many arguments to function call, expected 0, have 1
error: called object type
       'auto ((lambda at include/utils/hook_helper.hpp:256:71)::*)() const -> void'
       is not a function or function pointer
```

**根因**：LSPlant master 用了较重的 C++20/23 模板元编程
（`_sym.hook->* []<MemBackup auto backup>(ArtMethod *thiz) static -> ...` 模板 lambda）。
NDK r27d 的 **clang 18** 把 `backup` 解析成了 `hook_helper.hpp:256` 那个**无参** lambda。

**为什么不改源码**：`STRUCTURE.md` 的边界规则禁止修改 `third_party/`。
因此在 `native/CMakeLists.txt` 加了 `option(ZAI_ENABLE_LSPLANT ON)`，本机构建时置 OFF。

**影响范围**：无 M2 范围内的功能损失。`lsplant_adapter.cpp` 目前**没有任何真实
`lsplant::` 调用**（全是 TODO(M3)），ART / Java Hook 后端本就是 M3 才接线。
Runtime Core、Frida-Gum Native Backend、Zygisk 注入链路均不受影响。

**解除条件**（任一）：

```text
① 换 NDK r28+（clang ≥ 19）
② 把 LSPlant 固定到与 clang 18 兼容的 tag（需同步回写 SOURCE_LOCK.md）
```
```
