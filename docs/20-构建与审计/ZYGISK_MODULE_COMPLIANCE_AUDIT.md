# Zygisk 模块合规性审计 —— 对照 Magisk 官方实现

> 审计日期：2026-09-19
> 背景：模块"装上去用不了"。本轮不靠经验猜，逐条对照 Magisk 官方源码与官方模板查。
> 结论：**发现 4 个会导致"静默不加载"的硬问题**，其中 2 个是本次新增修复的致命项。

---

## 0. 权威依据（本次审计实际引用的来源）

| 来源 | 位置 / 链接 | 用来核对什么 |
|---|---|---|
| 官方 Zygisk 模块模板 | `external/zygisk/zygisk-module-sample`（topjohnwu/zygisk-module-sample，已在本地） | 目录布局、编译参数、API 版本对照表、STL 约束 |
| Magisk 源码 `native/src/core/zygisk/module.cpp` | 上游 master | 模块注册、API 版本检查、valid() 判定、dlopen 失败时是否打日志 |
| Magisk 源码 `native/src/core/zygisk/entry.cpp` | 上游 master | root companion（zygiskd）如何加载 so、`zygisk_companion_entry` |
| Magisk 源码 `native/src/core/module.rs` | 上游 master | `/data/adb/modules` 遍历、zygisk so 的收集与 ABI 映射、disable/unloaded 标记 |
| Magisk 开发者指南 | https://topjohnwu.github.io/Magisk/guides.html | module.prop 字段规范、`zygisk/unloaded` 语义、customize.sh 约定、update-binary 禁令 |

---

## 1. 目录到底该怎么放（先回答最容易搞混的问题）

**没有"第三个专门放 so 的目录"。** 所谓 `/data/adb/XXX` 和 `/data/adb/modules/<模块名>` 是同一棵树的两层：

```text
/data/adb/modules                       ← 模块根目录（Magisk 常量 MODULEROOT）
└── zygisk-packettool-tearhacker        ← 本模块目录，名字 = module.prop 的 id
    ├── module.prop                     ← 必须有，id 决定目录名
    ├── zygisk/                         ← ★ Zygisk 只认这一层
    │   ├── arm64-v8a.so                ← 64 位进程加载这个
    │   └── armeabi-v7a.so              ← 32 位进程加载这个
    ├── target.conf                     ← 本项目自己加的目标包名配置
    ├── post-fs-data.sh / service.sh / uninstall.sh
    └── webroot/                        ← KernelSU WebUI（Magisk 下不生效）
```

**判定开关是"zygisk 目录存在"，不是 module.prop 里的 `zygisk=true`。**
`module.rs` 里是 `let is_zygisk = dir.contains_path(cstr!("zygisk"))`。module.prop 里写 `zygisk=true` 官方文档没有这个字段，写了无害但也**不起作用** —— 只是留着给第三方管理器看。

**ABI 文件名映射**（`module.rs` 按编译目标 `cfg` 分支）：

| 设备架构 | 会去 open 的文件 |
|---|---|
| `aarch64` | `zygisk/arm64-v8a.so`（64 位进程）+ `zygisk/armeabi-v7a.so`（32 位进程） |
| `arm`（32 位机） | `zygisk/armeabi-v7a.so` |
| `x86_64` | `zygisk/x86_64.so` + `zygisk/x86.so` |
| `riscv64` | `zygisk/riscv64.so` |

所以 **aarch64 手机上两个 so 都会被打开**，32 位 App 走 `armeabi-v7a.so`。只打 arm64 的话，32 位 App 不会被注入。

---

## 2. 发现的问题与处置

### 🔴 P0-1　Zygisk API v5 与 `minMagisk=24000` 自相矛盾 → 静默不加载

**依据**：`module.cpp::RegisterModuleImpl`

```cpp
long api_version = *module;
// Unsupported version
if (api_version > ZYGISK_API_VERSION)
    return false;
```

返回 false → `mod` 没被赋值 → `valid()` 返回 false → 模块从列表里被 erase。
**整个过程不打任何日志**（`run_modules_pre` 只在 system_server 分支打 dlopen 失败日志），表现就是"模块装了、目录在、so 在，但从头到尾没加载过"。

官方模板 README 的版本对照表：

| Zygisk API | 最低 Magisk |
|---|---|
| v5 | **27000** |
| v4 | 26000 |
| v3 | 24300 |
| v2 | 24000 |

我们用的是 `zygisk.hpp` 的 `ZYGISK_API_VERSION 5`，却声明 `minMagisk=24000`。

**已修**：`module/module.prop` → `minMagisk=27000`。

---

### 🔴 P0-2　so 导出 5698 个全局符号，污染每一个 App 进程

**依据**：`module.cpp::run_modules_pre` 会把**所有** zygisk 模块 dlopen 进每一个 App 进程，之后才由 `preAppSpecialize` 决定去留。官方模板的 `Application.mk` 用 `-fvisibility=hidden -fvisibility-inlines-hidden` 就是为了这件事。

实测（修复前，arm64）：

```text
导出（已定义 + GLOBAL/WEAK）符号：5698
其中 glib / gum / capstone / json-glib / zai 前缀：2877
```

