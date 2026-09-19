# ai_analyzer —— PC 侧 Host / MCP 层

Android 侧 Runtime **不需要知道** MCP / LLM / OpenAI 的任何概念。
它只处理 `Command / Request / Response / Event`；翻译成本项目的协议在这一层完成。

对应《docs/90-历史归档/真正的工作.txt.md》§七：MCP 在 PC 侧，Android Runtime 只认命令。

> ⚠️ **包名为什么叫 `ai_analyzer` 而不是 `mcp`**
> 本层原定目录名是 `mcp/`（见总基线 §17.0）。实际落地时发现
> **与 MCP Python SDK 的顶层包名 `mcp` 硬冲突**：本地 `mcp/` 会把
> `import mcp.server` / `import mcp.types` 全部劫持到自己身上，SDK 无法导入。
> 因此统一改为 `ai_analyzer`，与已冻结的产物名（`libai_analyzer.so` /
> `ai-analyzer-host` / `ai-analyzer-mcp`）保持一致。
> **这是命名修正，不是架构变更** —— 分层与职责与总基线 §19.1 完全一致。

---

## 分层（对应总基线 §19.1）

```text
L6 门面层   host/server.py          MCPServer 实例 + 装配，不写业务逻辑
L5 注册层   tools/                  工具规格（specs）+ 薄封装处理（handlers）
L4 能力层   host/runtime_bridge.py  带能力门禁的调用入口
L3 门禁层   host/error_mapping.py   错误分层映射
L2 集成层   bridge/                 IPC 连接、心跳、重连、传输抽象
L1 契约层   protocol/ · schemas/    两端共用的常量 / 帧 / 消息 / 黄金样例
            mock/                   无真机时的等价后端
```

## 目录

| 目录 | 职责 |
|---|---|
| `protocol/` | **两端共用的 IPC 契约**：常量单一源、错误体系、帧编解码、消息构造校验、命令分级 |
| `schemas/` | 9 份 JSON Schema + 黄金样例（`examples/`、`examples/errors/`），两端契约的单一源 |
| `bridge/` | 连接管理：`client.py`（HELLO / 心跳 / 重连 / Session）、`session.py`、`transport.py`（UDS + TCP） |
| `mock/` | Mock Runtime 后端（UDS/TCP 服务端），无真机时用于端到端验证 |
| `tools/` | `spec.py` 契约模型 · `specs.py` 全部工具规格 · `handlers.py` 全部处理实现 |
| `host/` | `server.py` 门面 · `runtime_bridge.py` 能力层 · `surfaces.py` 分面 · `registry.py` 装配 · `error_mapping.py` 错误映射 |

## 分面

```text
Core Surface   25 个，常驻（总基线 §11.2）
Expert Surface 10 个，按组动态挂载：Memory+ · Network+ · Packet+ · Artifact+ · Job
合计 35 个工具，硬上限 45
```

**能力不可用的工具会被主动摘除并给出原因**，不是等 AI 调了才报错。

## 跑起来

```bash
cd ZygiskAIRuntime

# 1. 全量测试
python -m pytest tests

# 2. 端到端验收（Mock 后端，产出可核对的证据）
python tests/accept_mvp.py

# 3. 装配自检：打印可见工具与 list_tools() 实际暴露集
python -m ai_analyzer.host --mock --mount "Memory+,Network+,Packet+,Artifact+,Job" --check

# 4. 真跑一个 MCP Server（stdio），后端用 Mock
python -m ai_analyzer.host --mock --mount "Memory+,Packet+,Artifact+,Job"

# 5. 连真机 Runtime（需先 adb forward）
python -m ai_analyzer.host --endpoint tcp:127.0.0.1:27901
```

## 传输层

总基线 §10.1 冻结的是 **Unix Domain Socket**。实际支持两种端点，**帧格式与握手完全一致**：

```text
unix:/data/local/tmp/ai-analyzer/analyzer.sock    设备侧 UDS（冻结方案）
tcp:127.0.0.1:27901                               TCP 回环
```

TCP 回退的两个真实理由：

1. Windows 上的 CPython 不一定编译进 `socket.AF_UNIX`（本机 3.13.14 即没有）。
2. 真机部署本来就要经 `adb forward tcp:<port>` 落到设备侧 UDS。

传输层不改变协议 —— 常量、帧、消息、握手、心跳、重连在两种传输上一致。

## 纪律

```text
🔴 AI 不允许直接碰 Frida / Gum / LSPlant / ADB / mitmproxy
🔴 大文件（PCAP / dump / trace）永远不进协议 JSON，只传 metadata + sha256
🔴 协议层错误 → JSON-RPC error；执行层失败 → isError 结果。两者不得混为一谈
🔴 执行型工具必须区分 accepted / executed / verified
🔴 写操作必须过 Write Guard，confirm 默认 false
🔴 重连不恢复旧 Session；旧 session_id 一律失效
🟠 新工具必须同时改注册三件套，并实际跑 list_tools() 验证
```

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
