# Zygisk AI Runtime —— 模块 WebUI 设计 v1.0

> 层级：施工指导层（与 P4/P5 同级，属其补充），**不修改任何冻结项**。
> 冲突时服从 `00-权威基线/项目总基线_v1.1.md`。
> 日期：2026-09-19

---

## 1. 目标与范围

刷入模块后，在 **KernelSU 管理器里直接点击「打开」** 进入一个网页面板，做到：

0. **服务状态**（最醒目，置顶）——一眼看到 Runtime「未连接 / 启动中 / 等待连接 / 已连接」。
1. **模块全景**——一眼看到模块是否装对（产物 / ABI / 配置 / 设备环境）。
2. **网页端改配置**——主要是注入目标 `target.conf`，从已安装包列表里选，不用 `adb shell` 手打。
3. **看日志**——直接看 `ZAI:*` 的 logcat，判断注入链路有没有真的跑起来。

### v1 明确不做

| 不做 | 原因 |
|---|---|
| IPC 实时连接状态 | **M2 未完成，Runtime 目前只做 gum 初始化，无 IPC 行为**。做出来就是 Fake Success |
| Hook 管理 / 内存读写面板 | 依赖 M3，且属于 PC 侧 MCP 工具面，不该在网页上重复一套 |
| 自动 `force-stop` 目标 App | 破坏性操作（会杀掉用户正在用的 App），v1 只提示手动重启 |
| Magisk 侧 WebUI 入口 | Magisk 无此机制，见 §8 |

---

## 2. KernelSU WebUI 机制（已与官方文档核对）

来源：<https://kernelsu.org/zh_CN/guide/module-webui.html>

- Web 资源放模块根目录的 **`webroot/`** 子目录，**必须有 `index.html`**。
- 管理器用 **WebView** 加载该页面。
- KernelSU 注入全局 **`ksu`** 对象提供系统能力。官方 npm 包 `kernelsu@3.0.2` 只是它的薄封装，实测其 `index.js` 核心就一行：

  ```js
  ksu.exec(command, JSON.stringify(options), callbackFuncName);
  ```

  即：`exec` 把回调函数名挂到 `window` 上，由原生侧回调 `window[cb](errno, stdout, stderr)`。

- ⚠️ **官方警告**：安装时 KernelSU 会**自动设置 `webroot` 的权限与 SELinux context**，「如果不知道自己在做什么，请不要自行设置该目录的权限」。
  → 这直接约束了 `customize.sh`，见 §7.2。

### 可用 API（源自 `index.d.ts` + `index.js`）

| API | 说明 | 本设计是否用 |
|---|---|---|
| `exec(cmd)` | 执行 shell，返回 `{errno, stdout, stderr}` | ✅ 主力 |
| `spawn(cmd, args, opts)` | 流式子进程 | ❌ 暂不需要 |
| `listPackages(type)` | 列出已安装包名 | ✅ 用于下拉选目标 |
| `getPackagesInfo(pkgs)` | 包名 → 应用名 / 版本 / uid | ✅ 下拉显示应用名 |
| `moduleInfo()` | 模块信息字符串 | ✅ 兜底显示 |
| `fullScreen(bool)` | 全屏 | ❌ |
| `toast(msg)` | Toast | ✅ 操作反馈 |
| `enableEdgeToEdge(bool)` | 沉浸式 | ❌ |
| `exit()` | 关闭页面 | ❌ |

---

## 3. 关键决策：零构建

**不引入 npm / parcel / 打包链。** 理由：

1. **官方库本就是薄封装**，自行实现 ~30 行即可，无收益。
2. **不能用 ESM**：页面若以 `file://` 加载，其 origin 是 `null`，`<script type="module">` 会被 CORS 拦截导致整页失效。用 **classic script**（普通 `<script>`）最稳。
3. 本仓是 C/C++ + Python 工程，为 3KB 的 JS 引入 node 构建链不划算，且会给后续打包增加环节。

因此：`webroot/` 下只有两个文件，纯手写、零依赖。

```text
module/webroot/
├── index.html   页面结构 + 样式 + 逻辑
└── ksu.js       ksu 注入对象的薄封装 + 能力探测
```

> 若将来页面复杂到需要构建，须回来修订本文件 §3。

---

## 4. 目录与路径

模块安装后固定路径（id 为 `zygisk-ai-runtime`，不可改）：

```text
/data/adb/modules/zygisk-ai-runtime/
├── module.prop
├── target.conf          注入目标（一行包名，# 开头为注释）
├── zygisk/<abi>.so
└── webroot/             ← 本设计新增
    ├── index.html
    └── ksu.js
```

