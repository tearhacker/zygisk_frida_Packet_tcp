# DEVICE_MATRIX —— 真机 / Magisk / Zygisk 审计

**产出依据**：施工手册 P-1.5 · 专业开发技术指导总文档 §3.5
**审计日期**：2026-09-19
**审计方式**：`adb devices -l` 实机探测
**结论**：**❌ 无可用设备 —— P-1b 阻塞项之一**

---

## 1. 设备矩阵

| # | device | model | manufacturer | Android | API | ABI | kernel | page size | Magisk | Zygisk | SELinux | adb | 状态 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| — | — | — | — | — | — | — | — | — | — | — | — | ✅ 1.0.41 | ❌ **无设备连接** |

`adb devices -l` 实测输出：

```text
List of devices attached
（空）
```

adb 守护进程可正常启动（`tcp:5037`），说明 **adb 本身没问题，是没有任何设备接入**。

## 2. 本机 adb 环境（已就绪）

| 项 | 实测 |
|---|---|
| adb 版本 | 1.0.41 |
| adb 路径 | `C:\Program Files\platform-tools\adb.exe` |
| SDK 内 platform-tools | `%LOCALAPPDATA%\Android\Sdk\platform-tools`（含 `adb.exe`、`fastboot.exe`、`sqlite3.exe`） |
| 守护进程 | 可启动 |

**结论**：设备一旦接入即可用，无需再装工具。

## 3. 目标设备要求（M2 前必须满足）

```text
✅ ARM64（arm64-v8a）          —— 首发 ABI，`build/config/versions.env` 已锁
✅ Android API ≥ 30            —— Application.mk 锁定
✅ 已 root + 安装 Magisk       —— Zygisk 宿主
✅ Magisk 中 Zygisk 已启用      —— 否则 Runtime 无法注入
✅ 支持 16KB 页（Android 15+）  —— LSPlant 需 ANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES
⚪ SELinux permissive 或规则已放行（Android 侧 UDS 建在 /data/local/tmp）
```

## 4. 接入设备后需要补录的字段

设备接入后必须**重新跑一次本审计**，补齐：

```text
device（serial）
model / manufacturer
Android 版本 / API Level
ABI（确认含 arm64-v8a）
kernel 版本
page size（4096 还是 16384 —— 直接决定 LSPlant 编译参数）
Magisk 版本
Zygisk 状态（enabled / disabled）
SELinux 模式（enforcing / permissive）
```

采集命令：

```bash
adb devices -l
adb shell getprop ro.product.model
adb shell getprop ro.build.version.release
adb shell getprop ro.build.version.sdk
adb shell getprop ro.product.cpu.abi
adb shell uname -r
adb shell getconf PAGE_SIZE
adb shell su -c "magisk -V"
adb shell getprop | grep -i zygisk
adb shell getenforce
```

## 4.1 已排除的候选：本机 Android 模拟器

遍历时发现 `D:\ProgramerDevelop\MuMuPlayer`（MuMu 模拟器 12.0）。

**结论：不能替代真机，不列入设备矩阵。** 理由：

```text
❌ 架构为 x86_64，与项目首发 ABI arm64-v8a 不同
❌ 无 Magisk / Zygisk —— Zygisk 注入（M2 的核心验证点）无法进行
⚠️ 内核为模拟器定制，/proc/self/maps 与真机行为存在差异
```

**但它仍有一个用途**：设备到位前，可用 x86_64 模拟器 + 手动 `dlopen`
验证「协议契约在真实 Android 上成立」这一关键假设（不经 Zygisk）。
这属可选的风险前移手段，需单独评估，不计入 M2 验收。

## 5. 对当前阶段的影响

```text
不影响：M0 协议契约、Host 侧 MVP、Mock 后端、全部 199 项测试
        这些都不依赖真机（已实证：28/28 端到端验收在 Mock 后端上跑通）

不影响：M1 编译 —— 只产出二进制，不需要设备
        NDK r27d + CMake 4.3.1 + Ninja + Meson 已全部就绪并验证通过

阻塞：  M2 Walking Skeleton —— 需要真机验证 Zygisk 注入
        M3 Native Hook —— 需要真机产生 HOOK_ENTER / HOOK_LEAVE
        M4 Memory Write read-back、Network Capture、HTTPS 五级 —— 全部需要真机
```

> **设备是当前项目唯一的硬阻塞。** M1 可以先做完，把二进制备好。

## 6. 兼容性矩阵扩展要求（M6）

施工手册要求：第一阶段可先用一台主力设备，但 **M6 必须扩展兼容性矩阵**。建议至少覆盖：

```text
Android 10 / 12 / 13 / 14 / 15 各一台（LSPlant 在 Android 8.x 有已知 ART Hook 崩溃 issue）
arm64-v8a 必需；armeabi-v7a / x86_64 视需要
16KB 页设备至少一台（Android 15+）
```

## 7. 判定

```text
真机审计  ❌ FAIL（无设备）
  adb 工具链就绪，缺的是设备本身
  这是环境约束，不是工程缺陷
  按 P-1a / P-1b 拆分，本项属 **P-1b，标记 BLOCKED**
```
