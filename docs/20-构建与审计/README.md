# 20-构建与审计

P-1《落地前准备审计》阶段的交付物落点。**这一阶段原则上不写业务代码**，只产出事实记录。

> 依据：`../10-施工指导/ZygiskAIRuntime_AI施工手册_v2.0.md` §7（P-1）与
> `../10-施工指导/ZygiskAIRuntime_专业开发技术指导总文档_v1.0.md` §3。

---

## 交付物清单（权威版）

两份上位文档列出的清单**不一致**，此处取其**并集**作为权威清单：

| 文件 | 内容 | 产出依据 |
|---|---|---|
| `PROJECT_TREE_AUDIT.md` | 实际文件数 / 代码行数 / 空目录 / 缺失文件 / 多余文件 / 目录冲突 / 脚本引用不存在的路径 | 施工手册 P-1.1 |
| `SUPPLY_CHAIN_CHECK.md` | 逐依赖表：名称 · 版本 · 来源 · License · 实际路径 · 核心/外置 · 状态 | 专业指导 §3.3 |
| `ENVIRONMENT.md` | 工具链表：Tool · Version · Path · Expected · Actual · PASS/FAIL | 施工手册 P-1.4 |
| `DEVICE_MATRIX.md` | 设备矩阵：device · model · manufacturer · Android · API · ABI · kernel · page size · Magisk · Zygisk · SELinux · adb | 施工手册 P-1.5 |
| `BUILD_BLOCKERS.md` | 阻塞项清单（见下方阻塞规则） | 施工手册 P-1.6 |

---

## P-1 阻塞规则

以下任何一项失败，**都不得假装 P-1 完成**：

```text
NDK · CMake · ADB · ARM64 · Magisk/Zygisk · Frida-Gum source · LSPlant source
```

**已登记的冲突**：本机（Windows 开发机）按既定约定**不安装 NDK 与 CMake**，
因此严格按此规则判定，本机 P-1 永远无法通过。

**建议解法（待用户拍板）**：把 P-1 拆成两段 —

```text
P-1a  PC 侧可判定项       目录审计 · 供应链审计 · License 审计     ← 本机可完成
P-1b  Android 构建项      NDK · CMake · ARM64 · Magisk/Zygisk      ← 标记 BLOCKED 挂起
```

这样 `BUILD_BLOCKERS.md` 如实记录 P-1b 为 BLOCKED，
既不违反"不假装完成"，也不阻塞不依赖 NDK 的 M0（协议契约 + 黄金样例）。

---

## 当前状态

**5 份交付物已全部产出**（2026-09-19）。

| 交付物 | 判定 | 一句话结论 |
|---|---|---|
| [`PROJECT_TREE_AUDIT.md`](./PROJECT_TREE_AUDIT.md) | ✅ PASS | 140 自有文件 / 9956 行代码；无空目录、无多余文件、无目录冲突；脚本引用路径全部有效 |
| [`SUPPLY_CHAIN_CHECK.md`](./SUPPLY_CHAIN_CHECK.md) | ✅ PASS | 14/14 落盘核验通过；License 全核对；三条硬约束已落工程配置 |
| [`ENVIRONMENT.md`](./ENVIRONMENT.md) | P-1a ✅ / P-1b ❌ | Python/Git/JDK/Node/SDK/ADB 齐备；NDK/CMake/Ninja/Meson 全缺 |
| [`DEVICE_MATRIX.md`](./DEVICE_MATRIX.md) | ❌ FAIL | 无设备接入（adb 本身就绪） |
| [`BUILD_BLOCKERS.md`](./BUILD_BLOCKERS.md) | ⛔ PARTIAL | **P-1a PASS（3/3）· P-1b BLOCKED（0/4）** |

**整体判定（2026-09-19 修正后）：P-1.6 清单 6/7 PASS，唯一剩余阻塞是真机设备。**

```text
P-1a  PC 侧可判定项     ✅ PASS（3/3）—— ADB · Frida-Gum source · LSPlant source
P-1b  Android 构建项    ✅ 2/4
      NDK ✅ r27d · CMake ✅ 4.3.1 · Ninja ✅ 1.13.2 · Meson ✅ 1.12.0
      ARM64 ❌ · Magisk/Zygisk ❌  ← 同一根因：无设备

✅ M1（编译 libai_analyzer.so）已无环境阻塞
❌ M2 及之后仍被设备卡住

已完成且不受影响：M0 协议契约 ✅（114 项测试）· Host 侧 MVP ✅（199 项测试 + 28 项验收）
```

> 🔴 **修正说明**：首轮审计只探 `PATH`，误判「NDK / CMake / Ninja 全缺」。
> 实际 VS Professional 2026 自带 CMake 4.3.1 + Ninja 1.13.2，
> 另有独立解压的 NDK r27d。工具链端到端编译已验证通过（ELF64 / AArch64 共享库）。
> 路径已固化到 `ZygiskAIRuntime/build/config/toolchain.env`。