`CXX_VISIBILITY_PRESET hidden` 只管 C++，**管不到 C 写的 glib / gum / capstone / json-glib**，所以必须在链接期兜。

后果：污染宿主进程全局符号表（游戏进程里已有同名符号时会被覆盖或反之）、与其它 zygisk 模块互踩、dlopen 变慢且**每个 App 进程都要付这份代价**。

**已修**：新增 `native/zygisk_exports.map`（version script，只放行两个入口），CMake 加
`-Wl,--version-script=... -Wl,--exclude-libs,ALL -Wl,-z,lazy`。

实测（修复后）：

```text
arm64-v8a   : 已定义 GLOBAL/WEAK 导出 = 2（zygisk_module_entry / zygisk_companion_entry）
armeabi-v7a : 已定义 GLOBAL/WEAK 导出 = 2
DT_NEEDED   : liblog.so / libdl.so / libm.so / libc.so（无 libc++_shared，无第三方依赖）
```

顺带：去掉 BIND_NOW 后体积 14515600 → 13254560。

---

### 🟠 P0-3　包里没有 `target.conf` → 装完什么都不发生

配置为空集合时 `is_target()` 恒为 false，模块对任何进程都不注入。用户刷完之后的第一反应必然是"装了没反应"。

**已修**：新增 `module/target.conf`（默认全是注释 = 空目标），安装时 `customize.sh` 明确打印配置路径、以及"改完要重启目标 App"。

---

### 🟠 P1-1　`zygisk/unloaded` 会让模块被永久判定为 incompatible

**依据**：官方开发者指南

```text
zygisk/unloaded   <--- If exists, the native libraries are incompatible
```

`module.rs` 在成功打开 so 时会 `dir.unlink_at(cstr!("zygisk/unloaded"))`；反过来说，**只要曾经有一次加载失败，这个标记就会留下，之后 magiskd 不再把 so 交给 Zygisk**。

这是"换了修好的包也照样不生效"的经典根因。

**已修**：`customize.sh` 安装期 `rm -f "$MODPATH/zygisk/unloaded"`。

---

### 🟠 P1-2　自研 `update-binary` 违反官方禁令

**依据**：官方开发者指南原文

> 当模块通过 Magisk 应用下载时，`update-binary` 会被**强制**替换为最新的 `module_installer.sh`。
> **不要**在 `update-binary` 中添加任何自定义逻辑。

我们原先在里面塞了 4KB 自研逻辑（探测 magisk/ksud 并 exec、兜底解压等）。

**已修**：替换为 Magisk 官方 `scripts/module_installer.sh` 原版（9 行，只 source `util_functions.sh` 后 `install_module`）。自定义动作全部回归 `customize.sh`。

> 说明：KernelSU 走 `ksud module install`（Rust 实现），不执行 `update-binary`，所以换回官方版不影响 KSU 安装路径。

---

### 🟡 P2-1　postAppSpecialize 里复用 onLoad 保存的 JNIEnv

官方 example 只在 `preAppSpecialize` 里用 `env`；post 阶段 JNI 可用性没有任何书面保证，而这段代码跑在**每一个 App 进程**里，崩一次就是整机 App 起不来。

**已修**：进程名在 pre 阶段取一次并缓存到 `g_process_name`，post 阶段不再触碰 args / JNI。

### 🟡 P2-2　每个 App 进程都要把整个配置拉回来自己比对

原实现：App 侧 `connectCompanion` → companion 把所有包名发回来 → App 侧解析比对。
每个 App 启动都走一次全量配置传输，且 companion 每次都要 fopen。

**已修**：改成查询式协议，判定下沉到 root 侧，companion 内按 (mtime, size) 缓存配置。

```text
请求：[uint32 长度][进程名]
响应：单字节 '1' = 注入 / '0' = 跳过
```

用长度前缀而不是"读到 EOF"：避免依赖 `shutdown(fd, SHUT_WR)` 的半关闭语义（不同 Android 版本/不同 socket 类型行为不完全一致）。

### 🟡 P2-3　`zygisk/` 目录里混进了 README.md

Magisk 只 open `<abi>.so`，其它文件一律不看，但它们会随 zip 一起落到模块目录里，既脏也容易让人误以为会被加载。

**已修**：`scripts/package.py` 排除 `zygisk/` 下非 `.so` 文件；同时在打包期校验每个 so 的 ELF magic（最后一道能廉价拦下坏产物的关口）。

---

## 3. 【排障清单】Magisk 会"静默"跳过 Zygisk 模块的 6 种情况

真机上遇到"装了没反应"，**按这个顺序查**：

