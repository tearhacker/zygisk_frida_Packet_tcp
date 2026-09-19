# 文档中心

项目全部项目级文档集中在这里，**按优先级分层**。工程内随代码走的文档仍在 `../ZygiskAIRuntime/docs/`。

> **一条规则**：文档冲突时，**低优先级服从高优先级**。代码与文档冲突时，**先报告冲突，不擅自选边**。

---

## 优先级链

| 级别 | 文档 | 定位 | 状态 |
|---|---|---|---|
| **P0** | [`00-权威基线/项目总基线_v1.1.md`](./00-权威基线/项目总基线_v1.1.md) | **唯一权威设计书**：产品定义 / 五核心四基础设施 / 协议 / 工具面 / 双层验收 / 工程目录 | 已冻结 |
| **P1** | [`00-权威基线/SOURCE_LOCK.md`](./00-权威基线/SOURCE_LOCK.md) | 源码供应链锁定表：13 个仓库的 ref / commit / 体积 / 落盘核验 / 目录映射 | 有效 |
| **P2** | [`00-权威基线/LICENSES.md`](./00-权威基线/LICENSES.md) | 逐仓许可核对结果与三条硬约束 | 已完成 |
| **P3** | [`00-权威基线/STRUCTURE.md`](./00-权威基线/STRUCTURE.md) | 工程结构与目录的**唯一标准清单**，含边界规则与待填目录 | 有效 |
| **P4** | [`10-施工指导/ZygiskAIRuntime_专业开发技术指导总文档_v1.0.md`](./10-施工指导/ZygiskAIRuntime_专业开发技术指导总文档_v1.0.md) | 施工顺序说明书：路线 / 实施顺序 / 技术研究顺序 / 交付纪律 | 有效 |
| **P5** | [`10-施工指导/ZygiskAIRuntime_AI施工手册_v2.0.md`](./10-施工指导/ZygiskAIRuntime_AI施工手册_v2.0.md) | 逐阶段 · 逐任务 · 逐文件 · 逐验收的施工总规约 | 有效 |
| **P6** | 当前任务 Prompt | 每次单独下达 | 临时 |
| **P7** | AI 自己的推测 | **不得覆盖上位冻结文档** | 禁止越权 |

> P4 与 P5 在文档内被称作 `DEVELOPMENT_GUIDE v1.0` 与 `AI施工手册 v2.0`，即上表两份文件。

---

## 分层目录

```text
docs/
├── README.md                    本文件 —— 唯一文档入口
│
├── 00-权威基线/                  P0–P3 · 冻结 · 唯一实施依据
│   ├── 项目总基线_v1.1.md
│   ├── SOURCE_LOCK.md
│   ├── LICENSES.md
│   └── STRUCTURE.md
│
├── 10-施工指导/                  P4–P5 · 执行规约
│   ├── ZygiskAIRuntime_专业开发技术指导总文档_v1.0.md
│   ├── ZygiskAIRuntime_AI施工手册_v2.0.md
│   └── ZygiskAIRuntime_模块WebUI设计_v1.0.md
│
├── 20-构建与审计/                P-1 阶段交付物（已完成 2026-09-19）
│   ├── README.md                 交付物清单与 P-1a/P-1b 拆分说明
│   ├── PROJECT_TREE_AUDIT.md     ✅ PASS
│   ├── SUPPLY_CHAIN_CHECK.md     ✅ PASS
│   ├── ENVIRONMENT.md            P-1a ✅ / P-1b ❌
│   ├── DEVICE_MATRIX.md          ❌ 无设备
│   └── BUILD_BLOCKERS.md         ⛔ PARTIAL（P-1a PASS · P-1b BLOCKED）
│
├── 30-研究/                      深入研究记录（施工手册 §29）
│   └── README.md                 记录格式约定
│
└── 90-历史归档/                  **不作实施依据**，仅供追溯
    ├── 产品功能说明书.txt.md
    ├── 项目架构.txt.md
    ├── 源码选择.txt.md
    ├── MCP通用开发技术文档.md
    ├── MCP通用技术经验开发文档2.md
    └── 真正的工作.txt.md
```

---

## 历史归档

**与权威文档冲突时一律以权威文档为准。**

| 文档 | 原定位 | 为何归档 |
|---|---|---|
| `产品功能说明书.txt.md` | v2.0 功能基准 | 功能范围已被总基线 §1 / §14 重新定义 |
| `项目架构.txt.md` | v1.0-Final 工程基线 | 架构已被总基线 §3 取代 |
| `源码选择.txt.md` | 供应链锁定 | 已被 `SOURCE_LOCK.md` 取代（含地址纠偏） |
| `MCP通用开发技术文档.md` | War3 项目经验 | 经验已提炼进总基线 §19 工程纪律 |
| `MCP通用技术经验开发文档2.md` | UE4 项目经验 | 同上 |
| `真正的工作.txt.md` | v1.0 源码供应链与工程目录 | **布局已被总基线 §17 吸收**；保留为目录结构的出处备查 |

---

## 工程内文档

