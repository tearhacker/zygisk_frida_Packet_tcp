# Zygisk AI Runtime

**泪心独立研发 —— APP 逆向 / 封包 / 动态内存调试工具。**

Android 侧动态分析 Runtime。核心只围绕 **Zygisk + Frida-Gum + LSPlant** 构建，其余工具全部外置。

> 设计依据：`../docs/90-历史归档/真正的工作.txt.md`（v1.0 源码供应链与工程目录）。
> 功能/协议/工具面口径见 `../docs/00-权威基线/项目总基线_v1.1.md`（§17 工程目录已按本布局改版）。
> **完整目录标准清单 → [`STRUCTURE.md`](../docs/00-权威基线/STRUCTURE.md)**（含边界规则与待填目录）。

## 定位

```text
                    Zygisk AI Runtime
                           │
              ┌────────────┴────────────┐
              │                         │
        Zygisk Host                Runtime Core
              │                         │
              │              ┌──────────┴──────────┐
              │              │                     │
              │       Native Backend          ART Backend
              │              │                     │
              │       Frida-Gum 17.18.0         LSPlant
              │
              ▼
        Android App Process
```

真正属于本项目的核心是 `runtime/` 下的 **Runtime Manager + Hook/Memory/Process Manager + IPC**，
Frida-Gum 与 LSPlant 都只是可替换的 Backend。

## 三个核心源码

| 源码 | 版本 | 位置 | 用途 |
|---|---|---|---|
| Zygisk API | API v5（0BSD） | `zygisk/zygisk.hpp` | 唯一 API 来源，**禁止修改** |
| Frida-Gum | 17.18.0（wxWindows Licence 3.1） | `third_party/frida-gum/17.18.0/` | Native Backend，静态链接 |
| LSPlant | LGPL-3.0 | `third_party/lsplant/` | ART Backend，**必须动态链接为 `liblsplant.so`** |

> 🔴 LSPlant 是 LGPL-3.0，静态嵌入会触发"允许用户替换并重链接"义务。
> 构建脚本已强制 `SHARED`，详见 `../docs/00-权威基线/LICENSES.md`。

## 外置，不在本工程树内

```text
../external/
├── analysis/    jadx · apktool · rizin · r2frida · mobsf
├── network/     mitmproxy · pcapdroid · netbare
├── mcp/         python-sdk · specification
└── zygisk/      zygisk-module-sample（只读参考，非长期上游）
```

`tools/` 只放外部工具的接入说明与占位，**不编译进 `libai_analyzer.so`**。

## 目录

```text
zygisk/        Zygisk Host：module.cpp / entry.cpp / bootstrap.cpp
runtime/       Runtime Core：runtime · backend/{gum,art} · manager
native/        进程内能力：hook · memory · process · module · thread · ipc
third_party/   核心第三方源码（仅 2 个）
module/        Magisk 模块外壳（module.prop / *.sh / zygisk/<abi>.so）
ai_analyzer/   protocol · schemas · bridge · mock · tools · host（PC 侧，不进 Native）
build/         构建脚本 · 配置 · toolchain
scripts/       Windows 侧一键脚本
docs/ tests/   文档与测试
```

## 构建状态

✅ **已产出可刷的 Magisk 模块 zip**（2026-09-19）

```text
build/out/zygisk-ai-runtime.zip
  └── zygisk/arm64-v8a.so   13.5 MB · ELF64 / AArch64 / DYN
      导出 zygisk_module_entry · zygisk_companion_entry
      Frida-Gum + glib + capstone 已静态链入
```

**Frida-Gum 只能走源码构建，不能用 devkit** —— devkit 仅由
`github.com/frida/frida/releases/download/` 分发，本机代理拒绝该域名。
（备选：`meson -Ddevkits=gum` 可从源码现场生成 devkit，但仍需跑完整构建。）

### 双击构建（推荐，纯 cmd 环境可用）

根目录有两个一键入口，**不需要 Git Bash**：

```text
测试版.bat   → debug 构建（断言开、保留符号、不 strip）
               产物 build/out/zygisk-ai-runtime-debug.zip
发布版.bat   → release 构建（NDEBUG、strip 调试信息）
               产物 build/out/zygisk-ai-runtime.zip
```

