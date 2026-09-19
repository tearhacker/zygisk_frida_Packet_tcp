# 第三方许可证核对报告

**核对日期**：2026-09-19
**核对对象**：已落盘的 12 个仓库（核心 2 个在 `ZygiskAIRuntime/third_party/`，外置 10 个在 `external/`）
**依据**：各仓库根目录 LICENSE / COPYING / README 原文（逐仓实读，非推断）
**状态**：M1 强制前置项 —— ✅ 已完成核对，⚠️ 有 2 项触发集成方式约束

> 本报告只做**事实核对与工程决策建议**，不构成法律意见。若本项目未来涉及商业分发，需由法务复核。

---

## 1. 核对总表

| 项目 | 许可证 | 集成位置 | 链接方式 | 风险 | 义务 |
|---|---|---|---|---|---|
| **Frida-Gum** | wxWindows Library Licence 3.1 | Android 侧 `libai_analyzer.so` | 静态链接 | 🟢 低 | 保留声明；对 Gum 本身的修改需开源 |
| **LSPlant** | **LGPL-3.0** | Android 侧 | ⚠️ 见 §2 | 🟠 中 | **必须可替换/可重链接**（见 §2.1） |
| **zygisk-module-sample** | **0BSD**（public domain 等价） | Android 侧 | 仅取头文件 | 🟢 极低 | 无 |
| **mitmproxy** | MIT（BSD 风格原文） | Host 侧 Python | 库/进程 | 🟢 低 | 保留版权声明 |
| **PCAPdroid** | **GPL-3.0** | Android 侧网络后端 | ⚠️ 见 §2 | 🔴 高 | **禁止链接进本工程**（见 §2.2） |
| **NetBare** | MIT | Android 侧参考 | 参考实现 | 🟢 低 | 保留声明 |
| **JADX** | Apache-2.0 | Host 侧 | 独立进程 CLI | 🟢 低 | 保留声明 + NOTICE |
| **Apktool** | Apache-2.0 | Host 侧 | 独立进程 CLI | 🟢 低 | 保留声明 |
| **Rizin** | **GPL-3.0** | Host 侧 | 独立进程 CLI | 🟡 中 | 不链接、不改其源码并入本工程（见 §2.3） |
| **r2frida** | MIT | Host 侧参考 | 参考实现 | 🟢 低 | 保留声明 |
| **MCP Python SDK** | MIT | Host 侧 | pip 依赖 | 🟢 低 | 保留声明 |
| **MCP Specification** | MIT → **Apache-2.0** 过渡中；文档 CC-BY-4.0 | 规范参考 | 不集成 | 🟢 低 | 引用时标注来源 |

---

## 2. 三项触发工程约束的许可证🔴

### 2.1 LSPlant = LGPL-3.0 → **必须动态链接**

LGPL 对"静态链接"的要求是：必须让最终用户能够**用修改过的库替换原库并重新链接**（提供 object files 或等价手段）。静态嵌入 `libai_analyzer.so` 会直接触发该义务，实践上很难满足。

**决策：LSPlant 编译为独立 `liblsplant.so`，由 `libai_analyzer.so` 通过 `dlopen`/`dts` 动态依赖。**

```text
❌ libai_analyzer.so（静态包含 LSPlant 目标文件）
✅ libai_analyzer.so --dlopen--> liblsplant.so   ← 用户可替换该文件
```

工程落地要点：
- CMake 中 LSPlant 目标类型设为 `SHARED`，不得 `STATIC`；
- 打包时 `liblsplant.so` 作为独立文件分发（不合并进主 so）；
- 若日后修改 LSPlant 源码，修改部分需以 LGPL 开源，并在 `LICENSES.md` 记录 fork 位置。

### 2.2 PCAPdroid = GPL-3.0 → **禁止链接，只能进程外集成**

GPL 具有强传染性：把 GPL 代码链接进 `libai_analyzer.so`，该 so 整体需以 GPL 开源。

**决策：PCAPdroid 只作为独立 App / 独立进程使用，通过 IPC 或 VPN 服务交互；Adapter 不得复制其源码。**

```text
✅ libai_analyzer.so ──IPC/本地服务──> PCAPdroid（独立进程，GPL，自身合规）
❌ 把 PCAPdroid 的 .c/.java 复制或链接进本工程
```