随代码走，不并入本目录：

```text
../ZygiskAIRuntime/README.md     工程总览（构建状态、核心源码、外置清单）
../ZygiskAIRuntime/docs/         architecture · build · runtime · hook · memory · art · mcp · deployment
../ZygiskAIRuntime/ai_analyzer/README.md
../ZygiskAIRuntime/tools/README.md
../ZygiskAIRuntime/tests/README.md
../external/README.md            外置源码说明
```

---

## 引用约定

文档内部互相引用**一律相对文件自身所在目录**：

- `00-权威基线/` 里写 `SOURCE_LOCK.md`（同目录），写归档写 `../90-历史归档/真正的工作.txt.md`
- `ZygiskAIRuntime/` 里写 `../docs/00-权威基线/项目总基线_v1.1.md`
- `ZygiskAIRuntime/runtime/manager/` 里写 `../../../docs/00-权威基线/项目总基线_v1.1.md`

**移动或重命名任何文档，必须同步改引用**，改完用 grep 复查以下模式：

```bash
grep -rn "docs/build/\|docs/archive/\|docs/DEVELOPMENT_GUIDE\|\./STRUCTURE\.md" \
     --include="*.md" --include="*.h" --include="*.cpp" --include="*.env" --include="*.sh" .
```

---

## 已登记的不一致项（待裁决）

| # | 问题 | 现状 |
|---|---|---|
| 1 | **P-1 交付物清单两份文档不一致** | 施工手册列 `PROJECT_TREE_AUDIT`，专业指导列 `SUPPLY_CHAIN_CHECK`。已在 `20-构建与审计/README.md` 定义**并集 5 份**为权威清单 |
| 2 | **文件命名三套并存** | 中文（`项目总基线_v1.1.md`）· 英文（`SOURCE_LOCK.md`）· 中英混（`ZygiskAIRuntime_AI施工手册_v2.0.md`）。本次整理**未改名**以零风险；如需统一为单一 ASCII 约定，需单独一轮迁移 |
| 3 | **P-1 阻塞规则与本机环境冲突** | 施工手册 P-1.6 判定"无 NDK / CMake → P-1 不完成"，与"本机不装 NDK / CMake"的既定约定相撞。建议拆分为 **P-1a**（PC 侧可判定：目录 / 供应链 / License 审计，本机可完成）与 **P-1b**（Android 构建项，标记 BLOCKED 挂起） |
| 4 | **P4 与 P5 内容重叠约六成** | 两份新文档都定义了施工路线 / FAST-JOB / Write Guard / 双层验收。建议收敛为一份路线权威 + 一份增量规约 |
| 5 | **PC 侧包名 `mcp/` 与 MCP SDK 顶层包硬冲突** | ✅ **已修**：统一改为 `ai_analyzer/`（与 `libai_analyzer.so` 等产物名一致）。总基线 §17.0/§19.1 与 STRUCTURE.md 已同步 |
| 6 | **传输层需支持 TCP 回环** | ✅ **已解决（2026-09-19）**：已正式补进基线新增的 **§10.1.1 默认端点**，含 UDS / TCP 对照表与真机 `adb forward` 用法。UDS 仍为冻结方案，TCP 定为等价回退 |
| 7 | **IPC 端点默认值未裁定** | ⚠️ **原记录表述不准，已更正**：`constants.py` 里**早就有** `DEFAULT_SOCKET_PATH`（UDS）与 `DEFAULT_TCP_ENDPOINT`（原 `tcp:127.0.0.1:27901`），并非「搜不到端口或路径」；真正的问题是这些值**从未被裁定**，Android 侧不敢直接依赖。<br>**✅ 已裁定（2026-09-19，项目所有者）：TCP 端点 = `127.0.0.1:60500`**。已同步三处：Python 常量源（新增 `DEFAULT_TCP_HOST` / `DEFAULT_TCP_PORT`）、native 镜像 `ZAI_DEFAULT_TCP_*`、交叉校验表 `SCALAR_MAP`；原 27901 全工程替换，测试 202 项全绿。<br>绑定地址固定回环，**不提供 host 覆盖项**（Runtime 带 root，监听 `0.0.0.0` 等于把内存读写开放给同网段任何人）。<br>**仍未裁定**：UDS 路径是沿用现默认值 `/data/local/tmp/ai-analyzer/analyzer.sock`，还是按包名隔离（如 `/data/local/tmp/zai-runtime/<pkg>.sock`，需 root 侧创建）。 |
| 8 | **HELLO 用 `protocol`、其它消息用 `version`** | 同名字段两种写法（`protocol` vs `version`），语义相同。实现已按文档原样保留，并提供 `protocol_version_of()` 归一化读取。messages.py 顶部已记录。**是否统一需先改文档与黄金样例** |

---

## 作者与社区

**泪心独立研发 —— APP 逆向 / 封包 / 动态内存调试工具。**

```text
开发者    泪心
QQ        2254013571
Q群       435539500
Discord   https://discord.gg/yghYHcEdD
官网      http://teargamestorem.top/
```
