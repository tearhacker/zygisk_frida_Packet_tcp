# ZygiskAIRuntime 架构与目录标准清单

**生成日期**：2026-09-19
**依据**：`../90-历史归档/真正的工作.txt.md`（v1.0 源码供应链与工程目录）
**状态**：自有文件 140 个 / 自有代码 9956 行（Python 33 + C/C++ 23 个文件）/ 第三方源码 34M / **Android 侧仍未编译验证；Host 侧 MVP 已跑通（199 项测试 + 28 项验收全绿）**

> **位置变更（2026-09-19 文档整理）**：本文件已从 `ZygiskAIRuntime/` 移入 `docs/00-权威基线/`，
> 与 P0–P3 其余权威文档同层。文中相对路径一律以**本文件所在目录**为基准。

> 本文件是工程结构的**唯一标准清单**。目录改动必须同步本文件。
> 复现命令见文末 §7。

---

## 1. 分层总览

```text
                        ┌────────────────────────────┐
                        │   PC 侧（不在本工程树内）    │
                        │   AI · MCP Host · MCP Bridge│
                        └─────────────┬──────────────┘
                                      │ IPC（UDS，M2 接线）
                                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                        ZygiskAIRuntime                          │
│                                                                 │
│  ┌──────────────┐                    ┌───────────────────────┐  │
│  │ zygisk/      │  Entry/Bootstrap   │ runtime/              │  │
│  │ Zygisk Host  │ ──────────────────▶│ Runtime Core（核心资产）│  │
│  └──────────────┘                    └───────────┬───────────┘  │
│                                                  │              │
│                                      ┌───────────┴───────────┐  │
│                                      │                       │  │
│                              ┌───────▼──────┐   ┌────────────▼┐ │
│                              │ backend/gum/ │   │ backend/art/│ │
│                              │ Native       │   │ ART         │ │
│                              └───────┬──────┘   └────────────┬─┘ │
│                                      │                       │  │
│  ┌──────────────────────────────┐    │                       │  │
│  │ native/  进程内能力层         │    │                       │  │
│  │ hook·memory·process·module   │    │                       │  │
│  │ thread·ipc·runtime·common    │    │                       │  │
│  └──────────────────────────────┘    │                       │  │
│                                      │                       │  │
│                    ┌─────────────────▼───────────────────────▼┐ │
│                    │ third_party/  只有 2 个                   │ │
│                    │ frida-gum/17.18.0  ·  lsplant             │ │
│                    └──────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
                          Android App Process
```

**核心原则**：Frida-Gum 与 LSPlant 都只是**可替换的 Backend**。
真正属于本项目的是 `zygisk/` + `runtime/` + `native/` + `ai_analyzer/`。

---

## 2. 完整目录树（自有部分）

图例：`✅` 已写内容 · `🟡` 目录已建、待填 · `🔒` 上游源码，禁止修改