| # | 条件 | 现象 / 依据 | 怎么确认 |
|---|---|---|---|
| 1 | **Zygisk 总开关没开** | `module.rs`：zygisk 未启用时所有 zygisk 模块直接 `ignore` | Magisk App 设置里确认 Zygisk 打开 |
| 2 | 模块被 disable | `module.rs`：`disable` 文件存在则跳过 | `ls /data/adb/modules/<id>/disable` |
| 3 | **`zygisk/unloaded` 存在** | 官方：exists = incompatible，之后永不加载 | `ls /data/adb/modules/<id>/zygisk/unloaded`，有就删 |
| 4 | **API 版本高于宿主支持** | `module.cpp`：`api_version > ZYGISK_API_VERSION` → 静默丢弃 | 见 P0-1，本项目已要求 Magisk ≥27000 |
| 5 | 目标 App 在 **DenyList** | `app_specialize_pre`：命中 DenyList 直接 unmount，不加载模块 | Magisk 设置里把目标 App 移出排除列表 |
| 6 | **dlopen 失败**（缺依赖库等） | `run_modules_pre`：只有 system_server 分支打日志，**App 侧完全静默** | `readelf -d` 看 DT_NEEDED 是否都能在 App 进程里解析 |

外加本项目特有的两条：

- **没写 `target.conf`** → 空配置 = 不注入任何进程（P0-3 已补默认文件）
- **模块目录里同时有 `riru`** 或模块名是 `riru-core` → `module.rs` 直接跳过（与 Zygisk 不兼容）

---

## 4. 本次改动的文件清单

| 文件 | 改动 |
|---|---|
| `ZygiskAIRuntime/module/module.prop` | `minMagisk` 24000 → **27000** |
| `ZygiskAIRuntime/native/zygisk_exports.map` | **新增**：version script，只放行两个入口符号 |
| `ZygiskAIRuntime/native/CMakeLists.txt` | 链接期加 `--version-script` / `--exclude-libs,ALL` / `-z,lazy` |
| `ZygiskAIRuntime/zygisk/entry.cpp` | companion 改为查询式协议 + 配置按 mtime 缓存 |
| `ZygiskAIRuntime/zygisk/bootstrap.cpp` | 进程名在 pre 阶段缓存；判定改为一次 companion 查询；删除死代码 |
| `ZygiskAIRuntime/zygisk/bootstrap.h` | 新增 companion 协议常量与语义说明；明确 post 阶段不得用 JNI |
| `ZygiskAIRuntime/module/target.conf` | **新增**：默认空目标配置 + 使用说明 |
| `ZygiskAIRuntime/module/customize.sh` | 清理 `zygisk/unloaded`；每个 so 校验 ELF magic；安装界面打印配置指引 |
| `ZygiskAIRuntime/module/META-INF/.../update-binary` | 自研 4KB → **官方 `module_installer.sh` 原版** |
| `ZygiskAIRuntime/scripts/package.py` | 排除 `zygisk/` 非 .so；打包期校验 ELF magic；删除失败时降级为覆盖写 |

---

## 5. 验证结果（本机实测，非推断）

```text
编译   : arm64-v8a / armeabi-v7a 双 ABI 均通过（NDK r27d + CMake 4.3.1 + Ninja）
导出   : 两个 ABI 的已定义 GLOBAL/WEAK 导出均为 2 个
         zygisk_module_entry / zygisk_companion_entry
依赖   : DT_NEEDED = liblog.so libdl.so libm.so libc.so（无 libc++_shared）
体积   : arm64 13254560 / armv7 10912688
脚本   : 全部 sh -n 语法检查通过；换行符全部为 LF（官方要求，CRLF 会让 sh 起不来）
打包   : 12 个文件，zip 内 sha256 与源产物一致，权限 0755/0644 正确
```

---

## 6. 仍未解决的阻断

**真机验证依然被 root 阻断**（RMX5200 / Android 16，`ro.build.type=user`、BL locked、无 su、无 Magisk、`/data/adb` 不存在）。以上全部是源码与产物层面的修复，**尚未在真机上跑通一次**。

解 root 后的验证顺序：

```text
1. Magisk App 里确认 Zygisk 开关已打开（第 3 节第 1 条，最容易漏）
2. 刷 build/out/zygisk-packettool-tearhacker.zip
3. ls /data/adb/modules/zygisk-packettool-tearhacker/zygisk/   ← 确认 so 落地
4. ls /data/adb/modules/zygisk-packettool-tearhacker/zygisk/unloaded  ← 必须不存在
5. 往 target.conf 写入目标包名，确认目标 App 不在 DenyList
6. 重启目标 App
7. adb logcat | grep ZAI:      ← 看 ZAI:Bootstrap / ZAI:Companion / ZAI:Ipc
```

---

## 7. 遗留待办（未做，需决策）

1. **拆分 thin entry / payload**：现在 13MB 的 so 仍会被 dlopen 进每一个 App 进程，非目标进程靠 `DLCLOSE_MODULE_LIBRARY` 卸载，但**加载开销已经付过了**。业界做法（Hide My Applist / Zygisk-Il2CppDumper 一类）是把 zygisk so 做成几十 KB 的薄壳，在 pre 阶段用 `api->getModuleDir()` 拿到模块目录 fd、`openat` 出真正的 payload 再 dlopen。改动涉及 CMake target 拆分，本轮未做。
2. **LSPlant 仍 OFF**：NDK r27d 的 clang 18 编不过 LSPlant master，需 NDK r28+。
3. `service.sh` / `post-fs-data.sh` 目前是空脚本，仅保留结构约定。
