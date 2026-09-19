# 测试

| 目录 / 文件 | 内容 | 依赖 | 状态 |
|---|---|---|---|
| `protocol/` | 协议契约：帧边界、消息校验、schema + 黄金样例、常量两端一致性 | 纯 Python | ✅ 114 项 |
| `integration/` | Mock Runtime ↔ Bridge 端到端：握手、命令往返、事件、心跳、重连 | 纯 Python | ✅ 30 项 |
| `mcp/` | MCP 工具面：注册三件套、分面预算、能力门禁、schema 双向校验 | 纯 Python | ✅ 55 项 |
| `accept_mvp.py` | **端到端验收脚本**，10 节 28 项断言，产出可核对证据 | 纯 Python | ✅ 28/28 |
| `native/` | Backend 级单测（Gum / LSPlant 适配） | NDK + 真机 | 🟡 待建 |
| `runtime/` | Runtime Core 单测（Hook 状态机、Write Guard） | NDK + 真机 | 🟡 待建 |
| `semantic/` | 语义验收：read-back / 真实事件 / 证据链 | 真机 | 🟡 待建 |

验收是双层的：**流程验收（Test01–10）+ 语义验收**，两层都过才算完成
（见 `../../docs/00-权威基线/项目总基线_v1.1.md` §15）。
当前已覆盖的是**协议层与 Host 侧的语义验收**；真机语义验收仍需 NDK 环境。

## 怎么跑

```bash
cd ZygiskAIRuntime

python -m pytest tests              # 全量 199 项
python -m pytest tests/protocol     # 只跑协议契约
python -m pytest tests/integration  # 只跑端到端
python -m pytest tests/mcp          # 只跑工具面

python tests/accept_mvp.py          # 端到端验收（打印证据）
```

## 现在能覆盖什么

**已验证**（不依赖 NDK / 真机）：

```text
常量单一源：Python 与 Android 头文件逐项一致（解析头文件比对，不是人工核对）
帧编解码：0 字节 / 1 字节 / 正常 / 大帧 / 非法长度 / 截断 / 多余数据 / 畸形 JSON
消息契约：9 种消息构造与校验、严格模式、版本不匹配禁止进入 READY
黄金样例：双路径校验（JSON Schema + messages.validate）
握手链路：CONNECT → HELLO → HELLO_ACK → READY
命令往返：FAST 直接返回、JOB submit → status → result
事件通道：RUNTIME_READY 推送、Hook 三级事件、外部注入
心跳状态：CONNECTED → DEGRADED → DISCONNECTED
重连规则：旧 Session 失效、新 Session 建立、在途调用显式失败
内存校验：已映射可读、未映射 E_READ_FAILED + 可用区间
错误分层：协议层 → JSON-RPC error、执行层 → isError 结果
工具面：注册三件套一致、Core ≤25、能力门禁摘除、outputSchema 反向校验
```

**未覆盖**（环境阻塞，如实登记）：

```text
Zygisk 注入 / libai_analyzer.so 加载    ← 本机无 NDK / CMake
Frida-Gum / LSPlant 真实 Hook          ← 同上
真机 Memory Write read-back            ← 需要真机
真机 Network Capture / HTTPS 五级       ← 需要真机
```

## 纪律

```text
🔴 测试必须真跑绿，不允许「写了就算」
🔴 执行型断言不看 success=true，看语义证据（execution.verified / 真实事件）
🔴 能力降级、错误路径、超时、重连必须各有独立用例
🔴 黄金样例是冻结参考数据，代码必须满足它，而不是它迁就代码
```