两者都只是入口，实际逻辑在 `scripts/build_all.py`（Python 实现，不依赖 bash）。
之所以不让 `.bat` 直接干活用 cmd 写：工程路径含中文，cmd 代码页下写死中文路径会乱码，
改由 Python 内部用 `__file__` 推导路径即可规避。
（`.bat` 已 `chcp 65001`，中文提示可正常显示。）

`--skip-gum` 可复用已构建的 Frida-Gum，把构建从 ~15 分钟压到 ~40 秒：

```bash
python scripts/build_all.py --mode debug --skip-gum
```

### 手动分步（本机跑通的 bash 链路）

`scripts/*.bat` 在当前**沙箱**环境不可用（cmd.exe 被安全策略禁用），
但 `scripts/build_all.py` 与下面这套 bash 脚本在真实终端里都能用：

```bash
cd ZygiskAIRuntime
source build/config/toolchain.env        # NDK / CMake / Ninja / Meson 路径

# 0) 补 Frida-Gum 的必需依赖（只需一次）
python build/scripts/fetch_subproject.py tinycc libunwind libdwarf xz sqlite minizip-ng

# 1) Frida-Gum：meson 交叉编译（配置约 14 分钟 + 编译约 4 分钟）
bash build/scripts/build-gum.sh arm64-v8a

# 2) 把 gum 真实的 include 目录与依赖静态库导出给 CMake
python build/scripts/gen_gum_include_dirs.py

# 3) 本工程 native 层 → module/zygisk/arm64-v8a.so
bash build/scripts/build-native.sh arm64-v8a

# 4) 打包成 Magisk zip
python scripts/package.py
```

工具链路径可用环境变量覆盖：`ZAI_NDK` / `ZAI_CMAKE` / `ZAI_NINJA` / `ZAI_MESON` / `ZAI_PYTHON`，
默认值见 [`build/config/toolchain.env`](./build/config/toolchain.env)。

构建期还有两个**必须设**的环境变量（缺一个 meson 会以很隐蔽的方式崩）：

```text
PYTHONUTF8=0   setup 阶段（让 meson 用 replace 解码 cl.exe 的 GBK 输出）
PYTHONUTF8=1   compile 阶段（让 glib-mkenums 用 UTF-8 读含中文路径的 rsp 文件）
CODEBUDDY_SAFE_DELETE_ENABLED=0   沙箱给 shutil.rmtree 注入了钩子，会炸 meson 的临时目录清理
```

两者都已写进 `build/scripts/build-gum.sh`，不需要手工 export。

### LSPlant：当前需 `-DZAI_ENABLE_LSPLANT=OFF`

`native/CMakeLists.txt` 提供了 `option(ZAI_ENABLE_LSPLANT ON)`。本机构建时置 OFF：

```bash
export ZAI_ENABLE_LSPLANT=OFF
```

**原因**：LSPlant master 的 `art_method.cxx` 用了 C++20/23 模板 lambda
（`_sym.hook->* []<MemBackup auto backup>(...)`），NDK r27d 的 clang 18 把 `backup`
解析成了 `hook_helper.hpp:256` 那个**无参** lambda：

```text
error: too many arguments to function call, expected 0, have 1
error: called object type 'auto (lambda ...)::*)() const -> void' is not a function
```

按 `STRUCTURE.md` 的边界规则 third_party 源码不得修改，所以做成开关而非硬改。
**无功能损失**：`lsplant_adapter.cpp` 目前没有任何真实 `lsplant::` 调用（全是 TODO(M3)），
ART 后端本就是 M3 才接线。恢复条件：NDK r28+（clang ≥19），或固定到兼容的 LSPlant tag。

### 骨架代码已编译验证

`runtime/`、`zygisk/`、`native/` 下的代码**已于 2026-09-19 编译通过**。
过程中按 Frida-Gum 17.18.0 的真实签名修正了 `gum_backend.cpp` 的若干 API 调用
（`gum_memory_read` 返回新分配缓冲区、符号查找改成 OO 风格、
`gum_interceptor_attach` 第 4 参数改为 options），详见该文件注释。

⚠️ 编译通过 ≠ 真机可用：本机无 ARM64 设备，`adb devices` 为空，尚未做过运行时验证。