```text
ZygiskAIRuntime/
│
├── README.md                       ✅ 工程总览：核心源码 / 外置清单 / 构建状态
├── VERSION                         ✅ 版本单一源（含冻结的第三方版本）
├── .gitignore                      ✅ 排除构建产物、Frida-Gum 构建目录、artifacts
│
├── zygisk/                         Zygisk Host：只做 Entry / Bootstrap
│   ├── zygisk.hpp                  🔒 官方 API v5，全文禁止修改（0BSD）
│   ├── module.h                    ✅ AIRuntimeModule 类声明
│   ├── module.cpp                  ✅ ModuleBase 实现，逻辑全委托 bootstrap
│   ├── bootstrap.h                 ✅ 目标过滤 + 拉起 Runtime 的接口
│   ├── bootstrap.cpp               ✅ pre 过滤 / post 在独立线程启动 Runtime
│   └── entry.cpp                   ✅ REGISTER_ZYGISK_MODULE + COMPANION
│
├── runtime/                        Runtime Core —— 本项目真正的资产
│   ├── runtime.h                   ✅ 门面：start / stop / hooks / memory / process
│   ├── runtime.cpp                 ✅ 启动顺序 gum → art → manager → ipc
│   ├── runtime_context.h           ✅ 上下文事实：pkg / pid / abi / sdk / session
│   │
│   ├── backend/                    Backend 层，上层不直接接触具体库
│   │   ├── gum/                    Native Backend ← Frida-Gum
│   │   │   ├── gum_backend.h       ✅ pimpl 隔离，头文件不暴露 gum.h
│   │   │   └── gum_backend.cpp     ✅ 全项目唯一允许出现 gum_* 调用的文件
│   │   │
│   │   └── art/                    ART Backend ← LSPlant
│   │       ├── art_backend.h       ✅ ART 层门面（含 SDK 分级降级）
│   │       ├── art_backend.cpp     ✅ 委托给 adapter
│   │       ├── lsplant_adapter.h   ✅ 适配层接口
│   │       └── lsplant_adapter.cpp ✅ 唯一允许调 lsplant:: API 的文件
│   │
│   └── manager/                    能力管理者，向上提供稳定 API
│       ├── hook_manager.h          ✅ Hook 状态机：pending→active⇄disabled→removed
│       ├── hook_manager.cpp        ✅ create/info/list/enable/disable/remove
│       ├── memory_manager.h        ✅ WriteResult 三级：accepted/executed/verified
│       ├── memory_manager.cpp      ✅ 写后强制 read-back 校验
│       ├── process_manager.h       ✅ 进程 / 线程 / 模块查询
│       └── process_manager.cpp     ✅ /proc/self/task + Gum module map
│
├── native/                         进程内能力层（NDK + CMake）
│   ├── CMakeLists.txt              ✅ 主构建：强制 LSPlant SHARED（LGPL-3.0）
│   ├── Android.mk                  ✅ ndk-build 备选构建
│   ├── Application.mk              ✅ ABI=arm64-v8a / API 30 / c++_static
│   │
│   ├── include/                    对外头
│   │   ├── common/log.h            ✅ 统一 logcat 宏 + 错误码文本
│   │   ├── runtime/                🟡 待填
│   │   ├── hook/                   🟡 待填
│   │   ├── memory/                 🟡 待填
│   │   ├── process/                🟡 待填
│   │   ├── module/                 🟡 待填
│   │   ├── thread/                 🟡 待填
│   │   └── ipc/                    🟡 待填（M2 协议帧编解码）
│   │
│   └── src/                        实现
│       ├── common/log.cpp          ✅ 错误码表（对应协议错误分层）
│       ├── runtime/                🟡 待填
│       ├── hook/                   🟡 待填
│       ├── memory/                 🟡 待填
│       ├── process/                🟡 待填
│       ├── module/                 🟡 待填
│       ├── thread/                 🟡 待填
│       └── ipc/                    🟡 待填
│
├── third_party/                    核心第三方源码 —— 只有 2 个，不再增加
│   ├── frida-gum/                  🔒 wxWindows Licence 3.1，允许静态链接
│   │   └── 17.18.0/                🔒 32M
│   │       ├── gum/                核心头文件（gum.h / guminterceptor.h …）
│   │       ├── libs/ · bindings/ · ext/ · vapi/
│   │       ├── meson.build         构建入口
│   │       ├── meson.options       🔑 有 devkits 选项，可从源码造 devkit
│   │       └── subprojects/        ⚠️ 15 个 .wrap，构建时需联网拉取
│   │
│   └── lsplant/                    🔒 LGPL-3.0 —— 必须动态链接为 liblsplant.so
│       ├── lsplant/src/main/jni/   真正的 JNI 源码
│       │   ├── include/lsplant.hpp 🔒 主头文件（另有 .ixx → C++20 modules）
│       │   ├── CMakeLists.txt      🔑 C++23 + LSPLANT_BUILD_SHARED 选项
│       │   └── art/ · external/ · utils/
│       └── gradle/ · build.gradle.kts
│
├── module/                         Magisk 模块外壳
│   ├── module.prop                 ✅ id / name / version
│   ├── customize.sh                ✅ 校验产物存在，缺 so 直接 abort
│   ├── post-fs-data.sh             ✅ 空（Runtime 由 Zygisk 拉起，无需此阶段）
│   ├── service.sh                  ✅ 空（companion 守护侧，M2 接线）
│   ├── uninstall.sh                ✅ 只清本模块写过的路径
│   └── zygisk/
│       ├── README.md               ✅ 产物落位说明
│       └── arm64-v8a.so            ⚠️ 构建产物，当前不存在
│
├── ai_analyzer/                    PC 侧 Host/MCP 层，不进 Native Runtime
│   ├── README.md                   ✅ 分层说明 + 包名冲突说明
│   ├── protocol/                   ✅ IPC 契约：常量 / 错误 / 帧 / 消息 / 命令分级
│   ├── schemas/                    ✅ 9 份 JSON Schema + 黄金样例（examples/、errors/）
│   ├── bridge/                     ✅ client（握手/心跳/重连）· session · transport（UDS+TCP）
│   ├── mock/                       ✅ Mock Runtime 后端（无真机时端到端验证）
│   ├── tools/                      ✅ spec 模型 · specs 35 个工具规格 · handlers 实现
│   └── host/                       ✅ server 门面 · runtime_bridge · surfaces · registry · error_mapping
│
├── build/
│   ├── scripts/build-gum.sh        ✅ meson 交叉编译 Frida-Gum
│   ├── config/versions.env         ✅ 版本 + 构建参数单一源
│   └── toolchains/README.md        ✅ 说明用 NDK 自带 toolchain，不自维护
│
├── scripts/                        Windows 一键脚本
│   ├── build.ps1                   ✅ 主构建（含环境校验，缺 NDK 直接报错）
│   ├── build.bat                   ✅ 批处理壳
│   ├── clean.bat                   ✅ 清 build/out 与 module/zygisk/*.so
│   ├── install.bat                 ✅ adb push 到设备
│   └── package.bat                 ✅ 打包 Magisk 可刷 zip
│
├── tools/                          外部工具接入说明 —— 不编译进核心
│   ├── README.md                   ✅ 外置原则 + GPL 约束
│   └── frida/ · jadx/ · rizin/ · mitmproxy/ · wireshark/   🟡
│
├── docs/                           工程实施文档（随代码走）
│   ├── README.md                   ✅ 索引 + 指向 ../../docs/
│   └── architecture/ · build/ · runtime/ · hook/
│       memory/ · art/ · mcp/ · deployment/                 🟡
│
└── tests/
    ├── README.md                   ✅ 测试分层说明
    ├── accept_mvp.py               ✅ 端到端验收脚本（10 节 28 项断言）
    ├── protocol/                   ✅ 协议契约测试（114 项）
    ├── integration/                ✅ Mock ↔ Bridge 端到端（30 项）
    ├── mcp/                        ✅ MCP 工具面测试（55 项）
    ├── native/                     🟡 Backend 级单测（需 NDK + 真机）
    ├── runtime/                    🟡 Runtime Core 单测（需 NDK + 真机）
    └── semantic/                   🟡 真机语义验收
```

