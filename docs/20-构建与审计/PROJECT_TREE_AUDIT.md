# PROJECT_TREE_AUDIT —— 工程目录审计

**产出依据**：施工手册 P-1.1
**审计日期**：2026-09-19
**审计对象**：`ZygiskAIRuntime/`（核心工程树）+ `external/`（外置源码）
**审计方式**：`find` / `du` / `wc` 实机统计 + 逐项对照 `docs/00-权威基线/STRUCTURE.md`

---

## 1. 实际体量

| 项 | 实测值 |
|---|---|
| 自有文件总数（排除 `third_party/`、`__pycache__`） | **140** |
| 自有代码行数（`.py` + `.cpp` + `.h`） | **9956** |
| Python 文件 | 33 |
| C/C++ 文件 | 23（`.h` 12 · `.cpp` 11） |
| JSON（schema + 黄金样例） | 25 |
| Markdown | 7 |
| Shell / 批处理 / PowerShell | 5 / 4 / 1 |
| `.gitkeep` 占位 | 28 |
| `third_party/` | 34M（frida-gum 32M + lsplant 2.3M） |
| `external/` | 275M（analysis 148M · mcp 74M · network 53M · zygisk 111K） |

## 2. 各目录文件数

| 目录 | 文件数 | 说明 |
|---|---|---|
| `zygisk/` | 6 | Zygisk Host（含官方 `zygisk.hpp`） |
| `runtime/` | 15 | Runtime Core + backend + manager |
| `native/` | 20 | 构建脚本 + `common/` + `include/ipc/protocol_constants.h` |
| `module/` | 6 | Magisk 模块外壳 |
| `ai_analyzer/` | 54 | **PC 侧 Host/MCP 层**（M0 + MVP 全部产物） |
| `build/` | 3 | `build-gum.sh` · `versions.env` · toolchains 说明 |
| `scripts/` | 5 | Windows 一键脚本 |
| `tools/` | 6 | 外部工具接入说明 |
| `docs/` | 9 | 工程内文档（8 个分类目录 + 索引） |
| `tests/` | 12 | 协议 / 端到端 / 工具面 测试 + 验收脚本 |

## 3. 空目录

**无真正空目录** —— 所有未填目录都放了 `.gitkeep` 占位。

## 4. 实质待填目录（仅含 `.gitkeep`，共 28 个）

```text
native/  （12 个）
  include/{hook,memory,module,process,runtime,thread}
  src/{hook,ipc,memory,module,process,runtime,thread}
  → Android 侧实现，全部需要 NDK 才能落地

tests/   （2 个）
  native/   ← Backend 级单测（需 NDK + 真机）
  runtime/  ← Runtime Core 单测（需 NDK + 真机）

docs/    （8 个，工程内文档分类）
  architecture · art · build · deployment · hook · mcp · memory · runtime

tools/   （5 个，外部工具接入说明）
  frida · jadx · mitmproxy · rizin · wireshark
```

> 本次审计清理了 **5 个陈旧 `.gitkeep`**（所在目录已填入真实文件）：
> `ai_analyzer/{bridge,host,schemas}` · `tests/integration` · `native/include/ipc`

## 5. 缺失文件（相对 STRUCTURE.md 应有清单）

| 文件 | 原因 | 是否阻塞 |
|---|---|---|
| `module/zygisk/arm64-v8a.so` | **构建产物**，需 M1 编译 | ⛔ 阻塞 M1（预期） |
| `build/out/<abi>/` | 同上 | ⛔ 阻塞 M1（预期） |
| `third_party/frida-gum/17.18.0/build/<abi>/libgum.a` | 同上 | ⛔ 阻塞 M1（预期） |

其余 STRUCTURE.md 声明的文件**全部存在**。

## 6. 多余文件

**无多余文件。** 所有文件都能在 STRUCTURE.md 或本阶段新增产物（`ai_analyzer/`、`tests/`、`native/include/ipc/protocol_constants.h`、`pytest.ini`）中找到出处。

> `pytest.ini` 为本次新增（Host 侧测试配置），STRUCTURE.md 已同步。

## 7. 目录冲突

**无目录冲突。** 已处理的一处：

