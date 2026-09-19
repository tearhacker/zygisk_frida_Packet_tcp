# 多进程抓包与 MCP 实时附加 —— 需求与设计约束 v1.0

> 来源：项目所有者 2026-09-19 提出。
> 状态：**需求已登记，实现未完成**。本文件只定义需求与约束，不含实现代码。

## 1. 需求原文（转述）

1. **WebUI 必须支持多包名保存**：一次可配置多个目标包名，而不是只能填一个。
2. **多进程抓包**：同一次会话内，多个进程的网络流量要能同时抓，且能分辨出
   每条流量属于哪个进程。
3. **MCP 工具可实时附加 / 切换进程**：手机上把目标进程打开即可，MCP 侧能
   指到哪个进程就分析哪个，不需要重启整个工具链。
4. **模块目录改名**：刷入后模块文件夹为 `zygisk-packettool-tearhacker`
   （原 `zygisk-ai-runtime`）。

## 2. 已完成（2026-09-19）

| 项 | 状态 | 落点 |
|---|---|---|
| 模块 ID 改名 `zygisk-packettool-tearhacker` | ✅ | `module/module.prop`、`zygisk/entry.cpp::kTargetConf`、`module/webroot/index.html::MODDIR`、各构建脚本与文档 |
| target.conf 多包名（native 侧） | ✅ | `zygisk/entry.cpp::read_target_packages()` 返回全部行；`zygisk/bootstrap.h::TargetConfig.packages` + `matches()`；`bootstrap.cpp` 按行解析、集合匹配 |
| WebUI 多包名编辑与保存 | ✅ | `module/webroot/index.html`：textarea 多行编辑、包名 chips 展示、应用下拉「追加选中」、逐行校验、多包名 pidof |

## 3. 未完成项与其真实约束

### 3.1 多进程抓包

**约束 1：Zygisk 是进程内注入，天然是多实例。**
每个被注入的 App 进程里都跑着一份 Runtime，各自独立。因此「多进程抓包」
不是"一个 Runtime 抓多个进程"，而是"N 个 Runtime 各抓自己那份，再汇总"。

推论：必须有一个**跨进程的关联键**，否则 PC 侧拿到 N 路流量无法区分归属。
候选：`pid` + `package` + `connection_id`，由 Correlation Engine 归集。

**约束 2：抓包能力目前为 `network.capture` = true，但 Mock 后端不支持。**
真机 Runtime 尚未实现抓包（M2 未做）。`network.capture_start` / `capture_stop`
在当前 Mock 后端不可用（见 `apk.list` 返回的 `mock_supported` 白名单）。
所以"多进程抓包"今天**不具备可验证性**，先登记设计，等 M2 落地。

**设计待定项**：
- 抓包作用域：整机（VPN/Netfilter 式）vs 仅注入进程（in-process hook 式）。
  —— 当前架构是 in-process，天然按进程隔离，这其实**正好**满足"多进程且不混淆"。
- 多进程时的 Artifact 切分：每进程一个 PCAP，还是单 PCAP 带进程标签。
  （受"大文件不进 MCP JSON"约束，只能落 Artifact + metadata。）

### 3.2 MCP 实时附加 / 切换进程

**这是本需求里最需要澄清的一点，存在两种完全不同的语义：**

| 语义 | 含义 | 可行性 |
|---|---|---|
| A. **配置切换**（弱） | 改 target.conf → 手机重启 App → MCP 侧 Session 指向新进程 | ✅ 可行，且已支持多包名 |
| B. **运行时热附加**（强） | 进程**已经在跑**、没被注入过，不重启就把它拉进分析 | ❌ 当前不可行 |

原因（架构级，不是偷懒）：
Zygisk 只在 **`preAppSpecialize`**（进程由 zygote fork 出来的那一刻）注入一次。
进程已经跑起来之后，Zygisk **没有任何机制**把模块塞进去。
要做到 B，必须另开一条路：`ptrace` 注入、或 ` LD_PRELOAD` 重启动、
或 root 侧 `inject` —— 每一种都是独立于 Zygisk 的新注入通道，需要单独设计与实现。

**结论**：手机上"打开进程即可"这个操作，在语义 A 下是成立的
（打开 = 启动 → 触发 specialize → 注入 → PC 侧可见），
但它等价于**重新启动该 App**，不是"附着到一个已运行的进程"。
这点必须在产品话术上讲清楚，不能让使用者误以为支持热附加。

**待裁决**：项目所有者要的是 A 还是 B？
- 若 A：当前多包名改造已足够，补 PC 侧"切换当前分析目标进程"的工具即可。
- 若 B：需新增独立注入通道（建议单独立项，不并入 M2）。

### 3.3 Session 与多进程的关系

现有冻结约定：**一个 Session 绑定一个目标进程**。
多进程抓包与此冲突：要么 Session 升格为"进程组"，要么引入 `session_id + pid`
的两级寻址。

**这是冻结项级别的改动，需要走基线变更流程**，不得在实现阶段擅自决定。

## 4. 落地顺序建议

1. （已完）模块改名 + 多包名
2. M2 真机闭环：让单个进程的 IPC 真的通（当前连 `--mock` 都还没摘）
3. 澄清 3.2 的 A/B 语义 —— **这一步是阻塞项**，决定后续工作量量级
4. 若选 A：PC 侧加 `session.attach` / `session.detach`，Session 内维护进程表
5. 多进程抓包与 Correlation 归集（依赖 4）

## 5. 硬约束（不得违反）

- **禁止 Fake Success**：抓不到就是抓不到，不许用"已启动"冒充"已抓到"。
- **禁止把「抓到 HTTPS」当「能改 HTTPS」**：`https_decrypt=false` 是硬事实。
- **大文件不进 MCP JSON**：PCAP/dump 走 Artifact Manager，只传 metadata + sha256。
- **文档先行**：实现前先更新本文件，再动代码。