---

## 3. third_party 之外的源码在哪

外置源码在 **`../../external/`**（274M），不进本工程树、不编译进 `libai_analyzer.so`：

```text
../../external/
├── analysis/    jadx · apktool · rizin · r2frida · mobsf
├── network/     mitmproxy · pcapdroid · netbare
├── mcp/         python-sdk · specification
├── zygisk/      zygisk-module-sample（只读参考，非长期上游）
└── README.md
```

锁定表：**`SOURCE_LOCK.md`**（同目录）

---

## 4. 边界规则（改代码前必读）

| 规则 | 说明 |
|---|---|
| 🔴 PC 侧包名固定 `ai_analyzer`，**不得改回 `mcp`** | 与 MCP Python SDK 顶层包名硬冲突，会把 `import mcp.server` 劫持到自己身上 |
| 🔴 `gum_*` 只允许出现在 `runtime/backend/gum/gum_backend.cpp` | 其他文件一律禁止 include `<gum/...>` |
| 🔴 `lsplant::` 只允许出现在 `runtime/backend/art/lsplant_adapter.cpp` | 同上 |
| 🔴 `zygisk/zygisk.hpp` 一个字都不许改 | 官方 API，升级靠整体替换 |
| 🔴 `zygisk/` 层不得出现任何分析逻辑 | 只做目标过滤 + 拉起 Runtime |
| 🔴 `third_party/` 不得直接修改 | 需要改就 fork 到 `external/` 并在 LICENSES.md 记录 |
| 🔴 LSPlant 必须 `SHARED` | LGPL-3.0，静态嵌入触发"允许用户替换并重链接"义务 |
| 🔴 大文件不进内存/协议 | PCAP / dump / trace 走 Artifact Channel，只传 metadata + sha256 |
| 🟠 新增第三方源码需评审 | 目标：核心永远只有 2 个 |

---

## 5. 命名与路径约定

- 代码标识符、协议命令、工具名统一 **snake_case**（`runtime.hook` / `memory.read`）
- 文档内部互相引用一律**相对文件自身所在目录**
- 构建产物：`build/out/<abi>/` → 拷到 `module/zygisk/<abi>.so`
- 日志 tag 统一前缀 `ZAI:`

---

## 6. 体量与进度

| 项 | 数值 |
|---|---|
| 自有文件 | 140 个 |
| 自有代码 | 9956 行（Python 33 个文件 + C/C++ 23 个文件） |
| Host 侧测试 | **199 项全绿**（协议 114 · 端到端 30 · 工具面 55） |
| Host 侧验收 | **28/28 通过**（`tests/accept_mvp.py`） |
| MCP 工具 | Core 25 + Expert 10 = 35（硬上限 45） |
| third_party | 34M（frida-gum 32M + lsplant 2.3M） |
| 外置 external/ | 274M |
| Android 编译次数 | **0**（本机无 NDK / CMake） |
| 待填目录（🟡） | native 实现、tests/native、tests/runtime、tests/semantic、tools/ 外部工具接入说明 |

---

## 7. 复现 / 校验本清单

```bash
cd ZygiskAIRuntime

# 自有部分全树（排除第三方源码）
find . -path ./third_party -prune -o -print | sort

# 只看自有代码文件
find . -path ./third_party -prune -o -type f -print | sort

# 统计
find . -path ./third_party -prune -o -type f -print | wc -l
find . -path ./third_party -prune -o \( -name "*.cpp" -o -name "*.h" \) -print | xargs wc -l | tail -1
du -sh third_party/*
```

---

## 8. 相关文档

```text
../README.md                       文档中心索引（分层与优先级链）
项目总基线_v1.1.md                  P0 唯一权威（§17 工程目录已按本布局改版）
SOURCE_LOCK.md                      P1 供应链锁定表与目录映射
LICENSES.md                         P2 第三方许可与三条硬约束
10-施工指导/                        P4–P5 施工规约
20-构建与审计/                      P-1 交付物
../90-历史归档/真正的工作.txt.md     本目录结构的出处（v1.0，已归档）
../../external/README.md           外置源码说明
```
