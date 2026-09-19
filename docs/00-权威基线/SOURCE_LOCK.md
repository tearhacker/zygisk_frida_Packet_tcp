# 源码供应链锁定表 v1.1（已落盘核验）

**拉取日期**：2026-09-19
**拉取方式**：`codeload.github.com` zip 快照（非 git clone，**本地无 `.git` 目录**）
**本地根目录**：`external/`（2026-09-19 由 `vendor/` 迁入；**核心 2 个已移出到 `ZygiskAIRuntime/third_party/`**）
**核验状态**：关键头文件逐项检查通过（见 §3）

> ⚠️ 为什么不是 git clone：本机代理对 `github.com` 的 git 协议不稳定（间歇 `CONNECT tunnel failed, 502` / `Empty reply from server`），
> 而 `codeload.github.com` 的 zip 通道稳定。代价是**没有 git 历史、无法 `git pull` 更新**。
> 需要版本历史时，用 `git clone --depth 1` 单独补（脚本见 §5）。

---

## 1. 已拉取清单

### P0 核心（直接集成）

| 项目 | 上游 | 锁定 ref | commit | 本地路径 | 体积 |
|---|---|---|---|---|---|
| **Frida-Gum** | frida/frida-gum | tag `17.18.0` | `22e077120358a49b26e32110a6e2b8e80f1ed7f1` | `runtime/frida-gum` | 32M |
| **LSPlant** | LSPosed/LSPlant | branch `master` | `d8b5d1dbb664abc606644036822e4bb64547edf6` | `runtime/lsplant` | 2.3M |
| **zygisk-module-sample** | topjohnwu/zygisk-module-sample | branch `master` | `8ce26128f81baaed0b969aaf7f52f886b61af4ab` | `zygisk/zygisk-module-sample` | 115K |
| **MCP Python SDK** | modelcontextprotocol/python-sdk | tag `v2.2.0` | `9972c21aa42054fb1450c5fc614761ed11847ec6` | `mcp/python-sdk` | 18M |
| **MCP Specification** | modelcontextprotocol/specification | branch `main` | `24efd6e7cbd7a074e6b3b781eb370891df40afad` | `mcp/specification` | 56M |

### P1 网络

| 项目 | 上游 | 锁定 ref | commit | 本地路径 | 体积 |
|---|---|---|---|---|---|
| **mitmproxy** | mitmproxy/mitmproxy | branch `main` | `b506c68108e287104045333ade476d92c39c275e` | `network/mitmproxy` | 44M |
| **PCAPdroid** | **emanuele-f/PCAPdroid** ⚠️改 | branch `master` | `6571f9d7d9654b98fb84ed497092abf4195db9b6` | `network/pcapdroid` | 16M |
| **NetBare** | **MegatronKing/NetBare-Android** ⚠️改 | branch `master` | `df5b417ea663763932cabf1ef52f15b09ddc2e16` | `network/netbare` | 3.1M |

### P2 分析与参考

| 项目 | 上游 | 锁定 ref | commit | 本地路径 | 体积 |
|---|---|---|---|---|---|
| **JADX** | skylot/jadx | branch `master` | `2fb1b16386941660fda07e9017285aec40fcb37f` | `analysis/jadx/src` | 16M |
| **Apktool** | iBotPeaches/Apktool | branch `main` | `4f89d677628942570e20eadbf5aa1ebe892341ed` | `analysis/apktool/src` | 56M |
| **Rizin** | rizinorg/rizin | branch `dev` | `e00813631c1e26ea200a387b1741659939b0bb4b` | `analysis/rizin` | 77M |
| **r2frida** | nowsecure/r2frida | branch `master` | `fef42e0a7a92790fa8c08cc76a3294619e96e0ab` | `analysis/r2frida` | 1.2M |

commit 列为拉取时 `git ls-remote` 取得的 HEAD/tag 值，用于追溯；本地是 zip 快照，**不做本地提交校验**。

---

## 2. 与原《源码选择》表的差异（重要）

| 项 | 原表 | 实际情况 | 处理 |
|---|---|---|---|
| PCAPdroid | `PCAPdroid/PCAPdroid` | 该组织路径已失效，现仓库为 `emanuele-f/PCAPdroid` | ✅ 已改用新地址 |
| NetBare | `MegatronKing/NetBare` | 不存在；正确仓库是 `MegatronKing/NetBare-Android` | ✅ 已改用新地址 |
| MCP SDK 版本 | "v2" | 实际最新 tag 为 **v2.2.0** | ✅ 锁定 v2.2.0 |
| Frida-Gum | 17.18.0 | tag 存在，确认可拉 | ✅ 一致 |
| JADX / Apktool | "当前稳定版" | 最新 release：**jadx v1.5.6** / **apktool v3.0.3** | ⚠️ 二进制未下到（见 §4） |
| MCP Spec | 2026-07-28 | `schema/2026-07-28` 目录存在 | ✅ 一致 |

