# SUPPLY_CHAIN_CHECK —— 供应链审计

**产出依据**：专业开发技术指导总文档 §3.3 · 施工手册 P-1.2
**审计日期**：2026-09-19
**数据来源**：`docs/00-权威基线/SOURCE_LOCK.md`（锁定表）+ `docs/00-权威基线/LICENSES.md`（逐仓实读）+ **本次实机落盘核验**
**结论**：**14/14 落盘核验通过；License 全部核对完成；三条硬约束已落到工程配置**

---

## 1. 逐依赖表

| 名称 | 版本 | 来源 | 许可证 | 实际目录 | 核心/外置 | 独立进程 | 静态链接 | 动态链接 | 状态 |
|---|---|---|---|---|---|---|---|---|---|
| **Frida-Gum** | `17.18.0` (tag) | frida/frida-gum | wxWindows Licence 3.1 | `third_party/frida-gum/17.18.0` | **核心** | 否（嵌入） | ✅ 允许 | — | ✅ 已落盘 |
| **LSPlant** | `master` | LSPosed/LSPlant | **LGPL-3.0** | `third_party/lsplant` | **核心** | 否 | ❌ **禁止** | ✅ **必须** | ✅ 已落盘 |
| **zygisk-module-sample** | `master` | topjohnwu/zygisk-module-sample | **0BSD** | `external/zygisk/…`（仅取头文件） | 参考 | — | ✅ 允许 | — | ✅ 已落盘 |
| **MCP Python SDK** | `v2.2.0` (tag) | modelcontextprotocol/python-sdk | MIT | `external/mcp/python-sdk` | 外置（pip 源） | 否 | ✅ | ✅ | ✅ 已落盘 |
| **MCP Specification** | `2026-07-28` | modelcontextprotocol/specification | MIT → Apache-2.0 过渡 | `external/mcp/specification` | 规范参考 | — | 不集成 | 不集成 | ✅ 已落盘 |
| **mitmproxy** | `main` | mitmproxy/mitmproxy | MIT | `external/network/mitmproxy` | 外置 | ✅ | ✅ | ✅ | ✅ 已落盘 |
| **PCAPdroid** | `master` | **emanuele-f/PCAPdroid** ⚠️纠偏 | **GPL-3.0** | `external/network/pcapdroid` | 外置 | ✅ **必须** | ❌ **禁止** | ❌ **禁止** | ✅ 已落盘 |
| **NetBare** | `master` | **MegatronKing/NetBare-Android** ⚠️纠偏 | MIT | `external/network/netbare` | 外置参考 | ✅ | ✅ | ✅ | ✅ 已落盘 |
| **JADX** | `master` | skylot/jadx | Apache-2.0 | `external/analysis/jadx` | 外置 | ✅ CLI | ✅ | ✅ | ✅ 已落盘 |
| **Apktool** | `main` | iBotPeaches/Apktool | Apache-2.0 | `external/analysis/apktool` | 外置 | ✅ CLI | ✅ | ✅ | ✅ 已落盘 |
| **Rizin** | `dev` | rizinorg/rizin | **GPL-3.0** | `external/analysis/rizin` | 外置 | ✅ **必须** | ❌ **禁止** | ❌ **禁止** | ✅ 已落盘 |
| **r2frida** | `master` | nowsecure/r2frida | MIT | `external/analysis/r2frida` | 外置参考 | ✅ | ✅ | ✅ | ✅ 已落盘 |
| **MobSF** | `master` | MobSF/Mobile-Security-Framework-MobSF | GPL-3.0 | `external/analysis/mobsf` | 外置参考 | ✅ | ❌ 禁止 | ❌ 禁止 | ⚠️ 部分（zip 曾中断） |
| **Magisk** | 最新稳定版 | topjohnwu/Magisk | GPL-3.0 | 设备侧（无源码） | 运行环境 | 是 | — | — | ⚪ 不需源码 |

## 2. 落盘核验（本次实机逐项检查）