| 冲突 | 处理 |
|---|---|
| 原 `ZygiskAIRuntime/mcp/` 与 MCP Python SDK 顶层包 `mcp` **硬冲突**（`import mcp.server` 会解析到自己） | ✅ 已改名 `ai_analyzer/`，总基线 §17.0/§19.1、STRUCTURE.md、施工手册、专业指导全部同步 |

## 8. 脚本引用路径核验（施工手册 P-1.1 强制项）

核验 `scripts/*.bat` · `scripts/*.ps1` · `build/scripts/*.sh` 引用的全部路径：

| 被引用路径 | 存在 | 说明 |
|---|---|---|
| `build/scripts/build-gum.sh` | ✅ | |
| `module/zygisk/` | ✅ | |
| `module/{module.prop,customize.sh,post-fs-data.sh,service.sh,uninstall.sh}` | ✅ | 5 个全在 |
| `third_party/frida-gum/17.18.0` | ✅ | |
| `third_party/lsplant` | ✅ | |
| `native/{CMakeLists.txt,Android.mk,Application.mk}` | ✅ | |
| `build/config/versions.env` · `VERSION` · `zygisk/zygisk.hpp` | ✅ | |
| `build/out/` | ❌ | **构建产物目录**，首次编译时生成 |
| `module/zygisk/arm64-v8a.so` | ❌ | **构建产物**，首次编译时生成 |
| `third_party/frida-gum/17.18.0/build/<abi>/libgum.a` | ❌ | **构建产物** |
| `/data/local/tmp/zygisk-packettool-tearhacker` | — | 设备侧路径，非本地 |

**结论：无脚本引用了不存在的、本应存在的路径。** 3 处 MISS 全是构建产物，属预期。

## 9. 判定

```text
目录审计  ✅ PASS
  体量与 STRUCTURE.md 声明一致
  无空目录、无多余文件、无目录冲突
  脚本引用路径全部有效（MISS 项均为构建产物）
  待填目录 28 个，全部为 Android 侧实现或文档占位
```

**审计未发现需要立即整改的结构问题。**

---

## 10. M1 落地后的增量（2026-09-19）

§1–§9 的快照是 M1 之前的。M1 完成后新增 / 变更如下，**结构规则仍然成立**
（无空目录、无目录冲突、未新增散放文件）：

### 新增文件

```text
build/config/msvc-native.ini          meson 的 build machine 编译器 / linker / pkgconfig
build/scripts/build-native.sh         CMake 构建 + 拷 so 到 module/zygisk/
build/scripts/gen_gum_include_dirs.py 从 meson compile_commands.json 导出 gum 的 include + 依赖库
build/scripts/fetch_subproject.py     按名字拉单个 subproject（codeload zip）
build/scripts/fake-pkg-config.py      pkg-config 替身（只认 glib 家族）
scripts/package.py                    Python 打包 Magisk zip（package.bat 依赖 cmd，沙箱不可用）
build/generated/gum_includes.cmake    **自动生成**，勿手改（由 gen_gum_include_dirs.py 产出）
```

### 变更

```text
VERSION → VERSION.txt                 原名会被 C++20 标准头 #include <version> 命中，必须带后缀
native/CMakeLists.txt                 新增 option(ZAI_ENABLE_LSPLANT)；gum include 改为 meson 导出
build/config/toolchain.env            新增 MSVC 段（INCLUDE / LIB 手工拼）
build/config/versions.env             同步 VERSION.txt 的说明
scripts/prefetch_subprojects.py       从 OPTIONAL 移除 tinycc（arm64 下是必需依赖）
```

### 需要留意的两处"非源码"污染

```text
third_party/frida-gum/17.18.0/build/     meson 构建产物（builddir、libgum.a）——属 third_party 目录，
                                         但是**构建输出**而非上游源码，不受"third_party 不得修改"约束
build/out/_old_arm64_lsplant/            旧的 CMake 构建目录（带 LSPlant），可手动删除
```

> ⚠️ `third_party/frida-gum/17.18.0/build/arm64-v8a/` 下有多个 `_builddir_old*` 残留
> （每次 meson setup 失败前会 mv 一份）。它们只是磁盘占用，可安全删除。