---

## 3. 落盘核验（关键文件逐项检查）

```text
OK  runtime/frida-gum/gum/gum.h
OK  runtime/frida-gum/gum/guminterceptor.h
OK  runtime/frida-gum/gum/gummemory.h
OK  runtime/frida-gum/gum/gumstalker.h
OK  runtime/lsplant/lsplant/src/main/jni/include/lsplant.hpp
OK  zygisk/zygisk-module-sample/module/jni/zygisk.hpp     ← 唯一 API 来源
OK  mcp/python-sdk/src/mcp
OK  mcp/specification/schema/2026-07-28
OK  network/mitmproxy/mitmproxy
OK  network/pcapdroid/app
OK  network/netbare/netbare-core · netbare-injector · netbare-sample
OK  analysis/jadx/src/jadx-core
OK  analysis/apktool/src/brut.apktool
OK  analysis/rizin/librz
OK  analysis/r2frida/src
```

---

## 4. 未拉取 / 待补项

| 项 | 原因 | 后续处理 |
|---|---|---|
| **Magisk** | 设备侧运行环境，非源码依赖 | 不需要源码；设备装 Magisk 即可 |
| **MobSF** | zip 通道下载中断（仅参考项） | 低优先级，需要时再补 `MobSF/Mobile-Security-Framework-MobSF` |
| **jadx / apktool 二进制** | `github.com/.../releases/download` 域名被代理拒绝（502） | 换网络下载，或直接用本地已有的 jar；`analysis/jadx/bin`、`analysis/apktool/bin` 已预留目录 |
| **frida-mcp / delamain** | 原文档只给了名字，未确认具体仓库 | 二者均标注为"参考、不作核心"，暂不拉；确认仓库后补 |
| **LICENSE 核对** | ~~未做~~ → ✅ **已完成 2026-09-19** | 结果见 `LICENSES.md`；三条硬约束已落到 CMake / versions.env |

---

## 5. 复现命令

```bash
# 全量复现（同本次方式）
bash scripts/fetch_sources.sh     # git 通道版本（代理不稳时可能失败）

# 单仓补拉（zip 通道，稳定）
curl -sSL --retry 3 --retry-all-errors -o x.zip \
  https://codeload.github.com/<owner>/<repo>/zip/refs/tags/<tag>
unzip -qo x.zip

# 需要 git 历史时单独补
git clone --depth 1 --branch <ref> https://github.com/<owner>/<repo>.git <dir>
```

---

## 6. 待清理

```text
✅ 已全部清理：
   - vendor/_dup/    netbare / pcapdroid 重复副本 —— 已合并并删除
   - vendor/         目录本身已删除，内容全部迁出
   - lsplant 多余嵌套层 —— 已展平（原为 lsplant/lsplant/<repo>）
```

---

## 7. ✅ LICENSE 核对（已于 2026-09-19 完成）

总基线 §16.3 的 **M1 强制前置项**。逐仓实读 LICENSE / COPYING / README 原文，结果写入 `LICENSES.md`。

**核对结论**：12 个仓库全部完成，其中 **3 项触发集成方式硬约束**：

```text
🔴 LSPlant（LGPL-3.0）      必须 SHARED 动态链接，禁止静态嵌入
🔴 PCAPdroid（GPL-3.0）     禁止链接 / copy 源码，只能独立 App 经 IPC
🔴 Rizin（GPL-3.0）         仅 Host 侧独立进程 CLI，源码不得并入 host/
```

无负担项：Zygisk API 头文件 **0BSD**（官方 README 明确，不受 Magisk GPLv3 影响）；
Frida-Gum 为 wxWindows Licence 3.1（允许静态链接）；NetBare / mitmproxy / r2frida / MCP SDK 为 MIT；
JADX / Apktool 为 Apache-2.0。

**仍待办**：本项目自身开源许可**尚未声明**（Release 前必须定）。

<details>
<summary>核对时需重点关注的项（历史记录）</summary>


| 需重点核对 | 原因 |
|---|---|
| frida-gum | 将静态链接进 `libai_analyzer.so`，条款直接影响分发方式 |
| LSPlant | 同上 |
| PCAPdroid / NetBare | Android 侧集成，注意 GPL 传染性 |
| mitmproxy | Host 侧，MIT 系通常无碍 |
| Apktool / JADX | Host 侧调用 |