页面内**不依赖 `$MODDIR` 环境变量**（WebUI 进程里未必有），一律用绝对路径常量。

---

## 5. 数据来源（命令清单）

全部经 `exec()` 执行，以 root 身份。

### 5.1 只读

| 面板字段 | 命令 | 读不到时 |
|---|---|---|
| 模块元信息 | `cat /data/adb/modules/zygisk-ai-runtime/module.prop` | 标「异常」 |
| 注入目标 | `cat .../target.conf 2>/dev/null` | 显示「未配置（不注入任何 App）」 |
| 已装产物 | `ls -l .../zygisk` | 标「异常」 |
| 设备 ABI | `getprop ro.product.cpu.abi` / `ro.product.cpu.abilist` | 未知 |
| Android 版本 | `getprop ro.build.version.release` / `ro.build.version.sdk` | 未知 |
| 内核 | `uname -r` | 未知 |
| root 方案 | `ls -d /data/adb/ksu 2>/dev/null`（KSU）/ `ls -d /data/adb/magisk 2>/dev/null`（Magisk） | 未知 |
| 注入是否发生过 | `logcat -d \| grep -E "ZAI:" \| tail -n 80` | 显示「无记录」 |

> **logcat 的坑**：本模块 tag 形如 `ZAI:Bootstrap`，本身含冒号。而 `logcat -s` 的 filterspec 语法是 `TAG:PRIORITY`，直接写 `-s ZAI:Bootstrap` 会被误解析为「tag=ZAI，priority=Bootstrap」。
> **因此统一用 `logcat -d | grep -E "ZAI:"`，不用 `-s`。**

### 5.2 写

| 操作 | 命令 |
|---|---|
| 保存注入目标 | `sh -c "printf '%s\n' '<pkg>' > .../target.conf.tmp && mv .../target.conf.tmp .../target.conf && chmod 0644 .../target.conf"` |
| 清空注入目标 | `rm -f .../target.conf` |

**命令构造的两条硬约束**：

1. **写操作必须显式包一层 `sh -c`**。
   无法确定原生 `ksu.exec` 是走 `/system/bin/sh -c` 还是直接 `Runtime.exec`。
   重定向 `>` 和 `&&` 只在 shell 下成立，直接传会在非 shell 实现里被当成普通参数而静默失败。
   显式 `sh -c` 在两种实现下都成立。
2. **读操作一律不写 shell 元字符**（无管道、无重定向、无 `&&`），两种执行方式都能跑。
   读不到时在 JS 里靠 `errno` / `stderr` 判定，而不是靠 `2>/dev/null` 吞错误。

配合 §7.1 的白名单，进入 `sh -c` 的包名只可能含 `[A-Za-z0-9_.]`，不存在引号逃逸。

### 5.3 服务状态（2026-09-19 新增）

页面运行在**手机上**，能判定的是**设备侧 Runtime（60500）**；
PC 侧 MCP Server（60501）在电脑上，手机够不着。
因此拆成两段显示，**不许混为一谈**，更不许用手机侧状态冒充「MCP 已连上」。

判定输入（全部无管道、无重定向，遵守 §5.2 的硬约束）：

| 输入 | 命令 | 说明 |
|---|---|---|
| 目标包名 | `cat .../target.conf` | 没配目标就无从判定进程 |
| 目标进程是否活着 | `pidof <pkg>` | 不用 `ps \| grep` —— 管道在非 shell 实现下会失效 |
| 端口状态 | `cat /proc/net/tcp` + `cat /proc/net/tcp6` | 在 JS 里解析，不依赖 `netstat` / `ss` 是否存在 |

`/proc/net/tcp` 解析规则：`local_address` 形如 `0100007F:EC54`，
冒号后是**端口的十六进制**（`0xEC54 = 60500`）；`st` 列 `0A` = LISTEN，`01` = ESTABLISHED。

四态判定（互斥、可复现）：

| 状态 | 判定条件 | 含义 |
|---|---|---|
| **未连接** | 60500 未 LISTEN | 目标 App 没运行，或 Runtime 没被拉起 |
| **启动中** | 未 LISTEN 且 `pidof` 有结果 | 目标进程已起，正在 specialize |
| **等待连接** | 已 LISTEN 且无 ESTABLISHED | Runtime 在等 PC 接入 |
| **已连接** | 已 LISTEN 且有 ESTABLISHED | PC 已通过 `adb forward` 接入 |