工程落地要点：
- `PcapdroidAdapter` 只做**协议/接口调用**，不 vendor 其源码进核心工程；
- 若确需"抓包内核"能力，另选 MIT/BSD 后端（如自研 TUN 转发 + MIT 依赖），或接受本模块开源；
- `external/network/pcapdroid` 定位为**参考实现**，**不进入** `ZygiskAIRuntime/` 工程树，更不得链接进 `libai_analyzer.so`。

### 2.3 Rizin = GPL-3.0 → **仅 Host 侧独立进程调用**

Rizin 在 Host 侧以命令行/独立进程方式使用，不链接进本工程二进制，通常不构成衍生作品。**但不得把 rizin 源码并入 Host 代码库。**

工程落地要点：
- `analysis/rizin` 作为外部可执行程序探测（沿用 MCP 经验文档 §7 的"外部程序适配器"模式：`locate() / version() / run()`）；
- 依赖探测失败时优雅降级（工具仍可加载，调用时返回"依赖未就绪"）；
- 不得 copy `librz` 源码进入 `host/`。

---

## 3. 好消息：Zygisk 侧无 GPL 负担

`zygisk-module-sample` 的 README 原文明确：

> "Although the main Magisk project is licensed under GPLv3, the Zygisk API and its headers are not. Every source code in this repository is released under **0BSD** (a public domain equivalent license), so you don't have to worry about any licensing issues while developing Zygisk modules."

**结论**：
- 取 `module/jni/zygisk.hpp` 与构建骨架**没有任何传染性义务**；
- Magisk 主项目的 GPLv3 与我们的模块无关（我们不使用 Magisk 源码，只在设备上运行其环境）；
- Zygisk 模块本身可以闭源分发。

**Frida-Gum 的 wxWindows Library Licence 3.1** 是 LGPL 类的库级宽松许可：允许静态链接进专有软件，条件是保留许可声明、且对库本身的修改需以同许可公开。本项目不修改 Gum 的前提下无额外负担。

---

## 4. 分发时必须随附的声明

发布产物中需包含一份 `THIRD_PARTY_NOTICES`，至少含：

```text
Frida-Gum            wxWindows Library Licence 3.1    (c) Frida project
LSPlant              LGPL-3.0                         —— 以 liblsplant.so 动态链接分发
NetBare              MIT                              (c) 2019 Megatron King
mitmproxy            MIT                              (c) 2013 Aldo Cortesi
r2frida              MIT                              (c) 2015-2022 NowSecure
JADX                 Apache-2.0                       （附 NOTICE 文件）
Apktool              Apache-2.0
MCP Python SDK       MIT                              (c) 2024 Anthropic, PBC
Zygisk API headers   0BSD                             topjohnwu
```

运行时依赖（不随包分发，无需声明）：PCAPdroid（GPL-3.0，独立 App）、Rizin（GPL-3.0，独立 CLI）、Magisk（GPL-3.0，设备环境）。

---

## 5. 未决项

| 项 | 问题 | 处理建议 |
|---|---|---|
| MCP Specification | 处于 MIT → Apache-2.0 过渡期，同一仓内文件许可可能不同 | 仅作规范参考，不复制其文档进本工程；引用处标注来源与许可 |
| frida-gum `bindings/`（GumJS） | 未在 COPYING 外单独声明，主 COPYING 覆盖全仓 | 若启用 GumJS，需再确认一次；当前架构只用 Gum C API |
| 本项目自身许可 | **尚未声明** | 需明确（建议：Android 侧与 Host 侧分别定，或统一 Apache-2.0） |

---

## 6. 对总基线的影响

本报告**不改变已冻结架构**，只约束实现细节。对应总基线 §16.3：

- §16.3 "集成前必须逐仓核对 LICENSE 并写入 docs/00-权威基线/LICENSES.md" —— ✅ 已完成；
- 新增实现约束（写入工程规范，不是架构变更）：
  1. LSPlant 必须 `SHARED` 库，不得静态嵌入；
  2. PCAPdroid / Rizin 不得链接或 copy 源码；
  3. `external/` 中 GPL 项目不搬进 `ZygiskAIRuntime/` 工程目录。