核对结果写入 `LICENSES.md`，**不得事后补**。

</details>

---

## 8. 目录映射（2026-09-19 已执行完成）

**核心 2 个**（已搬入核心工程树）：

```text
external/runtime/frida-gum     → ZygiskAIRuntime/third_party/frida-gum/17.18.0/
external/runtime/lsplant       → ZygiskAIRuntime/third_party/lsplant/   （已展平一层嵌套）
external/zygisk/…/zygisk.hpp   → ZygiskAIRuntime/zygisk/zygisk.hpp      （只取头文件，原文件禁止修改）
```

**外置 10 个**（原地保留在 `external/`，不进核心工程树、不编译进 `libai_analyzer.so`）：

```text
external/analysis/{jadx,apktool,rizin,r2frida,mobsf}
external/network/{mitmproxy,pcapdroid,netbare}
external/mcp/{python-sdk,specification}         规范参考 + pip 依赖源
external/zygisk/zygisk-module-sample             只读参考，非长期上游
```

> 「外置」不等于删除、不等于不使用。网络面与静态分析仍依赖它们，
> 只是以独立进程 / 独立 App / Host 侧 CLI 的形式协作（见 `ZygiskAIRuntime/tools/README.md`）。

**已清空**：原 `vendor/` 目录已删除（内容全部迁出）。

---

## 9. Frida-Gum subprojects：必需 / 不需要（2026-09-19 实测）

`ZygiskAIRuntime/third_party/frida-gum/17.18.0/subprojects/` 下有 15 个 `.wrap`。
**arm64 + android** 目标下（`gumjs` / `gumpp` / `quickjs` / `tests` / `inspector` 均 disabled），
实测的必需性划分如下 —— 早期"tinycc 只给 graft_tool 用、xz 只给 tests 用"的判断**是错的**。

### 必需（缺一个 meson setup 就停）

| 依赖 | 判定依据 |
|---|---|
| `glib`（含内嵌 libffi / pcre2 / zlib / gvdb） | `meson.build:393` |
| `capstone` | `:419` `version: '>=5.0.0'` |
| `json-glib` | `:445` |
| **`tinycc`** | `:438` — `required: (host_abi in ['arm','arm64'] and little endian) or (…)`，**arm64 必中**；与 graft_tool 是否 disabled 无关 |
| **`libunwind`** | `:543` — `host_os_family in ['linux','freebsd','qnx']`，android 属于 linux family，默认 required |
| **`libdwarf`** | `:556` `required:false`，但 `:575` 有 `if not found → required: true` 兜底 |
| **`xz`** | libunwind 需要 `liblzma`（`Disabling support for LZMA-compressed symbol tables` 之前会先尝试拉取） |

缺失时的报错是统一的：

```text
ERROR: Subproject <name> is buildable: NO
ERROR: Automatic wrap-based subproject downloading is disabled
```

### 不需要

```text
v8 · quickjs     只在 gumjs 启用时需要（已 disabled）
openssl          meson.build:605 是 required: false，本项目网络面独立于 Gum
libsoup · glib-networking   inspector（已 disabled）
gtk-doc · sysprof            文档 / 性能剖析
sqlite · minizip-ng          database / 可选压缩（均为 required:false 或未启用）
```

> 拉取工具：`ZygiskAIRuntime/build/scripts/fetch_subproject.py <name> …`
> （不要用 `scripts/prefetch_subprojects.py` 补单个依赖 —— 它遍历全部 wrap，
> 任意一个失败就整体中断，实测会崩在 `json-glib/subprojects/glib` 的超长文件名上。）

## 10. LSPlant：锁定 ref 与工具链兼容性

| 项 | 值 |
|---|---|
| 上游 | `LSPosed/LSPlant` |
| 锁定 ref | branch `master` |
| commit | `d8b5d1dbb664abc606644036822e4bb64547edf6` |

⛔ **该 ref 与 NDK r27d 的 clang 18 不兼容**（`art_method.cxx` 的 C++20/23 模板 lambda 解析失败），
详见 `../20-构建与审计/BUILD_BLOCKERS.md` §7。当前构建用 `-DZAI_ENABLE_LSPLANT=OFF` 绕过。

**需要回写的场景**：若改用 NDK r28+ 或把 LSPlant 固定到兼容 tag，必须更新本表的 ref / commit，
并同步 `docs/20-构建与审计/BUILD_BLOCKERS.md` §7 与 `ZygiskAIRuntime/README.md` 的构建状态。