UI 颜色：灰 → 黄 → 蓝 → 绿。
**任何一态都必须有命令输出作证**；判不出来就落「未验证」，不许猜。

自动刷新默认关闭，可一键开启（5 秒一次）——状态是会变的，让用户手动点不如自动刷。

---

## 6. 状态如实原则（对应「禁止 Fake Success」）

页面每个状态位只能落在这四级之一，**不允许出现中间态的模糊美化**：

| 级别 | 含义 | 页面表现 |
|---|---|---|
| **已验证** | 有真实命令输出作证 | 绿 |
| **未验证** | 该检查没跑通（命令失败/无输出） | 灰 + 说明原因 |
| **未实现** | 功能本身还没做（如 IPC 状态） | 灰 + 标注「M2 未实现」 |
| **未知** | 无法判定 | 黄 + 说明为何判不了 |

明确纪律：**M2 之前，面板上不得出现「已连接 / 运行中 / 注入成功」这类字样**。
`logcat` 里有 `ZAI:Bootstrap` 的 specialize 记录，才算注入链路**真的**跑过一次——这是目前唯一可信的运行时证据。

---

## 7. 安全边界

### 7.1 包名白名单校验

`target.conf` 会被写进 shell 命令，**必须先校验再拼命令**，防命令注入：

- 只允许 `[A-Za-z0-9_.]`，且必须含至少一个 `.`；长度 ≤ 255。
- 不合规直接拒绝并提示，**不做转义后放行**（白名单优于黑名单）。

### 7.2 不动 webroot 权限

`customize.sh` 原有一句 `set_perm_recursive "$MODPATH" 0 0 0755 0644` 会覆盖整个模块目录，
与 KSU 官方警告冲突（可能让 WebUI 加载失败）。
→ 改为**逐项设置并跳过 `webroot`**，见 §9 的改动。

### 7.3 不做破坏性操作

- 不自动 `force-stop`、不自动重启、不改系统属性。
- 改配置后明确提示「需重启目标 App 才生效」，由用户自己操作。

---

## 8. Magisk 差异

- Magisk **没有** WebUI 机制，`webroot/` 对它只是无害的多余文件，不影响安装与注入。
- 因此本功能对 Magisk 用户**不可见**，页面自身会在「root 方案」一栏如实显示检测到的方案；
  若检测为 Magisk，页面顶部提示「当前 root 方案不支持内嵌面板，请用 KSU 管理器打开」。
- 可选后续：为 Magisk 补 `action.sh`（点击「动作」执行），但 Magisk 的 action 无交互 UI，只能做打印/切换，收益有限，**v1 不做**。

---

## 9. 对现有文件的影响

| 文件 | 改动 |
|---|---|
| `module/webroot/index.html` | 新增 |
| `module/webroot/ksu.js` | 新增 |
| `module/customize.sh` | 改：权限设置跳过 `webroot` |
| `scripts/package.py` | **不改**（`rglob` 遍历会自动纳入 webroot；`.html/.js` 落 `0644`） |
| `module/module.prop` | **不改**（KSU 靠 `webroot/index.html` 是否存在识别，无需额外字段） |

---

## 10. 验收

### 10.1 无真机时的静态验收（本轮可做）

- [x] `webroot/index.html` 与 `ksu.js` 已落盘
- [x] zip 内包含这两个文件，权限 `0644`
- [x] `customize.sh` 语法检查 + 确认跳过 webroot
- [x] HTML/JS 语法冒烟（无未闭合标签、JS 可被解析）

### 10.2 真机验收（等 M2，有设备后补）

- [ ] KSU 管理器模块卡片出现「打开」按钮
- [ ] 点开能看到模块元信息、产物、ABI、target.conf
- [ ] 改目标包名并保存后，`cat target.conf` 确为写入值
- [ ] 重启目标 App 后 `logcat` 出现 `ZAI:Bootstrap` 的 specialize 记录
- [ ] 注入非目标 App 时**不**出现该记录（负向验证）

---

## 11. 后续（M2 及以后）

1. **待裁决 #7（IPC 端点）落地后**，页面加「运行时状态」区：读 root 侧状态文件展示 IPC 是否存活、session 列表。
   —— 在那之前**不许**先画一个假的「已连接」。
2. 若 Runtime 侧提供只读状态文件（如 `/data/local/tmp/zai-runtime/status.json`），页面直接 `cat` 它，
   **不**为了面板而另起一套 IPC —— 避免与冻结的协议层冲突。