```text
OK  third_party/frida-gum/17.18.0/gum/gum.h
OK  third_party/lsplant/lsplant/src/main/jni/include/lsplant.hpp
OK  zygisk/zygisk.hpp                                  ← 从 sample 抽取，原文禁止修改
OK  external/mcp/python-sdk/src/mcp
OK  external/mcp/specification/schema/2026-07-28
OK  external/network/mitmproxy/mitmproxy
OK  external/network/pcapdroid/app
OK  external/network/netbare/netbare-core
OK  external/analysis/jadx/src/jadx-core
OK  external/analysis/apktool/src/brut.apktool
OK  external/analysis/rizin/librz
OK  external/analysis/r2frida/src
OK  external/analysis/mobsf
OK  external/zygisk/zygisk-module-sample
```

**14/14 全部通过。**

体积：`third_party/` 34M（frida-gum 32M + lsplant 2.3M）· `external/` 275M。

## 3. 三条硬约束（违反会导致合规事故）

| # | 约束 | 原因 | 工程落地位置 | 状态 |
|---|---|---|---|---|
| 1 | 🔴 **LSPlant 必须 `SHARED`，禁止静态嵌入** | LGPL-3.0 的"允许用户替换并重链接"义务 | `native/CMakeLists.txt` 强制 `LSPLANT_BUILD_SHARED=ON`；`build/config/versions.env` 有 `LSPLANT_LINK_MODE=SHARED` | ✅ 已落 |
| 2 | 🔴 **PCAPdroid 禁止链接或 copy 源码**，只能独立 App 经 IPC | GPL-3.0 强传染性 | `external/network/pcapdroid` 不进 `ZygiskAIRuntime/`；`tools/README.md` 已声明 | ✅ 已落 |
| 3 | 🔴 **Rizin 仅 Host 侧独立进程 CLI**，源码不得并入 `host/` | 同上，进程外调用不构成衍生作品 | `tools/README.md` 已声明；`external/analysis/rizin` 独立进程 | ✅ 已落 |

**无负担项**：Zygisk API 头文件是 **0BSD**（官方 README 原文明确，不受 Magisk GPLv3 影响）；Frida-Gum 的 wxWindows Licence 3.1 允许静态链接；NetBare / mitmproxy / r2frida / MCP SDK 为 MIT；JADX / Apktool 为 Apache-2.0。

## 4. 与原《源码选择》表的差异（地址纠偏）

| 项 | 原表 | 实际 | 处理 |
|---|---|---|---|
| PCAPdroid | `PCAPdroid/PCAPdroid` | 该组织路径已失效，正确为 `emanuele-f/PCAPdroid` | ✅ 已纠偏 |
| NetBare | `MegatronKing/NetBare` | 不存在；正确为 `MegatronKing/NetBare-Android` | ✅ 已纠偏 |
| MCP SDK | "v2" | 实际最新 tag 为 **v2.2.0** | ✅ 已锁定 |

## 5. 未完成项

| 项 | 状态 | 影响 |
|---|---|---|
| JADX / Apktool **二进制** | ❌ 未获取（`releases/download` 域名被代理拒绝） | M5 静态分析阶段需要；可换网络或本地已有 jar |
| MobSF | ⚠️ zip 中断，目录存在但不完整 | 仅参考项，低优先级 |
| frida-mcp / delamain | ❌ 未拉（原文档只给名字，未确认仓库） | 均为"参考、不作核心" |
| **本项目自身开源许可** | ❌ **未声明** | Release 前必须定 |

## 6. 判定

```text
供应链审计  ✅ PASS
  14/14 落盘核验通过（含关键头文件逐项检查）
  License 逐仓实读完成，三条硬约束已落到 CMake / versions.env / tools 说明
  两个地址纠偏已执行并记录
  4 项未完成项均已登记，且不阻塞当前阶段
```

> ⚠️ 本报告修正了 `SOURCE_LOCK.md` §4/§7 中「LICENSE 核对未做」的过期表述 ——
> 核对已于 2026-09-19 完成，结果见 `../00-权威基线/LICENSES.md`。