## 支持的 ABI

```text
arm64-v8a      64 位（默认，首次构建就是这个）
armeabi-v7a    32 位
```

Zygisk 按进程位数加载对应的 so：

```text
zygisk/arm64-v8a.so      → 只在 64 位进程注入
zygisk/armeabi-v7a.so    → 只在 32 位进程注入
```

**只带其中一个 ABI 也能正常安装**（`customize.sh` 要求"至少有一个"，不要求齐全），
但缺的那个 ABI 对应的进程**不会被注入** —— 例如只有 arm64 时，32 位 App 完全没反应。

构建指定 ABI：

```bash
python scripts/build_all.py --abi armeabi-v7a --mode release
python scripts/build_all.py --abi arm64-v8a   --mode release
```

两个都构建后，`module/zygisk/` 下会同时有两个 so，之后打出的 zip 两者都带。

## 配置目标进程

**默认不注入任何 App**（安全默认）：配置文件不存在时 `enabled=false`，
模块加载后立即 `DLCLOSE` 卸载，只在 logcat 留痕。

要注入指定 App，在手机上建配置文件：

```bash
adb shell
su
echo "com.example.target" > /data/adb/modules/zygisk-ai-runtime/target.conf
chmod 644 /data/adb/modules/zygisk-ai-runtime/target.conf
```

然后重启目标 App（不用重启手机）。之后的行为：

```text
其它进程   加载 → 过滤不通过 → 立刻卸载    日志: specialize: ... target_enabled=0
目标进程   加载 → 过滤通过   → 拉起 Runtime 日志: target matched: com.example.target
```

**为什么必须走 root companion**：App 进程读不到 `/data/adb`（目录权限），
所以配置由 Zygisk companion 在 **root 侧**读文件，再经 socket 回传给 App 进程。
这是 Zygisk 的固有约束，不是可选设计。

文件格式：一行一个包名，取第一个非空且非 `#` 开头的行。

> 当前骨架阶段即使注入成功，Runtime 也只做初始化（gum init），
> 尚无 Hook / IPC 行为 —— 那部分是 M2 后续工作。

## Host 侧进度（可运行）

PC 侧 MVP 已跑通，不依赖 NDK 与真机：

```bash
cd ZygiskAIRuntime
python -m pytest tests        # 199 项全绿
python tests/accept_mvp.py    # 端到端验收 28/28，打印可核对证据
```

覆盖：M0 协议契约（常量单一源 / 帧编解码 / 9 种消息 / 黄金样例）、
Bridge（握手 / 心跳 / 重连 / Session 失效）、Mock Runtime 后端、
MCP Server（Core 25 + Expert 10 工具，能力门禁自动摘除）。

细节见 [`ai_analyzer/README.md`](./ai_analyzer/README.md)。

## 许可

**本项目自身源码：Apache License 2.0**（见仓库根 [`LICENSE`](../LICENSE)）。

> ⚠️ 关于 Apache 2.0 的一个常见误解，先说清楚：
> 它是**宽松许可证（permissive）**，允许任何人自由使用、修改、再发布，
> **也包括闭源商用** —— 只需保留版权声明与许可证、并标注改过的文件。
> 它**不要求**「魔改后必须开源」。
> 若你要的是"衍生作品必须同样开源"，那属于 copyleft（GPL / LGPL 系），
> 与 Apache 2.0 不是一回事，需另行更换许可证。

分发二进制时必须随附第三方声明，见仓库根 [`NOTICE`](../NOTICE)。主要依赖：

| 组件 | 许可证 | 链接方式 |
|---|---|---|
| Frida-Gum | wxWindows Library Licence 3.1 | 静态链接（该证允许） |
| **LSPlant** | **LGPL-3.0** | **强制动态链接**（须允许用户替换） |
| Zygisk API | 0BSD | 仅头文件 |

完整核对与三条硬约束见 [`../docs/00-权威基线/LICENSES.md`](../docs/00-权威基线/LICENSES.md)。

## 联系与社区

```text
开发者    泪心
QQ        2254013571
Q群       435539500
Discord   https://discord.gg/yghYHcEdD
官网      http://teargamestorem.top/
```
